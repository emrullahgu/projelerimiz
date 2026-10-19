"""Verification: render CLD sheets (from a post-load dump) - overview + selected windows."""
import sys, os, collections, json
sys.path.insert(0, os.path.dirname(__file__))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from dwgdata import Dwg

dump, outdir, tag = sys.argv[1], sys.argv[2], sys.argv[3]
wins = []
for a in sys.argv[4:]:
    wins.append(tuple(map(float, a.split(','))))
d = Dwg(dump)
items = []
for (lay, k, pts, cl) in d.geo:
    if lay.startswith('CLD-'):
        items.append((lay, pts))
for ins in d.inserts:
    if ins['layer'].startswith('CLD-'):
        for (lay, k, pts, cl) in d.expand(ins):
            items.append((ins['layer'], pts))
texts = [t for t in d.texts if t['layer'].startswith('CLD-')]
print('items', len(items), 'texts', len(texts))


def color(lay):
    if lay.endswith('ALTLIK'):
        return '0.78'
    if 'PAFTA' in lay or 'TABLO' in lay or 'YAZI' in lay:
        return 'k'
    pal = ['tab:red', 'tab:blue', 'tab:green', 'tab:orange', 'tab:purple', 'tab:brown', 'tab:pink', 'tab:olive', 'tab:cyan']
    return pal[hash(lay) % len(pal)]


def render(win, fn, dpi, txt=True):
    x0, y0, x1, y1 = win
    W, H = x1 - x0, y1 - y0
    fig, ax = plt.subplots(figsize=(20, max(4, 20 * H / W)))
    for lay, pts in items:
        if any(x0 <= p[0] <= x1 and y0 <= p[1] <= y1 for p in pts):
            ax.plot([p[0] for p in pts], [p[1] for p in pts], color=color(lay), lw=0.3 if lay.endswith('ALTLIK') else 0.5)
    if txt:
        for t in texts:
            if x0 <= t['px'] <= x1 and y0 <= t['py'] <= y1:
                ax.text(t['px'], t['py'], t['s'][:60], fontsize=max(2.0, min(9.0, t['h'] / W * 2500)))
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect('equal')
    fig.savefig(fn, dpi=dpi)
    plt.close(fig)
    print('saved', fn)


xs = [p[0] for _, pts in items for p in pts]
ys = [p[1] for _, pts in items for p in pts]
ov = (min(xs), min(ys), max(xs), max(ys))
print('overview', ov)
render(ov, os.path.join(outdir, f'{tag}_overview.png'), 80, txt=False)
for i, w in enumerate(wins):
    render(w, os.path.join(outdir, f'{tag}_win{i}.png'), 110)
