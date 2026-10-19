"""Diagnostic: plot a region with every layer in its own colour (incl. excluded ones)."""
import sys, os, re, collections
sys.path.insert(0, os.path.dirname(__file__))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from dwgdata import Dwg

d = Dwg(sys.argv[1])
x0, y0, x1, y1 = map(float, sys.argv[2:6])
out = sys.argv[6]
items = []
for (lay, k, pts, cl) in d.geo:
    if any(x0 <= p[0] <= x1 and y0 <= p[1] <= y1 for p in pts):
        items.append((lay, pts))
for ins in d.inserts:
    if x0 <= ins['x'] <= x1 and y0 <= ins['y'] <= y1:
        for (lay, k, pts, cl) in d.expand(ins):
            items.append(('INS:' + ins['layer'], pts))
cnt = collections.Counter(l for l, _ in items)
cmap = plt.get_cmap('tab20')
col = {l: cmap(i % 20) for i, (l, _) in enumerate(cnt.most_common())}
fig, ax = plt.subplots(figsize=(20, 20))
for lay, pts in items:
    ax.plot([p[0] for p in pts], [p[1] for p in pts], color=col[lay], lw=0.4)
for t in d.texts:
    if x0 <= t['px'] <= x1 and y0 <= t['py'] <= y1 and t['h'] >= 15:
        ax.text(t['px'], t['py'], t['s'][:20], fontsize=5)
handles = [plt.Line2D([0], [0], color=col[l], lw=2) for l, _ in cnt.most_common(20)]
ax.legend(handles, [f'{l} ({n})' for l, n in cnt.most_common(20)], fontsize=7, loc='upper right')
ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect('equal')
fig.savefig(out, dpi=80)
print('ok', len(items))
