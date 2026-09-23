"""Local metre projection and point-to-road queries for the NDW site extent.

Equirectangular about the centre of the national site box. East-west scale is
exact at LAT0 and about 3% off at the north and south edges of the Netherlands.
A latitude-varying scale would bend north-south roads, so the scale stays fixed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


LAT0 = 52.093636
LON0 = 5.293156
M_PER_DEG_LAT = 111_320.0
M_PER_DEG_LON = 111_320.0 * math.cos(math.radians(LAT0))


def to_xy(lon: float, lat: float) -> tuple[float, float]:
    return ((lon - LON0) * M_PER_DEG_LON, (lat - LAT0) * M_PER_DEG_LAT)


def to_lonlat(x: float, y: float) -> tuple[float, float]:
    return (LON0 + x / M_PER_DEG_LON, LAT0 + y / M_PER_DEG_LAT)


def hypot(x: float, y: float) -> float:
    return math.hypot(x, y)


def bearing_deg(ax: float, ay: float, bx: float, by: float) -> float | None:
    dx, dy = bx - ax, by - ay
    if dx * dx + dy * dy < 1.0:
        return None
    return math.degrees(math.atan2(dx, dy)) % 360.0


def point_segment_distance(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> tuple[float, float, float]:
    dx, dy = bx - ax, by - ay
    len2 = dx * dx + dy * dy
    if len2 == 0.0:
        return hypot(px - ax, py - ay), ax, ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / len2))
    sx, sy = ax + t * dx, ay + t * dy
    return hypot(px - sx, py - sy), sx, sy


@dataclass
class Way:
    osm_id: str
    highway: str
    name: str | None
    ref: str | None
    oneway: str
    coords: list[tuple[float, float]]
    xy: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class Hit:
    way: Way
    distance_m: float
    snap_x: float
    snap_y: float
    seg_index: int


class RoadIndex:
    def __init__(self, ways: list[Way], cell_m: float = 120.0):
        self.ways = ways
        self.cell = cell_m
        self.buckets: dict[tuple[int, int], list[tuple[int, int]]] = {}
        for wi, way in enumerate(ways):
            way.xy = [to_xy(lon, lat) for lon, lat in way.coords]
            for si in range(len(way.xy) - 1):
                ax, ay = way.xy[si]
                bx, by = way.xy[si + 1]
                if (bx - ax) ** 2 + (by - ay) ** 2 < 0.01:
                    continue
                for cell in _cells_crossed(ax, ay, bx, by, cell_m):
                    self.buckets.setdefault(cell, []).append((wi, si))

    def nearby(self, lon: float, lat: float, radius_m: float) -> list[Hit]:
        px, py = to_xy(lon, lat)
        r = int(math.ceil(radius_m / self.cell)) + 1
        cx, cy = math.floor(px / self.cell), math.floor(py / self.cell)
        best: dict[tuple[int, int], Hit] = {}
        radius2 = radius_m * radius_m
        for ix in range(cx - r, cx + r + 1):
            for iy in range(cy - r, cy + r + 1):
                for wi, si in self.buckets.get((ix, iy), ()):
                    key = (wi, si)
                    if key in best:
                        continue
                    way = self.ways[wi]
                    ax, ay = way.xy[si]
                    bx, by = way.xy[si + 1]
                    dist, sx, sy = point_segment_distance(px, py, ax, ay, bx, by)
                    if dist * dist > radius2:
                        continue
                    best[key] = Hit(
                        way=way,
                        distance_m=dist,
                        snap_x=sx,
                        snap_y=sy,
                        seg_index=si,
                    )
        by_way: dict[str, Hit] = {}
        for hit in best.values():
            prev = by_way.get(hit.way.osm_id)
            if prev is None or hit.distance_m < prev.distance_m:
                by_way[hit.way.osm_id] = hit
        return sorted(by_way.values(), key=lambda h: h.distance_m)


def _cells_crossed(
    ax: float, ay: float, bx: float, by: float, cell: float
) -> set[tuple[int, int]]:
    x0, y0 = math.floor(ax / cell), math.floor(ay / cell)
    x1, y1 = math.floor(bx / cell), math.floor(by / cell)
    steps = max(abs(x1 - x0), abs(y1 - y0), 1)
    cells = set()
    for i in range(steps + 1):
        t = i / steps
        cells.add((math.floor((ax + (bx - ax) * t) / cell), math.floor((ay + (by - ay) * t) / cell)))
    return cells


def clip_linestring(hit: Hit, half_m: float) -> list[tuple[float, float]]:
    xy = hit.way.xy
    i = hit.seg_index
    snap = (hit.snap_x, hit.snap_y)
    backward = [xy[i]]
    acc = hypot(snap[0] - xy[i][0], snap[1] - xy[i][1])
    j = i
    while j > 0 and acc < half_m:
        step = hypot(xy[j][0] - xy[j - 1][0], xy[j][1] - xy[j - 1][1])
        acc += step
        backward.append(xy[j - 1])
        j -= 1
    forward = [snap, xy[i + 1]]
    acc = hypot(snap[0] - xy[i + 1][0], snap[1] - xy[i + 1][1])
    j = i + 1
    while j < len(xy) - 1 and acc < half_m:
        step = hypot(xy[j][0] - xy[j + 1][0], xy[j][1] - xy[j + 1][1])
        acc += step
        forward.append(xy[j + 1])
        j += 1
    line_xy = list(reversed(backward)) + forward
    deduped: list[tuple[float, float]] = []
    for x, y in line_xy:
        if not deduped or hypot(x - deduped[-1][0], y - deduped[-1][1]) > 0.5:
            deduped.append((x, y))
    if len(deduped) < 2:
        deduped = [xy[i], xy[i + 1]]
    return [to_lonlat(x, y) for x, y in deduped]


def polyline_length_m(coords: list[list[float]] | list[tuple[float, float]] | None) -> float:
    if not coords or len(coords) < 2:
        return 0.0
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(coords, coords[1:]):
        x1, y1 = to_xy(lon1, lat1)
        x2, y2 = to_xy(lon2, lat2)
        total += hypot(x2 - x1, y2 - y1)
    return total
