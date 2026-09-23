"""Read a Geofabrik PBF highway extract into Way objects and GeoJSON.

The raw download is a Netherlands PBF. osmium tags-filter keeps the configured
highway classes (ways, not a bbox clip) and osmium export writes GeoJSONSeq.
Python stays on the standard library and shells out to the osmium binary.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from geo import Way


def oneway_of(tags: dict) -> str:
    value = str(tags.get("oneway", "")).lower()
    if value in ("yes", "true", "1"):
        return "yes"
    if value in ("-1", "reverse"):
        return "reverse"
    if value in ("no", "false", "0"):
        return "no"
    return "none"


def _osmium() -> str:
    binary = shutil.which("osmium")
    if binary is None:
        raise RuntimeError("osmium is not on PATH. Install it with: brew install osmium-tool")
    return binary


def _export_config(path: Path) -> None:
    """Linestrings only, and only the tags kept on each road.

    osmium export reads its input twice, so this is a file on disk, not a pipe.
    area_tags false keeps closed roads (roundabouts) as linestrings.
    """
    path.write_text(
        json.dumps(
            {
                "attributes": {"type": True, "id": True},
                "linear_tags": True,
                "area_tags": False,
                "include_tags": ["highway", "name", "ref", "oneway"],
            },
            indent=2,
        )
    )


def ensure_highway_extract(pbf: Path, dest: Path, meta_path: Path, highways: list[str], refresh: bool) -> None:
    """Filter the PBF to the configured highway classes and cache GeoJSONSeq."""
    if not pbf.exists():
        raise RuntimeError(f"Missing {pbf}. Download the Geofabrik PBF first.")
    stamp = {
        "extract_version": 1,
        "source_pbf": pbf.name,
        "source_bytes": pbf.stat().st_size,
        "source_mtime_ns": pbf.stat().st_mtime_ns,
        "highways": sorted(highways),
    }
    if dest.exists() and meta_path.exists() and not refresh:
        try:
            previous = json.loads(meta_path.read_text())
        except json.JSONDecodeError:
            previous = None
        if previous == stamp:
            print(f"OSM highway extract present ({dest})")
            return
    binary = _osmium()
    dest.parent.mkdir(parents=True, exist_ok=True)
    filtered = dest.with_name(dest.stem + ".filtered.osm.pbf")
    config_path = dest.with_name(dest.stem + ".export.json")
    tmp = dest.with_suffix(dest.suffix + ".part")
    _export_config(config_path)
    highway_filter = "w/highway=" + ",".join(highways)
    print(f"Filtering {pbf.name} to {len(highways)} highway classes", flush=True)
    filt = subprocess.run(
        [binary, "tags-filter", "--overwrite", "--progress", "-o", str(filtered), str(pbf), highway_filter],
        check=False,
    )
    if filt.returncode != 0:
        filtered.unlink(missing_ok=True)
        raise RuntimeError(f"osmium tags-filter failed ({filt.returncode})")
    print(f"Exporting linestrings to {dest.name}", flush=True)
    tmp.unlink(missing_ok=True)
    exp = subprocess.run(
        [
            binary,
            "export",
            "--overwrite",
            "--progress",
            "-f",
            "geojsonseq",
            "-c",
            str(config_path),
            "--geometry-types=linestring",
            "-o",
            str(tmp),
            str(filtered),
        ],
        check=False,
    )
    filtered.unlink(missing_ok=True)
    if exp.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"osmium export failed ({exp.returncode})")
    tmp.replace(dest)
    meta_path.write_text(json.dumps(stamp, indent=2))
    print(f"  wrote {dest} ({dest.stat().st_size} bytes)")


def _loads_feature(line: str) -> dict:
    text = line.strip()
    if text.startswith("\x1e"):
        text = text[1:].strip()
    return json.loads(text)


def _way_id(props: dict) -> str | None:
    raw = props.get("@id", props.get("id"))
    if raw is None:
        return None
    text = str(raw)
    if text.startswith("w") and text[1:].isdigit():
        return text[1:]
    return text


def ways_from_geojsonl(path: Path, highways: set[str]) -> list[Way]:
    ways: list[Way] = []
    skipped = 0
    with path.open() as handle:
        for line in handle:
            if not line.strip():
                continue
            feature = _loads_feature(line)
            props = feature.get("properties") or {}
            highway = props.get("highway")
            if highway not in highways:
                skipped += 1
                continue
            geom = feature.get("geometry") or {}
            if geom.get("type") != "LineString":
                skipped += 1
                continue
            coords = [(float(x), float(y)) for x, y in geom.get("coordinates") or []]
            if len(coords) < 2:
                skipped += 1
                continue
            osm_id = _way_id(props)
            if osm_id is None:
                skipped += 1
                continue
            ref = props.get("ref")
            if not isinstance(ref, str):
                ref = None
            name = props.get("name")
            if not isinstance(name, str):
                name = None
            ways.append(
                Way(
                    osm_id=osm_id,
                    highway=str(highway),
                    name=name,
                    ref=ref,
                    oneway=oneway_of(props),
                    coords=coords,
                )
            )
            if len(ways) % 100000 == 0:
                print(f"  OSM ways read: {len(ways)}", flush=True)
    if skipped:
        print(f"  skipped {skipped} features that were not a configured highway linestring")
    return ways


def ways_to_geojson(ways: list[Way]) -> dict:
    features = []
    for way in ways:
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[round(lon, 6), round(lat, 6)] for lon, lat in way.coords],
                },
                "properties": {
                    "osm_id": way.osm_id,
                    "highway": way.highway,
                    "name": way.name,
                    "ref": way.ref,
                    "oneway": way.oneway,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def ways_from_geojson(path: Path) -> list[Way]:
    data = json.loads(path.read_text())
    ways: list[Way] = []
    for feature in data.get("features", []):
        geom = feature.get("geometry") or {}
        if geom.get("type") != "LineString":
            continue
        coords = [(float(x), float(y)) for x, y in geom.get("coordinates") or []]
        if len(coords) < 2:
            continue
        props = feature.get("properties") or {}
        ref = props.get("ref")
        ways.append(
            Way(
                osm_id=str(props.get("osm_id")),
                highway=props.get("highway") or "",
                name=props.get("name"),
                ref=ref,
                oneway=props.get("oneway") or "none",
                coords=coords,
            )
        )
    return ways
