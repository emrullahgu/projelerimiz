"""CLD engine - building model built from the architectural extraction.

Chooses the best sheet copy, registers floors to each other, classifies rooms,
assigns heights and collects doors / sanitary fixtures / columns per floor.
Everything stays in the drawing's plan coordinates (cm) of the chosen copy.
"""
import re
import math
from collections import Counter, defaultdict

from shapely.geometry import Polygon, Point, box
from shapely.ops import unary_union
from shapely import affinity

from dwgdata import Dwg
from arch import Arch, room_type, FLOOR_TITLE

FIX_MAP = [
    (r'klozet|klz|tefriş_klozet|wc_pan|toilet', 'KLOZET'),
    (r'pisuvar|urinal', 'PISUVAR'),
    (r'afdf435334ggs|lvb|lavabo|washbasin|lavatorio', 'LAVABO'),
    (r'dus|duş|shower', 'DUS'),
    (r'K_200|tezgah|eviye|sink', 'EVIYE'),
]


def fixture_type(name):
    for pat, t in FIX_MAP:
        if re.search(pat, name, re.I):
            return t
    return None


class Room:
    def __init__(self, rid, floor, name, tip, poly, area, label_area, fit, h):
        self.id, self.floor, self.name, self.tip = rid, floor, name, tip
        self.poly, self.area, self.label_area, self.fit, self.h = poly, area, label_area, fit, h
        self.galeri = False
        self.above = None

    @property
    def A(self):
        return self.label_area if (self.label_area and self.fit in ('YAKLASIK', 'SAPMA', 'BOLUNMUS')) else self.area

    def __repr__(self):
        return f'<{self.id} {self.floor} {self.name} {self.tip} {self.A:.1f}m2 h={self.h}>'


class Floor:
    def __init__(self, key, name, order, plan, kot, h):
        self.key, self.name, self.order, self.plan, self.kot, self.h = key, name, order, plan, kot, h
        self.rooms = []
        self.outline = plan.outline if plan else None
        if self.outline is not None:
            # morphological opening removes door-swing bulges (< 2.4 m) from the envelope
            op = self.outline.buffer(-220, join_style='mitre').buffer(220, join_style='mitre')
            if op.geom_type != 'Polygon' and not op.is_empty:
                op = max(op.geoms, key=lambda g: g.area)
            if not op.is_empty and op.area > 0.9 * self.outline.area:
                self.outline = op.simplify(5.0)
        self.doors = plan.doors if plan else []
        self.fixtures = []
        self.columns = plan.columns if plan else []
        self.ofs = (0.0, 0.0)   # this plan = ZK plan + ofs

    def to_zk(self, p):
        return (p[0] - self.ofs[0], p[1] - self.ofs[1])

    def from_zk(self, p):
        return (p[0] + self.ofs[0], p[1] + self.ofs[1])


class Building:
    def __init__(self, parcel, dump_path, log=print):
        self.parcel = parcel
        self.log = log
        self.d = Dwg(dump_path)
        self.A = Arch(self.d, log=log)
        self.u = 100.0
        self.info = {}
        self.floors = []
        self.build()

    # ------------------------------------------------------------------
    def build(self):
        A = self.A
        plans = A.find_plans()
        for pl in plans:
            if A.extract(pl):
                A.collect_inserts(pl)
                A.collect_columns(pl)
        # group plans into sheet copies by title y
        ys = sorted(set(round(p.title['py'] / 1000) for p in plans))
        copies = defaultdict(list)
        for p in plans:
            copies[round(p.title['py'] / 1000)].append(p)
        def score(ps):
            s = 0
            for p in ps:
                for r in p.rooms:
                    s += {'OK': 1.0, 'BOLUNMUS': 0.8, 'SAPMA': 0.5}.get(r['fit'], 0.2)
            return s
        best = max(copies.items(), key=lambda kv: (round(score(kv[1]), 1), kv[0]))
        self.copy_y = best[0] * 1000
        self.plans = {p.key: p for p in best[1] if p.bbox}
        self.log(f'P{self.parcel}: sheet copies {[(k, round(score(v), 1)) for k, v in copies.items()]} -> y~{self.copy_y}')
        self.levels()
        self.make_floors()
        self.register()
        self.make_rooms()
        self.galeri()
        self.project_info()

    def levels(self):
        d, A = self.d, self.A
        fr = A.frames()
        kots = Counter()
        for t in d.texts:
            if re.search(r'KES[İI]T[İI]|GÖRÜNÜŞ', t['s']) and t['h'] >= 30:
                F = [r for r in fr if r[0] <= t['px'] <= r[2] and r[1] <= t['py'] <= r[3]]
                if not F:
                    continue
                r = min(F, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
                for u in d.texts:
                    if r[0] <= u['px'] <= r[2] and r[1] <= u['py'] <= r[3]:
                        m = re.match(r'^\s*[+±]?\s*([0-9]{1,2}[.,][0-9]{2})\s*$', u['s'])
                        if m:
                            kots[float(m.group(1).replace(',', '.'))] += 1
        top = max([k for k in kots if 4.0 <= k <= 20.0], default=9.5)
        self.h_top = top                      # ridge / top of building (m)
        self.h_eave = round(max(5.0, top - 1.2), 2)   # hall clear height under trusses (approx.)
        # first floor level from 1K plan kot texts
        k1 = 3.50
        p1 = None
        for p in A.find_plans():
            if p.key == '1K':
                p1 = p
        self.kot_1k = k1
        if '1K' in getattr(self, 'plans', {}):
            bb = self.plans['1K'].bbox
            c = Counter()
            for t in d.texts:
                if bb[0] <= t['px'] <= bb[2] and bb[1] <= t['py'] <= bb[3]:
                    m = re.match(r'^\s*\+\s*([0-9]{1,2}[.,][0-9]{2})\s*$', t['s'])
                    if m:
                        v = float(m.group(1).replace(',', '.'))
                        if 2.0 <= v <= 8.0:
                            c[v] += 1
            if c:
                self.kot_1k = c.most_common(1)[0][0]

    def make_floors(self):
        fl = []
        if 'ZK' in self.plans:
            fl.append(Floor('ZK', 'ZEMİN KAT', 0, self.plans['ZK'], 0.0, self.kot_1k))
        for k, p in sorted(self.plans.items(), key=lambda kv: kv[1].order):
            if k in ('ZK', 'CT'):
                continue
            kot = self.kot_1k if k == '1K' else self.kot_1k * p.order
            fl.append(Floor(k, p.name, p.order, p, kot, max(3.0, self.h_top - kot - 1.0)))
        self.floors = fl
        self.roof = self.plans.get('CT')

    def floor(self, key):
        for f in self.floors:
            if f.key == key:
                return f
        return None

    def register(self):
        zk = self.floor('ZK')
        if zk is None:
            return
        zc = zk.outline.centroid
        for f in self.floors:
            if f.key == 'ZK':
                continue
            c = f.outline.centroid
            dx, dy = c.x - zc.x, c.y - zc.y
            # refine with columns (nearest neighbour median)
            if zk.columns and f.columns:
                ds = []
                for (x, y, w, h) in f.columns:
                    best = min(zk.columns, key=lambda q: (q[0] + dx - x) ** 2 + (q[1] + dy - y) ** 2)
                    ex, ey = x - best[0] - dx, y - best[1] - dy
                    if ex * ex + ey * ey < 150 ** 2:
                        ds.append((ex, ey))
                if len(ds) >= 4:
                    ds.sort()
                    dx += sorted(e[0] for e in ds)[len(ds) // 2]
                    dy += sorted(e[1] for e in ds)[len(ds) // 2]
            f.ofs = (dx, dy)
        # roof: align the CT plan geometry cluster centre with the ZK outline centre
        self.roof_ofs = None
        if self.roof is not None and self.roof.bbox:
            lines = self.A.lines_in(self.roof.bbox)
            allg = []
            for (lay, kind, pts, closed) in self.d.geo:
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                bb = self.roof.bbox
                if min(xs) >= bb[0] and max(xs) <= bb[2] and min(ys) >= bb[1] and max(ys) <= bb[3] and \
                        re.search(r'oluk|OLUK|ASIK|AŞIK|duvar|dograma|S-COLS|PARSEL|ÇATI|CATI|^0$', lay):
                    allg.append(box(min(xs), min(ys), max(xs) + 0.01, max(ys) + 0.01))
            if allg:
                u = unary_union([g.buffer(60) for g in allg])
                comp = max(list(u.geoms) if hasattr(u, 'geoms') else [u], key=lambda g: g.area)
                bx = comp.bounds
                zb = zk.outline.bounds
                self.roof_ofs = ((bx[0] + bx[2]) / 2 - (zb[0] + zb[2]) / 2, (bx[1] + bx[3]) / 2 - (zb[1] + zb[3]) / 2)
            ax = self.axis_offset(self.plans['ZK'], self.roof)
            if ax is not None:
                self.roof_ofs = ax
        # 1K: confirm with axis lines as well
        for f in self.floors:
            if f.key != 'ZK':
                ax = self.axis_offset(self.plans['ZK'], f.plan)
                if ax is not None and math.hypot(ax[0] - f.ofs[0], ax[1] - f.ofs[1]) > 30:
                    self.log(f'  {f.key}: axis registration {ax} replaces {f.ofs}')
                    f.ofs = ax

    def axis_lines(self, plan):
        bb = plan.bbox
        vx, hy = [], []
        for (lay, kind, pts, closed) in self.d.geo:
            if kind != 'GL' or len(pts) != 2:
                continue
            (x1, y1), (x2, y2) = pts
            if not (bb[0] <= x1 <= bb[2] and bb[0] <= x2 <= bb[2] and bb[1] <= y1 <= bb[3] and bb[1] <= y2 <= bb[3]):
                continue
            if re.search(r'aks|AKS|GRID', lay) is None:
                continue
            if abs(x1 - x2) < 1 and abs(y1 - y2) > 2500:
                vx.append(x1)
            elif abs(y1 - y2) < 1 and abs(x1 - x2) > 2500:
                hy.append(y1)
        return sorted(set(round(v, 1) for v in vx)), sorted(set(round(v, 1) for v in hy))

    def axis_offset(self, ref, other):
        """offset other-ref from matching axis line sets (vertical -> dx, horizontal -> dy)."""
        if other is None or not other.bbox:
            return None
        rx, ry = self.axis_lines(ref)
        ox, oy = self.axis_lines(other)

        def best(a, b):
            if len(a) < 2 or len(b) < 2:
                return None
            cands = {}
            for u in a:
                for v in b:
                    d = round(v - u)
                    cands[d] = cands.get(d, 0) + 1
            top = sorted(cands.items(), key=lambda kv: -kv[1])[:40]
            res = None
            for d, _ in top:
                n = sum(1 for u in a if any(abs(v - u - d) < 8 for v in b))
                if res is None or n > res[1]:
                    res = (d, n)
            return res
        bx_, by_ = best(rx, ox), best(ry, oy)
        if not bx_ or not by_ or bx_[1] < 2 or by_[1] < 2:
            return None
        return (float(bx_[0]), float(by_[0]))

    def clean_poly(self, r, A, f):
        """repair degenerate room polygons (slivers / wrong faces): a room's polygon must be
        compact (perimeter <= 1.6 x its minimum rectangle) and close to the labelled area."""
        poly = r['poly'].buffer(0)
        if poly.geom_type != 'Polygon':
            poly = max(poly.geoms, key=lambda g: g.area)
        u2 = 1e4
        mrr = poly.minimum_rotated_rectangle
        bad = poly.length > 1.6 * mrr.length or (r['label_area'] and poly.area / u2 > 1.35 * r['label_area'])
        if not bad:
            return poly
        hull = poly.convex_hull
        if hull.area / u2 <= 1.3 * A and hull.length <= 1.25 * hull.minimum_rotated_rectangle.length:
            return hull
        sx, sy = r.get('seed') or (poly.representative_point().x, poly.representative_point().y)
        a = math.sqrt(A) * 100.0 / 2
        bx = box(sx - a, sy - a, sx + a, sy + a)
        cl = bx.intersection(f.outline) if f.outline is not None else bx
        if cl.geom_type != 'Polygon' or cl.area < 0.5 * bx.area:
            cl = bx
        self.log(f'  room {r["name"]}: degenerate polygon (P={poly.length / 100:.0f} m) replaced by {"label box"}')
        return cl

    def make_rooms(self):
        n = 0
        for f in self.floors:
            for r in f.plan.rooms:
                nm = r['name'].strip()
                if not nm and r['fit'] == 'YAKLASIK':
                    continue          # orphan area label (e.g. "net alan" of a neighbour) - not a room
                nm = nm or 'MAHAL'
                if nm.upper() in ('ODASI', 'HOLÜ'):
                    nm = 'TEKNİK ODA' if nm.upper() == 'ODASI' else 'HOL'
                A = r['label_area'] if (r['label_area'] and r['fit'] in ('YAKLASIK', 'SAPMA', 'BOLUNMUS')) else r['area']
                tip = room_type(nm, A)
                if f.key == 'ZK' and tip in ('URETIM', 'DEPOH'):
                    h = self.h_eave
                else:
                    h = 2.80 if tip in ('OFIS', 'TOPLANTI', 'GIRIS', 'MESCIT', 'YEMEK') else 2.70
                n += 1
                poly = self.clean_poly(r, A, f)
                rm = Room(f'M{n:03d}', f.key, nm, tip, poly, poly.area / 1e4, r['label_area'], r['fit'], h)
                f.rooms.append(rm)
            # fixtures of this floor assigned to rooms
            for fx in f.plan.fixtures:
                t = fixture_type(fx['name'])
                if not t:
                    continue
                pt = Point(fx['x'], fx['y'])
                rm = next((r for r in f.rooms if r.poly.buffer(30).contains(pt)), None)
                f.fixtures.append(dict(tip=t, x=fx['x'], y=fx['y'], rot=fx['rot'], room=rm.id if rm else None,
                                       w=fx['bbox'][2] - fx['bbox'][0], h=fx['bbox'][3] - fx['bbox'][1]))

    def galeri(self):
        """1K rooms that are the ZK halls seen from above (double height) are voids."""
        zk = self.floor('ZK')
        for f in self.floors:
            if f.key == 'ZK' or zk is None:
                continue
            keep = []
            for r in f.rooms:
                shifted = affinity.translate(r.poly, -f.ofs[0], -f.ofs[1])
                dup = None
                for z in zk.rooms:
                    if z.tip in ('URETIM', 'DEPOH') and r.tip in ('URETIM', 'DEPOH'):
                        inter = shifted.intersection(z.poly).area
                        if inter > 0.4 * min(shifted.area, z.poly.area):
                            dup = z
                            break
                if dup is not None or r.tip in ('URETIM', 'DEPOH'):
                    r.galeri = True
                    if dup is not None:
                        dup.above = 'GALERI'
                    continue
                keep.append(r)
            f.rooms = keep
        # ZK rooms under a 1K room -> normal storey height; others keep their height
        for f in self.floors:
            if f.key == 'ZK':
                continue
            for z in zk.rooms:
                if z.tip in ('URETIM', 'DEPOH'):
                    continue
                for r in f.rooms:
                    shifted = affinity.translate(r.poly, -f.ofs[0], -f.ofs[1])
                    if shifted.intersection(z.poly).area > 0.3 * z.poly.area:
                        z.above = r.id
                        break

    def project_info(self):
        d = self.d
        info = {'parcel': self.parcel}
        for t in d.texts:
            s = t['s']
            m = re.search(r'İLİ\s*:\s*([A-ZÇĞİÖŞÜ]+)', s)
            if m:
                info['il'] = m.group(1)
            m = re.search(r'İLÇESİ\s*:\s*([A-ZÇĞİÖŞÜ]+)', s)
            if m:
                info['ilce'] = m.group(1)
            m = re.search(r'MAH\s*:\s*(.+)', s)
            if m:
                info['mahalle'] = m.group(1).strip()
            m = re.search(r'PARSEL ALANI\s*:\s*([0-9.,]+)', s)
            if m:
                info['parsel_alani'] = m.group(1)
            m = re.search(r'en fazla\s*([0-9]+)\s*kişi', s)
            if m:
                info['kisi'] = int(m.group(1))
            if 'ANONİM ŞİRKETİ' in s and 'BROSCO' in s:
                info['isveren'] = s.strip()
            m = re.search(r'TOPLAM YAPI ALANI\s*:.*=\s*([0-9.,]+)\s*m', s)
            if m:
                info['yapi_alani'] = m.group(1)
        info.setdefault('il', 'İZMİR')
        info.setdefault('ilce', 'KEMALPAŞA')
        info.setdefault('isveren', 'BROSCO İTHALAT İHRACAT VE TİCARET A.Ş.')
        self.info = info

    # ------------------------------------------------------------------
    def summary(self):
        out = [f'P{self.parcel} copy_y={self.copy_y} h_top={self.h_top} h_eave={self.h_eave} kot_1k={self.kot_1k} '
               f'roof_ofs={self.roof_ofs} info={self.info}']
        for f in self.floors:
            out.append(f'  {f.key} {f.name} kot={f.kot} ofs=({f.ofs[0]:.0f},{f.ofs[1]:.0f}) outline={f.outline.area/1e4:.0f}m2 '
                       f'rooms={len(f.rooms)} doors={len(f.doors)} fix={len(f.fixtures)} cols={len(f.columns)}')
            for r in f.rooms:
                out.append(f'     {r.id} {r.name[:24]:24s} {r.tip:9s} A={r.A:8.2f} fit={r.fit:9s} h={r.h} above={r.above}')
            c = Counter(x['tip'] for x in f.fixtures)
            out.append(f'     fixtures: {dict(c)}')
        return '\n'.join(out)
