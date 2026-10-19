"""CLD - collects the applied DWG and the plotted sheets of each parcel into
CLAUDE_LISP_BROSCO/Projeler and CLAUDE_LISP_BROSCO/Projeler PDF (one PDF per discipline + one complete set).

usage: python publish.py <out_dir(CLAUDE_LISP_BROSCO)> <final_dir> <parcel...>
"""
import json
import os
import shutil
import sys

from pypdf import PdfReader, PdfWriter

out, fin = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(out, '_kaynak', 'engine'))
from draw import DISC          # noqa: E402

proj = os.path.join(out, 'Projeler')
pdfd = os.path.join(out, 'Projeler PDF')
os.makedirs(proj, exist_ok=True)
for p in sys.argv[3:]:
    run = os.path.join(fin, f'P{p}')
    plan = json.load(open(os.path.join(run, 'plot_plan.json'), encoding='utf-8'))
    dwg = os.path.join(run, 'out.dwg')
    if os.path.exists(dwg):
        shutil.copy2(dwg, os.path.join(proj, f'CLD_P{p}_BROSCO {p} NOLU PARSEL TESİSAT PROJELERİ.dwg'))
    dst = os.path.join(pdfd, f'PARSEL_{p}')
    os.makedirs(dst, exist_ok=True)
    allw = PdfWriter()
    missing = []
    for code, short, title, fname in DISC:
        w = PdfWriter()
        pages = [q for q in plan if q['code'] == code]
        top = allw.add_outline_item(f'{code} - {title}', len(allw.pages)) if pages else None
        for q in pages:
            src = os.path.join(run, 'pdf', q['pdf'])
            if not os.path.exists(src) or os.path.getsize(src) < 5000:
                missing.append(q['name'])
                continue
            label = f'{q["name"]}  {q["title"]}' + (f' - {q["floor"]}' if q['floor'] else '') + f'  ({"ölçeksiz" if not q["floor"] else q["scale"]})'
            for pg in PdfReader(src).pages:
                w.add_page(pg)
                w.add_outline_item(label, len(w.pages) - 1)
                allw.add_page(pg)
                allw.add_outline_item(label, len(allw.pages) - 1, parent=top)
        if len(w.pages):
            with open(os.path.join(dst, f'CLD_P{p}_{code}_{fname}.pdf'), 'wb') as fh:
                w.write(fh)
    with open(os.path.join(dst, f'CLD_P{p}_00_TUM_PROJELER.pdf'), 'wb') as fh:
        allw.write(fh)
    print(f'P{p}: {len(allw.pages)} pages, missing {missing}')
