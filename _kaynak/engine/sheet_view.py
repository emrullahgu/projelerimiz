"""Diagnostic: plot the whole sheet area around plan titles with labels."""
import sys, os, re
sys.path.insert(0, os.path.dirname(__file__))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from dwgdata import Dwg
from arch import Arch, FLOOR_TITLE, EXCL

d = Dwg(sys.argv[1])
p = sys.argv[2]
out = sys.argv[3]
A = Arch(d)
titles = [t for t in d.texts if FLOOR_TITLE.search(t['s']) and t['h'] >= 30]
xs = [t['px'] for t in titles]; ys = [t['py'] for t in titles]
x0, x1 = min(xs) - 15000, max(xs) + 8000
y0, y1 = min(ys) - 4000, max(ys) + 14000
fig, ax = plt.subplots(figsize=(22, 18))
n = 0
for (lay, pts, closed) in A.wall_items():
    px = [q[0] for q in pts]; py = [q[1] for q in pts]
    if max(px) < x0 or min(px) > x1 or max(py) < y0 or min(py) > y1:
        continue
    ax.plot(px, py, color='0.4', lw=0.2)
    n += 1
for t in d.texts:
    if x0 <= t['px'] <= x1 and y0 <= t['py'] <= y1 and t['h'] >= 25 and re.search(r'[A-ZÇĞİÖŞÜ]{3,}', t['s']):
        ax.text(t['cx'], t['cy'], t['s'][:25], fontsize=5, color='b')
for t in titles:
    ax.plot(t['px'], t['py'], 'r*', ms=10)
    ax.text(t['px'], t['py'], t['s'][:30], fontsize=8, color='r')
ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect('equal')
ax.set_title(f'P{p} items={n}')
fig.savefig(os.path.join(out, f'P{p}_sheet.png'), dpi=90)
print('ok', n)
