"""CLD engine - drawing builders for the nine disciplines (separate sheets).

Each installation is drawn on its OWN framed sheet: a grey copy (block) of the
architectural floor plan + the installation overlay + a title block. Sheets of a
discipline are laid out in one row to the right of the architecture; the
discipline's legend, notes and calculation tables follow on the same row.
The original architectural plans are never drawn over.
"""
import math
import re
from collections import Counter
from datetime import date

import geo
from geo import m, U
from ops import Ops, Column
from elec import LUM
from arch import EXCL

TODAY = date(2026, 10, 19).strftime('%d.%m.%Y')
H_TAB = 25.0          # table text height (cm) -> 2.5 mm at 1/100
H_LBL = 18.0          # plan annotation text height
S = 2.5               # symbol scale for small plan symbols (1/100 drawings)

DISC = [
    ('01', 'ICT', 'ELEKTRİK İÇ TESİSAT PROJESİ', 'ELEKTRIK_IC_TESISAT'),
    ('02', 'TOP', 'TOPRAKLAMA PROJESİ', 'TOPRAKLAMA'),
    ('03', 'PAR', 'PARATONER (YILDIRIMDAN KORUNMA) PROJESİ', 'PARATONER'),
    ('04', 'KAK', 'KUVVETLİ AKIM - GÜÇ DAĞITIM PROJESİ', 'KUVVETLI_AKIM'),
    ('05', 'MEK', 'MEKANİK TESİSAT (ISITMA-SOĞUTMA-HAVALANDIRMA) PROJESİ', 'MEKANIK'),
    ('06', 'SIH', 'SIHHİ TESİSAT PROJESİ', 'SIHHI_TESISAT'),
    ('07', 'YUK', 'YÜKLEME CETVELLERİ (PANO YÜK DAĞILIMLARI)', 'YUKLEME_CETVELI'),
    ('08', 'KOL', 'KOLON ŞEMASI (TEK HAT DAĞITIM ŞEMASI)', 'KOLON_SEMASI'),
    ('09', 'AYH', 'AYDINLATMA HESABI (TS EN 12464-1)', 'AYDINLATMA_HESABI'),
]
ROOF_EXCL = re.compile(r'(ölç|ÖLÇ|Ölç|olcu|OLCU|^kot|yaz[ıi]|YAZI|^Y$|ANNO|IDEN|DIMS|Defpoints|ANTET|sar[ıi]$|tarama|'
                       r'HATCH|aks|AKS|^[1-9]$|PAFTA|IC-OLCU|POINT)', re.I)


def f1(x):
    return f'{x:,.1f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def f2(x):
    return f'{x:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def f0(x):
    return f'{x:,.0f}'.replace(',', '.')


def kw(W):
    return f2(W / 1000.0)


# ===================================================================== layout
class Ctx:
    """shared layout state for one parcel: rows of sheets to the right of the architecture."""
    def __init__(self, P):
        self.P = P
        self.frames = []        # plot windows (sheet frames + table zones) for PDF output
        b = P.b
        fr = [p.bbox for p in b.plans.values() if p.bbox]
        self.copy_bb = (min(f[0] for f in fr), min(f[1] for f in fr), max(f[2] for f in fr), max(f[3] for f in fr))
        y0, y1 = self.copy_bb[1] - 15000, self.copy_bb[3] + 15000
        mx = self.copy_bb[2]
        for (lay, k, pts, cl) in b.d.geo:
            for (x, y) in pts:
                if y0 <= y <= y1 and x > mx and x - self.copy_bb[2] < 250000:
                    mx = x
        for t in b.d.texts:
            if y0 <= t['py'] <= y1 and t['px'] > mx and t['px'] - self.copy_bb[2] < 250000:
                mx = t['px']
        self.x0 = mx + 6000.0
        self.y = self.copy_bb[3]
        self.zones = {}
        self.bg = {}

    def background(self, fk):
        """grey architecture block for one floor plan (block coords relative to the plan frame origin)."""
        if fk in self.bg:
            return self.bg[fk]
        b = self.P.b
        pl = b.plans[fk]
        x0, y0, x1, y1 = pl.bbox
        rx = ROOF_EXCL if fk == 'CT' else EXCL
        items = []
        for (lay, kind, pts, closed) in b.d.geo:
            if rx.search(lay) or len(pts) < 2:
                continue
            items.append((pts, closed))
        for ins in b.d.inserts:
            if ins['name'].startswith('*D') or rx.search(ins['layer']):
                continue
            if not (x0 <= ins['x'] <= x1 and y0 <= ins['y'] <= y1):
                continue
            for (lay, kind, pts, closed) in b.d.expand(ins):
                if rx.search(lay) or len(pts) < 2:
                    continue
                items.append((pts, closed))
        plines = []
        for pts, closed in items:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            if min(xs) < x0 or max(xs) > x1 or min(ys) < y0 or max(ys) > y1:
                continue
            if max(xs) - min(xs) > (x1 - x0) * 0.98 and max(ys) - min(ys) > (y1 - y0) * 0.98:
                continue
            q = [(round(p[0] - x0, 1), round(p[1] - y0, 1)) for p in pts]
            ded = [q[0]] + [v for u, v in zip(q[:-1], q[1:]) if abs(u[0] - v[0]) + abs(u[1] - v[1]) > 0.3]
            if len(ded) >= 2:
                plines.append((bool(closed), ded))
        texts = []
        f = b.floor(fk)
        if f is not None:
            for r in f.rooms:
                c = r.poly.representative_point()
                texts.append((round(c.x - x0, 1), round(c.y - y0 + 22, 1), 22.0, r.name[:30]))
                texts.append((round(c.x - x0, 1), round(c.y - y0 - 14, 1), 16.0, f'{f1(r.A)} m²'))
        name = f'CLD_P{self.P.parcel}_MIMARI_{fk}_V2'
        self.bg[fk] = (name, plines, texts, (x0, y0, x1, y1))
        return self.bg[fk]


class Sheet:
    def __init__(self, title, fk, ops, legend=None):
        self.title, self.fk, self.ops, self.legend = title, fk, ops, legend or []


def floor_name(P, fk):
    if fk == 'CT':
        return 'ÇATI PLANI'
    f = P.b.floor(fk)
    return f'{f.name} PLANI' if f else fk


def layout_row(P, ctx, code, title, prefix, sheets, zone_fn):
    """discipline row: header, sheets (background + frame + title block + overlay), then zone tables."""
    o = Ops(prefix)
    LT = o.layer('YAZI', 7)
    LF = o.layer('PAFTA', 7, None, 50)
    LB = o.layer('ALTLIK', 8, None, 13)
    x = ctx.x0
    ytop = ctx.y
    info = P.b.info
    o.T(LT, (x, ytop), 160.0, f'PARSEL {P.parcel} - {title}', 0)
    o.T(LT, (x, ytop - 230), 50.0, f'{info.get("isveren", "")} - {info.get("mahalle", "")} / {info.get("ilce", "")} / {info.get("il", "")}', 0)
    o.T(LT, (x, ytop - 310), 38.0, f'CLD otomatik proje  |  Disiplin {code}  |  {TODAY}  |  Paftalar 1/100  |  Katman öneki {prefix}*', 0)
    y = ytop - 600
    hmax = 0.0
    sheet_no = 0
    used_bg = []
    for sh in sheets:
        name, plines, texts, bb = ctx.background(sh.fk)
        if name not in used_bg:
            o.BK(name, plines, texts)
            used_bg.append(name)
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        tb = 700.0
        sx, sy = x, y - h            # lower-left of the plan area on this sheet
        o.I(LB, name, (sx, sy), 0.0, 1.0 / U)
        lw_ = 0.0
        lh_ = 0.0
        if sh.legend:
            # sheet legend inside the frame, right of the plan (each plotted sheet is self-explanatory)
            LTB = o.layer('TABLO', 7)
            lw_, lh_ = legend(o, LTB, sx + w + 250, y - 50, sh.legend, 20.0)
            lw_ += 400
        xr = max(sx + w + lw_ + 100, sx + 5400)          # room for the title block (antet)
        fb = min(sy, y - 50 - lh_ - 100)               # plan-area bottom (a tall legend stretches the frame)
        if sh.legend:
            o.P(LF, [(sx + w + 100, fb - 20), (sx + w + 100, y + 100)], False, 6.0)
        lw_ = xr - 100 - sx - w
        o.P(LF, [(sx - 100, fb - tb), (xr, fb - tb), (xr, y + 100), (sx - 100, y + 100)], True, 10.0)
        o.P(LF, [(sx - 100, fb - 20), (xr, fb - 20)], False, 6.0)
        sheet_no += 1
        antet(o, LF, LT, xr - 2500, fb - tb, xr, fb - 20, P, code, title, sh, sheet_no)
        ctx.frames.append(dict(code=code, no=sheet_no, title=sh.title, fk=sh.fk, floor=floor_name(P, sh.fk),
                               x0=sx - 100, y0=fb - tb, x1=xr, y1=y + 100))
        o.T(LT, (sx, fb - 160), 70.0, sh.title, 0)
        o.T(LT, (sx, fb - 300), 40.0, f'{floor_name(P, sh.fk)}  -  Ö: 1/100', 0)
        o.T(LT, (sx, fb - 400), 30.0, f'Parsel {P.parcel}  |  {info.get("isveren", "")[:60]}', 0)
        o.T(LT, (sx, fb - 480), 26.0, f'CLD - {TODAY} - mimari altlık: BROSCO {P.parcel} NOLU PARSEL MİMARİ.dwg', 0)
        o.extend(sh.ops, sx - bb[0], sy - bb[1])
        x += w + lw_ + 1200
        hmax = max(hmax, (y - fb) + tb + 200)
    zw, zh = zone_fn(o, x, y - 150, max(hmax, 9000.0))
    # frame + title block around the calculation tables (plotted as its own sheet)
    zx0, zy1 = x - 200, y + 150
    zx1 = max(x + zw + 100, zx0 + 5400)
    zy0 = y - 150 - zh - 300 - 750
    o.P(LF, [(zx0, zy0), (zx1, zy0), (zx1, zy1), (zx0, zy1)], True, 10.0)
    o.P(LF, [(zx0, zy0 + 750), (zx1, zy0 + 750)], False, 6.0)
    o.T(LT, (zx0 + 100, zy0 + 560), 70.0, 'HESAP TABLOLARI, CETVELLER VE NOTLAR', 0)
    o.T(LT, (zx0 + 100, zy0 + 400), 40.0, f'{title}  -  Ölçeksiz', 0)
    sheet_no += 1
    antet(o, LF, LT, zx1 - 2500, zy0 + 20, zx1, zy0 + 730, P, code, title, Sheet('HESAP TABLOLARI VE NOTLAR', None, None), sheet_no)
    ctx.frames.append(dict(code=code, no=sheet_no, title='HESAP TABLOLARI VE NOTLAR', fk=None, floor='',
                           x0=zx0, y0=zy0, x1=zx1, y1=zy1))
    zw = zx1 - x
    zh = zy1 - zy0
    rowh = max(hmax, zh) + 600 + 3500
    ctx.zones[code] = (ctx.x0, ytop, x + zw - ctx.x0, rowh)
    ctx.y = ytop - rowh
    return o


# largest extent of each CLD_S_* block at scale 1 (m) - used to fit legend samples into the row pitch
BLK_D = {'CLD_S_DL': .32, 'CLD_S_DLB': .32, 'CLD_S_HB': .6, 'CLD_S_PNL': .6, 'CLD_S_ETJ': 1.2, 'CLD_S_PLF': .3,
         'CLD_S_ACIL': .32, 'CLD_S_EXIT': .4, 'CLD_S_PRJ': .44, 'CLD_S_BOLLARD': .24, 'CLD_S_PGRUP': .5,
         'CLD_S_VAV': .4, 'CLD_S_TP': .5, 'CLD_S_ADP': .9, 'CLD_S_KMP': .6, 'CLD_S_KOLON': .3, 'CLD_S_OAP': .6,
         'CLD_S_TRAFO': 6.0, 'CLD_S_JEN': 4.0, 'CLD_S_TOP_EPB': .6, 'CLD_S_TOP_KAZIK': .5, 'CLD_S_PAR_UC': .4,
         'CLD_S_PAR_INIS': .55, 'CLD_S_KASET': .84, 'CLD_S_VRFOUT': 1.3, 'CLD_S_HRV': 1.4, 'CLD_S_MENFEZ': .6,
         'CLD_S_EMIS': .4, 'CLD_S_CATIFAN': 1.2, 'CLD_S_PANJUR': 1.2, 'CLD_S_RADYANT': 6.0, 'CLD_S_SIGFAN': .8,
         'CLD_S_ROGAR': .6, 'CLD_S_DEPO': 1.2, 'CLD_S_KLOZET': .6, 'CLD_S_LAVABO': .5, 'CLD_S_ABDEST': .4,
         'CLD_S_DUS': .9, 'CLD_S_YD': .8}


def antet(o, LF, LT, x0, y0, x1, y1, P, code, title, sh, no):
    """EMO / MMO style title block: project, owner, address, sheet, scale, date, author fields left blank to sign."""
    info = P.b.info
    mak = code in ('05', '06')
    rows = [
        ('İŞİN ADI', title[:60]),
        ('YAPI SAHİBİ', info.get('isveren', '')[:62]),
        ('ADRES', f'{info.get("mahalle", "")} / {info.get("ilce", "")} / {info.get("il", "")}  -  Ada: ......  Parsel: {P.parcel}'),
        ('PAFTA ADI', f'{sh.title[:48]} - {floor_name(P, sh.fk)}' if sh.fk else sh.title[:60]),
        ('ÖLÇEK / TARİH / PAFTA NO', f'{"1/100" if sh.fk else "Ölçeksiz"}   |   {TODAY}   |   {code}-{no:02d}'),
        ('PROJE MÜELLİFİ', ('Makine Mühendisi' if mak else 'Elektrik Mühendisi') + ' - Adı Soyadı: ..............................'),
        ('ODA SİCİL / SMM NO', ('MMO' if mak else 'EMO') + ' Sicil No: ............   SMM Belge No: ............   İmza: ............'),
    ]
    o.P(LF, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], True, 6.0)
    rh = (y1 - y0) / len(rows)
    for i, (k, v) in enumerate(rows):
        yy = y1 - (i + 1) * rh
        if i:
            o.L(LF, (x0, yy + rh), (x1, yy + rh))
        o.T(LT, (x0 + 30, yy + rh * 0.35), 18.0, k, 0)
        o.T(LT, (x0 + 620, yy + rh * 0.35), 20.0, v, 0)
    o.L(LF, (x0 + 590, y0), (x0 + 590, y1))


def legend(o, lay, x, y, items, h=H_TAB):
    seen, uniq = set(), []
    for it in items:
        key = (it[0], it[2])
        if key not in seen:
            seen.add(key)
            uniq.append(it)
    items = uniq
    rh = 3.2 * h
    w = max(len(t) for _, _, t in items) * 0.62 * h + 13 * h
    o.T(lay, (x, y), 1.3 * h, 'LEJANT', 0)
    y0 = y - 1.0 * h
    o.P(lay, [(x, y0), (x + w, y0), (x + w, y0 - rh * len(items) - h), (x, y0 - rh * len(items) - h)], True)
    for i, (blk, sc, t) in enumerate(items):
        cy = y0 - (i + 0.5) * rh - 0.5 * h
        if blk.startswith('#'):
            l2 = blk[1:] if blk[1:].startswith('CLD-') else lay
            o.P(l2, [(x + h, cy), (x + 11 * h, cy)], False, 0.0)     # >= 2,5 linetype periods
        elif blk:
            # fit the sample into the row: largest extent <= 2,6 h
            sc_l = min(sc, 2.6 * h / (BLK_D.get(blk, 0.3) * U))
            o.I(lay, blk, (x + 6.0 * h, cy), 0.0, sc_l)
        o.T(lay, (x + 12.0 * h, cy), h, t, 7)
    return w, rh * len(items) + 2.5 * h


def zone_std(legend_items, tables_fn):
    """standard zone: legend at the left, then a wrapped column of tables / notes."""
    def fn(o, x, y, colmax):
        LTB = o.layer('TABLO', 7)
        lw, lh = legend(o, LTB, x, y, legend_items) if legend_items else (0.0, 0.0)
        cx = x + lw + (400 if lw else 0)
        col = Column(o, cx, y, H_TAB, 250)
        col.colmax = colmax
        tables_fn(col, LTB)
        used_h = colmax if col.x > cx else (col.top - col.y)
        return (cx - x) + col.width_used(cx) + 400, max(lh, used_h)
    return fn


def arrow_label(o, lay, LT, p, target, label):
    dx, dy = target[0] - p[0], target[1] - p[1]
    dd = math.hypot(dx, dy)
    if dd < m(1.2):
        o.P(lay, [target, p], False, 0.0)
        o.T(LT, (p[0] + m(0.35), p[1] + m(0.30)), H_LBL, label, 0)
        return
    ux, uy = dx / dd, dy / dd
    L = min(m(1.2), dd * 0.5)
    q = (p[0] + ux * L, p[1] + uy * L)
    o.P(lay, [p, q], False, 0.0)
    hx, hy = -uy, ux
    o.P(lay, [(q[0] - ux * m(0.25) + hx * m(0.12), q[1] - uy * m(0.25) + hy * m(0.12)), q,
              (q[0] - ux * m(0.25) - hx * m(0.12), q[1] - uy * m(0.25) - hy * m(0.12))], False, 0.0)
    o.T(LT, (q[0] + m(0.15), q[1] + m(0.15)), H_LBL, label, 0)


def floors_with_rooms(P):
    return [f.key for f in P.b.floors if f.rooms]


# discipline builders live in draw_disc.py
