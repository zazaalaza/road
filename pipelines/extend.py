"""Extend point-snap highlight lines until neighbouring sites meet.

Distance is metres along an undirected road graph. A point is coloured only
when it lies on a path between two measurement sites: multi-source Dijkstra
builds the network Voronoi diagram, and only the paths from each boundary
back to its sites are kept. Outer tails stay gray except the existing
highlight clip (about half_m each side of a site).

Ways are bridged only when they share an endpoint, their OSM ref tags are
exactly equal and non-empty, neither is a *_link, and the bearings leaving
the shared node differ by at least 45 degrees (a continuation, corner, or
fork — not a reversal onto the opposing carriageway).
"""

from __future__ import annotations

import heapq
from collections import defaultdict

from geo import Way, bearing_deg, hypot, point_segment_distance, to_lonlat, to_xy

# OSM roads are stored at 6 decimal degrees (~0.1 m). Shared endpoints match
# at that precision; anything coarser would glue distinct junctions.
_NODE_DECIMALS = 6
_SAME_VERTEX_M = 0.05
_MIN_SPAN_M = 0.05
_BEARING_MIN_M = 1.0
_BRIDGE_MIN_DEG = 45.0
_INF = 1e18


class _Edge:
    __slots__ = ("lo", "hi", "length", "way_index", "c0", "c1")

    def __init__(self, lo: int, hi: int, length: float, way_index: int, c0: float, c1: float):
        self.lo = lo
        self.hi = hi
        self.length = length
        self.way_index = way_index
        self.c0 = c0
        self.c1 = c1


class _Snap:
    __slots__ = ("feature_index", "way_index", "chainage", "seg_index", "vertex")

    def __init__(self, feature_index: int, way_index: int, chainage: float, seg_index: int):
        self.feature_index = feature_index
        self.way_index = way_index
        self.chainage = chainage
        self.seg_index = seg_index
        self.vertex = -1


def extend_matches(features: list[dict], ways: list[Way], half_m: float, verbose: bool = True) -> list[dict]:
    """Return LineString features covering each site's Voronoi cell plus a trimmed clip."""
    if not features:
        return []
    if not ways:
        return list(features)

    geoms = _prepare_ways(ways)
    by_id: dict[str, list[int]] = defaultdict(list)
    for index, way in enumerate(ways):
        by_id[way.osm_id].append(index)

    snaps: list[_Snap | None] = []
    for feature_index, feature in enumerate(features):
        snaps.append(_locate(feature_index, feature, geoms, by_id))
    located = [snap for snap in snaps if snap is not None]
    if verbose:
        print(f"  extend: {len(located)}/{len(features)} snaps on {len(ways)} ways", flush=True)
    if not located:
        return list(features)

    if verbose:
        print("  extend: bridging ways…", flush=True)
    vertex_of_end, n_vertices = _bridge_vertices(ways, geoms)
    adj: list[list[tuple[int, int, float]]] = [[] for _ in range(n_vertices)]
    edges: list[_Edge] = []
    way_edges: list[list[tuple[float, float, int]]] = [[] for _ in ways]

    def add_vertex() -> int:
        nonlocal n_vertices
        adj.append([])
        n_vertices += 1
        return n_vertices - 1

    def add_edge(lo: int, hi: int, length: float, way_index: int, c0: float, c1: float) -> None:
        if lo == hi:
            return
        edge_id = len(edges)
        span = max(0.0, length)
        edges.append(_Edge(lo, hi, span, way_index, c0, c1))
        adj[lo].append((hi, edge_id, span))
        adj[hi].append((lo, edge_id, span))
        way_edges[way_index].append((c0, c1, edge_id))

    cuts: dict[int, list[_Snap]] = defaultdict(list)
    for snap in located:
        cuts[snap.way_index].append(snap)

    for way_index in range(len(ways)):
        total = geoms[way_index][1][-1]
        if total < _MIN_SPAN_M:
            continue
        start_v = vertex_of_end.get((way_index, True))
        end_v = vertex_of_end.get((way_index, False))
        if start_v is None or end_v is None:
            continue
        events: list[tuple[float, _Snap | None]] = [(0.0, None), (total, None)]
        for snap in cuts.get(way_index, ()):
            events.append((snap.chainage, snap))
        events.sort(key=lambda item: (item[0], item[1] is not None))
        clusters: list[list[tuple[float, _Snap | None]]] = []
        for chainage, snap in events:
            if clusters and chainage - clusters[-1][-1][0] <= _SAME_VERTEX_M:
                clusters[-1].append((chainage, snap))
            else:
                clusters.append([(chainage, snap)])
        sequence: list[tuple[float, int]] = []
        for cluster in clusters:
            position = cluster[0][0]
            sites = [snap for _, snap in cluster if snap is not None]
            at_start = position <= _SAME_VERTEX_M
            at_end = total - position <= _SAME_VERTEX_M
            if at_start:
                vertex = start_v
            elif at_end:
                vertex = end_v
            else:
                vertex = add_vertex()
            if not sites:
                sequence.append((position, vertex))
                continue
            sites[0].vertex = vertex
            sequence.append((position, vertex))
            for extra in sites[1:]:
                extra_vertex = add_vertex()
                extra.vertex = extra_vertex
                sequence.append((position, extra_vertex))
        for (c0, v0), (c1, v1) in zip(sequence, sequence[1:]):
            add_edge(v0, v1, c1 - c0, way_index, c0, c1)

    if verbose:
        print("  extend: distances…", flush=True)
    dist, owner, parent_v, parent_e = _dijkstra(n_vertices, adj, located)
    if verbose:
        print(f"  extend: graph {n_vertices} vertices, {len(edges)} edges", flush=True)
    intervals: list[list[tuple[int, float, float]]] = [[] for _ in edges]
    _mark_between_sites(edges, dist, owner, parent_v, parent_e, intervals)
    _mark_clips(located, geoms, way_edges, intervals, half_m)

    pieces: dict[int, list[list[tuple[float, float]]]] = defaultdict(list)
    for edge_id, edge in enumerate(edges):
        xy, cum = geoms[edge.way_index]
        for feature_index, t0, t1 in _merge_intervals(intervals[edge_id]):
            line = _slice(xy, cum, edge.c0 + t0, edge.c0 + t1)
            if len(line) >= 2:
                pieces[feature_index].append(line)

    emitted: set[int] = set()
    output: list[dict] = []
    for feature_index, lines in pieces.items():
        props = dict(features[feature_index].get("properties") or {})
        for line in _chain(lines):
            output.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": [[lon, lat] for lon, lat in line]},
                    "properties": props,
                }
            )
            emitted.add(feature_index)
    for index, feature in enumerate(features):
        if index not in emitted:
            output.append(feature)
    if verbose:
        print(f"  extend: {len(output)} lines", flush=True)
    return output


def _prepare_ways(ways: list[Way]) -> list[tuple[list[tuple[float, float]], list[float]]]:
    geoms = []
    for way in ways:
        xy = [to_xy(lon, lat) for lon, lat in way.coords]
        way.xy = xy
        cum = [0.0]
        for (ax, ay), (bx, by) in zip(xy, xy[1:]):
            cum.append(cum[-1] + hypot(bx - ax, by - ay))
        geoms.append((xy, cum))
    return geoms


def _locate(
    feature_index: int,
    feature: dict,
    geoms: list[tuple[list[tuple[float, float]], list[float]]],
    by_id: dict[str, list[int]],
) -> _Snap | None:
    props = feature.get("properties") or {}
    way_ids = by_id.get(str(props.get("osm_way_id")), ())
    if not way_ids or props.get("snap_lon") is None or props.get("snap_lat") is None:
        return None
    px, py = to_xy(float(props["snap_lon"]), float(props["snap_lat"]))
    best: tuple[float, int, float, int] | None = None
    for way_index in way_ids:
        xy, cum = geoms[way_index]
        for seg in range(len(xy) - 1):
            dist, sx, sy = point_segment_distance(px, py, xy[seg][0], xy[seg][1], xy[seg + 1][0], xy[seg + 1][1])
            if best is not None and dist >= best[0]:
                continue
            along = hypot(sx - xy[seg][0], sy - xy[seg][1])
            best = (dist, way_index, cum[seg] + along, seg)
    if best is None or best[0] > 50.0:
        return None
    _dist, way_index, chainage, seg = best
    return _Snap(feature_index, way_index, chainage, seg)


def _departure(xy: list[tuple[float, float]], at_start: bool) -> float | None:
    if len(xy) < 2:
        return None
    origin = xy[0] if at_start else xy[-1]
    step = 1 if at_start else -1
    cursor = step if at_start else len(xy) - 1 + step
    target = None
    travelled = 0.0
    while 0 <= cursor < len(xy):
        prev = cursor - step
        travelled += hypot(xy[cursor][0] - xy[prev][0], xy[cursor][1] - xy[prev][1])
        target = xy[cursor]
        if travelled >= _BEARING_MIN_M:
            break
        cursor += step
    if target is None:
        return None
    return bearing_deg(origin[0], origin[1], target[0], target[1])


def _angle_between(a: float, b: float) -> float:
    diff = abs(a - b) % 360.0
    if diff > 180.0:
        diff = 360.0 - diff
    return diff


def _can_bridge(left: tuple, right: tuple) -> bool:
    """left/right are (way_index, at_start, bearing, ref, is_link)."""
    if left[0] == right[0] and left[1] == right[1]:
        return False
    ref = left[3]
    if not ref or ref != right[3]:
        return False
    if left[4] or right[4]:
        return False
    if left[2] is None or right[2] is None:
        return False
    return _angle_between(left[2], right[2]) >= _BRIDGE_MIN_DEG


def _bridge_vertices(
    ways: list[Way], geoms: list[tuple[list[tuple[float, float]], list[float]]]
) -> tuple[dict[tuple[int, bool], int], int]:
    """One vertex per endpoint, shared across ways that are allowed to bridge."""
    groups: dict[tuple[float, float], list[int]] = defaultdict(list)
    ends: list[tuple[int, bool, float | None, str | None, bool]] = []
    for way_index, way in enumerate(ways):
        xy = geoms[way_index][0]
        if len(xy) < 2:
            continue
        link = way.highway.endswith("_link")
        ref = way.ref if isinstance(way.ref, str) and way.ref else None
        for at_start in (True, False):
            point = xy[0] if at_start else xy[-1]
            lon, lat = to_lonlat(point[0], point[1])
            groups[(round(lon, _NODE_DECIMALS), round(lat, _NODE_DECIMALS))].append(len(ends))
            ends.append((way_index, at_start, _departure(xy, at_start), ref, link))

    vertex_of_end: dict[tuple[int, bool], int] = {}
    next_vertex = 0

    def fresh() -> int:
        nonlocal next_vertex
        vertex = next_vertex
        next_vertex += 1
        return vertex

    for group in groups.values():
        parent = list(range(len(group)))

        def find(position: int) -> int:
            while parent[position] != position:
                parent[position] = parent[parent[position]]
                position = parent[position]
            return position

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                if _can_bridge(ends[group[i]], ends[group[j]]):
                    union(i, j)
        component_vertex: dict[int, int] = {}
        for position, endpoint_id in enumerate(group):
            root = find(position)
            if root not in component_vertex:
                component_vertex[root] = fresh()
            way_index, at_start = ends[endpoint_id][0], ends[endpoint_id][1]
            vertex_of_end[(way_index, at_start)] = component_vertex[root]
    return vertex_of_end, next_vertex


def _dijkstra(
    n_vertices: int,
    adj: list[list[tuple[int, int, float]]],
    snaps: list[_Snap],
) -> tuple[list[float], list[int], list[int], list[int]]:
    dist = [_INF] * n_vertices
    owner = [-1] * n_vertices
    parent_v = [-1] * n_vertices
    parent_e = [-1] * n_vertices
    heap: list[tuple[float, int]] = []
    for snap in snaps:
        vertex = snap.vertex
        if vertex < 0 or dist[vertex] == 0.0:
            continue
        dist[vertex] = 0.0
        owner[vertex] = snap.feature_index
        heapq.heappush(heap, (0.0, vertex))
    while heap:
        travelled, vertex = heapq.heappop(heap)
        if travelled > dist[vertex]:
            continue
        for neighbour, edge_id, length in adj[vertex]:
            candidate = travelled + length
            if candidate < dist[neighbour] - 1e-4:
                dist[neighbour] = candidate
                owner[neighbour] = owner[vertex]
                parent_v[neighbour] = vertex
                parent_e[neighbour] = edge_id
                heapq.heappush(heap, (candidate, neighbour))
    return dist, owner, parent_v, parent_e


def _mark_between_sites(
    edges: list[_Edge],
    dist: list[float],
    owner: list[int],
    parent_v: list[int],
    parent_e: list[int],
    intervals: list[list[tuple[int, float, float]]],
) -> None:
    full = [False] * len(edges)

    def add(edge_id: int, feature_index: int, t0: float, t1: float) -> None:
        if feature_index < 0 or t1 - t0 < _MIN_SPAN_M:
            return
        intervals[edge_id].append((feature_index, t0, t1))

    def mark_to_source(vertex: int) -> None:
        guard = 0
        while parent_v[vertex] != -1 and guard <= len(parent_v):
            edge_id = parent_e[vertex]
            if edge_id < 0 or full[edge_id]:
                break
            full[edge_id] = True
            add(edge_id, owner[vertex], 0.0, edges[edge_id].length)
            vertex = parent_v[vertex]
            guard += 1

    for edge_id, edge in enumerate(edges):
        left, right = owner[edge.lo], owner[edge.hi]
        if left < 0 or right < 0 or left == right:
            continue
        length = edge.length
        if length < _MIN_SPAN_M:
            mark_to_source(edge.lo)
            mark_to_source(edge.hi)
            continue
        split = (dist[edge.hi] + length - dist[edge.lo]) / 2.0
        if split < 0.0:
            split = 0.0
        elif split > length:
            split = length
        add(edge_id, left, 0.0, split)
        add(edge_id, right, split, length)
        mark_to_source(edge.lo)
        mark_to_source(edge.hi)


def _clip_bounds(cum: list[float], seg_index: int, snap_chain: float, half_m: float) -> tuple[float, float]:
    """Match clip_linestring: include the vertex that crosses half_m, and the whole current segment."""
    last = len(cum) - 1
    index = min(max(seg_index, 0), last - 1)
    travelled = snap_chain - cum[index]
    cursor = index
    back = cum[index]
    while cursor > 0 and travelled < half_m:
        travelled += cum[cursor] - cum[cursor - 1]
        back = cum[cursor - 1]
        cursor -= 1
    travelled = cum[index + 1] - snap_chain
    cursor = index + 1
    forward = cum[index + 1]
    while cursor < last and travelled < half_m:
        travelled += cum[cursor + 1] - cum[cursor]
        forward = cum[cursor + 1]
        cursor += 1
    return back, forward


def _subtract(free: list[tuple[float, float]], start: float, end: float) -> list[tuple[float, float]]:
    kept: list[tuple[float, float]] = []
    for left, right in free:
        if end <= left or start >= right:
            kept.append((left, right))
            continue
        if start > left:
            kept.append((left, min(start, right)))
        if end < right:
            kept.append((max(end, left), right))
    return [(left, right) for left, right in kept if right - left >= _MIN_SPAN_M]


def _mark_clips(
    snaps: list[_Snap],
    geoms: list[tuple[list[tuple[float, float]], list[float]]],
    way_edges: list[list[tuple[float, float, int]]],
    intervals: list[list[tuple[int, float, float]]],
    half_m: float,
) -> None:
    by_way: dict[int, list[_Snap]] = defaultdict(list)
    for snap in snaps:
        if snap.vertex >= 0:
            by_way[snap.way_index].append(snap)
    for way_index, sites in by_way.items():
        sites.sort(key=lambda snap: snap.chainage)
        cum = geoms[way_index][1]
        ordered = way_edges[way_index]
        for position, snap in enumerate(sites):
            back, forward = _clip_bounds(cum, snap.seg_index, snap.chainage, half_m)
            if position > 0 and snap.chainage - sites[position - 1].chainage > 1.0:
                back = max(back, (sites[position - 1].chainage + snap.chainage) / 2.0)
            if position + 1 < len(sites) and sites[position + 1].chainage - snap.chainage > 1.0:
                forward = min(forward, (snap.chainage + sites[position + 1].chainage) / 2.0)
            if forward - back < _MIN_SPAN_M:
                continue
            for c0, c1, edge_id in ordered:
                if c1 <= back or c0 >= forward:
                    continue
                t0 = max(0.0, back - c0)
                t1 = min(c1 - c0, forward - c0)
                free = [(t0, t1)]
                for other, a, b in intervals[edge_id]:
                    if other != snap.feature_index:
                        free = _subtract(free, a, b)
                for a, b in free:
                    intervals[edge_id].append((snap.feature_index, a, b))


def _merge_intervals(spans: list[tuple[int, float, float]]) -> list[tuple[int, float, float]]:
    by_site: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for feature_index, start, end in spans:
        if end > start:
            by_site[feature_index].append((start, end))
    merged: list[tuple[int, float, float]] = []
    for feature_index, parts in by_site.items():
        parts.sort()
        cur_s, cur_e = parts[0]
        for start, end in parts[1:]:
            if start <= cur_e + _MIN_SPAN_M:
                cur_e = max(cur_e, end)
            else:
                if cur_e - cur_s >= _MIN_SPAN_M:
                    merged.append((feature_index, cur_s, cur_e))
                cur_s, cur_e = start, end
        if cur_e - cur_s >= _MIN_SPAN_M:
            merged.append((feature_index, cur_s, cur_e))
    return merged


def _point_at(xy: list[tuple[float, float]], cum: list[float], chain: float) -> tuple[float, float]:
    if chain <= cum[0]:
        return xy[0]
    if chain >= cum[-1]:
        return xy[-1]
    lo, hi = 0, len(cum) - 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if cum[mid] <= chain:
            lo = mid
        else:
            hi = mid
    span = cum[hi] - cum[lo]
    t = 0.0 if span == 0.0 else (chain - cum[lo]) / span
    return (xy[lo][0] + (xy[hi][0] - xy[lo][0]) * t, xy[lo][1] + (xy[hi][1] - xy[lo][1]) * t)


def _slice(
    xy: list[tuple[float, float]], cum: list[float], start: float, end: float
) -> list[tuple[float, float]]:
    if end < start:
        start, end = end, start
    if end - start < _MIN_SPAN_M:
        return []
    points = [_point_at(xy, cum, start)]
    for index, chain in enumerate(cum):
        if start < chain < end:
            points.append(xy[index])
    points.append(_point_at(xy, cum, end))
    line: list[tuple[float, float]] = []
    for x, y in points:
        if not line or hypot(x - line[-1][0], y - line[-1][1]) > 0.01:
            line.append(to_lonlat(x, y))
    return line


def _dedupe(line: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for lon, lat in line:
        point = (round(float(lon), 6), round(float(lat), 6))
        if not out or point != out[-1]:
            out.append(point)
    return out


def _chain(lines: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    lines = [line for line in (_dedupe(line) for line in lines) if len(line) >= 2]
    if not lines:
        return []
    index: dict[tuple[float, float], list[int]] = defaultdict(list)
    for line_index, line in enumerate(lines):
        index[line[0]].append(line_index)
        if line[-1] != line[0]:
            index[line[-1]].append(line_index)
    used = [False] * len(lines)
    chained: list[list[tuple[float, float]]] = []

    def continuation(node: tuple[float, float]) -> int | None:
        if len(index[node]) != 2:
            return None
        pending = [line_index for line_index in index[node] if not used[line_index]]
        if len(pending) != 1:
            return None
        return pending[0]

    for start in range(len(lines)):
        if used[start]:
            continue
        used[start] = True
        line = list(lines[start])
        while True:
            nxt = continuation(line[-1])
            if nxt is None:
                break
            used[nxt] = True
            other = lines[nxt]
            if other[0] == line[-1]:
                line.extend(other[1:])
            else:
                line.extend(list(reversed(other))[1:])
        prefix: list[list[tuple[float, float]]] = []
        node = lines[start][0]
        while True:
            nxt = continuation(node)
            if nxt is None:
                break
            used[nxt] = True
            other = lines[nxt]
            if other[-1] == node:
                prefix.append(other[:-1])
                node = other[0]
            else:
                prefix.append(list(reversed(other))[:-1])
                node = other[-1]
        if prefix:
            merged: list[tuple[float, float]] = []
            for part in reversed(prefix):
                merged.extend(part)
            merged.extend(line)
            line = merged
        if len(line) >= 2:
            chained.append(line)
    return chained


def selftest() -> None:
    """Geometric checks for the coverage rules. No downloads."""
    from geo import to_xy as project

    def dense(points: list[tuple[float, float]], step: float = 20.0) -> list[tuple[float, float]]:
        if len(points) < 2:
            return points
        out = [points[0]]
        for (ax, ay), (bx, by) in zip(points, points[1:]):
            length = hypot(bx - ax, by - ay)
            count = max(1, int(round(length / step)))
            for i in range(1, count + 1):
                t = i / count
                out.append((ax + (bx - ax) * t, ay + (by - ay) * t))
        return out

    def way(osm_id: str, ref: str | None, highway: str, xy: list[tuple[float, float]]) -> Way:
        return Way(
            osm_id=osm_id,
            highway=highway,
            name=None,
            ref=ref,
            oneway="yes",
            coords=[to_lonlat(x, y) for x, y in xy],
        )

    def feature(site_id: str, road: Way, xy: tuple[float, float], speed: float) -> dict:
        lon, lat = to_lonlat(xy[0], xy[1])
        return {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[lon, lat], [lon, lat]]},
            "properties": {
                "method": "point_snap",
                "site_id": site_id,
                "name": site_id,
                "osm_way_id": road.osm_id,
                "highway": road.highway,
                "road_ref": road.ref,
                "confidence": 0.9,
                "match_distance_m": 1.0,
                "snap_lon": lon,
                "snap_lat": lat,
                "notes": "nearest_way",
                "reason": "",
                "color_speed": "#112233" if speed > 50 else "#332211",
                "metric_speed_kmh": speed,
            },
        }

    def sites_at(result: list[dict], x: float, y: float, tol: float = 2.0) -> set[str]:
        found = set()
        for item in result:
            coords = item["geometry"]["coordinates"]
            xy = [project(lon, lat) for lon, lat in coords]
            for (ax, ay), (bx, by) in zip(xy, xy[1:]):
                dist, _, _ = point_segment_distance(x, y, ax, ay, bx, by)
                if dist <= tol:
                    found.add(item["properties"]["site_id"])
                    break
        return found

    def expect(result: list[dict], x: float, y: float, site: str) -> None:
        found = sites_at(result, x, y)
        if found != {site}:
            raise SystemExit(f"at ({x:.1f}, {y:.1f}) expected {site}, found {found or 'empty'}")

    def expect_empty(result: list[dict], x: float, y: float) -> None:
        found = sites_at(result, x, y)
        if found:
            raise SystemExit(f"at ({x:.1f}, {y:.1f}) expected empty, found {found}")

    straight = way("w", "A1", "motorway", dense([(x, 0.0) for x in (0.0, 2000.0)]))
    two = extend_matches(
        [feature("A", straight, (400.0, 0.0), 80), feature("B", straight, (1600.0, 0.0), 30)],
        [straight],
        180,
        verbose=False,
    )
    expect(two, 230, 0, "A")
    expect_empty(two, 160, 0)
    expect(two, 990, 0, "A")
    expect(two, 1010, 0, "B")
    expect(two, 1770, 0, "B")
    expect_empty(two, 1820, 0)
    if two[0]["properties"]["metric_speed_kmh"] not in (80, 30):
        raise SystemExit("match properties were not copied onto the extended line")

    close = way("c", "A1", "motorway", dense([(x, 0.0) for x in (-400.0, 600.0)]))
    near = extend_matches(
        [feature("A", close, (0.0, 0.0), 80), feature("B", close, (200.0, 0.0), 30)],
        [close],
        180,
        verbose=False,
    )
    expect(near, -170, 0, "A")
    expect_empty(near, -210, 0)
    expect(near, 90, 0, "A")
    expect(near, 110, 0, "B")
    expect(near, 370, 0, "B")
    expect_empty(near, 410, 0)

    row = way("r", "A1", "motorway", dense([(float(x), 0.0) for x in range(-400, 1401, 20)]))
    three = extend_matches(
        [
            feature("L", row, (0.0, 0.0), 80),
            feature("M", row, (100.0, 0.0), 60),
            feature("R", row, (1000.0, 0.0), 40),
        ],
        [row],
        180,
        verbose=False,
    )
    expect(three, 30, 0, "L")
    expect(three, 70, 0, "M")
    expect(three, 200, 0, "M")
    expect(three, 500, 0, "M")
    expect(three, 600, 0, "R")
    expect_empty(three, -220, 0)
    expect(three, 1160, 0, "R")
    expect_empty(three, 1220, 0)

    stem = way("stem", "A12", "motorway", dense([(-400.0, 0.0), (0.0, 0.0)]))
    branch = way("branch", "A12", "motorway", dense([(0.0, 0.0), (500.0, 0.0)]))
    empty = way("empty", "A12", "motorway", dense([(0.0, 0.0), (0.0, 300.0)]))
    y_result = extend_matches(
        [feature("A", stem, (-100.0, 0.0), 80), feature("B", branch, (400.0, 0.0), 30)],
        [stem, branch, empty],
        180,
        verbose=False,
    )
    expect(y_result, -260, 0, "A")
    expect_empty(y_result, -320, 0)
    expect(y_result, 140, 0, "A")
    expect(y_result, 170, 0, "B")
    expect(y_result, 480, 0, "B")
    expect_empty(y_result, 0, 40)
    expect_empty(y_result, 0, 200)

    main_a = way("ma", "A15", "motorway", dense([(0.0, 0.0), (400.0, 0.0)]))
    other = way("mb", "A16", "motorway", dense([(400.0, 0.0), (900.0, 0.0)]))
    refs = extend_matches(
        [feature("A", main_a, (350.0, 0.0), 80), feature("B", other, (700.0, 0.0), 30)],
        [main_a, other],
        180,
        verbose=False,
    )
    expect(refs, 300, 0, "A")
    expect_empty(refs, 450, 0)
    expect(refs, 600, 0, "B")

    east = way("east", "A15", "motorway", dense([(0.0, 0.0), (400.0, 0.0)]))
    west_pts = dense([(400.0, 0.0), (0.0, 40.0)])
    west = way("west", "A15", "motorway", west_pts)
    west_len = hypot(400.0, 40.0)
    west_site = (400.0 - 400.0 * (350.0 / west_len), 40.0 * (350.0 / west_len))
    west_probe = (400.0 - 400.0 * (100.0 / west_len), 40.0 * (100.0 / west_len))
    carriage = extend_matches(
        [feature("E", east, (350.0, 0.0), 80), feature("W", west, west_site, 30)],
        [east, west],
        180,
        verbose=False,
    )
    expect_empty(carriage, west_probe[0], west_probe[1])
    expect(carriage, 200, 0, "E")
    expect_empty(carriage, 80, 0)

    main = way("main", "A15", "motorway", dense([(0.0, 0.0), (300.0, 0.0)]))
    link = way("link", "A15", "motorway_link", dense([(300.0, 0.0), (300.0, 200.0)]))
    main2 = way("main2", "A15", "motorway", dense([(300.0, 200.0), (700.0, 200.0)]))
    linked = extend_matches(
        [feature("A", main, (100.0, 0.0), 80), feature("B", main2, (600.0, 200.0), 30)],
        [main, link, main2],
        180,
        verbose=False,
    )
    expect_empty(linked, 300, 100)
    expect_empty(linked, 320, 200)
    expect(linked, 500, 200, "B")

    only_link = way("only", "A15", "motorway_link", dense([(0.0, 0.0), (400.0, 0.0)]))
    beyond = way("beyond", "A15", "motorway", dense([(400.0, 0.0), (800.0, 0.0)]))
    on_link = extend_matches(
        [feature("L1", only_link, (100.0, 0.0), 80), feature("L2", only_link, (300.0, 0.0), 30)],
        [only_link, beyond],
        180,
        verbose=False,
    )
    expect(on_link, 150, 0, "L1")
    expect(on_link, 250, 0, "L2")
    expect_empty(on_link, 500, 0)

    blank_a = way("ba", None, "primary", dense([(0.0, 0.0), (400.0, 0.0)]))
    blank_b = way("bb", None, "primary", dense([(400.0, 0.0), (800.0, 0.0)]))
    blanks = extend_matches(
        [feature("A", blank_a, (350.0, 0.0), 80), feature("B", blank_b, (700.0, 0.0), 30)],
        [blank_a, blank_b],
        180,
        verbose=False,
    )
    expect_empty(blanks, 450, 0)

    lone = way("lone", "A1", "motorway", dense([(0.0, 0.0), (2000.0, 0.0)]))
    alone = extend_matches([feature("S", lone, (1000.0, 0.0), 80)], [lone], 180, verbose=False)
    expect(alone, 900, 0, "S")
    expect(alone, 1100, 0, "S")
    expect_empty(alone, 700, 0)
    expect_empty(alone, 1300, 0)

    west_arm = way("jw", "A7", "motorway", dense([(-300.0, 0.0), (0.0, 0.0)]))
    east_arm = way("je", "A7", "motorway", dense([(0.0, 0.0), (400.0, 0.0)]))
    north_arm = way("jn", "A7", "motorway", dense([(0.0, 0.0), (0.0, 400.0)]))
    triple = extend_matches(
        [
            feature("A", west_arm, (-100.0, 0.0), 80),
            feature("B", east_arm, (300.0, 0.0), 30),
            feature("C", north_arm, (0.0, 200.0), 50),
        ],
        [west_arm, east_arm, north_arm],
        180,
        verbose=False,
    )
    expect(triple, -50, 0, "A")
    expect(triple, 80, 0, "A")
    expect(triple, 130, 0, "B")
    expect(triple, 0, 30, "A")
    expect(triple, 0, 80, "C")

    joined = way("joined", "A15;A16", "motorway", dense([(0.0, 0.0), (400.0, 0.0)]))
    single = way("single", "A15", "motorway", dense([(400.0, 0.0), (800.0, 0.0)]))
    compound = extend_matches(
        [feature("A", joined, (350.0, 0.0), 80), feature("B", single, (700.0, 0.0), 30)],
        [joined, single],
        180,
        verbose=False,
    )
    expect_empty(compound, 450, 0)

    print("extend selftest ok")
