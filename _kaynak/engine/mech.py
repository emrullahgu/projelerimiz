"""CLD engine - mechanical design (HVAC).

Offices / lobby / mescit: VRF heat-pump system (4-way cassettes), heat-recovery
fresh air units (EN 16798-1 cat. II, 10 l/s per person), WC/abdesthane exhaust.
Production halls: mechanical roof exhaust (3 ACH) with fresh-air louvres and
natural-gas radiant tube heaters (Ti = 16 C). Climate: İzmir, To = 0 C (TS 825 / TS 2164),
summer 35 C DB.
"""
import math
from dataclasses import dataclass, field
from shapely.geometry import Point

import geo
from geo import m, U
from elec import pick

TO_WINTER = 0.0
U_WALL, U_ROOF, U_FLOOR, U_WIN = 0.60, 0.40, 0.60, 2.10      # W/m2K (TS 825 İzmir, double glazing)
U_PANEL = 0.45                                                 # sandwich panel envelope of halls
COOL_Q = {'OFIS': 140, 'TOPLANTI': 160, 'GIRIS': 120, 'MESCIT': 130, 'LAB': 150, 'YEMEK': 150, 'GENEL': 110}
TI = {'OFIS': 22, 'TOPLANTI': 22, 'GIRIS': 20, 'MESCIT': 22, 'LAB': 22, 'YEMEK': 22, 'GENEL': 20,
      'WC': 20, 'ABDEST': 22, 'BANYO': 24, 'SOYUNMA': 22, 'HOL': 18, 'MUTFAK': 20}
PERSON_M2 = {'OFIS': 10.0, 'TOPLANTI': 2.5, 'GIRIS': 10.0, 'MESCIT': 1.5, 'LAB': 10.0, 'YEMEK': 1.5, 'GENEL': 15.0}
VRF_IN = [2.2, 2.8, 3.6, 4.5, 5.6, 7.1, 9.0, 11.2, 14.0]
VRF_OUT = [8.0, 10.0, 12.1, 14.0, 22.4, 28.0, 33.5, 40.0, 45.0, 50.4, 56.0, 61.5, 68.0, 73.0, 80.0, 85.0, 90.0, 96.0, 101.0, 112.0, 123.5, 135.0]
HRV = [300, 500, 800, 1000, 1500, 2000, 2500, 3000, 4000, 5000]
FAN = [100, 150, 250, 400, 600, 1000, 1500, 2000]
RT_KW = [10, 15, 20, 25, 30, 40]
R410A_LIM = 0.44          # kg/m3 practical limit, TS EN 378-1 Annex C


def tg(x):
    return f'{x:g}'.replace('.', ',')


@dataclass
class Unit:
    x: float
    y: float
    ang: float
    kind: str      # VRF, DIF (supply), EMI (exhaust grille), FAN, RT (radiant), CF (roof fan), LV (louvre), OU (outdoor), HRV
    blk: str
    label: str
    room: str
    floor: str
    cap: float = 0.0


class MechDesign:
    def __init__(self, b, elec=None):
        self.b = b
        self.units = []
        self.rows = []         # per room load table
        self.halls = []
        self.ducts = []        # (floor, layer key, pts)
        self.pipes = []        # refrigerant pipe routes (floor, pts)
        self.sum = {}
        self.run()

    def ext_len(self, f, r):
        """facade length of a room: building outline inside the room's 1,2 m buffer (clamped)."""
        ol = f.outline.exterior
        g = ol.intersection(r.poly.buffer(m(1.2)))
        Lx = max(0.0, g.length / U - 2 * 1.2) if not g.is_empty else 0.0
        return min(Lx, 0.5 * r.poly.length / U)

    def heat_loss(self, f, r, Ti):
        dT = Ti - TO_WINTER
        Lx = self.ext_len(f, r)
        h = max(r.h, 2.7) + 0.5
        Aw = Lx * h
        Awin = 0.30 * Aw
        Q = U_WALL * (Aw - Awin) * dT + U_WIN * Awin * dT
        top = (f.key == self.b.floors[-1].key) or (f.key == 'ZK' and r.above is None)
        if top:
            Q += U_ROOF * r.A * dT
        if f.key == 'ZK':
            Q += U_FLOOR * r.A * 0.5 * dT
        Q += 0.34 * 0.5 * r.A * r.h * dT
        return Q * 1.10, Lx

    def vent_heat(self, fresh, dT):
        """residual fresh-air heating after the heat-recovery unit (eta 0,75)."""
        return 0.34 * fresh * dT * (1 - 0.75)

    def run(self):
        b = self.b
        vrf_total = 0.0
        heat_total = 0.0
        fresh_by_floor = {}
        exh_by_floor = {}
        for f in b.floors:
            for r in f.rooms:
                t = r.tip
                if t in COOL_Q and not (t == 'GENEL' and r.A < 6.0):
                    Qc = COOL_Q[t] * r.A
                    Qh, Lx = self.heat_loss(f, r, TI.get(t, 20))
                    pers = max(1, math.ceil(r.A / PERSON_M2.get(t, 10.0)))
                    fresh = (7.0 * pers + 0.7 * r.A) * 3.6        # TS EN 16798-1 cat. II, low-polluting
                    Qh += self.vent_heat(fresh, TI.get(t, 20) - TO_WINTER)
                    need = max(Qc, Qh / 1.1) / 1000.0
                    n = max(1, math.ceil(need / 7.1))
                    cap = pick(need / n, VRF_IN)
                    mx, my, Mx, My = r.poly.bounds
                    pts = geo.grid_points(r.poly, n, min(m(1.0), 0.25 * min(Mx - mx, My - my)))[:n]
                    for (x, y) in pts:
                        self.units.append(Unit(x, y, 0.0, 'VRF', 'CLD_S_KASET', f'{tg(cap)} kW', r.id, f.key, cap))
                    nd = max(1, math.ceil(fresh / 250.0))
                    for i, (x, y) in enumerate(geo.grid_points(r.poly, nd, min(m(0.8), 0.25 * min(Mx - mx, My - my)))[:nd]):
                        self.units.append(Unit(x + m(0.7), y + m(0.5), 0.0, 'DIF', 'CLD_S_MENFEZ', f'{fresh / nd:.0f} m³/h', r.id, f.key))
                        self.units.append(Unit(x - m(0.7), y - m(0.5), 0.0, 'EMI', 'CLD_S_EMIS', f'{fresh / nd:.0f} m³/h', r.id, f.key))
                    fresh_by_floor[f.key] = fresh_by_floor.get(f.key, 0.0) + fresh
                    vrf_total += n * cap
                    heat_total += Qh
                    self.rows.append(dict(room=r, Qc=Qc, Qh=Qh, Lx=Lx, n=n, cap=cap, pers=pers, fresh=fresh, kind='VRF'))
                elif t in ('WC', 'ABDEST', 'BANYO', 'SOYUNMA', 'MUTFAK'):
                    V = r.A * r.h
                    nfix = 1 + (1 if t == 'ABDEST' else 0)
                    q = max(10 * V, 50.0 * nfix)
                    c = r.poly.representative_point()
                    self.units.append(Unit(c.x, c.y, 0.0, 'WCE', 'CLD_S_EMIS', f'{q:.0f} m³/h', r.id, f.key))
                    exh_by_floor[f.key] = exh_by_floor.get(f.key, 0.0) + q
                    self.rows.append(dict(room=r, Qc=0, Qh=0, Lx=0, n=0, cap=0, pers=0, fresh=0, exh=q, kind='EXH'))
                elif t == 'SIGINAK':
                    c = r.poly.representative_point()
                    pers = max(1, math.floor(r.A / 1.0))
                    self.units.append(Unit(c.x, c.y, 0.0, 'FAN', 'CLD_S_SIGFAN', 'Sığınak havalandırma cihazı + kum filtresi', r.id, f.key))
                    self.rows.append(dict(room=r, Qc=0, Qh=0, Lx=0, n=0, cap=0, pers=pers, fresh=0, exh=0, kind='SIG'))
        # per-floor central units placed at the office core
        self.hrv = {}
        for fk, q in fresh_by_floor.items():
            f = b.floor(fk)
            core = [r for r in f.rooms if r.tip in ('GIRIS', 'HOL')] or [r for r in f.rooms if r.tip not in ('URETIM', 'DEPOH')]
            hub = max(core, key=lambda r: r.A)
            c0 = hub.poly.representative_point()
            x, y, a = c0.x, c0.y, 0.0
            size = pick(q * 1.1, HRV)
            self.hrv[fk] = size
            self.units.append(Unit(x, y, a, 'HRV', 'CLD_S_HRV', f'HRV {size} m³/h', hub.id, fk, size))
            # duct mains: from HRV to every supply diffuser of the floor (orthogonal)
            for u in self.units:
                if u.floor == fk and u.kind == 'DIF':
                    self.ducts.append((fk, 'SUP', geo.ortho((x, y), (u.x, u.y))))
                if u.floor == fk and u.kind == 'EMI':
                    self.ducts.append((fk, 'EXH', geo.ortho((x + m(0.4), y), (u.x, u.y))))
        self.exh_fans = {}
        for fk, q in exh_by_floor.items():
            self.exh_fans[fk] = pick(q * 1.1, FAN)
            f = b.floor(fk)
            wet = [u for u in self.units if u.floor == fk and u.kind == 'WCE']
            if not wet:
                continue
            cx = sum(u.x for u in wet) / len(wet)
            cy = sum(u.y for u in wet) / len(wet)
            # fan on a facade stretch that borders a wet room (never inside a hall / mescit / lobby),
            # otherwise inside the wet room with a roof / shaft discharge
            from shapely.ops import unary_union
            wet_rooms = [r for r in f.rooms if r.id in {u.room for u in wet}]
            band = unary_union([r.poly.buffer(m(1.2)) for r in wet_rooms])
            g = f.outline.exterior.intersection(band)
            if not g.is_empty and g.length > m(0.6):
                qf = g.interpolate(g.project(Point(cx, cy)))
                host = min(wet_rooms, key=lambda r: r.poly.distance(qf))
                ip = host.poly.buffer(-m(0.3))
                ip = ip if (not ip.is_empty and ip.geom_type == 'Polygon') else host.poly
                q2 = ip.exterior.interpolate(ip.exterior.project(qf))
                fx, fy = q2.x, q2.y
                lbl = f'WC egzoz fanı {self.exh_fans[fk]} m³/h (cepheye atış)'
            else:
                host = max(wet_rooms, key=lambda r: r.A)
                c2 = host.poly.representative_point()
                fx, fy = c2.x, c2.y
                lbl = f'WC egzoz fanı {self.exh_fans[fk]} m³/h (şaft / çatıya atış)'
            self.units.append(Unit(fx, fy, 0.0, 'FAN', 'CLD_S_SIGFAN', lbl, host.id, fk))
            for u in wet:
                self.ducts.append((fk, 'WCE', geo.ortho((fx, fy), (u.x, u.y))))
        # VRF outdoor units: one per cluster of conditioned rooms (rooms > 25 m apart -> separate system)
        zk = b.floor('ZK')
        self.vrf_out = []
        self.comb = []
        self.refr = []
        vrf_units = [u for u in self.units if u.kind == 'VRF']
        clusters = []
        for u in vrf_units:
            fl = b.floor(u.floor)
            pz = fl.to_zk((u.x, u.y))
            for cl in clusters:
                if any(math.hypot(pz[0] - q[0], pz[1] - q[1]) < m(25.0) for q in cl['pts']):
                    cl['pts'].append(pz)
                    cl['units'].append(u)
                    break
            else:
                clusters.append(dict(pts=[pz], units=[u]))
        ol = zk.outline
        cen = ol.centroid
        for ci, cl in enumerate(clusters):
            cx = sum(p[0] for p in cl['pts']) / len(cl['pts'])
            cy = sum(p[1] for p in cl['pts']) / len(cl['pts'])
            q = ol.exterior.interpolate(ol.exterior.project(Point(cx, cy)))
            vx, vy = q.x - cen.x, q.y - cen.y
            L = math.hypot(vx, vy) or 1
            ox, oy = q.x + vx / L * m(2.5), q.y + vy / L * m(2.5)
            tot_in = sum(u.cap for u in cl['units'])
            need = tot_in * 0.85
            caps = []
            if tot_in < 7.0:
                # too small for VRF -> split / multi-split heat pump (combination ratio would be < 50 %)
                kind_txt = 'Multi-split dış ünite'
                caps = [pick(tot_in * 1.0, [3.5, 5.0, 6.8, 8.0])]
            else:
                kind_txt = 'VRF dış ünite'
                rest = need
                while rest > 0:
                    c = pick(min(rest, 101.0), VRF_OUT)
                    caps.append(c)
                    rest -= c
            self.comb.append((ci + 1, tot_in, sum(caps), tot_in / max(sum(caps), 0.1)))
            for i, c in enumerate(caps):
                self.units.append(Unit(ox + i * m(1.6), oy, 0.0, 'OU', 'CLD_S_VRFOUT', f'{kind_txt} {tg(c)} kW (sistem {ci + 1})', '', 'ZK', c))
            n_pipe0 = len(self.pipes)
            self.vrf_out += caps
            for u in cl['units']:
                fl = b.floor(u.floor)
                if u.floor == 'ZK':
                    self.pipes.append(('ZK', geo.ortho((ox, oy), (u.x, u.y))))
                else:
                    riser = fl.from_zk((q.x, q.y))
                    self.pipes.append((u.floor, geo.ortho(riser, (u.x, u.y))))
            if any(u.floor != 'ZK' for u in cl['units']):
                self.pipes.append(('ZK', [(ox, oy), (q.x, q.y)]))
            # refrigerant concentration (TS EN 378-1): factory + additional charge vs. smallest served room
            Lp = sum(geo.path_len(pp) for (_, pp) in self.pipes[n_pipe0:]) / U
            Lp += sum(b.floor(u.floor).kot for u in cl['units'] if u.floor != 'ZK')
            charge = 0.15 * sum(caps) + 0.07 * Lp
            served = {}
            for u in cl['units']:
                rr = next((r for r in b.floor(u.floor).rooms if r.id == u.room), None)
                if rr is not None:
                    served[rr.id] = rr
            small = min(served.values(), key=lambda r: r.A * r.h) if served else None
            Vs = small.A * small.h if small else 0.0
            conc = charge / Vs if Vs else 0.0
            self.refr.append(dict(sys=ci + 1, charge=charge, Lp=Lp, room=small.name if small else '-', V=Vs, c=conc,
                                  ok=conc <= R410A_LIM))
        vrf_total = sum(u.cap for u in vrf_units)
        # production halls
        for r in zk.rooms:
            if r.tip not in ('URETIM', 'DEPOH'):
                continue
            V = r.A * r.h
            ach = 3.0
            Q = ach * V
            fan = 12000.0
            n = max(2, math.ceil(Q / fan))
            pts = geo.grid_points(r.poly, n, m(4.0))[:n]
            roof_pts = pts
            for (x, y) in pts:
                self.units.append(Unit(x, y, 0.0, 'CF', 'CLD_S_CATIFAN', f'{fan:.0f} m³/h', r.id, 'ZK', fan))
            av = [(d['x'], d['y']) for d in zk.doors]
            # louvres: free-area velocity <= 2,2 m/s, 1200x800 louvre ~0,45 m2 free area; only on the hall
            # facade walls (hall boundary within 1 m of the building outline), away from doors
            lv_size, lv_free = '1200x800', 0.45
            n_lv = max(n, math.ceil((Q / 3600.0) / (2.2 * lv_free)))
            facade = r.poly.exterior.intersection(zk.outline.exterior.buffer(m(1.0)))
            fl_len = facade.length / U if not facade.is_empty else 0.0
            if fl_len < n_lv * 3.0:
                lv_size, lv_free = '1600x1200', 0.85
                n_lv = max(n, math.ceil((Q / 3600.0) / (2.2 * lv_free)))
            segs = []
            if fl_len:
                segs = [g for g in (facade.geoms if hasattr(facade, 'geoms') else [facade])
                        if g.geom_type == 'LineString' and g.length > m(2.0)]
            lv_pts = []
            if segs:
                tot = sum(g.length for g in segs)
                for i in range(n_lv):
                    d = tot * (i + 0.5) / n_lv
                    g = segs[-1]
                    for g_ in segs:
                        if d <= g_.length:
                            g = g_
                            break
                        d -= g_.length
                    d = min(d, g.length)
                    dd = d
                    for k_ in range(8):
                        dd = (d + k_ * m(1.5)) % g.length
                        p = g.interpolate(dd)
                        if all(math.hypot(p.x - ax, p.y - ay) >= m(3.0) for (ax, ay) in av):
                            break
                    p = g.interpolate(dd)
                    p1 = g.interpolate(max(0.0, dd - m(0.5)))
                    p2 = g.interpolate(min(g.length, dd + m(0.5)))
                    a = math.atan2(p2.y - p1.y, p2.x - p1.x) + math.pi / 2
                    if not r.poly.contains(Point(p.x + math.cos(a) * m(0.4), p.y + math.sin(a) * m(0.4))):
                        a += math.pi
                    lv_pts.append((p.x + math.cos(a) * m(0.2), p.y + math.sin(a) * m(0.2), a))
            else:
                lv_pts = geo.perimeter_points(r.poly, n_lv, m(0.2), av, m(3.0))
            for (x, y, a) in lv_pts:
                self.units.append(Unit(x, y, a, 'LV', 'CLD_S_PANJUR', f'Taze hava panjuru {lv_size}', r.id, 'ZK'))
            v_lv = (Q / 3600.0) / (len(lv_pts) * lv_free) if lv_pts else 0.0
            # heating (Ti 16 C)
            Ti = 16.0
            dT = Ti - TO_WINTER
            Lx = self.ext_len(zk, r)
            Aw = Lx * (self.b.h_eave + 1.0)
            # winter: roof fans on low speed / interlocked, 0,7 1/h total air change (infiltration + minimum fresh air)
            Qh = (U_PANEL * Aw + U_ROOF * r.A * 1.05 + U_FLOOR * 0.5 * r.A * 0.4) * dT + 0.34 * 0.7 * V * dT
            Qh *= 1.10
            # coverage: one tube heater per <= 180 m2; unit size from the heat loss (+15 %)
            nh = max(2, math.ceil(r.A / 180.0))
            if Qh / 1000.0 / nh * 1.15 > RT_KW[-1]:
                nh = math.ceil(Qh / 1000.0 * 1.15 / RT_KW[-1])
            unit_kw = pick(Qh / 1000.0 / nh * 1.15, RT_KW)
            ang = geo.long_angle(r.poly)
            heaters = geo.grid_points(r.poly, nh, m(5.0))[:nh]
            for (x, y) in heaters:
                self.units.append(Unit(x + m(1.5), y + m(1.5), ang, 'RT', 'CLD_S_RADYANT', f'Radyant tüp ısıtıcı {tg(unit_kw)} kW', r.id, 'ZK', unit_kw))
            self.halls.append(dict(room=r, V=V, ach=ach, Q=Q, fan=fan, n=n, Qh=Qh, nh=nh, unit_kw=unit_kw, Lx=Lx, n_lv=len(lv_pts),
                                   lv_size=lv_size, v_lv=v_lv, q_win=0.7 * V))
        # electrical demand of mechanical plant (kW) -> MKP
        kw = sum(self.vrf_out) / 3.3 if self.vrf_out else 0.0
        kw += sum(0.0008 * s for s in self.hrv.values()) + sum(0.12 for _ in self.exh_fans)
        kw += sum(h['n'] * 1.5 + h['nh'] * 0.15 for h in self.halls)
        self.sum = dict(vrf_in=vrf_total, vrf_out=self.vrf_out, heat=heat_total, hrv=self.hrv, exh=self.exh_fans, kw=kw, comb=self.comb, refr=self.refr)
