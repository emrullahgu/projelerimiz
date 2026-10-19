"""Write a plain-text report of every table / note produced for a parcel (for review)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from design import Project
from draw import DISC, Ctx
from draw_disc import BUILDERS


def main():
    dump_dir, out_dir = sys.argv[1], sys.argv[2]
    for p in sys.argv[3:]:
        P = Project(p, os.path.join(dump_dir, f'P{p}.txt'), log=lambda s: None)
        ctx = Ctx(P)
        lines = [f'##### PARSEL {p}']
        b = P.b
        lines.append(f'floors: ' + ', '.join(f'{f.key} kot={f.kot} rooms={len(f.rooms)}' for f in b.floors) + f'  h_top={b.h_top} h_eave={b.h_eave}')
        for f in b.floors:
            for r in f.rooms:
                lines.append(f'  room {r.id} {f.key} {r.name} tip={r.tip} A={r.A:.2f} label={r.label_area} fit={r.fit} h={r.h}')
        for code, short, title, fname in DISC:
            o = BUILDERS[code](P, ctx)
            lines.append(f'\n==== {code} {title}  (ops={len(o.ops)})')
            from collections import Counter
            lines.append('  op kinds: ' + str(Counter(op[0] for op in o.ops)))
            lines.append('  inserts: ' + str(Counter(op[2] for op in o.ops if op[0] == 'I').most_common()))
            for op in o.ops:
                if op[0] == 'TB':
                    lines.append(f'  --- TABLE: {op[5]}')
                    for r in op[6]:
                        lines.append('    | ' + ' | '.join(r))
                elif op[0] == 'NT':
                    lines.append(f'  --- NOTES: {op[5]}')
                    for s in op[6]:
                        lines.append('    ' + s)
        open(os.path.join(out_dir, f'review_P{p}.txt'), 'w', encoding='utf-8').write('\n'.join(lines))
        print('written', p)


if __name__ == '__main__':
    main()
