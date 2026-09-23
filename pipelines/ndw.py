"""Parse NDW DATEX II measurement configuration and the minute publications."""

from __future__ import annotations

import gzip
import re
from collections import Counter
from xml.etree import ElementTree as ET

REF_AT_START = re.compile(r"^\s*([AN]\d{1,3})\b")
METER_RANGE = re.compile(r"van_(\d+)_tot_(\d+)", re.I)
KM_RANGE = re.compile(r"van\s+(\d+(?:[.,]\d+)?)\s+naar\s+(\d+(?:[.,]\d+)?)", re.I)
KM_POINT = re.compile(r"(?:km|hmp)\s*(\d+(?:[.,]\d+)?)", re.I)

SIDE_BEARING = {
    "northBound": 0.0,
    "northEastBound": 45.0,
    "eastBound": 90.0,
    "southEastBound": 135.0,
    "southBound": 180.0,
    "southWestBound": 225.0,
    "westBound": 270.0,
    "northWestBound": 315.0,
}


def local(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _text(elem: ET.Element, name: str) -> str | None:
    for child in elem.iter():
        if local(child.tag) == name and child.text and child.text.strip():
            return child.text.strip()
    return None


def _direct_text(elem: ET.Element, name: str) -> str | None:
    for child in elem:
        if local(child.tag) == name and child.text and child.text.strip():
            return child.text.strip()
    return None


def _xsi_type(elem: ET.Element) -> str | None:
    for key, value in elem.attrib.items():
        if key == "type" or key.endswith("}type"):
            return value
    return None


def _coord(elem: ET.Element) -> tuple[float, float] | None:
    lat = lon = None
    for child in elem.iter():
        name = local(child.tag)
        if name == "latitude" and child.text:
            lat = float(child.text)
        elif name == "longitude" and child.text:
            lon = float(child.text)
        if lat is not None and lon is not None:
            return lon, lat
    return None


def _num(text: str | None) -> float | None:
    if text is None:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def parse_site_name(name: str | None) -> dict:
    """Road number only when the name starts with it.

    Names like 'Droespolderweg kr A15 toerit' mention A15 but the site is not on it.
    'N57 A15 - N218' is a route on N57. Chainage is read from the RWS metre form
    (`R_van_30000_tot_30500`), `van 102 naar 102.5`, or `km` / `hmp`.
    """
    raw = name or ""
    ref_match = REF_AT_START.match(raw)
    ref = ref_match.group(1) if ref_match else None
    km_start = km_end = None
    carriageway = None
    chainage_direction = None

    meter = METER_RANGE.search(raw)
    km_range = KM_RANGE.search(raw)
    km_point = KM_POINT.search(raw)
    if meter:
        a, b = int(meter.group(1)), int(meter.group(2))
        km_start = a / 1000.0 if a >= 1000 else float(a)
        km_end = b / 1000.0 if b >= 1000 else float(b)
    elif km_range:
        km_start = _num(km_range.group(1))
        km_end = _num(km_range.group(2))
    elif km_point:
        km_start = km_end = _num(km_point.group(1))

    if km_start is not None and km_end is not None and km_end != km_start:
        chainage_direction = "increasing" if km_end > km_start else "decreasing"

    if re.search(r"\bHRL\b", raw) or re.search(r"(?:^|[\s_])L_van_", raw) or raw.rstrip().endswith(" Li"):
        carriageway = "L"
    elif re.search(r"\bHRR\b", raw) or re.search(r"(?:^|[\s_])R_van_", raw) or raw.rstrip().endswith(" Re"):
        carriageway = "R"

    return {
        "road_ref": ref,
        "km_start": km_start,
        "km_end": km_end,
        "carriageway": carriageway,
        "chainage_direction": chainage_direction,
    }


def _first_display(elem: ET.Element) -> tuple[float, float] | None:
    for child in elem.iter():
        if local(child.tag) == "locationForDisplay":
            coord = _coord(child)
            if coord:
                return coord
    return None


def _segment(elem: ET.Element) -> tuple[list[list[float]] | None, float | None, str | None]:
    """Chain itinerary start/end points. Bearing comes from the longest part."""
    parts: list[tuple[list[list[float]], str | None]] = []
    for block in elem.iter():
        if local(block.tag) != "locationContainedInItinerary":
            continue
        start = end = None
        carriageway = None
        for child in block.iter():
            name = local(child.tag)
            if name == "linearCoordinatesStartPoint" and start is None:
                start = _coord(child)
            elif name == "linearCoordinatesEndPoint" and end is None:
                end = _coord(child)
            elif name == "carriageway" and child.text and carriageway is None:
                carriageway = child.text.strip()
        if start and end:
            parts.append(([[start[0], start[1]], [end[0], end[1]]], carriageway))
    if not parts:
        return None, None, None
    from geo import polyline_length_m, bearing_deg, to_xy

    longest = max(parts, key=lambda part: polyline_length_m(part[0]))
    (lon1, lat1), (lon2, lat2) = longest[0]
    x1, y1 = to_xy(lon1, lat1)
    x2, y2 = to_xy(lon2, lat2)
    line: list[list[float]] = []
    for coords, _carriageway in parts:
        for point in coords:
            if not line or abs(line[-1][0] - point[0]) > 1e-7 or abs(line[-1][1] - point[1]) > 1e-7:
                line.append(point)
    return line, bearing_deg(x1, y1, x2, y2), longest[1]


def _indexes(elem: ET.Element) -> dict[str, list[int]]:
    speed: list[int] = []
    flow: list[int] = []
    travel: list[int] = []
    for child in elem.iter():
        if local(child.tag) != "measurementSpecificCharacteristics" or "index" not in child.attrib:
            continue
        try:
            index = int(child.attrib["index"])
        except ValueError:
            continue
        value_type = vehicle = None
        for node in child.iter():
            name = local(node.tag)
            if name == "specificMeasurementValueType" and node.text:
                value_type = node.text.strip()
            elif name == "vehicleType" and node.text:
                vehicle = node.text.strip()
        if value_type == "trafficSpeed" and vehicle == "anyVehicle":
            speed.append(index)
        elif value_type == "trafficFlow" and vehicle == "anyVehicle":
            flow.append(index)
        elif value_type == "travelTimeInformation":
            travel.append(index)
    return {"speed": speed, "flow": flow, "travel": travel}


def _site_name(elem: ET.Element) -> str | None:
    for child in elem:
        if local(child.tag) == "measurementSiteName":
            return _text(child, "value")
    return None


def _equipment(elem: ET.Element) -> str | None:
    for child in elem:
        if local(child.tag) == "measurementEquipmentTypeUsed":
            return _text(child, "value")
    return None


def parse_sites(path: str) -> tuple[list[dict], dict]:
    """Every measurement site that has a display coordinate. No geographic clip."""
    sites: list[dict] = []
    stats: Counter = Counter()
    with gzip.open(path, "rb") as handle:
        for _event, elem in ET.iterparse(handle, events=("end",)):
            if local(elem.tag) != "measurementSiteRecord":
                continue
            stats["records"] += 1
            display = _first_display(elem)
            if display is None:
                stats["no_display"] += 1
                elem.clear()
                continue
            location_type = None
            for child in elem:
                if local(child.tag) == "measurementSiteLocation":
                    location_type = _xsi_type(child)
            name = _site_name(elem)
            parsed = parse_site_name(name)
            segment, segment_bearing, carriageway_type = _segment(elem)
            side = _direct_text(elem, "measurementSide")
            indexes = _indexes(elem)
            kind = "travel_time" if indexes["travel"] and not indexes["speed"] else "speed_flow"
            if indexes["travel"] and indexes["speed"]:
                kind = "both"
            sites.append(
                {
                    "site_id": elem.attrib.get("id"),
                    "name": name,
                    "location_type": location_type,
                    "lon": display[0],
                    "lat": display[1],
                    "measurement_side": side,
                    "side_bearing": SIDE_BEARING.get(side or ""),
                    "lanes": _num(_direct_text(elem, "measurementSiteNumberOfLanes")),
                    "equipment": _equipment(elem),
                    "value_kind": kind,
                    "segment": segment,
                    "segment_bearing": segment_bearing,
                    "carriageway_type": carriageway_type,
                    "indexes": indexes,
                    **parsed,
                }
            )
            stats["kept"] += 1
            if parsed["road_ref"]:
                stats["with_ref"] += 1
            stats[f"kind:{kind}"] += 1
            elem.clear()
            if stats["records"] % 20000 == 0:
                print(f"  measurement records scanned: {stats['records']}", flush=True)
    return sites, dict(stats)


def _measured_number(block: ET.Element) -> tuple[str | None, float | None, bool]:
    errored = False
    kind = None
    value = None
    for node in block.iter():
        name = local(node.tag)
        if name == "dataError" and (node.text or "").strip().lower() == "true":
            errored = True
        elif name == "basicData":
            kind = _xsi_type(node)
        elif name == "speed" and node.text and value is None:
            value = _num(node.text)
        elif name == "vehicleFlowRate" and node.text and value is None:
            value = _num(node.text)
        elif name == "travelTime" and value is None:
            for child in node.iter():
                if local(child.tag) == "duration" and child.text:
                    value = _num(child.text)
                    kind = kind or "TravelTimeData"
                    break
    if errored or value is None or value < 0:
        return kind, None, errored
    return kind, value, False


def parse_measurements(path: str, wanted: dict[str, dict], publication: str) -> dict[str, dict]:
    """Keep minute values for the given sites. Speed/flow indexes are the anyVehicle ones."""
    found: dict[str, dict] = {}
    publication_time = None
    with gzip.open(path, "rb") as handle:
        for _event, elem in ET.iterparse(handle, events=("end",)):
            name = local(elem.tag)
            if name == "publicationTime" and publication_time is None and elem.text:
                publication_time = elem.text.strip()
                elem.clear()
                continue
            if name != "siteMeasurements":
                continue
            site_id = None
            for child in elem:
                if local(child.tag) == "measurementSiteReference":
                    site_id = child.attrib.get("id")
                    break
            site = wanted.get(site_id or "")
            if site is None:
                elem.clear()
                continue
            stamp = _direct_text(elem, "measurementTimeDefault")
            by_index: dict[int, float] = {}
            for child in elem:
                if local(child.tag) != "measuredValue" or "index" not in child.attrib:
                    continue
                try:
                    index = int(child.attrib["index"])
                except ValueError:
                    continue
                _kind, value, _err = _measured_number(child)
                if value is not None:
                    by_index[index] = value
            bucket = found.setdefault(site_id, {})
            indexes = site["indexes"]
            if publication == "speed":
                speeds = [by_index[i] for i in indexes["speed"] if i in by_index]
                flows = [by_index[i] for i in indexes["flow"] if i in by_index]
                bucket["speed_kmh"] = sum(speeds) / len(speeds) if speeds else None
                bucket["flow_vehh"] = sum(flows) if flows else None
                bucket["speed_time"] = stamp
                bucket["speed_seen"] = True
            else:
                durations = [by_index[i] for i in indexes["travel"] if i in by_index]
                if not durations and by_index and indexes["travel"]:
                    durations = []
                if not indexes["travel"] and by_index:
                    # Travel-time publications usually have a single index.
                    first = min(by_index)
                    durations = [by_index[first]]
                bucket["travel_time_s"] = durations[0] if durations else None
                bucket["travel_time"] = stamp
                bucket["travel_seen"] = True
            elem.clear()
    for bucket in found.values():
        bucket["publication_time"] = publication_time
    return found


def attach_metrics(sites: list[dict], speed: dict[str, dict], travel: dict[str, dict]) -> dict:
    joined_speed = usable_speed = usable_flow = 0
    joined_travel = usable_travel = 0
    speed_sites = travel_sites = 0
    for site in sites:
        metrics = {}
        metrics.update(speed.get(site["site_id"], {}))
        travel_row = travel.get(site["site_id"], {})
        for key, value in travel_row.items():
            if key not in metrics or metrics.get(key) is None:
                metrics[key] = value
        site["metrics"] = {
            "speed_kmh": metrics.get("speed_kmh"),
            "flow_vehh": metrics.get("flow_vehh"),
            "travel_time_s": metrics.get("travel_time_s"),
            "speed_time": metrics.get("speed_time"),
            "travel_time": metrics.get("travel_time"),
            "publication_time": metrics.get("publication_time"),
        }
        if site["value_kind"] in ("speed_flow", "both"):
            speed_sites += 1
            if metrics.get("speed_seen"):
                joined_speed += 1
            if site["metrics"]["speed_kmh"] is not None:
                usable_speed += 1
            if site["metrics"]["flow_vehh"] is not None:
                usable_flow += 1
        if site["value_kind"] in ("travel_time", "both"):
            travel_sites += 1
            if metrics.get("travel_seen"):
                joined_travel += 1
            if site["metrics"]["travel_time_s"] is not None:
                usable_travel += 1
    return {
        "speed_flow_sites": speed_sites,
        "speed_rows_joined": joined_speed,
        "speed_usable": usable_speed,
        "flow_usable": usable_flow,
        "travel_sites": travel_sites,
        "travel_rows_joined": joined_travel,
        "travel_usable": usable_travel,
    }
