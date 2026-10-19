"""CLD engine - plumbing (sıhhi tesisat) design.

TS EN 806-3 (loading units, simplified pipe sizing), DIN 1988-300 peak flow,
TS EN 12056-2 (system I, K=0.5 -> 0.7 for industrial washrooms), TS EN 12056-3
roof drainage (r = 0.030 l/s.m2 for İzmir, C = 1.0), fire cabinet water per
Binaların Yangından Korunması Hakkında Yönetmelik (2 cabinets x 100 l/min, 60 min).
"""
import math
import re
from dataclasses import dataclass
from shapely.geometry import Polygon, Point, LineString
from shapely.ops import unary_union

import geo
from geo import m, U
from elec import pick

FIX = {
    #         LU   DU   hot  dia  label
    'KLOZET':  (1, 2.0, False, 100, 'Klozet (6 L rezervuar)'),
    'LAVABO':  (1, 0.5, True, 50, 'Lavabo'),
    'PISUVAR': (1, 0.5, False, 50, 'Pisuvar'),
    'ABDEST':  (2, 0.6, True, 50, 'Abdest musluğu (ayak yıkama)'),
    'EVIYE':   (2, 0.8, True, 50, 'Eviye'),
    'DUS':     (2, 0.6, True, 50, 'Duş'),
    'YS':      (0, 0.8, False, 50, 'Yer süzgeci'),
    'BULASIK': (2, 0.8, False, 50, 'Bulaşık makinesi'),
}
WET = ('WC', 'ABDEST', 'BANYO', 'SOYUNMA', 'MUTFAK')


@dataclass
class Fx:
    x: float
    y: float
    tip: str
    room: str
    floor: str
    gen: bool = False


# PPR-C PN20 pipes: (outer diameter mm, inner diameter mm)
PPR = [(20, 13.2), (25, 16.6), (32, 21.2), (40, 26.6), (50, 33.4), (63, 42.0), (75, 50.0), (90, 60.0)]


def pipe_for_flow(q_ls, vmax=2.0):
    for od, di in PPR:
        v = q_ls / 1000.0 / (math.pi * (di / 1000.0) ** 2 / 4)
        if v <= vmax:
            return od
    return PPR[-1][0]


def su_cap(LU):
    """pipe from the loading units: design flow (DIN 1988-300) at v <= 2 m/s in PPR-C PN20."""
    return pipe_for_flow(max(0.15, peak_flow(LU)))


def manning_pipe(q_ls, slope=0.01, n=0.009):
    """smallest PVC gravity pipe (full bore, Manning) carrying q at the slope."""
    for d in (110, 125, 160, 200, 250, 315, 400, 500):
        di = d * 0.94 / 1000.0
        A = math.pi * di * di / 4
        R = di / 4
        Q = A * (R ** (2 / 3)) * (slope ** 0.5) / n * 1000.0
        if Q >= q_ls:
            return d, Q
    return 500, Q


def peak_flow(LU):
    v = 0.1 * LU
    if v <= 0:
        return 0.0
    if v < 0.2:
        return v
    return max(0.2, 1.48 * v ** 0.19 - 0.94)


class PlumbDesign:
    def __init__(self, b, elec=None):
        self.b = b
        self.fx = []
        self.stacks = []      # dict(code, x, y, floors, kind)
        self.lines = []       # (floor, kind CW/HW/DR/RW/SW, pts, dia)
        self.rogars = []
        self.downpipes = []
        self.tank = None
        self.sum = {}
        self.run()

    def run(self):
        b = self.b
        # ---------------------------------------------------------- fixtures
        for f in b.floors:
            got = {}
            for x in f.fixtures:
                if x['tip'] in FIX and x['room']:
                    rm = next((r for r in f.rooms if r.id == x['room']), None)
                    if rm and rm.tip in WET:
                        self.fx.append(Fx(x['x'], x['y'], x['tip'], rm.id, f.key))
                        got.setdefault(rm.id, set()).add(x['tip'])
            for r in f.rooms:
                if r.tip not in WET:
                    continue
                want = {'WC': ['KLOZET', 'LAVABO'], 'ABDEST': ['ABDEST', 'ABDEST'], 'BANYO': ['DUS', 'LAVABO'],
                        'SOYUNMA': ['DUS', 'LAVABO'], 'MUTFAK': ['EVIYE', 'BULASIK']}[r.tip]
                have = got.get(r.id, set())
                if r.tip == 'WC' and r.A < 1.2:
                    want = ['KLOZET']
                missing = [w for w in want if w not in have] if r.tip != 'ABDEST' else want
                av = [(d['x'], d['y']) for d in f.doors]
                for t, (x, y, a) in zip(missing, geo.perimeter_points(r.poly, len(missing), m(0.30), av, m(0.7))):
                    self.fx.append(Fx(x, y, t, r.id, f.key, True))
                c = r.poly.representative_point()
                self.fx.append(Fx(c.x, c.y, 'YS', r.id, f.key, True))
        # ------------------------------------------------- stacks (clusters)
        zk = b.floor('ZK')
        wet_pts = []
        for f in b.floors:
            for r in f.rooms:
                if r.tip in WET:
                    c = r.poly.centroid
                    p = f.to_zk((c.x, c.y))
                    wet_pts.append((p, f.key, r))
        clusters = []
        for p, fk, r in wet_pts:
            for cl in clusters:
                if math.hypot(cl['x'] - p[0], cl['y'] - p[1]) < m(7.0):
                    cl['items'].append((p, fk, r))
                    n = len(cl['items'])
                    cl['x'] = (cl['x'] * (n - 1) + p[0]) / n
                    cl['y'] = (cl['y'] * (n - 1) + p[1]) / n
                    break
            else:
                clusters.append(dict(x=p[0], y=p[1], items=[(p, fk, r)]))
        for i, cl in enumerate(clusters):
            # stack at the wet room corner nearest the cluster centre (ZK reference)
            zrooms = [r for (p, fk, r) in cl['items'] if fk == 'ZK'] or [r for (p, fk, r) in cl['items']]
            r0 = min(zrooms, key=lambda r: r.poly.centroid.distance(Point(cl['x'], cl['y'])))
            f0 = b.floor(r0.floor)
            tgt = f0.from_zk((cl['x'], cl['y']))
            x, y, a = geo.wall_point(r0.poly, tgt, m(0.15))
            sx, sy = f0.to_zk((x, y))
            floors = sorted(set(fk for (p, fk, r) in cl['items']), key=lambda k: b.floor(k).kot)
            self.stacks.append(dict(code=f'PK-{i + 1}', x=sx, y=sy, floors=floors, items=cl['items']))
        # ------------------------------------------------ branch pipes / units
        tot_LU = 0
        tot_DU = 0.0
        self.room_rows = []
        self.heaters = []
        for st in self.stacks:
            st_LU = 0
            st_DU = 0.0
            for fk in st['floors']:
                f = b.floor(fk)
                sp = f.from_zk((st['x'], st['y']))
                for p, k, r in st['items']:
                    if k != fk:
                        continue
                    fxs = [x for x in self.fx if x.room == r.id]
                    LU = sum(FIX[x.tip][0] for x in fxs)
                    DU = sum(FIX[x.tip][1] for x in fxs)
                    st_LU += LU
                    st_DU += DU
                    self.room_rows.append(dict(room=r, fxs=fxs, LU=LU, DU=DU, stack=st['code']))
                    for x in fxs:
                        dia = FIX[x.tip][3]
                        self.lines.append((fk, 'DR', geo.ortho((x.x, x.y), sp), dia))
                        if FIX[x.tip][0] > 0:
                            self.lines.append((fk, 'CW', geo.ortho((sp[0] + m(0.25), sp[1]), (x.x + m(0.1), x.y + m(0.1))), 20))
                    # hot water: local electric heater in the room (instant heater / 80 l termosifon), short HW branches
                    hot = [x for x in fxs if FIX[x.tip][2]]
                    if hot:
                        hx, hy, ha = geo.wall_point(r.poly, (hot[0].x, hot[0].y), m(0.15))
                        kind_h = 'TS 80 l' if r.tip in ('MUTFAK', 'BANYO', 'SOYUNMA') else 'ASI 3,5 kW'
                        self.heaters.append(dict(x=hx, y=hy, ang=ha, floor=fk, room=r.id, kind=kind_h))
                        self.lines.append((fk, 'CW', geo.ortho((sp[0] + m(0.25), sp[1]), (hx, hy)), 20))
                        for x in hot:
                            self.lines.append((fk, 'HW', geo.ortho((hx, hy), (x.x + m(0.2), x.y + m(0.2))), 20))
            fx_st = [x for (p, k, r) in st['items'] for x in self.fx if x.room == r.id]
            maxdu = max([FIX[x.tip][1] for x in fx_st] or [0.0])
            Q = max(0.7 * math.sqrt(st_DU), maxdu) if st_DU > 0 else 0.0
            wc = any(x.tip == 'KLOZET' for x in fx_st)
            hot_LU = sum(FIX[x.tip][0] for x in fx_st if FIX[x.tip][2])
            st.update(LU=st_LU, DU=st_DU, Q=Q, dia=100 if (wc or Q > 1.5) else 70, cw=su_cap(st_LU), qd=peak_flow(st_LU),
                      hw=0, hot_LU=hot_LU, n_heat=sum(1 for h in self.heaters if any(h['room'] == r.id for (p_, k_, r) in st['items'])))
            tot_LU += st_LU
            tot_DU += st_DU
        # -------------------------------------------- outside: rogars, mains
        ol = zk.outline
        cen = ol.centroid
        out_ring = ol.buffer(m(2.0)).exterior
        for st in self.stacks:
            q = ol.exterior.interpolate(ol.exterior.project(Point(st['x'], st['y'])))
            vx, vy = q.x - cen.x, q.y - cen.y
            L = math.hypot(vx, vy) or 1
            rx, ry = q.x + vx / L * m(2.0), q.y + vy / L * m(2.0)
            rr = out_ring.interpolate(out_ring.project(Point(rx, ry)))
            self.rogars.append(dict(code=f'R{len(self.rogars) + 1}', x=rr.x, y=rr.y, stack=st['code']))
            self.lines.append(('ZK', 'DR', [(st['x'], st['y']), (q.x, q.y), (rr.x, rr.y)], 100 if st['dia'] <= 100 else st['dia']))
        # connection rogar (OSB sewer) beside the first rogar
        if self.rogars:
            r0 = self.rogars[0]
            self.osb = (r0['x'], r0['y'])
            for r in self.rogars[1:]:
                self.lines.append(('ZK', 'SW', geo.ring_route(ol.buffer(m(2.0)), (r['x'], r['y']), (r0['x'], r0['y'])), 150))
        # water entry (meter) near the office core and main to each stack
        core = [r for r in zk.rooms if r.tip in ('GIRIS', 'HOL')] or zk.rooms
        hub = min(core, key=lambda r: r.poly.distance(ol.exterior)) if core else None
        hp = hub.poly.centroid if hub else cen
        q = ol.exterior.interpolate(ol.exterior.project(hp))
        vx, vy = q.x - cen.x, q.y - cen.y
        L = math.hypot(vx, vy) or 1
        self.meter = (q.x + vx / L * m(2.5), q.y + vy / L * m(2.5))
        self.entry = (q.x, q.y)
        for st in self.stacks:
            self.lines.append(('ZK', 'CW', [self.meter, self.entry] + geo.ortho(self.entry, (st['x'] + m(0.25), st['y']))[1:], st['cw']))
        # -------------------------------------------------- rain water
        A_roof = ol.area / (U * U)
        r_int = 0.030
        cap = 4.5
        ang = geo.long_angle(ol)
        ux, uy = math.cos(ang), math.sin(ang)
        vx_, vy_ = -uy, ux
        ring = ol.exterior
        cs = [px * vx_ + py * vy_ for (px, py) in ring.coords]
        cmin, cmax = min(cs), max(cs)
        BIG = m(1000.0)

        def band(c0, c1):
            # polygon of the strip c0 <= p.v <= c1
            ox, oy = (sum(q[0] for q in ring.coords) / len(ring.coords), sum(q[1] for q in ring.coords) / len(ring.coords))
            t0 = ox * ux + oy * uy
            pts_ = [(c * vx_ + t * ux, c * vy_ + t * uy) for c, t in ((c0, t0 - BIG), (c1, t0 - BIG), (c1, t0 + BIG), (c0, t0 + BIG))]
            return Polygon(pts_)

        def gline(c):
            ox, oy = ol.centroid.x, ol.centroid.y
            t0 = ox * ux + oy * uy
            ln = LineString([(c * vx_ + (t0 - BIG) * ux, c * vy_ + (t0 - BIG) * uy), (c * vx_ + (t0 + BIG) * ux, c * vy_ + (t0 + BIG) * uy)])
            g = ln.intersection(ol)
            segs = [q for q in (g.geoms if hasattr(g, 'geoms') else [g]) if q.geom_type == 'LineString' and q.length > m(1.0)]
            return max(segs, key=lambda q: q.length) if segs else None
        rox, roy = (b.roof_ofs if (b.roof is not None and b.roof_ofs is not None) else (0.0, 0.0))
        gut_c, ridge_c = [], []
        if b.roof is not None and b.roof.bbox and b.roof_ofs is not None:
            rb = b.roof.bbox
            for t in b.d.texts:
                if not (rb[0] <= t['px'] <= rb[2] and rb[1] <= t['py'] <= rb[3]):
                    continue
                x_, y_ = t['px'] - rox, t['py'] - roy
                c = x_ * vx_ + y_ * vy_
                if re.search(r'OLU[ĞG]U', t['s']):
                    if not any(abs(c - q) < m(1.5) for q in gut_c):
                        gut_c.append(c)
                elif re.match(r'^\s*\+\s*\d+[.,]\d+\s*$', t['s']):
                    if not any(abs(c - q) < m(1.5) for q in ridge_c):
                        ridge_c.append(c)
        text_gutters = bool(gut_c)
        for c_e in (cmin, cmax):
            if not any(abs(c_e - q) < m(4.0) for q in gut_c):
                gut_c.append(c_e)
        gut_c = sorted(min(max(c, cmin), cmax) for c in gut_c)
        self.gutters = []
        for i, c in enumerate(gut_c):
            lo = gut_c[i - 1] if i else None
            hi = gut_c[i + 1] if i + 1 < len(gut_c) else None

            def split(a_, b_):
                rr = [q for q in ridge_c if min(a_, b_) < q < max(a_, b_)]
                return rr[0] if rr else (a_ + b_) / 2
            c0 = split(lo, c) if lo is not None else cmin - m(1.0)
            c1 = split(c, hi) if hi is not None else cmax + m(1.0)
            A_g = band(c0, c1).intersection(ol).area / (U * U)
            eave = abs(c - cmin) < m(4.0) or abs(c - cmax) < m(4.0)
            C = 1.0 if eave else 1.5
            Q = C * r_int * A_g
            n_g = max(2, math.ceil(Q / cap))
            sgn = 1.0 if abs(c - cmin) < m(4.0) else (-1.0 if abs(c - cmax) < m(4.0) else 0.0)
            gl = gline(c + sgn * m(0.3))
            k_ = 1
            while sgn and (gl is None or gl.length < m(5.0)) and k_ <= 12:
                # extreme is only a corner: walk inward until the eave edge is long enough
                gl2 = gline(c + sgn * m(0.3 + 0.5 * k_))
                if gl2 is not None and (gl is None or gl2.length > gl.length):
                    gl = gl2
                k_ += 1
            self.gutters.append(dict(code=f'O{i + 1}', c=c, kind='Saçak oluğu' if eave else 'İç dere (orta oluk)', A=A_g, C=C, Q=Q,
                                     n=n_g, line=gl, eave=eave))
        if not text_gutters:
            # roof plan has no gutter labels: eaves = outline edges within 30 deg of the long axis, even spacing
            Qr = A_roof * r_int
            n = max(4, math.ceil(Qr / cap))
            n += n % 2
            coords = list(ring.coords)
            eaves = [LineString([a_, c_]) for a_, c_ in zip(coords[:-1], coords[1:])
                     if abs((math.degrees(math.atan2(c_[1] - a_[1], c_[0] - a_[0]) - ang) + 90) % 180 - 90) < 30
                     and math.hypot(c_[0] - a_[0], c_[1] - a_[1]) > m(4)] or [LineString(coords)]
            pts = []
            for _ in range(400):
                if len(pts) >= n:
                    break
                best = None
                for e in eaves:
                    ts = sorted([e.project(Point(p_)) for p_ in pts if e.distance(Point(p_)) < m(0.5)] + [0.0, e.length])
                    for t0, t1 in zip(ts[:-1], ts[1:]):
                        if best is None or t1 - t0 > best[0]:
                            best = (t1 - t0, e, (t0 + t1) / 2)
                if best is None or best[0] < m(2):
                    break
                q_ = best[1].interpolate(best[2])
                pts.append((q_.x, q_.y))
            self.gutters = [dict(code='O1', kind='Saçak olukları (tüm saçaklar)', A=A_roof, C=1.0, Q=Qr, n=n, line=None,
                                 eave=True, pts=list(pts))]
        Qr = sum(g['Q'] for g in self.gutters) if self.gutters else A_roof * r_int
        n = sum(g['n'] for g in self.gutters) if self.gutters else max(4, math.ceil(Qr / cap))
        pts = [] if text_gutters else pts
        for g in (self.gutters if text_gutters else []):
            gl = g['line']
            if gl is None:
                continue
            k = g['n']
            for j in range(k):
                q = gl.interpolate(gl.length * (j + 0.5) / k)
                pts.append((q.x, q.y))
                g.setdefault('pts', []).append((q.x, q.y))
        self.n_req = n
        self.downpipes = [dict(code=f'YK-{i + 1}', x=p[0], y=p[1]) for i, p in enumerate(pts)]
        rring = ol.buffer(m(1.5))
        if rring.geom_type != 'Polygon':
            rring = max(rring.geoms, key=lambda g: g.area)
        self.rain_ring = list(rring.exterior.coords)
        far = max(rring.exterior.coords, key=lambda p: math.hypot(p[0] - self.meter[0], p[1] - self.meter[1]))
        vx, vy = far[0] - cen.x, far[1] - cen.y
        L = math.hypot(vx, vy) or 1
        self.tank = (far[0] + vx / L * m(4.0), far[1] + vy / L * m(4.0))
        for d in self.downpipes:
            q = rring.exterior.interpolate(rring.exterior.project(Point(d['x'], d['y'])))
            # internal (valley) downpipes: under-slab drain to the collector, along the gutter axis direction
            self.lines.append(('ZK', 'RW', geo.ortho((d['x'], d['y']), (q.x, q.y)) if ol.contains(Point(d['x'], d['y'])) and
                               ol.exterior.distance(Point(d['x'], d['y'])) > m(1.0) else [(d['x'], d['y']), (q.x, q.y)], 100))
        # collector ring and tank inlet sized by Manning at 1 % (half of the roof flow per ring branch)
        self.ring_dia, qring = manning_pipe(Qr / 2.0)
        self.inlet_dia, qin = manning_pipe(Qr)
        self.lines.append(('ZK', 'RW', [far, self.tank], self.inlet_dia))
        # overflow of the tank to the OSB storm-water network
        self.overflow = (self.tank[0] + vx / L * m(4.0), self.tank[1] + vy / L * m(4.0))
        self.lines.append(('ZK', 'RW', [self.tank, self.overflow], self.inlet_dia))
        # ------------------------------------------------- fire hose cabinets (BYKHY, TS EN 671-1)
        self.fire_cab()
        # ------------------------------------------------- water demand
        pers = b.info.get('kisi', 30)
        daily = pers * 60.0 / 1000.0 + 0.5           # m3/day, industrial workers (no showers) + cleaning
        tank_dom = pick(daily * 1.5, [1, 2, 3, 5, 7.5, 10, 15, 20])
        fire_q = 2 * 100.0 * 60 / 1000.0             # 12 m3 (2 cabinets simultaneously x 100 l/min x 60 min)
        fire_tank = pick(fire_q * 1.1, [10, 15, 20, 25, 30, 40, 50])
        rain_tank = pick(A_roof * 0.02, [10, 15, 20, 25, 30, 40, 50, 60, 80, 100])   # 20 l/m2 retention (KOSBİ)
        qd = peak_flow(tot_LU)
        H = 25.0 + b.kot_1k + 5.0
        hyd_kw = 1000 * 9.81 * qd / 1000 * H / 0.5 / 1000
        hyd = pick(hyd_kw * 1.3, [0.37, 0.55, 0.75, 1.1, 1.5, 2.2, 3.0, 4.0])
        fire_kw = pick(1000 * 9.81 * (12.0 / 3600) * 60 / 0.55 / 1000 * 1.2, [3.0, 4.0, 5.5, 7.5, 11.0, 15.0])
        self.sum = dict(LU=tot_LU, DU=tot_DU, qd=qd, main=su_cap(tot_LU), A_roof=A_roof, Qr=Qr, n_yk=len(self.downpipes), n_req=n, gutters=self.gutters, n_cab=len(self.cabinets),
                        ring_dia=self.ring_dia, inlet_dia=self.inlet_dia,
                        pers=pers, daily=daily, tank_dom=tank_dom, fire_tank=fire_tank, rain_tank=rain_tank, H=H,
                        hyd_kw=hyd, fire_kw=fire_kw, jockey_kw=1.1)


def _fire_cover(poly, cands, R, step):
    """greedy cover of the floor polygon (sample grid) by cabinets of reach R."""
    mx, my, Mx, My = poly.bounds
    samples = []
    y = my + step / 2
    while y < My:
        x = mx + step / 2
        while x < Mx:
            if poly.contains(Point(x, y)):
                samples.append((x, y))
            x += step
        y += step
    left = set(range(len(samples)))
    chosen = []
    while left and len(chosen) < 60:
        best, bc = None, set()
        for c in cands:
            cov = {i for i in left if math.hypot(samples[i][0] - c[0], samples[i][1] - c[1]) <= R}
            if len(cov) > len(bc):
                best, bc = c, cov
        if not best:
            break
        chosen.append(best)
        left -= bc
    return chosen


def _fire_cab(self):
    b = self.b
    zk = b.floor('ZK')
    ol = zk.outline
    R = m(25.0)          # 30 m hose reel + jet, path allowance -> 25 m straight-line coverage
    self.cabinets = []   # dict(floor, x, y, ang)
    self.fire_lines = []  # (floor, pts, dia)
    # pump station + fire water tank beside the water entry, outside the building
    q = ol.exterior.interpolate(ol.exterior.project(Point(self.entry)))
    nx, ny = self.meter[0] - q.x, self.meter[1] - q.y
    L = math.hypot(nx, ny) or 1.0
    nx, ny = nx / L, ny / L
    tx, ty = -ny, nx
    px, py = q.x + nx * m(5.0) + tx * m(6.0), q.y + ny * m(5.0) + ty * m(6.0)
    k = 0
    while k < 40 and Point(px, py).buffer(m(2.5)).intersects(ol):
        px, py = px + nx * m(1.0), py + ny * m(1.0)
        k += 1
    self.pump_pt = (px, py)
    self.fire_tank_pt = (px + tx * m(4.0), py + ty * m(4.0))
    main = ol.buffer(-m(1.0))
    if main.geom_type != 'Polygon':
        main = max(main.geoms, key=lambda g: g.area)
    for f in b.floors:
        if not f.rooms:
            continue
        fo = unary_union([r.poly for r in f.rooms]).buffer(m(0.3)).buffer(-m(0.3))
        if fo is None or fo.is_empty:
            continue
        if fo.geom_type != 'Polygon':
            fo = max(fo.geoms, key=lambda g: g.area)
        ring = fo.buffer(-m(0.3))
        if ring.geom_type != 'Polygon':
            ring = max(ring.geoms, key=lambda g: g.area)
        cands = [ring.exterior.interpolate(t).coords[0] for t in
                 [ring.exterior.length * i / max(8, int(ring.exterior.length / m(5.0))) for i in range(max(8, int(ring.exterior.length / m(5.0))))]]
        for d in f.doors:
            cands.append((d['x'], d['y']))
        cands = [c for c in cands if fo.buffer(m(0.5)).contains(Point(c))]
        chosen = _fire_cover(fo, cands, R, m(4.0))
        for (x, y) in chosen:
            x2, y2, a = geo.wall_point(min(f.rooms, key=lambda r: r.poly.distance(Point(x, y))).poly, (x, y), m(0.15))
            self.cabinets.append(dict(floor=f.key, x=x2, y=y2, ang=a))
    # fire main: pump -> building entry -> ring inside the ZK outline -> each cabinet; upper floors by a riser
    entry = (q.x, q.y)
    self.fire_lines.append(('ZK', [self.pump_pt, entry], 80))
    zc = [c for c in self.cabinets if c['floor'] == 'ZK']
    for c in zc:
        self.fire_lines.append(('ZK', geo.ring_route(main, entry, (c['x'], c['y'])), 50))
    for f in b.floors:
        if f.key == 'ZK':
            continue
        cs = [c for c in self.cabinets if c['floor'] == f.key]
        if not cs:
            continue
        # riser at the ZK point under the first upper-floor cabinet (stair / core wall)
        rz = f.to_zk((cs[0]['x'], cs[0]['y']))
        self.fire_lines.append(('ZK', geo.ring_route(main, entry, rz), 80))
        rp = f.from_zk(rz)
        self.risers_fire = getattr(self, 'risers_fire', []) + [(f.key, rp, rz)]
        fr = f.outline.buffer(-m(1.0))
        if fr.geom_type != 'Polygon':
            fr = max(fr.geoms, key=lambda g: g.area)
        for c in cs:
            self.fire_lines.append((f.key, geo.ring_route(fr, rp, (c['x'], c['y'])), 50))


PlumbDesign.fire_cab = _fire_cab
