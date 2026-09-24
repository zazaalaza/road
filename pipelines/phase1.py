#!/usr/bin/env python3
"""NDW × OSM phase 1: fetch, normalize, point-snap, write a manifest.

    python3 pipelines/phase1.py all         # fetch if missing, normalize, match
    python3 pipelines/phase1.py metrics     # refresh minute files only, rematch
    python3 pipelines/phase1.py match       # rematch from processed files
    python3 pipelines/phase1.py tiles       # vector tiles from the GeoJSON on disk
    python3 pipelines/phase1.py selftest    # tiny in-memory check, no downloads

Config (extent, point-snap radius): pipelines/matching_config.json
Outputs: data/processed/, data/matches/, and data/tiles/ndw.mbtiles.
Raw downloads stay in data/raw/. The test page reads the manifest through
/api/ndw-osm/ and the map through /ndw-tiles/{z}/{x}/{y}.pbf.

OSM comes from the Geofabrik Netherlands PBF, filtered with the osmium CLI
(brew install osmium-tool). Every NDW site in the national measurement file
is kept. There is no bbox clip.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPELINES = Path(__file__).resolve().parent
sys.path.insert(0, str(PIPELINES))

import matchers  # noqa: E402
import ndw  # noqa: E402
import osm  # noqa: E402
from tiles import build_tiles  # noqa: E402
from geo import RoadIndex, Way  # noqa: E402

RAW_NDW = ROOT / "data" / "raw" / "ndw"
RAW_OSM = ROOT / "data" / "raw" / "osm"
PROCESSED = ROOT / "data" / "processed"
MATCHES = ROOT / "data" / "matches"
USER_AGENT = "roads-ndw-osm-phase1/0.1 (local research)"


def load_config(path: Path) -> dict:
    return json.loads(path.read_text())


def extent_of(config: dict) -> dict:
    return config["extents"][config["extent_profile"]]


def _download(url: str, dest: Path, timeout: int = 180) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, tmp.open("wb") as handle:
            total = 0
            next_report = 50 * 1024 * 1024
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                handle.write(chunk)
                total += len(chunk)
                if total >= next_report:
                    print(f"  {total / (1024 * 1024):.0f} MB", flush=True)
                    next_report += 50 * 1024 * 1024
    except urllib.error.URLError as exc:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"download failed for {url}: {exc}") from exc
    tmp.replace(dest)


def _pbf_path(config: dict) -> Path:
    return RAW_OSM / config["osm"]["pbf_filename"]


def _extract_path(config: dict) -> Path:
    return RAW_OSM / config["osm"]["extract_filename"]


def fetch_osm(config: dict, refresh: bool) -> None:
    RAW_OSM.mkdir(parents=True, exist_ok=True)
    pbf = _pbf_path(config)
    # A partial or HTML error page is far smaller than the Netherlands PBF.
    if refresh or not pbf.exists() or pbf.stat().st_size < 50_000_000:
        print(f"Downloading {config['osm']['pbf_url']}")
        _download(config["osm"]["pbf_url"], pbf, timeout=600)
        print(f"  wrote {pbf} ({pbf.stat().st_size} bytes)")
    else:
        print(f"OSM PBF present ({pbf.name}, {pbf.stat().st_size} bytes)")
    osm.ensure_highway_extract(
        pbf,
        _extract_path(config),
        RAW_OSM / "nl_highways.meta.json",
        list(config["highways"]),
        refresh,
    )


def fetch_ndw(config: dict, refresh: bool, metrics_only: bool) -> None:
    RAW_NDW.mkdir(parents=True, exist_ok=True)
    files = {
        "measurement.xml.gz": config["ndw"]["measurement_url"],
        "trafficspeed.xml.gz": config["ndw"]["trafficspeed_url"],
        "traveltime.xml.gz": config["ndw"]["traveltime_url"],
    }
    for name, url in files.items():
        dest = RAW_NDW / name
        if metrics_only and name == "measurement.xml.gz":
            if not dest.exists():
                raise RuntimeError(f"Missing {dest}. Run a full fetch before metrics-only refresh.")
            continue
        if dest.exists() and not refresh and not (metrics_only and name != "measurement.xml.gz"):
            print(f"NDW present ({dest.name})")
            continue
        print(f"Downloading {url}")
        _download(url, dest)
        print(f"  wrote {dest} ({dest.stat().st_size} bytes)")


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"  {path.relative_to(ROOT)}  {path.stat().st_size} bytes")


def _sites_geojson(sites: list[dict]) -> dict:
    features = []
    for site in sites:
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(site["lon"], 6), round(site["lat"], 6)]},
                "properties": {
                    "site_id": site["site_id"],
                    "name": site.get("name"),
                    "road_ref": site.get("road_ref"),
                    "km_start": site.get("km_start"),
                    "km_end": site.get("km_end"),
                    "carriageway": site.get("carriageway"),
                    "value_kind": site.get("value_kind"),
                    "equipment": site.get("equipment"),
                    "location_type": site.get("location_type"),
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _segments_geojson(sites: list[dict]) -> dict:
    features = []
    for site in sites:
        segment = site.get("segment")
        if not segment or len(segment) < 2:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[round(lon, 6), round(lat, 6)] for lon, lat in segment],
                },
                "properties": {"site_id": site["site_id"], "name": site.get("name"), "road_ref": site.get("road_ref")},
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _metrics_blob(sites: list[dict]) -> dict:
    rows = {}
    for site in sites:
        metrics = site.get("metrics") or {}
        rows[site["site_id"]] = {
            "speed_kmh": metrics.get("speed_kmh"),
            "flow_vehh": metrics.get("flow_vehh"),
            "travel_time_s": metrics.get("travel_time_s"),
            "metric_time": metrics.get("speed_time") or metrics.get("travel_time"),
            "data_missing": metrics.get("speed_kmh") is None
            and metrics.get("flow_vehh") is None
            and metrics.get("travel_time_s") is None,
        }
    return {"sites": rows}


def _chainage_check(sites: list[dict]) -> dict:
    """Does parsed km increase toward the east on A15? Used as a sanity check, not as a locator."""
    rows = [
        (site["km_start"], site["lon"])
        for site in sites
        if site.get("road_ref") == "A15" and site.get("km_start") is not None
    ]
    if len(rows) < 4:
        return {"a15_sites_with_km": len(rows)}
    rows.sort()
    half = len(rows) // 2
    low = sum(lon for _km, lon in rows[:half]) / half
    high = sum(lon for _km, lon in rows[half:]) / (len(rows) - half)
    return {
        "a15_sites_with_km": len(rows),
        "mean_lon_lower_km": round(low, 4),
        "mean_lon_higher_km": round(high, 4),
        "higher_km_is_farther_east": high > low,
    }


def _point_bounds(points: list[tuple[float, float]]) -> dict:
    min_lon = min_lat = float("inf")
    max_lon = max_lat = float("-inf")
    for lon, lat in points:
        if lon < min_lon:
            min_lon = lon
        if lon > max_lon:
            max_lon = lon
        if lat < min_lat:
            min_lat = lat
        if lat > max_lat:
            max_lat = lat
    return {"min_lon": min_lon, "min_lat": min_lat, "max_lon": max_lon, "max_lat": max_lat}


def _way_bounds(ways: list) -> dict:
    min_lon = min_lat = float("inf")
    max_lon = max_lat = float("-inf")
    for way in ways:
        for lon, lat in way.coords:
            if lon < min_lon:
                min_lon = lon
            if lon > max_lon:
                max_lon = lon
            if lat < min_lat:
                min_lat = lat
            if lat > max_lat:
                max_lat = lat
    return {"min_lon": min_lon, "min_lat": min_lat, "max_lon": max_lon, "max_lat": max_lat}


def normalize(config: dict) -> tuple[list[dict], list]:
    measurement = RAW_NDW / "measurement.xml.gz"
    extract = _extract_path(config)
    if not measurement.exists() or not extract.exists():
        raise RuntimeError("Missing raw inputs. Run `python3 pipelines/phase1.py fetch` first.")
    print("Parsing measurement sites…")
    sites, stats = ndw.parse_sites(str(measurement))
    if not sites:
        raise RuntimeError("NDW measurement file contained no sites with coordinates.")
    site_bounds = _point_bounds([(site["lon"], site["lat"]) for site in sites])
    print(f"  kept {len(sites)} sites ({stats})")
    print(f"  site bounds {site_bounds}")
    configured = extent_of(config)
    outside = [
        site
        for site in sites
        if not (
            configured["min_lon"] - 1e-6 <= site["lon"] <= configured["max_lon"] + 1e-6
            and configured["min_lat"] - 1e-6 <= site["lat"] <= configured["max_lat"] + 1e-6
        )
    ]
    if outside:
        print(f"  warning: {len(outside)} sites are outside the configured extent; they are still kept")
    wanted = {site["site_id"]: site for site in sites}
    print("Parsing trafficspeed…")
    speed = ndw.parse_measurements(str(RAW_NDW / "trafficspeed.xml.gz"), wanted, "speed")
    print("Parsing traveltime…")
    travel = ndw.parse_measurements(str(RAW_NDW / "traveltime.xml.gz"), wanted, "travel")
    metric_stats = ndw.attach_metrics(sites, speed, travel)
    print(f"  metrics {metric_stats}")
    chainage = _chainage_check(sites)
    print(f"  chainage {chainage}")
    highways = set(config["highways"])
    print("Reading OSM extract…")
    ways = osm.ways_from_geojsonl(extract, highways)
    if not ways:
        raise RuntimeError("OSM extract contained no highway ways.")
    osm_bounds = _way_bounds(ways)
    highway_counts = dict(Counter(way.highway for way in ways))
    print(f"  {len(ways)} ways")
    print(f"  way bounds {osm_bounds}")
    print(f"  classes {highway_counts}")
    _write(
        PROCESSED / "sites_index.json",
        {
            "sites": sites,
            "parse_stats": stats,
            "metric_stats": metric_stats,
            "chainage": chainage,
            "site_bounds": site_bounds,
            "osm_bounds": osm_bounds,
            "osm_highway_counts": highway_counts,
            "osm_source": config["osm"]["pbf_url"],
        },
    )
    _write(PROCESSED / "ndw_sites.geojson", _sites_geojson(sites))
    _write(PROCESSED / "ndw_segments.geojson", _segments_geojson(sites))
    _write(PROCESSED / "osm_roads.geojson", osm.ways_to_geojson(ways))
    _write(PROCESSED / "ndw_latest_metrics.json", _metrics_blob(sites))
    return sites, ways


def _load_sites() -> tuple[list[dict], dict]:
    path = PROCESSED / "sites_index.json"
    if not path.exists():
        raise RuntimeError("Missing data/processed/sites_index.json. Run normalize first.")
    payload = json.loads(path.read_text())
    return payload["sites"], payload


def refresh_metrics(config: dict) -> None:
    fetch_ndw(config, refresh=True, metrics_only=True)
    sites, payload = _load_sites()
    wanted = {site["site_id"]: site for site in sites}
    speed = ndw.parse_measurements(str(RAW_NDW / "trafficspeed.xml.gz"), wanted, "speed")
    travel = ndw.parse_measurements(str(RAW_NDW / "traveltime.xml.gz"), wanted, "travel")
    metric_stats = ndw.attach_metrics(sites, speed, travel)
    print(f"  metrics {metric_stats}")
    payload["sites"] = sites
    payload["metric_stats"] = metric_stats
    _write(PROCESSED / "sites_index.json", payload)
    _write(PROCESSED / "ndw_latest_metrics.json", _metrics_blob(sites))


def run_match(config: dict, sites: list[dict] | None = None, ways: list | None = None) -> dict:
    if sites is None:
        sites, payload = _load_sites()
    else:
        payload = json.loads((PROCESSED / "sites_index.json").read_text())
    if ways is None:
        ways = osm.ways_from_geojson(PROCESSED / "osm_roads.geojson")
    print(f"Indexing {len(ways)} OSM ways…")
    index = RoadIndex(ways)
    half = float(config["highlight_half_length_m"])
    print("Matching point_snap…")
    matched, missed = matchers.match_point_snap(sites, index, float(config["point_snap_radius_m"]), half)
    _write(MATCHES / "method_point_snap.geojson", {"type": "FeatureCollection", "features": matched})
    _write(MATCHES / "method_point_snap_unmatched.json", {"method": "point_snap", "sites": missed})
    summary = matchers.summarize(sites, matched, missed)
    print(
        f"  point_snap: matched {summary['matched']}/{summary['sites_attempted']} "
        f"({summary['match_rate']}), median {summary['median_distance_m']} m, "
        f"collisions {summary['collision_ways']}"
    )
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "extent_profile": config["extent_profile"],
        "extent": extent_of(config),
        "bbox_profile": config["extent_profile"],
        "bbox": extent_of(config),
        "point_snap_radius_m": config["point_snap_radius_m"],
        "inputs": {
            "osm_ways": len(ways),
            "osm_source": payload.get("osm_source"),
            "osm_bounds": payload.get("osm_bounds"),
            "osm_highway_counts": payload.get("osm_highway_counts"),
            "ndw_sites": len(sites),
            "site_bounds": payload.get("site_bounds"),
            "parse_stats": payload.get("parse_stats"),
            "metric_stats": payload.get("metric_stats"),
            "chainage": payload.get("chainage"),
        },
        "point_snap": summary,
    }
    _write(MATCHES / "comparison_manifest.json", manifest)
    return manifest


def selftest() -> None:
    from ndw import parse_site_name

    cases = {
        "A15 R_van_30000_tot_30500": ("A15", 30.0, 30.5, "R", "increasing"),
        "A15 L_van_32500_tot_32000": ("A15", 32.5, 32.0, "L", "decreasing"),
        "N470 km 15.391 Re": ("N470", 15.391, 15.391, "R", None),
        "N457 hmp 4.75 Li": ("N457", 4.75, 4.75, "L", None),
        "N57 A15 - N218": ("N57", None, None, None, None),
        "Droespolderweg kr A15 toerit 13 - Droespolderweg kr Merseyweg": (None, None, None, None, None),
        "A16 Van Brieneroordbrug (A20 Terbregseplein-A15 Ridderkerk) HRB": ("A16", None, None, None, None),
    }
    for name, expected in cases.items():
        parsed = parse_site_name(name)
        got = (
            parsed["road_ref"],
            parsed["km_start"],
            parsed["km_end"],
            parsed["carriageway"],
            parsed["chainage_direction"],
        )
        if got != expected:
            raise SystemExit(f"name parse failed for {name!r}: {got} != {expected}")

    def way(osm_id: str, highway: str, ref: str, lat: float, oneway: str) -> Way:
        return Way(
            osm_id=osm_id,
            highway=highway,
            name=None,
            ref=ref or None,
            oneway=oneway,
            coords=[(4.200, lat), (4.210, lat)],
        )

    # The site sits on the residential way. Two motorways are farther away, so
    # point snap must pick the way under the point.
    site_lat = 51.90 + (8 / 111_320)
    ways = [
        way("north", "motorway", "A15", 51.90 + (20 / 111_320), "reverse"),
        way("south", "motorway", "A15", 51.90 - (20 / 111_320), "yes"),
        way("local", "residential", "", site_lat, "none"),
    ]
    index = RoadIndex(ways)
    site = {
        "site_id": "S1",
        "name": "A15 R_van_10000_tot_10500",
        "lon": 4.205,
        "lat": site_lat,
        "road_ref": "A15",
        "km_start": 10.0,
        "segment": [[4.204, site_lat], [4.206, site_lat]],
        "segment_bearing": 90.0,
        "side_bearing": None,
        "metrics": {"speed_kmh": 80, "flow_vehh": 1000, "travel_time_s": None, "speed_time": "t"},
    }
    snap_ok, snap_miss = matchers.match_point_snap([site], index, 25, 180)
    if len(snap_ok) != 1 or snap_ok[0]["properties"]["osm_way_id"] != "local":
        raise SystemExit(f"point_snap should pick the residential way under the point, got {snap_ok} {snap_miss}")
    if snap_ok[0]["properties"]["metric_speed_kmh"] != 80:
        raise SystemExit("metrics were not copied onto the match")
    if "color_confidence" in snap_ok[0]["properties"]:
        raise SystemExit("point snap must not write a confidence colour")
    summary = matchers.summarize([site], snap_ok, snap_miss)
    if summary["matched"] != 1 or summary["sites_attempted"] != 1:
        raise SystemExit(f"point snap summary should count the one site, got {summary}")
    far = dict(site, site_id="S2", lat=site_lat + 1)
    _ok, miss = matchers.match_point_snap([far], index, 25, 180)
    if _ok or not miss or miss[0]["reason"] != "no_way_within_radius":
        raise SystemExit(f"a site outside the radius must be unmatched, got {_ok} {miss}")
    print("selftest ok")


def main() -> None:
    parser = argparse.ArgumentParser(description="NDW–OSM matching phase 1")
    parser.add_argument("command", choices=("fetch", "normalize", "match", "all", "metrics", "tiles", "selftest"))
    parser.add_argument("--refresh", action="store_true", help="Re-download files even if they exist")
    parser.add_argument("--config", type=Path, default=PIPELINES / "matching_config.json")
    args = parser.parse_args()
    if args.command == "selftest":
        selftest()
        return
    if args.command == "tiles":
        build_tiles()
        return
    config = load_config(args.config)
    started = time.time()
    if args.command in ("fetch", "all"):
        fetch_ndw(config, refresh=args.refresh, metrics_only=False)
        fetch_osm(config, refresh=args.refresh)
    if args.command == "metrics":
        refresh_metrics(config)
        run_match(config)
    elif args.command == "normalize":
        normalize(config)
    elif args.command == "match":
        run_match(config)
        build_tiles()
    elif args.command == "all":
        sites, ways = normalize(config)
        run_match(config, sites, ways)
        build_tiles()
    if args.command == "metrics":
        build_tiles()
    print(f"done in {time.time() - started:.1f}s")


if __name__ == "__main__":
    main()
