import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from dwgdata import Dwg
from arch import Arch, is_room_label, parse_area
import arch_rooms as AR
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

d = Dwg(sys.argv[1])
A = Arch(d)
key = sys.argv[2]
ty = float(sys.argv[3])
pl = [p for p in A.find_plans() if p.key == key and abs(p.title['py'] - ty) < 50][0]
comp = A.plan_region(pl)
mx = comp.bounds
pl.bbox = (mx[0] - 300, mx[1] - 300, mx[2] + 300, mx[3] + 300)
lines = A.lines_in(pl.bbox)
seeds = AR.make_seeds(A, pl, is_room_label, parse_area)
for r in AR.RADII:
    walls = unary_union([ln.buffer(r, quad_segs=2) for ln in lines])
    polys = list(walls.geoms) if hasattr(walls, 'geoms') else [walls]
    holes = [Polygon(ring) for p in polys for ring in p.interiors]
    big = max(polys, key=lambda p: Polygon(p.exterior).area)
    print(f'r={r}: comps={len(polys)} holes={len(holes)} bigext={Polygon(big.exterior).area/1e4:.0f}m2')
    for sd in seeds:
        res = []
        for (px, py) in sd['pts']:
            c = [h for h in holes if h.contains(Point(px, py))]
            res.append(f"{min(c, key=lambda h: h.area).buffer(r, join_style='mitre').area/1e4:.1f}" if c else '-')
        print(f"    {sd['name'][:22]:22s} L={sd['label_area']} pts={len(sd['pts'])} -> {res}")
