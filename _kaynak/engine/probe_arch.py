"""Diagnostic: run architecture extraction for one parcel and print/plot results."""
import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
from dwgdata import Dwg
from arch import Arch

p = sys.argv[1]
dump = sys.argv[2]
out = sys.argv[3] if len(sys.argv) > 3 else None
t0 = time.time()
d = Dwg(dump)
print('loaded', time.time() - t0, 'texts', len(d.texts), 'inserts', len(d.inserts), 'geo', len(d.geo), 'blocks', len(d.blocks))
A = Arch(d)
plans = A.find_plans()
for pl in plans:
    ok = A.extract(pl)
    print(f"== {pl.key} {pl.name} title@({pl.title['px']:.0f},{pl.title['py']:.0f}) ok={ok} bbox={tuple(round(v) for v in pl.bbox) if pl.bbox else None}")
    if not ok:
        continue
    A.collect_inserts(pl)
    A.collect_columns(pl)
    print(f"   outline area={pl.outline.area/1e4:.1f} m2  rooms={len(pl.rooms)} doors={len(pl.doors)} fixtures={len(pl.fixtures)} cols={len(pl.columns)}")
    for r in sorted(pl.rooms, key=lambda r: -r['area']):
        la = r['label_area']
        flag = '' if la is None else ('OK' if abs(r['area'] - la) <= max(1.0, 0.12 * la) else f'MISMATCH {la}')
        print(f"     {r['name'][:30]:30s} A={r['area']:9.2f} label={la} {flag} fit={r.get('fit')} r={r.get('r')}")
    used = set()
    for r in pl.rooms:
        pass
    print('   labels in plan:', len(pl.labels))
    for t in pl.labels:
        print(f"      L {t['cx']:9.0f} {t['cy']:9.0f} h={t['h']:4.0f} {t['kind']} j={t.get('j72')},{t.get('j73')} {t['s'][:40]}")
    if out:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(16, 16))
        for ln in A.lines_in(pl.bbox):
            xs, ys = ln.xy
            ax.plot(xs, ys, color='0.6', lw=0.3)
        for r in pl.rooms:
            xs, ys = r['poly'].exterior.xy
            ax.fill(xs, ys, alpha=0.3)
            c = r['poly'].representative_point()
            ax.text(c.x, c.y, f"{r['name'][:18]}\n{r['area']:.1f}", fontsize=6, ha='center')
        xs, ys = pl.outline.exterior.xy
        ax.plot(xs, ys, color='k', lw=1.2)
        for dd in pl.doors:
            ax.plot(dd['x'], dd['y'], 'r^', ms=3)
        for f in pl.fixtures:
            ax.plot(f['x'], f['y'], 'bs', ms=3)
        for c in pl.columns:
            ax.plot(c[0], c[1], 'k+', ms=4)
        ax.set_aspect('equal')
        ax.set_title(f'P{p} {pl.name} @ {pl.title["py"]:.0f}')
        fn = os.path.join(out, f'P{p}_{pl.key}_{int(pl.title["py"])}.png')
        fig.savefig(fn, dpi=110)
        plt.close(fig)
        print('   ->', fn)
