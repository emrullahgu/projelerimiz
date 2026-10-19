import sys, re
sys.path.insert(0, '.')
from dwgdata import Dwg
from arch import FLOOR_TITLE
for p in (2, 3, 4, 5):
    d = Dwg(sys.argv[1] + f'/P{p}.txt')
    rects = []
    for (lay, k, pts, cl) in d.geo:
        if k != 'GP' or len(pts) < 4:
            continue
        xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        if 3000 < w < 40000 and 3000 < h < 40000 and len(pts) <= 6:
            rects.append((lay, min(xs), min(ys), max(xs), max(ys)))
    print('P', p, 'rects', len(rects))
    for t in d.texts:
        if FLOOR_TITLE.search(t['s']) and t['h'] >= 30:
            inside = [r for r in rects if r[1] <= t['px'] <= r[3] and r[2] <= t['py'] <= r[4]]
            inside.sort(key=lambda r: (r[3] - r[1]) * (r[4] - r[2]))
            print('  ', t['s'][:16], round(t['px']), round(t['py']), [(r[0], round(r[1]), round(r[2]), round(r[3]), round(r[4])) for r in inside[:2]])
