"""CLD engine - earthing (topraklama) and lightning protection (paratoner).

Earthing (Elektrik Tesislerinde Topraklamalar Yönetmeliği, TS EN 62305-3, DIN 18014):
  meshed foundation earth electrode St/tZn 30x3,5 mm (ring + max 20x20 m mesh), connection
  lugs (filiz) at every steel column, every down conductor and the main earthing bar (AEB),
  connecting strips from every lug to the nearest strip, local bars in wet rooms,
  transformer protective ring + 4 rods bonded to the foundation network by two separate strips.
  R(meshed foundation) = rho / (2 D), D = 1,13 sqrt(A).  Transformer ring R = 2 rho / (3 D).
Lightning (efficiency method, IEC/TS 61024-1-1 as referenced by TS EN 62305 practice):
  Ad = area of the footprint expanded by 3H, Nd = Ng Ad Cd 1e-6, E = 1 - Nc/Nd,
  required level: E <= 0,80 IV, <= 0,90 III, <= 0,95 II, <= 0,98 I (else I + extra measures).
  Mesh air termination, air rods at corners and next to roof equipment, down conductors
  at every real corner and at most `dc` apart along the perimeter, test joints 0,5 m above ground.
  Separation distance s = ki kc / km l, kc = 1/(2n) + 0,1 + 0,2 (c/h)^(1/3).
"""
import math
from shapely.geometry import Point, Polygon, LineString, box
from shapely.ops import unary_union, nearest_points
from shapely import affinity

import geo
from geo import m, U

RHO = 100.0          # soil resistivity (Ohm.m) - assumption, to be verified by measurement
NG = 3.0             # flashes / km2 / year (İzmir region ~ 30 thunderstorm days)
LPL = {  # level: (rolling sphere r, mesh, down conductor spacing, ki, efficiency)
    'I': (20, 5, 10, 0.08, 0.98), 'II': (30, 10, 10, 0.06, 0.95), 'III': (45, 15, 15, 0.04, 0.90), 'IV': (60, 20, 20, 0.04, 0.80)}


def real_corners(poly, min_edge=m(3.0), min_turn=20.0):
    pts = list(poly.simplify(m(1.5)).exterior.coords)[:-1]
    changed = True
    while changed and len(pts) > 3:
        changed = False
        for i in range(len(pts)):
            a, b, c = pts[i - 1], pts[i], pts[(i + 1) % len(pts)]
            e1 = math.hypot(b[0] - a[0], b[1] - a[1])
            e2 = math.hypot(c[0] - b[0], c[1] - b[1])
            t1 = math.atan2(b[1] - a[1], b[0] - a[0])
            t2 = math.atan2(c[1] - b[1], c[0] - b[0])
            turn = abs((math.degrees(t2 - t1) + 180) % 360 - 180)
            if turn < min_turn or min(e1, e2) < min_edge and turn < 60:
                pts.pop(i)
                changed = True
                break
    return pts


class EarthDesign:
    def __init__(self, b, elec, mech=None):
        self.b = b
        self.e = elec
        self.mech = mech
        self.run()

    def run(self):
        b, e = self.b, self.e
        zk = b.floor('ZK')
        ol = zk.outline
        # ------------------------------------------------ lightning risk
        H = b.h_top
        Ad = ol.buffer(m(3 * H), quad_segs=16).area / (U * U)
        Cd = 0.5
        Nd = NG * Ad * Cd * 1e-6
        Nc = 1.0e-3
        E = 1 - Nc / Nd if Nd > Nc else 0.0
        if Nd <= Nc:
            lvl, note = 'IV', 'Nd ≤ Nc: zorunlu değil, LPL IV önerilir'
        elif E <= 0.80:
            lvl, note = 'IV', ''
        elif E <= 0.90:
            lvl, note = 'III', ''
        elif E <= 0.95:
            lvl, note = 'II', ''
        elif E <= 0.98:
            lvl, note = 'I', ''
        else:
            lvl, note = 'I', 'E > 0,98: LPL I + ilave önlemler'
        r_s, mesh, dc, ki, eff = LPL[lvl]
        A_fp = ol.area / (U * U)
        self.risk = dict(A=A_fp, P=ol.exterior.length / U, H=H, Ad=Ad, Cd=Cd, Ng=NG, Nd=Nd, Nc=Nc, E=E, lvl=lvl, r=r_s,
                         mesh=mesh, dc=dc, ki=ki, eff=eff, note=note)
        # ------------------------------------------------ down conductors (arc length)
        olr = ol.exterior
        corners = real_corners(ol)
        tc = sorted(olr.project(Point(p)) for p in corners)
        if not tc:
            tc = [0.0]
        L = olr.length
        down = []
        for i, t0 in enumerate(tc):
            t1 = tc[(i + 1) % len(tc)] + (L if i == len(tc) - 1 else 0.0)
            run = t1 - t0
            k = max(1, math.ceil(run / m(dc) - 1e-6))
            for j in range(k):
                q = olr.interpolate((t0 + run * j / k) % L)
                down.append((q.x, q.y))
        # keep down conductors (test box + rod) out of exterior door openings
        ext_doors = []
        for d in zk.doors:
            if olr.distance(Point(d['x'], d['y'])) < m(0.5):
                ext_doors.append((olr.project(Point(d['x'], d['y'])), m(d.get('w', 1.0)) / 2 + m(0.3)))

        def in_door(t):
            for td, half in ext_doors:
                dd = (t - td + L / 2) % L - L / 2
                if abs(dd) < half:
                    return td, half, dd
            return None

        def slide(t):
            for _ in range(4):
                hit = in_door(t)
                if not hit:
                    break
                td, half, dd = hit
                t = (td + (half if dd >= 0 else -half)) % L
            return t
        ts_d = sorted(slide(olr.project(Point(p))) for p in down)
        for _ in range(40):
            gl = [((ts_d[(i + 1) % len(ts_d)] - ts_d[i]) % L, i) for i in range(len(ts_d))]
            g, i = max(gl)
            if g <= m(dc) + 1e-6:
                break
            ts_d = sorted(ts_d + [slide((ts_d[i] + g / 2) % L)])
        down = []
        for t in ts_d:
            q = olr.interpolate(t)
            if all(math.hypot(q.x - a[0], q.y - a[1]) > m(1.0) for a in down):
                down.append((q.x, q.y))
        self.down = down
        gaps = []
        ts = sorted(olr.project(Point(p)) for p in down)
        for i in range(len(ts)):
            gaps.append(((ts[(i + 1) % len(ts)] - ts[i]) % L) / U)
        c_max = max(gaps) if gaps else dc
        n = len(down)
        kc = 1.0 / (2 * n) + 0.1 + 0.2 * (c_max / H) ** (1.0 / 3.0)
        # outward normals at the down conductors (for symbol placement)
        self.down_n = []
        for (x, y) in down:
            t = olr.project(Point(x, y))
            p1, p2 = olr.interpolate(max(0, t - m(1))), olr.interpolate(min(L, t + m(1)))
            tx, ty = p2.x - p1.x, p2.y - p1.y
            tl = math.hypot(tx, ty) or 1
            nx, ny = -ty / tl, tx / tl
            if ol.contains(Point(x + nx * m(0.4), y + ny * m(0.4))):
                nx, ny = -nx, -ny
            self.down_n.append((nx, ny))
        # roof equipment (roof fans, VRF outdoor units if on roof) -> air rods + separation distance
        rox, roy = (b.roof_ofs if (b.roof is not None and b.roof_ofs is not None) else b.floors[-1].ofs)
        self.roof_key = 'CT' if (b.roof is not None and b.roof_ofs is not None) else b.floors[-1].key
        self.roof_ofs = (rox, roy)
        equip = []
        if self.mech is not None:
            for u in self.mech.units:
                if u.kind == 'CF':
                    equip.append((u.x, u.y))
        l_max = H
        for (x, y) in equip:
            dd = min(math.hypot(x - p[0], y - p[1]) for p in down) / U
            l_max = max(l_max, H + dd)
        self.risk.update(kc=kc, c=c_max, s=ki * kc / 1.0 * H, s_eq=ki * kc / 1.0 * l_max, l_eq=l_max, n=n)
        # ------------------------------------------------ air termination (roof plan)
        ang = geo.long_angle(ol)
        roof = affinity.translate(ol.buffer(m(0.3), join_style='mitre'), rox, roy)
        if roof.geom_type != 'Polygon':
            roof = max(roof.geoms, key=lambda g: g.area)
        self.roof = list(roof.exterior.coords)
        self.roof_mesh = geo.lines_clip(roof.buffer(-m(0.2)), m(mesh) * 0.98, ang)
        # keep >= s between the air conductors and the roof fans (housing r = 0,6 m): detour around them
        s_eq = self.risk['s_eq']
        keep = [Point(x + rox, y + roy).buffer(m(0.6 + s_eq + 0.05), quad_segs=8) for (x, y) in equip]
        if keep:
            self.roof_mesh = detour_all(self.roof_mesh, keep)
        rods = [(p[0] + rox, p[1] + roy) for p in corners]
        per = LineString(self.roof)
        nr = max(4, math.ceil(per.length / U / (2 * mesh)))
        for i in range(nr):
            q = per.interpolate(per.length * i / nr).coords[0]
            if all(math.hypot(q[0] - r[0], q[1] - r[1]) > m(3) for r in rods):
                rods.append(q)
        self.rods = rods
        self.equip_rods = []
        self.equip_links = []
        off = max(1.2, 0.6 + s_eq + 0.1)
        net = unary_union([LineString(self.roof)] + [LineString(sg) for sg in self.roof_mesh])
        for (x, y) in equip:
            for dx in (-1, 1):
                rp = (x + rox + dx * m(off), y + roy)
                self.equip_rods.append(rp)
                a, _ = nearest_points(net, Point(rp))
                if a.distance(Point(rp)) > m(0.05):
                    self.equip_links.append([(a.x, a.y), rp])
        # ------------------------------------------------ foundation earth
        ring = ol.buffer(-m(0.30), join_style='mitre')
        if ring.geom_type != 'Polygon':
            ring = max(ring.geoms, key=lambda g: g.area)
        self.ring = list(ring.exterior.coords)
        self.mesh = geo.lines_clip(ring, m(20.0) * 0.98, ang)
        strips = unary_union([LineString(self.ring)] + [LineString(sg) for sg in self.mesh])
        lugs = []
        if zk.columns:
            for (x, y, w, h) in zk.columns:
                if ring.buffer(m(0.6)).contains(Point(x, y)):
                    lugs.append(('KOLON', x, y))
        adp = e.panels['ADP']
        self.aeb = (adp.x + m(0.9) * math.cos(adp.ang - math.pi / 2), adp.y + m(0.9) * math.sin(adp.ang - math.pi / 2))
        lugs.append(('AEB', self.aeb[0], self.aeb[1]))
        self.rod_links = []
        for i, (x, y) in enumerate(down):
            q = ring.exterior.interpolate(ring.exterior.project(Point(x, y)))
            lugs.append(('INIS', q.x, q.y))
            nx, ny = self.down_n[i]
            self.rod_links.append([(q.x, q.y), (x + nx * m(1.2), y + ny * m(1.2))])
        # connecting strips from each lug to the nearest strip (DIN 18014)
        self.links = []
        for kind, x, y in lugs:
            pt = Point(x, y)
            if strips.distance(pt) > m(0.3):
                a, _ = nearest_points(strips, pt)
                self.links.append([(a.x, a.y), (x, y)])
        self.lugs = lugs
        self.yeb = []
        for f in b.floors:
            for r in f.rooms:
                if r.tip in ('WC', 'ABDEST', 'BANYO', 'MUTFAK', 'SOYUNMA') and r.A >= 1.4:
                    x, y, a = geo.wall_point(r.poly, (r.poly.centroid.x, r.poly.centroid.y - m(10)), m(0.12))
                    self.yeb.append((f.key, x, y, a, r.id))
        # ------------------------------------------------- resistance
        D = 1.13 * math.sqrt(A_fp)
        R_f = RHO / (2 * D)
        Lr, dr = 2.0, 0.02
        R_rod = RHO / (2 * math.pi * Lr) * math.log(4 * Lr / dr)
        R_tot = R_f      # rods at the test joints lie inside the potential funnel of the mesh -> not counted
        tx, ty = e.trafo_pt
        self.trafo_ring = [(tx - m(3), ty - m(2.5)), (tx + m(3), ty - m(2.5)), (tx + m(3), ty + m(2.5)), (tx - m(3), ty + m(2.5)), (tx - m(3), ty - m(2.5))]
        self.trafo_rods = self.trafo_ring[:4]
        corners_tr = sorted(self.trafo_rods, key=lambda c: ring.exterior.distance(Point(c)))
        c1 = corners_tr[0]
        c2 = next((c for c in corners_tr[1:] if math.hypot(c[0] - c1[0], c[1] - c1[1]) >= m(4.9)), corners_tr[1])
        q1 = ring.exterior.interpolate(ring.exterior.project(Point(c1)))
        q2 = ring.exterior.interpolate(ring.exterior.project(Point(c2)))
        if math.hypot(q1.x - q2.x, q1.y - q2.y) < m(3):
            t2 = ring.exterior.project(q1) + m(4)
            q2 = ring.exterior.interpolate(t2 % ring.exterior.length)
        self.trafo_links = [[c1, (q1.x, q1.y)], [c2, (q2.x, q2.y)]]
        D_tr = 1.13 * math.sqrt(30.0)
        R_ring_tr = 2 * RHO / (3 * D_tr)
        R_tr = 1 / (1 / R_ring_tr + 4 * 0.6 / R_rod)
        # the transformer ring lies ~3 m from the foundation ring (overlapping funnels): no parallel credit
        R_comb = R_tot
        # MV earth fault: U_E = I_F * R <= 2 U_Tp (TS EN 50522, t_F = 1 s -> U_Tp = 117 V); r = 1 (conservative)
        U_lim = 2 * 117.0
        I_F_max = U_lim / R_comb
        strip_len = (LineString(self.ring).length + sum(LineString(sg).length for sg in self.mesh) +
                     sum(LineString(l).length for l in self.links) + LineString(self.trafo_ring).length +
                     sum(LineString(l).length for l in self.trafo_links) +
                     sum(LineString(l).length for l in self.rod_links)) / U + 1.5 * len(lugs)
        air_len = (LineString(self.roof).length + sum(LineString(sg).length for sg in self.roof_mesh) +
                   sum(LineString(l).length for l in self.equip_links)) / U
        self.res = dict(rho=RHO, A=A_fp, D=D, R_f=R_f, R_rod=R_rod, nrod=len(down), R_tot=R_tot, R_tr=R_tr, R_comb=R_comb,
                        ok=R_comb <= 2.0, U_lim=U_lim, I_F_max=I_F_max, strip=strip_len, air=air_len, down_len=len(down) * H, clips=air_len + len(down) * H)


def _arc(ring, a, b, n=10):
    """shorter arc of a circle boundary between two points on it."""
    L = ring.length
    ta, tb = ring.project(Point(a)), ring.project(Point(b))
    d = (tb - ta) % L
    if d > L / 2:
        d -= L
    return [ring.interpolate((ta + d * i / n) % L).coords[0] for i in range(1, n)]


def detour(seg, C):
    ls = LineString(seg)
    if not ls.intersects(C):
        return [list(seg)]
    out = ls.difference(C)
    pieces = [g for g in (out.geoms if hasattr(out, 'geoms') else [out]) if g.length > 1.0]
    pieces.sort(key=lambda g: ls.project(Point(g.coords[0])))
    if not pieces:
        return []
    res = [list(pieces[0].coords)]
    for g in pieces[1:]:
        res[-1] += _arc(C.exterior, res[-1][-1], g.coords[0]) + list(g.coords)
    return res


def detour_all(segs, circles):
    for C in circles:
        nxt = []
        for sg in segs:
            nxt += detour(sg, C)
        segs = nxt
    return segs
