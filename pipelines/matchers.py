"""Point-snap NDW sites onto the nearest OSM highway within a radius.

The road number is not used. A site with no way inside the radius is unmatched.
"""

from __future__ import annotations

import math
from collections import Counter

from geo import Hit, RoadIndex, clip_linestring, polyline_length_m


def _metric_fields(site: dict) -> dict:
    metrics = site.get("metrics") or {}
    speed = metrics.get("speed_kmh")
    flow = metrics.get("flow_vehh")
    travel = metrics.get("travel_time_s")
    if speed is not None:
        stamp = metrics.get("speed_time")
    elif travel is not None:
        stamp = metrics.get("travel_time")
    else:
        stamp = None
    length_m = polyline_length_m(site.get("segment"))
    implied = None
    if speed is None and travel and length_m >= 50:
        implied = length_m / travel * 3.6
    return {
        "metric_speed_kmh": _round(speed, 1),
        "metric_flow_vehh": _round(flow, 1),
        "metric_travel_time_s": _round(travel, 1),
        "metric_time": stamp,
        "metric_speed_implied_kmh": _round(implied, 1),
        "color_speed": _color_speed(speed if speed is not None else implied),
        "color_flow": _color_flow(flow),
        "color_travel": _color_travel(travel),
    }


def _round(value, digits: int):
    if value is None:
        return None
    return round(float(value), digits)


def _lerp(stops: list[tuple[float, tuple[int, int, int]]], value: float) -> str:
    if value <= stops[0][0]:
        return _hex(stops[0][1])
    if value >= stops[-1][0]:
        return _hex(stops[-1][1])
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if a <= value <= b:
            t = (value - a) / (b - a) if b != a else 0.0
            rgb = tuple(round(ca[i] + (cb[i] - ca[i]) * t) for i in range(3))
            return _hex(rgb)
    return _hex(stops[-1][1])


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _color_speed(value) -> str:
    if value is None:
        return "#6b7280"
    return _lerp(
        [(0, (215, 48, 39)), (40, (252, 141, 89)), (70, (254, 224, 139)), (100, (26, 152, 80))],
        float(value),
    )


def _color_flow(value) -> str:
    if value is None:
        return "#6b7280"
    return _lerp([(0, (224, 243, 248)), (800, (103, 169, 207)), (2500, (33, 102, 172))], float(value))


def _color_travel(value) -> str:
    if value is None:
        return "#6b7280"
    return _lerp([(0, (26, 152, 80)), (45, (254, 224, 139)), (120, (215, 48, 39))], float(value))


def _feature(site: dict, hit: Hit, confidence: float, notes: str, half_m: float) -> dict:
    snap_lon, snap_lat = _lonlat(hit)
    line = clip_linestring(hit, half_m)
    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [[round(lon, 6), round(lat, 6)] for lon, lat in line],
        },
        "properties": {
            "method": "point_snap",
            "site_id": site["site_id"],
            "name": site.get("name"),
            "osm_way_id": hit.way.osm_id,
            "highway": hit.way.highway,
            "road_ref": site.get("road_ref"),
            "confidence": round(confidence, 3),
            "match_distance_m": round(hit.distance_m, 1),
            "site_lon": round(site["lon"], 6),
            "site_lat": round(site["lat"], 6),
            "snap_lon": round(snap_lon, 6),
            "snap_lat": round(snap_lat, 6),
            "notes": notes,
            **_metric_fields(site),
        },
    }


def _lonlat(hit: Hit) -> tuple[float, float]:
    from geo import to_lonlat

    return to_lonlat(hit.snap_x, hit.snap_y)


def _unmatched(site: dict, reason: str) -> dict:
    return {
        "site_id": site["site_id"],
        "name": site.get("name"),
        "reason": reason,
        "lon": site.get("lon"),
        "lat": site.get("lat"),
        "road_ref": site.get("road_ref"),
        "notes": "",
    }


def _progress(done: int) -> None:
    if done and done % 20000 == 0:
        print(f"  point_snap {done}", flush=True)


def match_point_snap(sites: list[dict], index: RoadIndex, radius_m: float, half_m: float) -> tuple[list[dict], list[dict]]:
    matched, missed = [], []
    for site in sites:
        hits = index.nearby(site["lon"], site["lat"], radius_m)
        if not hits:
            missed.append(_unmatched(site, "no_way_within_radius"))
        else:
            hit = hits[0]
            confidence = max(0.0, 1.0 - hit.distance_m / radius_m)
            matched.append(_feature(site, hit, confidence, "nearest_way", half_m))
        _progress(len(matched) + len(missed))
    return matched, missed


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * p
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (hi - rank) + ordered[hi] * (rank - lo)


def summarize(sites: list[dict], matched: list[dict], missed: list[dict]) -> dict:
    distances = [float(feature["properties"]["match_distance_m"]) for feature in matched]
    highway = Counter(feature["properties"]["highway"] for feature in matched)
    claims: Counter = Counter(feature["properties"]["osm_way_id"] for feature in matched)
    collision_ways = sum(1 for count in claims.values() if count > 1)
    collision_extra = sum(count - 1 for count in claims.values() if count > 1)
    reasons = Counter(row["reason"] for row in missed)
    total = len(sites)
    matched_ids = {feature["properties"]["site_id"] for feature in matched}

    def subset(predicate) -> dict:
        attempted = [site for site in sites if predicate(site)]
        hit = sum(1 for site in attempted if site["site_id"] in matched_ids)
        return {"attempted": len(attempted), "matched": hit, "unmatched": len(attempted) - hit}

    share = {name: round(count / len(matched), 4) for name, count in highway.most_common()} if matched else {}
    return {
        "method": "point_snap",
        "sites_attempted": total,
        "matched": len(matched),
        "unmatched": len(missed),
        "match_rate": round(len(matched) / total, 4) if total else None,
        "median_distance_m": _round(_percentile(distances, 0.5), 1),
        "p90_distance_m": _round(_percentile(distances, 0.9), 1),
        "highway_share": share,
        "collision_ways": collision_ways,
        "collision_extra_sites": collision_extra,
        "unmatched_reasons": dict(reasons),
        "subsets": {
            "ref_named": subset(lambda site: bool(site.get("road_ref"))),
            "road_A15": subset(lambda site: site.get("road_ref") == "A15"),
            "road_A16": subset(lambda site: site.get("road_ref") == "A16"),
            "road_A20": subset(lambda site: site.get("road_ref") == "A20"),
        },
    }
