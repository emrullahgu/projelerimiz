"""CLD - writes the accoreconsole script that applies all 9 LISPs to a parcel DWG, saves it,
and plots every sheet frame / table zone to PDF (true 1/100 where a standard sheet fits).

usage: python final_scr.py <out_dir(CLAUDE_LISP_BROSCO)> <run_dir> <parcel> <plane: xy|xz>
"""
import json
import os
import sys

out, run, p, plane = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
rep = json.load(open(os.path.join(out, '_kaynak', 'build_report.json'), encoding='utf-8'))[p]
runf = run.replace('\\', '/')

# DWG To PDF.pc3 media (name, width mm, height mm) as listed by -PLOT ?
SIZES = [('A3', 420, 297), ('A2', 594, 420), ('A1', 841, 594), ('A0', 1189, 841), ('B1', 1000, 707), ('B0', 1414, 1000),
         ('2A0', 1682, 1189), ('4A0', 2378, 1682)]
MEDIA = []
for nm, a, b in SIZES:
    for (w, h) in ((a, b), (b, a)):
        MEDIA.append((f'ISO full bleed {nm} ({w:.2f} x {h:.2f} MM)', w, h))


def choose(wmm, hmm):
    """smallest sheet that holds the frame at 1/100 (+10 mm margin) -> (media, orientation, scale)."""
    fit = [m for m in MEDIA if m[1] >= wmm + 10 and m[2] >= hmm + 10]
    if fit:
        m = min(fit, key=lambda m: m[1] * m[2])
        return m[0], ('_L' if m[1] > m[2] else '_P'), '1=10', True
    # larger than 4A0 at 1/100 -> fitted onto 4A0 with the same aspect
    m = max([m for m in MEDIA if (m[1] > m[2]) == (wmm > hmm)], key=lambda m: m[1] * m[2])
    return m[0], ('_L' if m[1] > m[2] else '_P'), '_F', False


L = []
w = L.append
w(f'(setvar "TRUSTEDPATHS" "{runf}/lsp")')
w('(setvar "FILEDIA" 0)')
w('(setvar "BACKGROUNDPLOT" 0)')
for f in sorted(os.listdir(os.path.join(run, 'lsp'))):
    if f.lower().endswith('.lsp'):
        w(f'(load "{runf}/lsp/{f}")')
w('(princ "\\n#CLD-LOADED")')
w(f'(c:CLD_P{p}_ICTESISAT)')          # re-run check: same entity count, nothing duplicated
w(f'(command "_.SAVEAS" "2018" "{runf}/out.dwg")')
w('(princ "\\n#CLD-SAVED")')
# plotting is done on the saved state; a plan-plane copy for XZ (front) drawings - not saved
w('(command "_.UCS" "_W")')
if plane == 'xz':
    w('(setq ss (ssget "_X" (list (cons 410 "Model"))))')
    w('(command "_.ROTATE3D" ss "" "_X" "0,0,0" "-90")')
w('(vl-catch-all-apply (quote command-s) (list "_.VSCURRENT" "_2"))')
w('(command "_.PLAN" "_W")')
plan = []
for fr in rep['frames']:
    wmm, hmm = (fr['x1'] - fr['x0']) / 10.0, (fr['y1'] - fr['y0']) / 10.0
    media, orient, scale, true_scale = choose(wmm, hmm)
    name = f"{fr['code']}-{fr['no']:02d}"
    pdf = f'{runf}/pdf/{name}.pdf'
    w(f'(command "_.-PLOT" "_Y" "Model" "DWG To PDF.pc3" "{media}" "_M" "{orient}" "_N" "_W" '
      f'"{fr["x0"]:.2f},{fr["y0"]:.2f}" "{fr["x1"]:.2f},{fr["y1"]:.2f}" "{scale}" "_C" "_Y" "acad.ctb" "_Y" "_W" "{pdf}" "_N" "_Y")')
    w(f'(princ "\\n#CLD-PLOT {name}")')
    plan.append(dict(name=name, code=fr['code'], no=fr['no'], title=fr['title'], floor=fr.get('floor', ''), media=media,
                     scale='1/100' if true_scale else 'sığdırılmış', pdf=f'{name}.pdf'))
w('(princ "\\n#CLD-DONE")')
open(os.path.join(run, 'final.scr'), 'w', encoding='cp1254').write('\n'.join(L) + '\n')
json.dump(plan, open(os.path.join(run, 'plot_plan.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(len(plan), 'plots')
