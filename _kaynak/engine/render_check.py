"""Verification: render CLD-* layers from a post-load dump over the architecture."""
import sys, os, re, collections
sys.path.insert(0, os.path.dirname(__file__))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from dwgdata import Dwg
from arch import EXCL

dump, prefix, out = sys.argv[1], sys.argv[2], sys.argv[3]
region = tuple(map(float, sys.argv[4:8])) if len(sys.argv) >= 8 else None
d = Dwg(dump)
items, arch = [], []
for (lay, k, pts, cl) in d.geo:
    (items if lay.startswith(prefix) else arch).append((lay, pts))
for ins in d.inserts:
    if ins['layer'].startswith(prefix):
        for (lay, k, pts, cl) in d.expand(ins):
            items.append((ins['layer'], pts))
texts = [t for t in d.texts if t['layer'].startswith(prefix)]
cnt = collections.Counter(l for l, _ in items)
print('CLD items', len(items), 'texts', len(texts), dict(cnt.most_common(12)))
print('CLD inserts', collections.Counter(i['name'] for i in d.inserts if i['layer'].startswith(prefix)).most_common(30))
if region is None:
    xs = [p[0] for _, pts in items for p in pts]
    ys = [p[1] for _, pts in items for p in pts]
    region = (min(xs), min(ys), max(xs), max(ys))
x0, y0, x1, y1 = region
fig, ax = plt.subplots(figsize=(22, 22 * (y1 - y0) / max(1, (x1 - x0))) if (y1 - y0) < (x1 - x0) else (16, 16))
for lay, pts in arch:
    if EXCL.search(lay):
        continue
    if any(x0 <= p[0] <= x1 and y0 <= p[1] <= y1 for p in pts):
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color='0.75', lw=0.25)
cmap = plt.get_cmap('tab10')
col = {l: cmap(i % 10) for i, (l, _) in enumerate(cnt.most_common())}
for lay, pts in items:
    if any(x0 <= p[0] <= x1 and y0 <= p[1] <= y1 for p in pts):
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=col[lay], lw=0.5)
for t in texts:
    if x0 <= t['px'] <= x1 and y0 <= t['py'] <= y1:
        ax.text(t['px'], t['py'], t['s'][:40], fontsize=3.5)
handles = [plt.Line2D([0], [0], color=col[l], lw=2) for l, _ in cnt.most_common(10)]
ax.legend(handles, [l for l, _ in cnt.most_common(10)], fontsize=8, loc='upper right')
ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect('equal')
fig.savefig(out, dpi=110)
print('saved', out)
