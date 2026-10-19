import sys, collections
sys.path.insert(0, '.')
from dwgdata import Dwg
from arch import EXCL
d = Dwg(sys.argv[1])
x0, y0, x1, y1 = map(float, sys.argv[2:6])
c = collections.Counter()
for (lay, k, pts, cl) in d.geo:
    if any(x0 <= p[0] <= x1 and y0 <= p[1] <= y1 for p in pts):
        c[(lay, k, 'X' if EXCL.search(lay) else '')] += 1
for ins in d.inserts:
    if x0 <= ins['x'] <= x1 and y0 <= ins['y'] <= y1:
        c[('INS ' + ins['layer'], ins['name'][:20], 'X' if EXCL.search(ins['layer']) else '')] += 1
for k, v in c.most_common(60):
    print(v, k)
print('CNT layers types (whole dwg) for plane-unknown types:')
for k, v in d.counts.most_common(400):
    lay, typ = k.split('|')
    if typ in ('HATCH', 'SOLID', 'MLINE', 'REGION', '3DSOLID', 'WIPEOUT', 'POLYLINE', 'DIMENSION') and v > 20:
        print('  ', v, k)
