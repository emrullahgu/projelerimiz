import sys, collections
sys.path.insert(0, '.')
from dwgdata import Dwg
d = Dwg(sys.argv[1])
pat = sys.argv[2]
import re
bb = collections.defaultdict(lambda: [1e18, 1e18, -1e18, -1e18, 0])
for (lay, k, pts, cl) in d.geo:
    if re.search(pat, lay):
        b = bb[lay]
        for p in pts:
            b[0] = min(b[0], p[0]); b[1] = min(b[1], p[1]); b[2] = max(b[2], p[0]); b[3] = max(b[3], p[1])
        b[4] += 1
for ins in d.inserts:
    if re.search(pat, ins['layer']):
        b = bb['INS:' + ins['layer']]
        b[0] = min(b[0], ins['x']); b[1] = min(b[1], ins['y']); b[2] = max(b[2], ins['x']); b[3] = max(b[3], ins['y']); b[4] += 1
for k, b in sorted(bb.items(), key=lambda x: -x[1][4]):
    print(f'{b[4]:6d} {k[:45]:45s} x {b[0]:9.0f}..{b[2]:9.0f}  y {b[1]:9.0f}..{b[3]:9.0f}')
