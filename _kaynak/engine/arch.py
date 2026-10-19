"""CLD engine - architecture extraction from a dumped DWG.

Finds floor plans (by title), the building outline of each plan, rooms (enclosed
spaces around room labels, validated against the architect's m² labels), doors,
sanitary fixtures, columns, levels and registration offsets between floors.
"""
import math
import re
from collections import defaultdict

import shapely
from shapely.geometry import LineString, Polygon, Point, MultiPolygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

from dwgdata import Dwg

# layers never used as room boundaries (annotation, furniture, hatch, dims, axes, 3D)
EXCL = re.compile(
    r'(ölç|ÖLÇ|Ölç|olcu|OLCU|^kot$|yaz[ıi]|YAZI|^Y$|ANNO|IDEN|tefri|TEFR|aks|AKS|arama|^TF1$|ANTET|sar[ıi]$|'
    r'^[1-9]$|DIMS|Defpoints|IC-OLCU|POINT|PARSEL_|PARSEL ?ALN|KES[İI]T|FLOR|MAKE2D|^oluk$|^ASIK$|80cm|S-STRS|gorunen|Agac|ağaç|'
    r'tarama|HATCH|GRID|^kot|SİMGE|simge|antet|cerceve|çerçeve|PAFTA)', re.I)
FURN = re.compile(r'(tefri|TEFR|mobil|furn)', re.I)
DOOR_L = re.compile(r'(kap[ıi]|door|M_kapi)', re.I)
COL_L = re.compile(r'(kolon|S-COLS|column|^CM$)', re.I)

FLOOR_TITLE = re.compile(r'((ZEM[İI]N|BODRUM|ASMA|[0-9]+\s*\.?\s*(NORMAL\s*)?)\s*KAT|[ÇC]ATI)\s*PLANI', re.I)
AREA_RE = re.compile(r'^\s*([0-9][0-9.,]*)\s*m\s*[²2]', re.I)
KOT_RE = re.compile(r'^[±+\-]?\s*([0-9]+[.,][0-9]{2})$')


def parse_num(s):
    s = s.strip()
    if '.' in s and ',' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None


def parse_area(s):
    m = AREA_RE.match(s)
    return parse_num(m.group(1)) if m else None


def floor_key(title):
    t = title.upper().replace('İ', 'I')
    if 'ZEM' in t:
        return 'ZK', 'ZEMİN KAT', 0
    if 'BODRUM' in t:
        return 'BK', 'BODRUM KAT', -1
    if 'ASMA' in t:
        return 'AK', 'ASMA KAT', 0.5
    if 'ÇATI' in title.upper() or 'CATI' in t:
        return 'CT', 'ÇATI', 99
    m = re.search(r'([0-9]+)', t)
    n = int(m.group(1)) if m else 1
    return f'{n}K', f'{n}. KAT', n


# ---------------------------------------------------------------- room types
TYPE_RULES = [
    (r'ÜRET[İI]M|[İI]MALAT|FABR[İI]KA|ATÖLYE|ATOLYE|PRODUCTION', 'URETIM'),
    (r'SEVK|YÜKLEME|YUKLEME|AMBAR|STOK|HAMMADDE|MAMUL', 'DEPO'),
    (r'AÇIK OF[İI]S|OF[İI]S|[İI]DAR[İI]|MÜDÜR|MUDUR|MUHASEBE|YÖNET|BÜRO|BURO|SEKRETER|PLANLAMA|SATIN', 'OFIS'),
    (r'TOPLANTI', 'TOPLANTI'),
    (r'ABDEST', 'ABDEST'),
    (r'MESC[İI]T', 'MESCIT'),
    (r'SOYUNMA|G[İI]Y[İI]NME|DOLAP', 'SOYUNMA'),
    (r'DUŞ|DUS', 'BANYO'),
    (r'BANYO', 'BANYO'),
    (r'\bWC\b|TUVALET|LAVABO|HELA', 'WC'),
    (r'YEMEKHANE|YEMEK', 'YEMEK'),
    (r'MUTFAK|ÇAY OCA|CAY OCA|OFFICE', 'MUTFAK'),
    (r'SI[ĞG]INAK', 'SIGINAK'),
    (r'JENERAT|JENARAT|TRAFO|ELEKTR[İI]K ODASI|PANO ODASI|KAZAN|POMPA|TEKN[İI]K|HİDROFOR|HIDROFOR|KOMPRES', 'TEKNIK'),
    (r'ÇÖP|COP ', 'DEPO'),
    (r'DEPO|ARŞ[İI]V|ARSIV|KİLER|KILER', 'DEPO'),
    (r'MERD[İI]VEN', 'MERDIVEN'),
    (r'ASANS', 'ASANSOR'),
    (r'GÜV\.?\s*HOL|GUV\.?\s*HOL|YANGIN', 'HOL'),
    (r'LOB[İI]|G[İI]R[İI]Ş|GIRIS|BEKLEME|RESEPS|DANIŞMA', 'GIRIS'),
    (r'KOR[İI]DOR|HOL|SİRKÜLASYON', 'HOL'),
    (r'REVİR|REVIR|SAĞLIK', 'OFIS'),
    (r'LABORATUVAR|LAB\b|KAL[İI]TE', 'LAB'),
    (r'SERVER|SİSTEM ODASI|BİLGİ İŞLEM', 'TEKNIK'),
    (r'GÜVENL[İI]K|KULÜBE', 'OFIS'),
    (r'BALKON', 'BALKON'),
    (r'TERAS', 'TERAS'),
]


def room_type(name, area):
    n = name.upper()
    for pat, tip in TYPE_RULES:
        if re.search(pat, n):
            if tip == 'HOL' and area and area > 150 and 'GÜV' not in n and 'YANGIN' not in n:
                return 'URETIM'
            if tip == 'DEPO' and area and area > 300:
                return 'DEPOH'
            return tip
    return 'GENEL'


IS_NAME = re.compile(r'[A-Za-zÇĞİÖŞÜçğıöşü]{2,}')
NOT_ROOM = re.compile(
    r'(GİRİŞ$|^ÜRETİM GİRİŞ|^İDARE GİRİŞ|^MESCİT GİRİŞ|^SIĞINAK GİRİŞ|KAPI|PENCERE|EĞİM|EGIM|ÖLÇEK|PLANI|KES[İI]T|'
    r'GÖRÜNÜŞ|^EI ?[0-9]|^REI|^K:|^F[0-9]+|BETON|DUVAR|PANEL|PROF[İI]L|SIVA|KAROPLAKA|SERAMİK|PARKE|'
    r'ROGAR|RÖGAR|OLUK|^YK|^N$|CADDES|SOKA|ADA|PARSEL|^h:|cm\b|mm\b|HORTUM|YANGIN DOLABI|DÖŞEME|ÇATI|YALITIM|İZOLASYON|'
    r'Korkuluk|KORKULUK|^\(|^[A-Z]$|^[0-9]+$|^%)', re.I)


def is_room_label(t):
    s = t['s']
    if not IS_NAME.search(s) or parse_area(s) is not None:
        return False
    if NOT_ROOM.search(s.strip()):
        # "İDARE GİRİŞ" etc. are door/entrance annotations, but "GİRİŞ-LOBİ" is a room
        if not re.search(r'LOB[İI]|HOL[ÜU]', s, re.I):
            return False
    return len(s) <= 40


class Plan:
    def __init__(self, key, name, order, title):
        self.key, self.name, self.order, self.title = key, name, order, title
        self.bbox = None
        self.outline = None
        self.rooms = []
        self.doors = []
        self.fixtures = []
        self.columns = []
        self.labels = []
        self.ofs = (0.0, 0.0)


class Arch:
    def __init__(self, dwg: Dwg, unit_per_m=100.0, log=print):
        self.d = dwg
        self.u = unit_per_m
        self.log = log
        self._wcache = None

    # -------------------------------------------------------- wall geometry
    def wall_items(self):
        """all candidate boundary geometry in model space (WCS), with insert expansion."""
        if self._wcache is not None:
            return self._wcache
        items = []
        for (lay, kind, pts, closed) in self.d.geo:
            if EXCL.search(lay) or len(pts) < 2:
                continue
            items.append((lay, pts, closed, bool(DOOR_L.search(lay)) or kind == 'GA'))
        for ins in self.d.inserts:
            if EXCL.search(ins['layer']) or FURN.search(ins['layer']):
                continue
            if ins['name'].startswith('*D') or ins['name'].startswith('*X'):
                continue
            door = bool(DOOR_L.search(ins['layer']) or re.search(r'kap[ıi]|door|seksiyonel', ins['name'], re.I))
            for (lay, kind, pts, closed) in self.d.expand(ins):
                if EXCL.search(lay) or FURN.search(lay) or len(pts) < 2:
                    continue
                items.append((lay, pts, closed, door or bool(DOOR_L.search(lay)) or kind == 'GA'))
        self._wcache = items
        return items

    def lines_in(self, bb, nodoor=False):
        x0, y0, x1, y1 = bb
        out = []
        for (lay, pts, closed, door) in self.wall_items():
            if nodoor and door:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            if max(xs) < x0 or min(xs) > x1 or max(ys) < y0 or min(ys) > y1:
                continue
            if closed and len(pts) > 2:
                pts = list(pts) + [pts[0]]
            # drop degenerate / gigantic (site boundary) items
            if (max(xs) - min(xs)) > 40000 or (max(ys) - min(ys)) > 40000:
                continue
            out.append(LineString(pts))
        return out

    # -------------------------------------------------------------- plans
    def find_plans(self):
        titles = [t for t in self.d.texts if FLOOR_TITLE.search(t['s']) and t['h'] >= 30]
        plans = []
        for t in titles:
            key, name, order = floor_key(FLOOR_TITLE.search(t['s']).group(0))
            plans.append(Plan(key, name, order, t))
        return plans

    def frames(self):
        if getattr(self, '_frames', None) is None:
            rects = []
            for (lay, k, pts, cl) in self.d.geo:
                if k != 'GP' or len(pts) < 4 or len(pts) > 6:
                    continue
                xs = [q[0] for q in pts]
                ys = [q[1] for q in pts]
                w, h = max(xs) - min(xs), max(ys) - min(ys)
                if 3000 < w < 40000 and 3000 < h < 40000:
                    rects.append((min(xs), min(ys), max(xs), max(ys)))
            self._frames = rects
        return self._frames

    def plan_region(self, plan, search=16000):
        tx, ty = plan.title['px'], plan.title['py']
        fr = [r for r in self.frames() if r[0] <= tx <= r[2] and r[1] <= ty <= r[3]]
        if fr:
            r = min(fr, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
            return box(r[0] + 40, r[1] + 40, r[2] - 40, r[3] - 40)
        bb = (tx - search, ty - 2500, tx + search, ty + search)
        lines = self.lines_in(bb)
        if not lines:
            return None
        u = unary_union([ln.buffer(4.0, quad_segs=2) for ln in lines])
        comps = list(u.geoms) if hasattr(u, 'geoms') else [u]
        best = None
        for c in comps:
            minx, miny, maxx, maxy = c.bounds
            w, h = maxx - minx, maxy - miny
            if w < 800 or h < 800:
                continue
            # the title sits under the plan, inside its horizontal extent (right-aligned allowed)
            if not (minx - 1500 <= tx <= maxx + 2500):
                continue
            if miny < ty - 1500 or miny > ty + 4000:
                continue
            score = c.convex_hull.area
            if best is None or score > best[0]:
                best = (score, c)
        if best is None:
            return None
        c = best[1]
        return c

    # --------------------------------------------------------------- rooms
    def extract(self, plan):
        comp = self.plan_region(plan)
        if comp is None:
            self.log(f'  ! plan region not found: {plan.name} @ {plan.title["px"]:.0f},{plan.title["py"]:.0f}')
            return False
        minx, miny, maxx, maxy = comp.bounds
        plan.bbox = (minx, miny, maxx, maxy)
        lines = self.lines_in(plan.bbox)
        from arch_rooms import make_seeds, extract_rooms
        seeds = make_seeds(self, plan, is_room_label, parse_area)
        plan.rooms = extract_rooms(self, plan, lines, seeds, self.lines_in(plan.bbox, nodoor=True))
        return True

    def _old_extract(self, plan, lines, polys):
        holes = []
        for p in polys:
            for ring in p.interiors:
                hp = Polygon(ring)
                if hp.area > 0.3 * self.u * self.u:
                    holes.append(hp)
        tree = STRtree(holes) if holes else None
        # labels inside plan
        T = [t for t in self.d.texts if plan.bbox[0] <= t['cx'] <= plan.bbox[2] and plan.bbox[1] <= t['cy'] <= plan.bbox[3]]
        names = [t for t in T if is_room_label(t) and t['h'] >= 15]
        areas = [t for t in T if parse_area(t['s']) is not None]
        plan.labels = names + areas
        found = {}
        def holder(pt):
            if tree is None:
                return None
            cand = [holes[i] for i in tree.query(pt)]
            cand = [c for c in cand if c.contains(pt)]
            return min(cand, key=lambda c: c.area) if cand else None
        for t in names + areas:
            for (px, py) in ((t['cx'], t['cy']), (t['px'], t['py']), (t['px'], t['py'] + t['h'] * 0.5)):
                hp = holder(Point(px, py))
                if hp is not None:
                    k = id(hp)
                    rec = found.setdefault(k, dict(poly=hp, names=[], areas=[]))
                    if t in names:
                        rec['names'].append(t)
                    else:
                        rec['areas'].append(t)
                    break
        rooms = []
        for rec in found.values():
            hp = rec['poly']
            nm = ' '.join(t['s'] for t in sorted(rec['names'], key=lambda t: (-round(t['py']), t['px'])))
            nm = re.sub(r'\s+', ' ', nm).strip()
            if rec['names']:
                # remove exact duplicates (architect overlays)
                parts = []
                for t in sorted(rec['names'], key=lambda t: (-round(t['py']), t['px'])):
                    if t['s'] not in parts:
                        parts.append(t['s'])
                nm = ' '.join(parts)
            lab = None
            for t in rec['areas']:
                v = parse_area(t['s'])
                if v and ('Net' in t['s'] or lab is None):
                    lab = v
            poly = hp.buffer(2.5, join_style='mitre').simplify(2.0)
            if poly.geom_type != 'Polygon':
                poly = max(poly.geoms, key=lambda g: g.area)
            A = poly.area / (self.u * self.u)
            rooms.append(dict(name=nm, label_area=lab, area=A, poly=poly,
                              label=(rec['names'] or rec['areas'])[0]))
        plan.rooms = rooms
        return True

    # ----------------------------------------------------- doors / fixtures
    def collect_inserts(self, plan):
        bb = plan.bbox
        doors, fixtures = [], []
        for ins in self.d.inserts:
            if not (bb[0] <= ins['x'] <= bb[2] and bb[1] <= ins['y'] <= bb[3]):
                continue
            nm = ins['name']
            if DOOR_L.search(ins['layer']) or re.search(r'kap[ıi]|door|seksiyonel', nm, re.I):
                b = self.d.insert_bbox(ins)
                if b:
                    w = max(b[2] - b[0], b[3] - b[1])
                    doors.append(dict(x=(b[0] + b[2]) / 2, y=(b[1] + b[3]) / 2, w=min(w, 600.0) / self.u, bbox=b, name=nm))
            elif FURN.search(ins['layer']) or re.search(r'klz|klozet|lavabo|pisuvar|eviye|du[sş]|ocak|batarya|wc', nm, re.I):
                b = self.d.insert_bbox(ins)
                if b:
                    fixtures.append(dict(x=(b[0] + b[2]) / 2, y=(b[1] + b[3]) / 2, bbox=b, name=nm, layer=ins['layer'], rot=ins['rot']))
        plan.doors, plan.fixtures = doors, fixtures

    def collect_columns(self, plan):
        bb = plan.bbox
        cols = []
        for (lay, kind, pts, closed) in self.d.geo:
            if not closed or not COL_L.search(lay) or len(pts) < 4:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            if not (bb[0] <= min(xs) and max(xs) <= bb[2] and bb[1] <= min(ys) and max(ys) <= bb[3]):
                continue
            w, h = max(xs) - min(xs), max(ys) - min(ys)
            if 8 <= w <= 120 and 8 <= h <= 120:
                cols.append(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, w, h))
        # dedupe
        out = []
        for c in cols:
            if not any(abs(c[0] - o[0]) < 5 and abs(c[1] - o[1]) < 5 for o in out):
                out.append(c)
        plan.columns = out
