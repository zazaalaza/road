#!/usr/bin/env python3
"""Build one vector-tile set from the GeoJSON already on disk.

MapLibre retiled those GeoJSON files in the browser on every zoom, which is
why roads and dots vanished and painted back in. This writes data/tiles/ndw.mbtiles
once. The page then requests tiles that already exist.

    python3 pipelines/tiles.py

Requires the tippecanoe CLI (brew install tippecanoe).
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATCHES = ROOT / "data" / "matches"
PROCESSED = ROOT / "data" / "processed"
TILES = ROOT / "data" / "tiles"
MBTILES = TILES / "ndw.mbtiles"


def _points(features: list[dict], lon_key: str, lat_key: str, path: Path) -> int:
    count = 0
    with path.open("w") as handle:
        for feature in features:
            props = feature.get("properties") or feature
            lon = props.get(lon_key) if "properties" in feature else feature.get(lon_key)
            lat = props.get(lat_key) if "properties" in feature else feature.get(lat_key)
            if lon is None or lat is None:
                continue
            body = props if "properties" in feature else feature
            point = {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": body,
            }
            handle.write(json.dumps(point, separators=(",", ":")) + "\n")
            count += 1
    return count


def _matched_points(path: Path) -> int:
    data = json.loads((MATCHES / "method_point_snap.geojson").read_text())
    return _points(data["features"], "site_lon", "site_lat", path)


def _missed_points(path: Path) -> int:
    data = json.loads((MATCHES / "method_point_snap_unmatched.json").read_text())
    features = []
    for site in data["sites"]:
        features.append(
            {
                "site_id": site.get("site_id"),
                "name": site.get("name"),
                "reason": site.get("reason"),
                "road_ref": site.get("road_ref"),
                "notes": site.get("notes"),
                "method": data.get("method"),
                "lon": site["lon"],
                "lat": site["lat"],
            }
        )
    return _points(features, "lon", "lat", path)


def build_tiles() -> None:
    tippecanoe = shutil.which("tippecanoe")
    if tippecanoe is None:
        raise SystemExit("tippecanoe is not installed. brew install tippecanoe")
    for path in (
        PROCESSED / "osm_roads.geojson",
        PROCESSED / "ndw_segments.geojson",
        MATCHES / "method_point_snap.geojson",
        MATCHES / "method_point_snap_unmatched.json",
    ):
        if not path.exists():
            raise SystemExit(f"Missing {path}. Run python3 pipelines/phase1.py match first.")

    TILES.mkdir(parents=True, exist_ok=True)
    sites = TILES / "sites.geojsonl"
    missed = TILES / "missed.geojsonl"
    print("Writing site points…", flush=True)
    print(f"  sites { _matched_points(sites) }", flush=True)
    print(f"  missed { _missed_points(missed) }", flush=True)

    # drop-rate 1 keeps every feature at every zoom. Low zooms simplify lines
    # but do not throw roads away, so zooming out does not reveal a new subset.
    command = [
        tippecanoe,
        f"--output={MBTILES}",
        "--force",
        "--read-parallel",
        "--no-feature-limit",
        "--no-tile-size-limit",
        "--drop-rate=1",
        "--minimum-zoom=5",
        "--maximum-zoom=14",
        "--base-zoom=14",
        "--simplify-only-low-zooms",
        "--name=ndw-osm",
        "--description=NDW sites point-snapped to OSM roads",
        f"--named-layer=roads:{PROCESSED / 'osm_roads.geojson'}",
        f"--named-layer=matches:{MATCHES / 'method_point_snap.geojson'}",
        f"--named-layer=segments:{PROCESSED / 'ndw_segments.geojson'}",
        f"--named-layer=sites:{sites}",
        f"--named-layer=missed:{missed}",
    ]
    print("Building vector tiles…", flush=True)
    subprocess.run(command, check=True)
    _report()


def _report() -> None:
    connection = sqlite3.connect(MBTILES)
    rows = connection.execute(
        """
        SELECT zoom_level, COUNT(*), MAX(LENGTH(tile_data)), SUM(LENGTH(tile_data))
        FROM tiles
        GROUP BY zoom_level
        ORDER BY zoom_level
        """
    ).fetchall()
    connection.close()
    print(f"  wrote {MBTILES} ({MBTILES.stat().st_size} bytes)")
    for zoom, count, largest, total in rows:
        print(f"  z{zoom}: {count} tiles, largest {largest} bytes, total {total} bytes")


if __name__ == "__main__":
    try:
        build_tiles()
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
