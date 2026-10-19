"""CLD engine - build all LISP deliverables.

usage: python build.py <dump_dir> <out_dir> [parcels...]
"""
import os
import sys
import json
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from design import Project
from draw import DISC, Ctx
from draw_disc import BUILDERS
from lispgen import write_lisp

CMD = {'01': 'ICTESISAT', '02': 'TOPRAKLAMA', '03': 'PARATONER', '04': 'KUVVETLIAKIM', '05': 'MEKANIK',
       '06': 'SIHHITESISAT', '07': 'YUKLEMECETVELI', '08': 'KOLONSEMASI', '09': 'AYDHESABI'}


def summary(P):
    e, b, m, pl, ea = P.elec, P.b, P.mech, P.plumb, P.earth
    t = e.tot
    rooms = sum(len(f.rooms) for f in b.floors)
    return [
        f'Mimari: {len(b.floors)} kat, {rooms} mahal, kat kotlari ' + ', '.join(f'{f.key}={f.kot:+.2f}' for f in b.floors) +
        f', bina yuksekligi {b.h_top:.2f} m',
        f'Elektrik: kurulu {t["inst"] / 1000:.1f} kW, talep {t["demand"] / 1000:.1f} kW, trafo {t["trafo"]} kVA, '
        f'KMP {t["kmp"]} kVAr, jenerator {t["gen"]} kVA',
        f'Aydinlatma: {len(e.lums)} armatur, {len(e.outs)} priz/cikis, {len(e.circuits)} linye, {len(e.panels)} pano',
        f'Topraklama: R={ea.res["R_comb"]:.2f} ohm (birlesik), paratoner LPL {ea.risk["lvl"]}, {len(ea.down)} inis',
        f'Mekanik: VRF {m.sum["vrf_in"]:.1f} kW ic unite, dis unite {"+".join(str(c) for c in m.sum["vrf_out"])} kW',
        f'Sihhi: {len(pl.fx)} armatur, {len(pl.stacks)} pis su kolonu, {len(pl.downpipes)} yagmur inisi',
    ]


def main():
    dump_dir, out_dir = sys.argv[1], sys.argv[2]
    parcels = sys.argv[3:] or ['2', '3', '4', '5']
    report = {}
    for p in parcels:
        t0 = time.time()
        P = Project(p, os.path.join(dump_dir, f'P{p}.txt'), log=print)
        ctx = Ctx(P)
        ext = (0.0, -1.0, 0.0)
        pe = P.b.d.hdr.get('PLANE', ['(0.0 0.0 1.0)'])[0].strip('()').split()
        if len(pe) == 3:
            ext = tuple(float(v) for v in pe)
        folder = os.path.join(out_dir, f'PARSEL_{p}')
        os.makedirs(folder, exist_ok=True)
        summ = summary(P)
        allops = []
        files = []
        for code, short, title, fname in DISC:
            o = BUILDERS[code](P, ctx)
            cmd = f'c:CLD_P{p}_{CMD[code]}'
            path = os.path.join(folder, f'CLD_P{p}_{code}_{fname}.lsp')
            n = write_lisp(path, p, code, fname, title, o, ext, P.b.info, summ, cmd)
            files.append((os.path.basename(path), n, os.path.getsize(path)))
            allops.append((code, o, cmd))
        report[p] = dict(files=files, zones=ctx.zones, frames=ctx.frames, summary=summ, secs=round(time.time() - t0, 1))
        print(f'P{p}: {len(files)} files in {time.time() - t0:.1f}s')
        for f in files:
            print('   ', f)
    json.dump(report, open(os.path.join(out_dir, '_kaynak', 'build_report.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
