"""CLD engine - room extraction.

Rooms are the free-space faces between walls (plan frame minus buffered wall lines).
Wall gaps (open doors, missing panel lines) are closed progressively with larger
buffer radii; for each room label the radius whose face area best matches the
architect's m² label is chosen. Labels left without a face (open halls) share the
residual building area (outline minus found rooms) by Voronoi partition; small
unenclosed rooms get a labelled-area box. Overlaps are carved from the larger room.
"""
import math
import re

from shapely.geometry import Polygon, Point, box, MultiPoint
from shapely.ops import unary_union, voronoi_diagram
from shapely.strtree import STRtree

RADII = (2.5, 8.0, 18.0, 35.0, 60.0, 90.0)
HALL = re.compile(r'ÜRET|URET|DEPO|İMALAT|FABR|ATÖLYE|SEVK|AMBAR|^HOL\b', re.I)


def make_seeds(arch, plan, is_room_label, parse_area):
    T = [t for t in arch.d.texts if plan.bbox[0] <= t['cx'] <= plan.bbox[2] and plan.bbox[1] <= t['cy'] <= plan.bbox[3]]
    names = [t for t in T if is_room_label(t) and t['h'] >= 15]
    areas = [t for t in T if parse_area(t['s']) is not None and t['h'] >= 10]

    def dd(lst):
        out = []
        for t in lst:
            if not any(o['s'] == t['s'] and abs(o['cx'] - t['cx']) < 20 and abs(o['cy'] - t['cy']) < 20 for o in out):
                out.append(t)
        return out
    names, areas = dd(names), dd(areas)
    plan.labels = names + areas
    # merge vertically stacked name parts ("JENARATÖR" / "ODASI", "LOBİ" / "BEKLEME")
    used = set()
    groups = []
    srt = sorted(names, key=lambda t: -t['cy'])
    for t in srt:
        if id(t) in used:
            continue
        g = [t]
        used.add(id(t))
        for u in srt:
            if id(u) in used:
                continue
            last = g[-1]
            if abs(u['cx'] - last['cx']) < 2.0 * last['h'] and 0 < last['cy'] - u['cy'] < 1.9 * last['h'] \
                    and abs(u['h'] - last['h']) < 0.5 and not re.search(r'WC|MESC', u['s']) \
                    and re.match(r'^(ODASI|HOLÜ|HOLU|BEKLEME|ALANI|DEPOSU|MERDİVENİ|GİRİŞ)$', u['s'].strip(), re.I):
                g.append(u)
                used.add(id(u))
        groups.append(g)
    # global greedy name<->area pairing (area label sits just below its name)
    pairs = []
    for gi, g in enumerate(groups):
        last = g[-1]
        for ai, a in enumerate(areas):
            dx = abs(a['cx'] - last['cx'])
            dy = last['cy'] - a['cy']
            if dx < max(300, 3 * last['h']) and -3.0 * last['h'] < dy < 4 * last['h'] + 60:
                cost = dx + 2.0 * abs(dy - 1.2 * last['h'])
                pairs.append((cost, gi, ai))
    pairs.sort()
    g2a, used_a = {}, set()
    for cost, gi, ai in pairs:
        if gi in g2a or ai in used_a:
            continue
        g2a[gi] = ai
        used_a.add(ai)
    seeds = []
    for gi, g in enumerate(groups):
        nm = ' '.join(x['s'] for x in g)
        pts = [(x['cx'], x['cy']) for x in g]
        lab = None
        if gi in g2a:
            a = areas[g2a[gi]]
            lab = parse_area(a['s'])
            pts.append((a['cx'], a['cy']))
            for aj, b in enumerate(areas):
                if aj not in used_a and 'Net' in b['s'] and abs(b['cx'] - a['cx']) < 300 and 0 < a['cy'] - b['cy'] < 120:
                    lab = parse_area(b['s'])
                    used_a.add(aj)
        seeds.append(dict(name=nm, label_area=lab, pts=pts, label=g[0]))
    for ai, a in enumerate(areas):
        if ai not in used_a:
            seeds.append(dict(name='', label_area=parse_area(a['s']), pts=[(a['cx'], a['cy'])], label=a))
    return seeds


def _faces(walls, frame, u2):
    free = frame.difference(walls)
    comps = list(free.geoms) if hasattr(free, 'geoms') else [free]
    fb = frame.exterior
    faces = [c for c in comps if c.area > 0.25 * u2 and c.exterior.distance(fb) > 1.0]
    outside = [c for c in comps if c.exterior.distance(fb) <= 1.0]
    return faces, outside


def _poly1(g):
    if g.is_empty:
        return g
    if g.geom_type != 'Polygon':
        g = max(g.geoms, key=lambda x: x.area)
    return g


def extract_rooms(arch, plan, lines, seeds, env_lines=None):
    u2 = arch.u * arch.u
    frame = box(*plan.bbox)
    L = {}
    for r in RADII:
        walls = unary_union([ln.buffer(r, quad_segs=2) for ln in lines])
        faces, outside = _faces(walls, frame, u2)
        L[r] = (faces, STRtree(faces) if faces else None)
    # building outline: morphological closing of the wall set (closes gaps up to 6 m)
    plan.outline = None
    env = env_lines if env_lines else lines
    if env:
        for R in (500.0, 300.0, 150.0):
            walls = unary_union([ln.buffer(R, quad_segs=4) for ln in env])
            faces, outside = _faces(walls, frame, u2)
            inner = frame.difference(unary_union(outside)) if outside else frame
            ol = _poly1(inner.buffer(-R, quad_segs=4).buffer(0))
            if not ol.is_empty and ol.area > 50 * u2:
                plan.outline = Polygon(ol.exterior).simplify(5.0)
                break
    if plan.outline is None:
        plan.outline = frame

    def face_at(r, pts):
        faces, tree = L[r]
        if tree is None:
            return None
        for (px, py) in pts:
            pt = Point(px, py)
            c = [faces[i] for i in tree.query(pt) if faces[i].contains(pt)]
            if c:
                return c[0]
        return None

    choice = {}
    for si, sd in enumerate(seeds):
        lab = sd['label_area']
        hall = bool(HALL.search(sd['name'])) or (lab or 0) > 150
        opts = []
        for ri, r in enumerate(RADII):
            f = face_at(r, sd['pts'])
            if f is None:
                continue
            poly = _poly1(f.buffer(r, join_style='mitre', mitre_limit=3.0).simplify(2.0))
            A = poly.area / u2
            others = [sj for sj, so in enumerate(seeds) if sj != si and any(f.contains(Point(p)) for p in so['pts'])]
            bigger = [sj for sj in others if (seeds[sj]['label_area'] or 0) > (lab or 0) or
                      (HALL.search(seeds[sj]['name']) and not hall)]
            if bigger:
                continue
            err = abs(A - lab) / max(lab, 0.5) if lab else 0.0
            if not lab and not hall and A > 150:
                continue
            opts.append((err + 0.015 * ri, ri, poly, A, err))
            if lab and err < 0.04:
                break
            if not lab and not others:
                break
        opts.sort(key=lambda o: o[0])
        good = [o for o in opts if not lab or o[4] <= 0.45]
        choice[si] = good[0] if good else None

    rooms = {}
    for si, o in choice.items():
        if o is None:
            continue
        sd = seeds[si]
        rooms[si] = dict(name=sd['name'], label_area=sd['label_area'], area=o[3], poly=o[2], label=sd['label'],
                         fit='OK' if (not sd['label_area'] or o[4] <= 0.15) else 'SAPMA', r=RADII[o[1]], seed=sd['pts'][0])
    # merged clusters: one face holding several unmatched labelled rooms whose label
    # areas add up to the face area -> Voronoi split of that face
    for r in RADII:
        faces = L[r][0]
        free_s = [si for si in choice if choice[si] is None and si not in rooms]
        if not free_s:
            break
        for f in faces:
            ins = [si for si in free_s if f.contains(Point(seeds[si]['pts'][0]))]
            if len(ins) < 2:
                continue
            S = sum((seeds[si]['label_area'] or 4.0) for si in ins)
            fpoly = _poly1(f.buffer(r, join_style='mitre', mitre_limit=3.0))
            FA = fpoly.area / u2
            if abs(FA - S) / S > 0.35:
                continue
            pts = [Point(seeds[si]['pts'][0]) for si in ins]
            vd = voronoi_diagram(MultiPoint(pts), envelope=fpoly.envelope.buffer(20 * arch.u))
            for si, pt in zip(ins, pts):
                for cell in vd.geoms:
                    if cell.contains(pt):
                        pg = _poly1(cell.intersection(fpoly))
                        if not pg.is_empty:
                            sd = seeds[si]
                            rooms[si] = dict(name=sd['name'], label_area=sd['label_area'], area=pg.area / u2, poly=pg.simplify(2.0),
                                             label=sd['label'], fit='BOLUNMUS', r=r, seed=sd['pts'][0])
                        break
            free_s = [si for si in free_s if si not in rooms]
    # residual building space for unmatched seeds
    unmatched = [si for si in choice if choice[si] is None and si not in rooms]
    if unmatched:
        taken = unary_union([r['poly'].buffer(3.0) for r in rooms.values()]) if rooms else None
        resid = plan.outline.difference(taken) if taken is not None else plan.outline
        comps = list(resid.geoms) if hasattr(resid, 'geoms') else [resid]
        comps = [c for c in comps if c.area > 0.5 * u2]
        groups = {}
        for si in unmatched:
            pt = Point(seeds[si]['pts'][0])
            for ci, c in enumerate(comps):
                if c.contains(pt) or c.distance(pt) < 30:
                    groups.setdefault(ci, []).append(si)
                    break
        for ci, sis in groups.items():
            c = comps[ci]
            ca = c.area / u2
            minors = [si for si in sis if not (HALL.search(seeds[si]['name']) or (seeds[si]['label_area'] or 0) >= 0.15 * ca)]
            majors = [si for si in sis if si not in minors]
            # minor rooms: labelled-area boxes clipped to the component
            for si in minors:
                sd = seeds[si]
                lab = sd['label_area'] or 4.0
                a = math.sqrt(lab) * arch.u / 2
                px, py = sd['pts'][0]
                pg = _poly1(box(px - a, py - a, px + a, py + a).intersection(c))
                if pg.is_empty or pg.area < 0.5 * lab * u2:
                    pg = box(px - a, py - a, px + a, py + a)
                rooms[si] = dict(name=sd['name'], label_area=sd['label_area'], area=pg.area / u2, poly=pg, label=sd['label'],
                                 fit='YAKLASIK', r=None, seed=sd['pts'][0])
            if not majors:
                continue
            cc = c
            if minors:
                cc = _poly1(c.difference(unary_union([rooms[si]['poly'].buffer(3.0) for si in minors])))
            if len(majors) == 1:
                cells = {majors[0]: cc}
            else:
                pts = [Point(seeds[si]['pts'][0]) for si in majors]
                vd = voronoi_diagram(MultiPoint(pts), envelope=cc.envelope.buffer(20 * arch.u))
                cells = {}
                for si, pt in zip(majors, pts):
                    for cell in vd.geoms:
                        if cell.contains(pt):
                            cells[si] = _poly1(cell.intersection(cc))
                            break
            for si, pg in cells.items():
                sd = seeds[si]
                if pg is None or pg.is_empty:
                    continue
                lab = sd['label_area']
                if lab and not HALL.search(sd['name']) and pg.area / u2 > 1.6 * lab:
                    a = math.sqrt(lab) * arch.u / 2
                    px, py = sd['pts'][0]
                    bx = _poly1(box(px - a, py - a, px + a, py + a).intersection(pg))
                    pg = bx if (not bx.is_empty and bx.area > 0.5 * lab * u2) else box(px - a, py - a, px + a, py + a)
                A = pg.area / u2
                lab = sd['label_area']
                rooms[si] = dict(name=sd['name'], label_area=lab, area=A, poly=pg.simplify(3.0), label=sd['label'],
                                 fit='BOLUNMUS' if (not lab or abs(A - lab) / lab <= 0.25) else 'SAPMA', r=None,
                                 seed=sd['pts'][0])
        for si in unmatched:
            if si not in rooms:
                sd = seeds[si]
                lab = sd['label_area'] or 4.0
                a = math.sqrt(lab) * arch.u / 2
                px, py = sd['pts'][0]
                rooms[si] = dict(name=sd['name'], label_area=sd['label_area'], area=lab, poly=box(px - a, py - a, px + a, py + a),
                                 label=sd['label'], fit='YAKLASIK', r=None, seed=sd['pts'][0])
    out = sorted(rooms.values(), key=lambda r: r['poly'].area)
    # carve smaller rooms out of larger ones
    for i, big in enumerate(out):
        cut = [s['poly'] for s in out[:i] if s['poly'].intersects(big['poly'])
               and s['poly'].intersection(big['poly']).area > 0.3 * s['poly'].area]
        if cut:
            pg = _poly1(big['poly'].difference(unary_union(cut).buffer(1.0)))
            if not pg.is_empty and pg.area > 0.3 * big['poly'].area:
                big['poly'] = pg
                big['area'] = pg.area / u2
    hull = plan.outline.buffer(3 * arch.u)
    return [r for r in out if hull.contains(Point(r['seed']))]
