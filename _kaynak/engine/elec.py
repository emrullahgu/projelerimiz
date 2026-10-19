"""CLD engine - electrical design (lighting, sockets, panels, circuits, power distribution).

Standards / rules used (documented in the drawings' notes):
  * TS EN 12464-1 illuminance targets, lumen (utilisation factor) method
  * Elektrik İç Tesisleri Yönetmeliği: <=1.5 % voltage drop on final circuits, <=1.5 % feeders
  * IEC 60364-5-52 current ratings (Cu, PVC, method C / D approx.), 30 mA RCD on socket circuits
  * Binaların Yangından Korunması Hakkında Yönetmelik: emergency & exit lighting
"""
import math
import re
from dataclasses import dataclass, field
from shapely.geometry import Point, LineString, Polygon, box
from shapely import affinity

import geo
from geo import m, U

# --------------------------------------------------------------- catalogue
# code: (description, W, lumen, block)
LUM = {
    'HB':  ('LED yüksek tavan (highbay) armatürü 150 W, 21.000 lm, IP65', 150, 21000, 'CLD_S_HB'),
    'PNL': ('LED panel armatür 60x60, 36 W, 3.600 lm, UGR<19', 36, 3600, 'CLD_S_PNL'),
    'DL':  ('LED downlight 18 W, 1.800 lm, IP20', 18, 1800, 'CLD_S_DL'),
    'DLB': ('LED downlight 12 W, 1.200 lm, IP44 (ıslak hacim)', 12, 1200, 'CLD_S_DLB'),
    'ETJ': ('LED etanj armatür 36 W, 4.000 lm, IP65', 36, 4000, 'CLD_S_ETJ'),
    'PLF': ('LED sensörlü plafonyer 18 W, 1.600 lm', 18, 1600, 'CLD_S_PLF'),
    'ACL': ('LED acil aydınlatma armatürü 3 W, 3 saat, sürekli/sürekli olmayan', 3, 200, 'CLD_S_ACIL'),
    'EXT': ('LED çıkış/yönlendirme armatürü 3 W, 3 saat', 3, 0, 'CLD_S_EXIT'),
    'PRJ': ('LED projektör 100 W, 12.000 lm, IP66 (cephe)', 100, 12000, 'CLD_S_PRJ'),
}

# room type: (E lux, luminaire, maintenance factor, description)
ROOM_LIGHT = {
    'URETIM':  (300, 'HB', 0.70, 'Üretim alanı (orta hassasiyette iş)'),
    'DEPOH':   (200, 'HB', 0.70, 'Depo / sevkiyat holü'),
    'OFIS':    (500, 'PNL', 0.80, 'Açık ofis / büro'),
    'TOPLANTI': (500, 'PNL', 0.80, 'Toplantı odası'),
    'GIRIS':   (200, 'DL', 0.80, 'Giriş / lobi / bekleme'),
    'HOL':     (100, 'DL', 0.80, 'Hol / koridor'),
    'MESCIT':  (200, 'DL', 0.80, 'Mescit'),
    'WC':      (200, 'DLB', 0.80, 'WC'),
    'ABDEST':  (200, 'DLB', 0.80, 'Abdesthane'),
    'BANYO':   (200, 'DLB', 0.80, 'Duş / banyo'),
    'SOYUNMA': (200, 'DLB', 0.80, 'Soyunma'),
    'MUTFAK':  (300, 'DL', 0.80, 'Mutfak / çay ocağı'),
    'YEMEK':   (200, 'DL', 0.80, 'Yemekhane'),
    'SIGINAK': (100, 'ETJ', 0.70, 'Sığınak'),
    'TEKNIK':  (200, 'ETJ', 0.70, 'Teknik hacim'),
    'DEPO':    (100, 'ETJ', 0.70, 'Depo / çöp odası'),
    'MERDIVEN': (150, 'PLF', 0.80, 'Merdiven'),
    'LAB':     (500, 'PNL', 0.80, 'Laboratuvar'),
    'GENEL':   (150, 'DL', 0.80, 'Genel mahal'),
}
UF_TAB = [(0.6, 0.36), (0.8, 0.44), (1.0, 0.50), (1.25, 0.55), (1.5, 0.59), (2.0, 0.64), (2.5, 0.68), (3.0, 0.71), (4.0, 0.74), (5.0, 0.76)]


def interp(x, tab):
    if x <= tab[0][0]:
        return tab[0][1]
    for (x0, y0), (x1, y1) in zip(tab[:-1], tab[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return tab[-1][1]


def pick(x, lst):
    for v in lst:
        if v >= x - 1e-9:
            return v
    return lst[-1]


# cable ampacity (Cu, A) - IEC 60364-5-52 Table B.52.4, method C, PVC 70 C, 3 loaded conductors
AMP = [(1.5, 17.5), (2.5, 24), (4, 32), (6, 41), (10, 57), (16, 76), (25, 96), (35, 119), (50, 144),
       (70, 184), (95, 223), (120, 259), (150, 299), (185, 341), (240, 403), (300, 464)]
BUS_DF = 0.6
BRK = [6, 10, 16, 20, 25, 32, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500]
# correction factors: final circuits grouped in conduit/tray 0,80; feeders on the shared perimeter tray
# under the steel roof: grouping 0,82 x ambient 40 C 0,87 = 0,71
K_FINAL = 0.80
K_FEEDER = 0.71
MAX_FINAL = {'A': 2.5, 'HB': 4.0, 'AC': 2.5, 'P': 4.0}
PE_STD = [16, 25, 35, 50, 70, 95, 120, 150, 185, 240]


def s_txt(S):
    return {1.5: '1,5', 2.5: '2,5'}.get(S, f'{S:g}')


def du_1f(L, P, S):
    return 200.0 * L * P / (56.0 * S * 230.0 ** 2)


def du_3f(L, P, S):
    return 100.0 * L * P / (56.0 * S * 400.0 ** 2)


def size_cable(P, L, three, In_brk, du_max, min_s=1.5, k=K_FINAL, max_s=None):
    """smallest section with Iz*k >= In and dU <= du_max; returns (S, dU)."""
    best = None
    for S, Iz in AMP:
        if S < min_s or Iz * k < In_brk:
            continue
        if max_s is not None and S > max_s:
            break
        du = du_3f(L, P, S) if three else du_1f(L, P, S)
        best = (S, du)
        if du <= du_max:
            return S, du
    if best:
        return best
    # no section within the cap carries the breaker current: ampacity wins over the cap
    for S, Iz in AMP:
        if S >= min_s and Iz * k >= In_brk:
            return S, (du_3f(L, P, S) if three else du_1f(L, P, S))
    S = AMP[-1][0]
    return S, (du_3f(L, P, S) if three else du_1f(L, P, S))


def size_parallel(In, L, P, du_max):
    """parallel NYY runs for large feeders (transformer -> ADP): returns (n, S, du, Iz_tot)."""
    kpar = {1: 1.0, 2: 0.88, 3: 0.82, 4: 0.77}
    for n in (1, 2, 3, 4):
        for S, Iz in AMP:
            if S < 95:
                continue
            if n * Iz * kpar[n] * K_FEEDER >= In:
                du = du_3f(L, P / n, S)
                if du <= du_max:
                    return n, S, du, n * Iz * kpar[n] * K_FEEDER
    S, Iz = AMP[-1]
    return 4, S, du_3f(L, P / 4, S), 4 * Iz * 0.77 * K_FEEDER


def pe_size(S):
    """TS HD 60364-5-54 Table 54.2, rounded up to a standard section."""
    return S if S <= 16 else (16 if S <= 35 else pick(S / 2, PE_STD))


def cable_name(S, three, kind='NYM', four=False):
    if three:
        if S <= 16:
            return f'{kind} 5x{s_txt(S)} mm²'
        n = pick(S / 2, [16, 25, 35, 50, 70, 95, 120, 150])
        return f'{kind} 3x{s_txt(S)}+{s_txt(n)} + 1x{s_txt(pe_size(S))} (PE) mm²'
    if four:
        return f'{kind} 4x{s_txt(S)} mm²'
    return f'{kind} 3x{s_txt(S)} mm²'


# ---------------------------------------------------------------- objects
@dataclass
class Lum:
    x: float
    y: float
    kod: str
    room: str
    floor: str
    acil: bool = False
    circuit: str = ''


@dataclass
class Out:
    x: float
    y: float
    ang: float
    kind: str        # N normal, E etanj, G industrial group, K dedicated 1ph, K3 dedicated 3ph
    W: float
    blk: str
    desc: str
    room: str
    floor: str
    three: bool = False
    circuit: str = ''


@dataclass
class Sw:
    x: float
    y: float
    ang: float
    blk: str
    room: str
    floor: str


@dataclass
class Panel:
    code: str
    name: str
    kind: str
    floor: str
    x: float
    y: float
    ang: float
    parent: str
    blk: str
    acil: bool = False
    circuits: list = field(default_factory=list)
    route: list = field(default_factory=list)    # feeder route points (ZK plan coords)
    route_floor: list = field(default_factory=list)
    feeder: dict = field(default_factory=dict)


@dataclass
class Circuit:
    code: str
    panel: str
    kind: str        # A light, AC emergency, P socket, G industrial, K dedicated, F feeder
    desc: str
    pts: list
    W: float
    nl: int = 0
    no: int = 0
    three: bool = False
    phase: str = 'R'
    brk: str = ''
    cable: str = ''
    L: float = 0.0
    du: float = 0.0
    rcd: str = ''
    floor: str = ''


class ElecDesign:
    def __init__(self, b, mech_kW=30.0, fire_kW=8.6, mech=None, plumb=None):
        self.b = b
        self.mech = mech
        self.plumb = plumb
        self.mech_kW = mech_kW
        self.fire_kW = fire_kW
        self.lums, self.outs, self.sws = [], [], []
        self.calc = {}        # room id -> lighting calc dict
        self.panels = {}
        self.circuits = []
        self.busbars = []
        self.facade = []
        self.notes = []
        self.run()

    # ------------------------------------------------------------ helpers
    def floor_rooms(self, fk):
        f = self.b.floor(fk)
        return f.rooms if f else []

    def all_rooms(self):
        for f in self.b.floors:
            for r in f.rooms:
                yield f, r

    def doors_of(self, f, r):
        out = []
        for d in f.doors:
            if r.poly.exterior.distance(Point(d['x'], d['y'])) < m(0.6):
                out.append(d)
        return out

    # ----------------------------------------------------------- lighting
    def light_calc(self, f, r):
        E, kod, MF, desc = ROOM_LIGHT.get(r.tip, ROOM_LIGHT['GENEL'])
        A = max(0.5, r.A)
        P = max(1.0, r.poly.length / U)
        h = r.h
        hm = max(0.8, (h - 0.5 if kod == 'HB' else h) - 0.85)
        k = 2.0 * A / (hm * P)
        uf = interp(k, UF_TAB)
        W_l, lm = LUM[kod][1], LUM[kod][2]
        N = E * A / (lm * uf * MF)
        return dict(E=E, kod=kod, MF=MF, desc=desc, A=A, P=P, h=h, hm=hm, k=k, uf=uf, lm=lm, W=W_l, N=N)

    def lighting(self):
        for f, r in self.all_rooms():
            c = self.light_calc(f, r)
            n = max(1, math.ceil(c['N'] * 0.98))
            # make sure the maintained illuminance is reached (E >= Em)
            while n * c['lm'] * c['uf'] * c['MF'] / c['A'] < c['E'] * 0.995:
                n += 1
            mx, my, Mx, My = r.poly.bounds
            margin = min(m(0.5) if c['kod'] != 'HB' else m(2.5), 0.22 * min(Mx - mx, My - my))
            pts = geo.grid_points(r.poly, n, margin)
            if len(pts) < n:
                pts = geo.grid_points(r.poly, n, margin / 3.0)
            if len(pts) < n:
                pts = geo.top_up(r.poly, pts, n)
            # trim grid overshoot: drop the most crowded points until exactly n remain (E stays >= Em)
            while len(pts) > n:
                k_ = min(range(len(pts)), key=lambda i: min(math.hypot(pts[i][0] - q[0], pts[i][1] - q[1])
                                                         for j, q in enumerate(pts) if j != i))
                pts = pts[:k_] + pts[k_ + 1:]
            c['n'] = len(pts)
            c['E_real'] = len(pts) * c['lm'] * c['uf'] * c['MF'] / c['A']
            c['Wm2'] = len(pts) * c['W'] / c['A']
            self.calc[r.id] = c
            for i, (x, y) in enumerate(pts):
                # every 4th highbay with 3h emergency kit (escape route lighting >= 1 lx)
                ac = (c['kod'] == 'HB' and i % 4 == 0)
                self.lums.append(Lum(x, y, c['kod'], r.id, f.key, ac))
            # emergency + exit
            if r.tip in ('GIRIS', 'HOL', 'MERDIVEN', 'SIGINAK', 'TEKNIK', 'MESCIT') or (r.tip == 'OFIS' and r.A > 30):
                k = max(1, math.ceil(r.A / 60))
                for (x, y) in geo.grid_points(r.poly, k, min(m(0.6), 0.3 * min(Mx - mx, My - my))):
                    self.lums.append(Lum(x + m(0.35), y, 'ACL', r.id, f.key, True))
            for d in self.doors_of(f, r):
                ext = f.outline.exterior.distance(Point(d['x'], d['y'])) < m(1.0)
                if ext or r.tip in ('URETIM', 'DEPOH', 'GIRIS', 'SIGINAK'):
                    wx, wy, ang = geo.wall_point(r.poly, (d['x'], d['y']), m(0.15))
                    if not any(l.kod == 'EXT' and math.hypot(l.x - wx, l.y - wy) < m(2) for l in self.lums):
                        self.lums.append(Lum(wx, wy, 'EXT', r.id, f.key, True))

    # ------------------------------------------------------------- sockets
    def sockets(self):
        b = self.b
        for f, r in self.all_rooms():
            av = [(d['x'], d['y']) for d in self.doors_of(f, r)]
            items = []
            A = r.A
            t = r.tip
            if t in ('URETIM', 'DEPOH'):
                k = max(2, math.ceil(A / 150.0))
                cols = [(c[0], c[1]) for c in f.columns if r.poly.buffer(-m(0.3)).contains(Point(c[0], c[1]))]
                if len(cols) >= k:
                    sel = geo.spread_points(cols, k)
                    for (x, y) in sel:
                        self.outs.append(Out(x + m(0.35), y, 0.0, 'G', 5000, 'CLD_S_PGRUP',
                                             'Endüstriyel priz grubu (CEE 3P+N+E 32A + CEE 16A + 2x16A)', r.id, f.key, True))
                else:
                    for (x, y, a) in geo.perimeter_points(r.poly, k, m(0.15), av, m(2.5)):
                        self.outs.append(Out(x, y, a, 'G', 5000, 'CLD_S_PGRUP',
                                             'Endüstriyel priz grubu (CEE 3P+N+E 32A + CEE 16A + 2x16A)', r.id, f.key, True))
                continue
            if t in ('OFIS', 'TOPLANTI', 'LAB'):
                items += [('N', 300, 'CLD_S_PRIZ', 'Priz 16A')] * max(4, math.ceil(A / 5.0))
                items += [('U', 300, 'CLD_S_PRIZU', 'Bilgisayar prizi (ayrı linye, UPS hazırlığı)')] * max(2, math.ceil(A / 10.0))
            elif t in ('GIRIS', 'MESCIT'):
                items += [('N', 300, 'CLD_S_PRIZ', 'Priz 16A')] * max(2, math.ceil(A / 15.0))
            elif t == 'HOL':
                if A > 4:
                    items += [('N', 300, 'CLD_S_PRIZ', 'Priz 16A')] * max(1, math.ceil(A / 15.0))
            elif t in ('WC', 'BANYO', 'SOYUNMA'):
                if A >= 3.0:
                    items += [('E', 300, 'CLD_S_PRIZE', 'Etanj priz IP44')]
            elif t == 'ABDEST':
                items += [('E', 300, 'CLD_S_PRIZE', 'Etanj priz IP44'),
                          ('K', 3500, 'CLD_S_CK_ISITICI', 'Ani su ısıtıcı 3,5 kW')]
            elif t == 'MUTFAK':
                items += [('N', 300, 'CLD_S_PRIZ', 'Tezgah prizi')] * 4
                items += [('K', 2000, 'CLD_S_CK_TERMOSIFON', 'Termosifon 80 L 2 kW'),
                          ('K', 2200, 'CLD_S_CK_BULASIK', 'Bulaşık makinesi')]
            elif t in ('SIGINAK',):
                items += [('E', 300, 'CLD_S_PRIZE', 'Etanj priz IP44')] * 2
                items += [('K', 750, 'CLD_S_CK_ASPIRATOR', 'Sığınak havalandırma cihazı')]
            elif t == 'TEKNIK':
                items += [('E', 300, 'CLD_S_PRIZE', 'Etanj priz IP44')] * 2
            elif t == 'DEPO':
                items += [('E', 300, 'CLD_S_PRIZE', 'Etanj priz IP44')]
            else:
                if A > 4:
                    items += [('N', 300, 'CLD_S_PRIZ', 'Priz 16A')] * max(1, math.ceil(A / 10.0))
            pts = geo.perimeter_points(r.poly, len(items), m(0.12), av, m(0.8))
            for it, (x, y, a) in zip(items, pts):
                self.outs.append(Out(x, y, a, it[0], it[1], it[2], it[3], r.id, f.key, False))
        # termosifon per WC core per floor (largest WC of the floor)
        for f in b.floors:
            wcs = [r for r in f.rooms if r.tip == 'WC']
            if wcs:
                big = max(wcs, key=lambda r: r.A)
                x, y, a = geo.perimeter_points(big.poly, 1, m(0.12), [], 0)[0]
                self.outs.append(Out(x, y, a, 'K', 2000, 'CLD_S_CK_TERMOSIFON', 'Elektrikli termosifon 80 L 2 kW', big.id, f.key))

    def switches(self):
        for f, r in self.all_rooms():
            if r.tip in ('URETIM', 'DEPOH', 'MERDIVEN', 'SIGINAK'):
                continue
            ds = self.doors_of(f, r)
            if ds:
                d = min(ds, key=lambda d: r.poly.exterior.distance(Point(d['x'], d['y'])))
                tx, ty = d['x'], d['y']
                x, y, a = geo.wall_point(r.poly, (tx, ty), m(0.10))
                # move along the wall next to the door leaf
                ex, ey = math.cos(a - math.pi / 2), math.sin(a - math.pi / 2)
                off = m(min(0.9, d['w'] / 2 + 0.2))
                cand = [(x + ex * off, y + ey * off), (x - ex * off, y - ey * off)]
                x, y = max(cand, key=lambda p: r.poly.buffer(-m(0.05)).contains(Point(p)))
            else:
                hub = None
                for z in f.rooms:
                    if z.tip in ('GIRIS', 'HOL') and z.id != r.id:
                        hub = z.poly.centroid
                        break
                tgt = (hub.x, hub.y) if hub else (r.poly.centroid.x, r.poly.centroid.y)
                x, y, a = geo.wall_point(r.poly, tgt, m(0.10))
            nl = len([l for l in self.lums if l.room == r.id and l.kod not in ('ACL', 'EXT')])
            blk = 'CLD_S_ANH2' if nl >= 8 else ('CLD_S_VAV' if r.tip == 'HOL' and r.A > 8 else 'CLD_S_ANH1')
            self.sws.append(Sw(x, y, a, blk, r.id, f.key))

    # -------------------------------------------------------------- panels
    def place_panels(self):
        b = self.b
        zk = b.floor('ZK')
        ol = zk.outline
        P = {}
        # reference: generator room or office core (lobby)
        ref = None
        for r in zk.rooms:
            if r.tip == 'TEKNIK':
                ref = r
                break
        if ref is None:
            ref = next((r for r in zk.rooms if r.tip == 'GIRIS'), None)
        refpt = (ref.poly.centroid.x, ref.poly.centroid.y) if ref else (ol.centroid.x, ol.centroid.y)
        halls = [r for r in zk.rooms if r.tip in ('URETIM', 'DEPOH')]
        host = min(halls, key=lambda h: h.poly.distance(Point(refpt))) if halls else None
        if host is not None:
            # ADP on the exterior wall of the nearest hall, close to the reference
            ext = host.poly.intersection(ol.exterior.buffer(m(0.8)))
            tgt = refpt
            q = ol.exterior.interpolate(ol.exterior.project(Point(refpt)))
            x, y, a = geo.wall_point(host.poly, (q.x, q.y), m(0.35))
        else:
            x, y, a = geo.wall_point(ol, refpt, m(0.35))
        P['ADP'] = Panel('ADP', 'ANA DAĞITIM PANOSU', 'ADP', 'ZK', x, y, a, 'TR', 'CLD_S_ADP')
        ex, ey = math.cos(a - math.pi / 2), math.sin(a - math.pi / 2)
        P['KMP'] = Panel('KMP', 'KOMPANZASYON PANOSU', 'KMP', 'ZK', x + ex * m(1.4), y + ey * m(1.4), a, 'ADP', 'CLD_S_KMP')
        P['MKP'] = Panel('MKP', 'MEKANİK PANOSU', 'MKP', 'ZK', x - ex * m(1.4), y - ey * m(1.4), a, 'ADP', 'CLD_S_OAP')
        # outdoor: transformer kiosk, generator, fire pump room - outside the real exterior wall
        q = ol.exterior.interpolate(ol.exterior.project(Point(x, y)))
        d = ol.exterior.project(q)
        p1 = ol.exterior.interpolate(max(0.0, d - m(1.0)))
        p2 = ol.exterior.interpolate(min(ol.exterior.length, d + m(1.0)))
        tx_, ty_ = p2.x - p1.x, p2.y - p1.y
        tl = math.hypot(tx_, ty_) or 1.0
        tx_, ty_ = tx_ / tl, ty_ / tl
        nx, ny = -ty_, tx_
        if ol.contains(Point(q.x + nx * m(0.5), q.y + ny * m(0.5))):
            nx, ny = -nx, -ny

        def outside(px, py, hw, hh):
            k = 0
            while k < 40 and box(px - hw, py - hh, px + hw, py + hh).distance(ol) < m(2.0):
                px, py = px + nx * m(1.0), py + ny * m(1.0)
                k += 1
            return (px, py)
        base = (q.x + nx * m(6.0), q.y + ny * m(6.0))
        self.trafo_pt = outside(base[0], base[1], m(3.0), m(2.5))
        self.gen_pt = outside(base[0] + tx_ * m(8.0), base[1] + ty_ * m(8.0), m(2.0), m(0.8))
        self.ypp_pt = outside(base[0] - tx_ * m(7.0), base[1] - ty_ * m(7.0), m(1.5), m(1.5))
        if self.plumb is not None and getattr(self.plumb, 'pump_pt', None):
            # fire pump panel inside the fire pump station (plumbing)
            self.ypp_pt = (self.plumb.pump_pt[0], self.plumb.pump_pt[1] - m(1.0))
        self.out_normal = (nx, ny)
        P['YPP'] = Panel('YPP', 'YANGIN POMPA PANOSU', 'YPP', 'ZK', self.ypp_pt[0], self.ypp_pt[1], a, 'ADP', 'CLD_S_OAP', acil=True)
        # production sub-panels: on the hall wall nearest the hall centroid
        for i, h in enumerate(sorted(halls, key=lambda r: r.poly.centroid.x)):
            c = h.poly.centroid
            hx, hy, ha = geo.wall_point(h.poly, (c.x, c.y), m(0.35))
            code = f'UTP-{i + 1}'
            P[code] = Panel(code, f'ÜRETİM TALİ PANOSU {i + 1}', 'UTP', 'ZK', hx, hy, ha, 'ADP', 'CLD_S_TP')
            P[code].room = h.id
        # office floor panels
        for f in b.floors:
            off = [r for r in f.rooms if r.tip not in ('URETIM', 'DEPOH')]
            if not off:
                continue
            hub = next((r for r in f.rooms if r.tip in ('GIRIS',)), None) or \
                next((r for r in f.rooms if r.tip in ('HOL',)), None) or max(off, key=lambda r: r.A)
            core = unaryc([r.poly for r in off])
            hx, hy, ha = geo.wall_point(hub.poly, (core.x, core.y), m(0.12))
            code = f'IDP-{f.key}'
            P[code] = Panel(code, f'İDARİ BÖLÜM {f.name} PANOSU', 'IDP', f.key, hx, hy, ha, 'ADP', 'CLD_S_TP', acil=True)
        self.panels = P

    def panel_of(self, f, r):
        if r.tip in ('URETIM', 'DEPOH'):
            for p in self.panels.values():
                if p.kind == 'UTP' and getattr(p, 'room', None) == r.id:
                    return p.code
        code = f'IDP-{f.key}'
        if code in self.panels:
            return code
        return 'IDP-ZK' if 'IDP-ZK' in self.panels else 'ADP'

    # ------------------------------------------------------------ circuits
    def wall_order(self, outs, roomf, p0):
        """rooms nearest to the panel first, inside a room along the wall ring."""
        byroom = {}
        for o in outs:
            byroom.setdefault(o.room, []).append(o)
        res = []
        for rid in sorted(byroom, key=lambda rid: min(geo.manh(p0, (o.x, o.y)) for o in byroom[rid])):
            ring = roomf[rid][1].poly.exterior
            lst = sorted(byroom[rid], key=lambda o: ring.project(Point(o.x, o.y)))
            # start the ring walk at the outlet nearest to the panel
            k = min(range(len(lst)), key=lambda i: geo.manh(p0, (lst[i].x, lst[i].y)))
            res += lst[k:] + lst[:k]
        return res

    def make_circuits(self):
        b = self.b
        roomf = {r.id: (f, r) for f, r in self.all_rooms()}
        by_panel = {}
        for l in self.lums:
            f, r = roomf[l.room]
            by_panel.setdefault(self.panel_of(f, r), {'L': [], 'E': [], 'O': []})
        for o in self.outs:
            f, r = roomf[o.room]
            by_panel.setdefault(self.panel_of(f, r), {'L': [], 'E': [], 'O': []})
        for l in self.lums:
            f, r = roomf[l.room]
            pc = self.panel_of(f, r)
            (by_panel[pc]['E'] if l.kod in ('ACL', 'EXT') else by_panel[pc]['L']).append(l)
        for o in self.outs:
            f, r = roomf[o.room]
            by_panel[self.panel_of(f, r)]['O'].append(o)
        circuits = []
        self._panel_rooms = {pc: set([l.room for l in grp['L']] + [o.room for o in grp['O']]) for pc, grp in by_panel.items()}
        for pc, grp in by_panel.items():
            pn = self.panels[pc]
            p0 = (pn.x, pn.y)
            n = 0

            def add(kind, desc, items, W, nl=0, no=0, three=False):
                nonlocal n
                n += 1
                prefix = {'A': 'A', 'AC': 'AC', 'P': 'P', 'G': 'G', 'K': 'K'}[kind]
                code = f'{prefix}{n}'
                c = Circuit(code, pc, kind, desc, [(it.x, it.y) for it in items], W, nl, no, three, floor=pn.floor)
                for it in items:
                    if not isinstance(it, Panel):
                        it.circuit = code
                        it.panel = pc
                circuits.append(c)

            def too_long(items, W, smax, extra=3.0, lim=1.5):
                # projected voltage drop of the chain at the largest allowed section (load lumped at the end)
                L = geo.path_len([p0] + [(it.x, it.y) for it in items]) / U * 1.15 + extra
                return du_1f(L, W, smax) > lim
            # lighting: group by room, highbays <= 8, others <= 10 points / 1500 W, dU <= 1,5 % at the cap
            rooms = {}
            for l in grp['L']:
                rooms.setdefault(l.room, []).append(l)
            cur, curW = [], 0.0
            for rid in sorted(rooms, key=lambda rid: geo.manh(p0, (rooms[rid][0].x, rooms[rid][0].y))):
                rr = roomf[rid][1]
                ls = geo.serpentine([(l.x, l.y) for l in rooms[rid]], geo.long_angle(rr.poly), p0)
                lmap = {(l.x, l.y): l for l in rooms[rid]}
                for pt in ls:
                    l = lmap[pt]
                    W = LUM[l.kod][1]
                    lim = 8 if l.kod == 'HB' else 10
                    far = cur and math.hypot(cur[-1].x - l.x, cur[-1].y - l.y) > m(15.0)
                    hbk = l.kod == 'HB'
                    longc = cur and too_long(cur + [l], curW + W, MAX_FINAL['HB' if hbk else 'A'], 6.0 if hbk else 3.0)
                    if cur and (far or longc or len(cur) >= lim or curW + W > 1500 or (cur[0].kod == 'HB') != hbk):
                        add('A', 'Aydınlatma' + (' (yüksek tavan)' if cur[0].kod == 'HB' else ''), cur, curW, nl=len(cur))
                        cur, curW = [], 0.0
                    cur.append(l)
                    curW += W
            if cur:
                add('A', 'Aydınlatma' + (' (yüksek tavan)' if cur[0].kod == 'HB' else ''), cur, curW, nl=len(cur))
            if grp['E']:
                order = geo.nn_order(p0, [(e_.x, e_.y) for e_ in grp['E']])
                emap = {(e_.x, e_.y): e_ for e_ in grp['E']}
                es = [emap[q] for q in order]
                cur = []
                for e_ in es:
                    if cur and (len(cur) >= 15 or math.hypot(cur[-1].x - e_.x, cur[-1].y - e_.y) > m(25.0) or
                                too_long(cur + [e_], sum(LUM[q.kod][1] for q in cur + [e_]), MAX_FINAL['AC'])):
                        add('AC', 'Acil aydınlatma / yönlendirme', cur, sum(LUM[q.kod][1] for q in cur), nl=len(cur))
                        cur = []
                    cur.append(e_)
                if cur:
                    add('AC', 'Acil aydınlatma / yönlendirme', cur, sum(LUM[q.kod][1] for q in cur), nl=len(cur))
            # sockets
            norm = [o for o in grp['O'] if o.kind in ('N', 'E')]
            ups = [o for o in grp['O'] if o.kind == 'U']
            for lst, nm in ((norm, 'Priz'), (ups, 'Bilgisayar prizi (UPS hazırlığı)')):
                lst = self.wall_order(lst, roomf, p0)
                cur = []
                for o_ in lst:
                    if cur and (len(cur) >= 6 or math.hypot(cur[-1].x - o_.x, cur[-1].y - o_.y) > m(15.0) or
                                too_long(cur + [o_], sum(q.W for q in cur + [o_]), MAX_FINAL['P'])):
                        add('P', nm, cur, sum(q.W for q in cur), no=len(cur))
                        cur = []
                    cur.append(o_)
                if cur:
                    add('P', nm, cur, sum(q.W for q in cur), no=len(cur))
            for o in grp['O']:
                if o.kind == 'G':
                    add('G', 'Endüstriyel priz grubu', [o], o.W, no=1, three=True)
                elif o.kind in ('K', 'K3'):
                    add('K', o.desc, [o], o.W, no=1, three=o.three)
            # panel-specific dedicated loads
            if pn.kind == 'IDP':
                fl = b.floor(pn.floor)
                vrf = [r for r in fl.rooms if r.tip in ('OFIS', 'GIRIS', 'MESCIT', 'TOPLANTI', 'LAB', 'YEMEK')]
                if vrf:
                    iu = [u for u in (self.mech.units if self.mech else []) if u.kind == 'VRF' and u.floor == pn.floor]
                    if iu:
                        order = geo.nn_order(p0, [(u.x, u.y) for u in iu])
                        pts_iu = [Panel('', '', 'PT', pn.floor, q[0], q[1], 0.0, '', '') for q in order]
                        add('K', 'VRF iç üniteleri besleme', pts_iu, 60.0 * len(iu) + 100, no=len(iu))
                    else:
                        add('K', 'VRF iç üniteleri besleme', [pn], 120.0 * max(1, len(vrf)) + 200, no=1)
            if pn.kind == 'UTP':
                add('K', 'Aydınlatma kumanda (kontaktör/saat rölesi)', [pn], 50, no=1)
                # sectional door motor at the widest exterior door of this panel's hall(s)
                zk = b.floor('ZK')
                halls = [r for r in zk.rooms if r.id in self._panel_rooms.get(pc, set()) and r.tip in ('URETIM', 'DEPOH')]
                dr = [d for d in zk.doors if d.get('w', 0) >= 2.5 and
                      zk.outline.exterior.distance(Point(d['x'], d['y'])) < m(1.0) and
                      any(h.poly.buffer(m(1.0)).contains(Point(d['x'], d['y'])) for h in halls)]
                if dr:
                    d = max(dr, key=lambda d: d['w'])
                    add('K', 'Seksiyonel kapı motoru', [Panel('', '', 'PT', 'ZK', d['x'], d['y'], 0.0, '', '')], 750, no=1, three=True)
                else:
                    # sectional doors are nested inside façade blocks: length allowance instead of a guessed point
                    add('K', 'Seksiyonel kapı motoru (L≈25 m kabul)', [pn], 750, no=1, three=True)
                    circuits[-1].L_fix = 25.0
            pn.circuits = [c.code for c in circuits if c.panel == pc]
        # sizing + phases
        for c in circuits:
            pn = self.panels[c.panel]
            pts = [(pn.x, pn.y)] + list(c.pts)
            hb = c.desc.endswith('(yüksek tavan)')
            c.L = getattr(c, 'L_fix', None) or geo.path_len([(p[0], p[1]) for p in pts]) / U * 1.15 + (6.0 if hb else 3.0)
            # hall panels: cables run on the tray under the steel roof -> grouping 0,82 x 40 C 0,87
            kk = K_FEEDER if pn.kind == 'UTP' else K_FINAL
            four = False
            if c.kind in ('A', 'AC'):
                brk_in = 10 if c.W <= 1000 else 16
                lim = 1.5
                S, du = size_cable(c.W, c.L, False, brk_in, lim, 1.5, kk, MAX_FINAL['HB' if hb else 'A'])
                c.brk = f'B{brk_in}A'
                c.rcd = '300 mA' if c.kind == 'A' else '-'
                if hb and any(l.acil for l in self.lums if l.circuit == c.code and getattr(l, 'panel', None) == c.panel):
                    four = True
                    c.desc = 'Aydınlatma (yüksek tavan, AK: sürekli faz)'
            elif c.kind == 'P':
                lim = 1.5
                S, du = size_cable(c.W, c.L, False, 16, lim, 2.5, kk, MAX_FINAL['P'])
                c.brk, c.rcd = 'B16A', '30 mA'
            elif c.kind == 'G':
                # checked at 16 A continuous (11 kW) per group; group box has its own C32/C16/B16 + 30 mA RCD
                lim = 3.0
                S, du = size_cable(11000.0, c.L, True, 32, lim, 6, kk)
                c.brk, c.rcd = 'C32A', '30 mA (A tipi)'
                c.desc = 'End. priz grubu (4P C32+C16+2xB16)'
            else:
                I = c.W / (692.8 * 0.9) if c.three else c.W / (230.0 * 0.95)
                In = pick(1.25 * I, [10, 16, 20, 25, 32, 40, 50, 63])
                # dedicated power circuits: <= 3 % (kuvvet tesisatı), section capped at 6 mm2
                lim = 3.0
                S, du = size_cable(c.W, c.L, c.three, In, lim, 2.5 if In > 10 else 1.5, kk, 6.0)
                c.brk = f'{"C" if c.three else "B"}{In}A'
                c.rcd = '30 mA' if not c.three else '300 mA'
            if du > lim + 1e-6:
                # a single far point that cannot be split further: take the next sections until dU fits
                inb = int(re.sub(r'[^0-9]', '', c.brk))
                S, du = size_cable(11000.0 if c.kind == 'G' else c.W, c.L, c.three, inb, lim, S, kk, 10.0)
            # residual current protection (TS HD 60364-4-41 411.3.3, EİTY, EMO): every single-phase final
            # circuit 30 mA (A type for electronics / inverters), three-phase motor circuits 300 mA;
            # panel inputs 300 mA S (selective), ADP main: adjustable toroidal relay (fire protection)
            if c.kind in ('A', 'AC', 'P'):
                c.rcd = '30 mA A tipi' if 'UPS' in c.desc else '30 mA'
            elif c.kind == 'G':
                c.rcd = '30 mA A tipi (kutu içi)'
            elif c.three:
                c.rcd = '300 mA'
            else:
                c.rcd = '30 mA A tipi' if 'VRF' in c.desc else '30 mA'
            c.cable = cable_name(S, c.three, 'NYM', four)
            c.S, c.du = S, du
        # phase balance per panel
        for pc, pn in self.panels.items():
            cs = [c for c in circuits if c.panel == pc]
            load = {'R': 0.0, 'S': 0.0, 'T': 0.0}
            for c in sorted(cs, key=lambda c: -c.W):
                if c.three:
                    c.phase = 'RST'
                    for k in load:
                        load[k] += c.W / 3
                else:
                    k = min(load, key=load.get)
                    c.phase = k
                    load[k] += c.W
            singles = [c for c in cs if not c.three]
            for _ in range(60):
                hi, lo = max(load, key=load.get), min(load, key=load.get)
                gap = load[hi] - load[lo]
                best = None
                for a in singles:
                    if a.phase != hi:
                        continue
                    if 0 < a.W < gap and (best is None or abs(gap - 2 * a.W) < abs(gap - 2 * best[0].W)):
                        best = (a, None)
                    for b2 in singles:
                        if b2.phase == lo and 0 < a.W - b2.W < gap:
                            d = a.W - b2.W
                            if best is None or abs(gap - 2 * d) < abs(gap - 2 * (best[0].W - (best[1].W if best[1] else 0))):
                                best = (a, b2)
                if best is None:
                    break
                a, b2 = best
                d = a.W - (b2.W if b2 else 0)
                if abs(gap - 2 * d) >= gap - 1e-6:
                    break
                a.phase = lo
                load[hi] -= a.W
                load[lo] += a.W
                if b2:
                    b2.phase = hi
                    load[lo] -= b2.W
                    load[hi] += b2.W
            pn.load_phase = load
        self.circuits = circuits

    # --------------------------------------------------- distribution / sizing
    def distribution(self):
        b = self.b
        zk = b.floor('ZK')
        self.tray = zk.outline.buffer(-m(0.6))
        if self.tray.geom_type != 'Polygon':
            self.tray = max(self.tray.geoms, key=lambda g: g.area)
        # machine busbars: one per hall, fed directly from ADP
        hall_rooms = [r for r in zk.rooms if r.tip in ('URETIM', 'DEPOH')]
        self.machine_density = 60.0     # W/m2 light industry assumption
        for i, h in enumerate(sorted(hall_rooms, key=lambda r: r.poly.centroid.x)):
            ax = geo.main_axis(h.poly, m(4.0))
            P = self.machine_density * h.A
            I = P / (692.8 * 0.85)
            rating = pick(1.25 * I, [100, 160, 250, 400, 630, 800, 1000])
            self.busbars.append(dict(code=f'BARA-{i + 1}', room=h.id, pts=ax, P=P, I=I, rating=rating,
                                     desc=f'Makine besleme bara kanalı {rating} A (3P+N+PE)'))
        # facade floodlights
        ring = zk.outline.exterior
        n = max(4, math.ceil(ring.length / U / 18.0))
        for i in range(n):
            p = ring.interpolate(ring.length * (i + 0.5) / n)
            self.facade.append((p.x, p.y))
        # feeder routes + sizing
        adp = self.panels['ADP']
        loads = self.panel_loads()
        self.bus_df = BUS_DF
        for code, pn in self.panels.items():
            if code in ('ADP', 'KMP'):
                continue
            fl = b.floor(pn.floor)
            if code == 'YPP':
                # fire pump: dedicated circuit taken BEFORE the ADP main breaker (TS EN 12845 10.8)
                route = [self.trafo_pt, (pn.x, pn.y)]
                vert = 2.0
            elif pn.floor == 'ZK':
                route = geo.ring_route(self.tray, (adp.x, adp.y), (pn.x, pn.y))
                direct = geo.ortho((adp.x, adp.y), (pn.x, pn.y))
                if math.hypot(adp.x - pn.x, adp.y - pn.y) < m(10.0) or geo.path_len(direct) < geo.path_len(route):
                    route = direct
                vert = 2.0
            else:
                rz = fl.to_zk((pn.x, pn.y))
                route = geo.ring_route(self.tray, (adp.x, adp.y), rz)
                vert = fl.kot + 3.0
            pn.route = route
            L = geo.path_len(route) / U * 1.10 + vert + 3.0
            P = loads[code]['demand']
            I = P / (692.8 * 0.9)
            outs = [int(re.sub(r'[^0-9]', '', c.brk) or 0) for c in self.circuits if c.panel == code]
            if code == 'YPP':
                # aM fuse / magnetic-only MCCB sized for the locked-rotor current (~6 x In for 20 s)
                In = pick(max(25, 2.5 * I), BRK)
                S, du = size_cable(P, L, True, In, 1.5, 6, K_FEEDER)
                cab = cable_name(S, True, 'NHXH-FE180/E90')
                rcd = 'KAKR yok (yalnız alarm)'
                prot = f'aM sigorta {In} A (ana şalter öncesi), {rcd}'
            else:
                In = pick(max(25, 1.25 * I, 1.6 * max(outs or [0])), BRK)
                S, du = size_cable(P, L, True, In, 1.5, 6, K_FEEDER)
                cab = cable_name(S, True, 'NYY')
                rcd = 'B tipi 300 mA S' if code == 'MKP' else '300 mA S'
                prot = f'{In} A + {rcd}'
            pn.feeder = dict(L=L, P=P, I=I, In=In, S=S, du=du, cable=cab, prot=prot, rcd=rcd)
        for bb in self.busbars:
            h = next(r for r in zk.rooms if r.id == bb['room'])
            start = bb['pts'][0] if bb['pts'] else (h.poly.centroid.x, h.poly.centroid.y)
            route = geo.ring_route(self.tray, (adp.x, adp.y), start)
            L = geo.path_len(route) / U * 1.10 + 6.0
            In = pick(bb['rating'], BRK)
            Pd = bb['P'] * BUS_DF
            S, du = size_cable(Pd, L, True, In, 1.5, 16, K_FEEDER)
            bb.update(route=route, L=L, In=In, S=S, du=du, Pd=Pd, Id=Pd / (692.8 * 0.85), cable=cable_name(S, True, 'NYY'),
                      rcd='1 A S (ayarlı toroid)')
        # facade floodlights: one 3-phase circuit from ADP, two branches around the outline
        Pc = len(self.facade) * LUM['PRJ'][1]
        if self.facade:
            i0 = min(range(len(self.facade)), key=lambda i: math.hypot(self.facade[i][0] - adp.x, self.facade[i][1] - adp.y))
            Lc = math.hypot(self.facade[i0][0] - adp.x, self.facade[i0][1] - adp.y) / U * 1.2 + ring.length / U / 2 + 6.0
        else:
            Lc = 10.0
        Sc, duc = size_cable(Pc, Lc, True, 16, 1.5, 2.5, K_FEEDER)
        self.cephe = dict(P=Pc, L=Lc, I=Pc / (692.8 * 0.9), In=16, S=Sc, du=duc, cable=cable_name(Sc, True, 'NYY'))
        # totals
        self.totals()

    def panel_loads(self):
        out = {}
        for code, pn in self.panels.items():
            cs = [c for c in self.circuits if c.panel == code]
            inst = sum(c.W for c in cs)
            out[code] = dict(inst=inst, demand=inst)
        # demand factors (EİTY / practice)
        for code, v in out.items():
            pn = self.panels[code]
            if pn.kind == 'UTP':
                v['demand'] = 0.9 * sum(c.W for c in self.circuits if c.panel == code and c.kind in ('A', 'AC')) + \
                    0.6 * sum(c.W for c in self.circuits if c.panel == code and c.kind not in ('A', 'AC'))
            elif pn.kind == 'IDP':
                v['demand'] = 0.8 * v['inst']
        out['MKP'] = dict(inst=self.mech_kW * 1000, demand=0)
        out['MKP']['demand'] = 0.8 * out['MKP']['inst']
        out['YPP'] = dict(inst=self.fire_kW * 1000, demand=0)
        out['YPP']['demand'] = out['YPP']['inst']
        self._loads = out
        return out

    def totals(self):
        loads = self._loads
        light_out = self.cephe['P']
        bus = sum(bb['P'] for bb in self.busbars)
        inst = sum(v['inst'] for k, v in loads.items()) + bus + light_out
        # demand: busbars BUS_DF (machines), sub panels as computed, mech 0.8; the fire pump runs only
        # when production is stopped (fire) -> not added to the normal transformer demand
        dem = sum(v['demand'] for k, v in loads.items() if k != 'YPP') + BUS_DF * bus + light_out
        cosphi1 = 0.80
        P = dem / 1000.0
        S_need = P / 0.95 * 1.20
        trafo = pick(S_need, [100, 160, 250, 400, 630, 800, 1000, 1250, 1600, 2000])
        uk = 0.04 if trafo <= 630 else 0.06
        Qc = P * (math.tan(math.acos(cosphi1)) - math.tan(math.acos(0.98)))
        kmp = pick(Qc, [10, 15, 20, 25, 30, 40, 50, 60, 75, 90, 100, 120, 150, 180, 200, 250, 300, 400])
        In_tr = trafo * 1000 / (math.sqrt(3) * 400)
        main_brk = pick(In_tr, BRK)
        ik = trafo * 1000 / (math.sqrt(3) * 400 * uk) / 1000.0
        # transformer -> ADP cable (parallel NYY runs, derated, sized for the main breaker)
        Ltr = math.hypot(self.trafo_pt[0] - self.panels['ADP'].x, self.trafo_pt[1] - self.panels['ADP'].y) / U + 8.0
        n_tr, S_tr, du_tr, Iz_tr = size_parallel(main_brk, Ltr, dem, 0.5)
        # three-phase short-circuit current at every panel: transformer (uk) + cables (Cu 56, x' = 0,08 mOhm/m)
        Ztr = uk * 400.0 ** 2 / (trafo * 1000.0)
        Rtr_c, Xtr_c = Ltr / (56.0 * S_tr * n_tr), 0.08e-3 * Ltr / n_tr

        def ik_at(R, X):
            return 1.05 * 400.0 / (math.sqrt(3) * math.hypot(R, Ztr + X)) / 1000.0
        self.ik_adp = ik_at(Rtr_c, Xtr_c)
        for code, pn in self.panels.items():
            fd = pn.feeder
            if not fd:
                continue
            if code == 'YPP':
                fd['Ik'] = ik_at(fd['L'] / (56.0 * fd['S']), 0.08e-3 * fd['L'])
            else:
                fd['Ik'] = ik_at(Rtr_c + fd['L'] / (56.0 * fd['S']), Xtr_c + 0.08e-3 * fd['L'])
            fd['Icu'] = pick(fd['Ik'] * 1.1, [6, 10, 15, 25, 36, 50])
        for bb in self.busbars:
            bb['Ik'] = ik_at(Rtr_c + bb['L'] / (56.0 * bb['S']), Xtr_c + 0.08e-3 * bb['L'])
        pe_tr = pick(S_tr / 2, PE_STD)
        tr_cable = (f'{n_tr} x (NYY 3x{s_txt(S_tr)}+{s_txt(pick(S_tr / 2, PE_STD))} + 1x{s_txt(pe_tr)} PE) mm²' +
                    (' - her hatta ayrı PE' if n_tr > 1 else ''))
        # emergency (generator) bus: office panels; fire pump has its own diesel/electric source
        # selection (TS EN 12845) but is also backed by the generator; emergency luminaires are 3 h self-contained
        em_idp = sum(loads[k]['demand'] for k in loads if k.startswith('IDP'))
        ypp = loads.get('YPP', {}).get('inst', 0)
        em = ypp + em_idp
        GEN = [20, 30, 45, 60, 80, 100, 135, 165, 200, 250, 300, 400, 500]
        # running load with 25 % reserve, and the largest motor step: fire pump with soft starter (~3 x In),
        # step kVA <= gen kVA with the other emergency loads running (voltage dip <= ~15 %)
        p_main = (self.fire_kW - 1.1) * 1000 if self.fire_kW > 2.2 else ypp     # main pump (jockey 1,1 kW excluded)
        start_kva = 3.0 * p_main / 1000.0 / (0.88 * 0.85)
        gen_run = em / 1000.0 / 0.8 * 1.25
        gen_start = em_idp / 1000.0 / 0.8 + start_kva
        gen = pick(max(gen_run, gen_start), GEN)
        # generator -> YPP back-up line: taken at the generator terminals, ahead of the ADP ATS
        adp = self.panels['ADP']
        ypp_pn = self.panels.get('YPP')
        if ypp_pn is not None:
            self.gen_ypp_route = geo.ortho(self.gen_pt, (ypp_pn.x, ypp_pn.y))
            Lg = geo.path_len(self.gen_ypp_route) / U * 1.1 + 5.0
            Ig = ypp / (692.8 * 0.85)
            Ing = pick(max(25, 2.5 * Ig), BRK)
            Sg, dug = size_cable(ypp, Lg, True, Ing, 1.5, 6, K_FEEDER)
            self.gen_ypp = dict(L=Lg, P=ypp, I=Ig, In=Ing, S=Sg, du=dug, cable=cable_name(Sg, True, 'NHXH-FE180/E90'))
        else:
            self.gen_ypp_route, self.gen_ypp = [], {}
        self.tot = dict(inst=inst, demand=dem, P=P, S_need=S_need, trafo=trafo, uk=uk, Qc=Qc, kmp=kmp, In_tr=In_tr,
                        main_brk=main_brk, ik=ik, em=em, gen=gen, bus=bus, light_out=light_out, cosphi1=cosphi1,
                        tr_cable=tr_cable, tr_L=Ltr, tr_du=du_tr, tr_Iz=Iz_tr, ypp=ypp, em_idp=em_idp,
                        gen_run=gen_run, gen_start=gen_start, start_kva=start_kva, I_dem=dem / (692.8 * 0.9))

    # -------------------------------------------------------------- run
    def run(self):
        self.lighting()
        self.sockets()
        self.switches()
        self.place_panels()
        self.make_circuits()
        self.distribution()


def unaryc(polys):
    from shapely.ops import unary_union
    return unary_union(polys).centroid
