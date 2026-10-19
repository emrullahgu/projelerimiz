"""CLD engine - geometry helpers on shapely polygons (plan coordinates, cm)."""
import math
from shapely.geometry import Polygon, Point, LineString, box
from shapely.ops import unary_union, nearest_points
from shapely import affinity

U = 100.0   # drawing units per metre


def m(x):
    return x * U


def ccw(poly):
    from shapely.geometry.polygon import orient
    return orient(poly, 1.0)


def grid_points(poly, n, margin):
    """n luminaire points on a regular grid inside poly (keeps >= margin to the walls).
    Tries the grid arrangements closest to n first (n <= cols*rows <= 1.25 n) so the layout
    neither falls short nor overshoots."""
    if n <= 0:
        return []
    inner = poly.buffer(-margin)
    if inner.is_empty or inner.area < 1:
        inner = poly.buffer(-margin / 3)
    if inner.is_empty:
        c = poly.representative_point()
        return [(c.x, c.y)]
    mrr = poly.minimum_rotated_rectangle
    cs = list(mrr.exterior.coords)[:4]
    e1 = (cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
    e2 = (cs[2][0] - cs[1][0], cs[2][1] - cs[1][1])
    L1, L2 = math.hypot(*e1), math.hypot(*e2)
    if L1 < L2:
        e1, e2, L1, L2 = e2, e1, L2, L1
    ang = math.atan2(e1[1], e1[0])
    c = poly.centroid
    ri = affinity.rotate(inner, -ang, origin=c, use_radians=True)
    rp = affinity.rotate(poly, -ang, origin=c, use_radians=True)
    x0, y0, x1, y1 = rp.bounds
    W, H = max(x1 - x0, 1), max(y1 - y0, 1)

    def layout(cols, rows):
        pts = []
        for j in range(rows):
            for i in range(cols):
                x = x0 + (i + 0.5) * W / cols
                y = y0 + (j + 0.5) * H / rows
                if ri.contains(Point(x, y)):
                    pts.append((x, y))
        return pts
    best = None
    cands = []
    for cols in range(1, max(2, n) + 2):
        rows = max(1, math.ceil(n / cols))
        for rr in (rows, rows + 1):
            if cols * rr <= max(n + 2, 1.6 * n):
                cands.append((cols, rr))
    # prefer square-ish cells, then fewest extra points
    cands.sort(key=lambda cr: (abs(math.log((W / cr[0]) / (H / cr[1]))), cr[0] * cr[1]))
    for cols, rows in cands[:40]:
        pts = layout(cols, rows)
        if len(pts) >= n and (best is None or len(pts) < len(best) or
                              (len(pts) == len(best) and abs(math.log((W / cols) / (H / rows))) < best_r)):
            best = pts
            best_r = abs(math.log((W / cols) / (H / rows)))
            if len(pts) <= 1.15 * n + 1:
                break
    if best is None:
        cols = max(1, round(math.sqrt(n * W / H)))
        rows = max(1, math.ceil(n / cols))
        for it in range(40):
            best = layout(cols, rows)
            if len(best) >= n:
                break
            if W / cols >= H / rows:
                cols += 1
            else:
                rows += 1
    if not best:
        p = ri.representative_point()
        best = [(p.x, p.y)]
    out = []
    for (x, y) in best:
        q = affinity.rotate(Point(x, y), ang, origin=c, use_radians=True)
        out.append((q.x, q.y))
    return out


def top_up(poly, pts, n):
    """add points (farthest-point sampling on a fine interior grid) until n points exist."""
    pts = list(pts)
    x0, y0, x1, y1 = poly.bounds
    step = max(20.0, math.sqrt(poly.area / max(n * 6, 1)))
    cand = []
    y = y0 + step / 2
    while y < y1:
        x = x0 + step / 2
        while x < x1:
            if poly.contains(Point(x, y)):
                cand.append((x, y))
            x += step
        y += step
    while len(pts) < n and cand:
        if pts:
            nxt = max(cand, key=lambda p: min((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 for q in pts))
        else:
            nxt = cand[len(cand) // 2]
        pts.append(nxt)
        cand.remove(nxt)
    return pts


def perimeter_points(poly, k, inset, avoid=(), avoid_r=0.0, corner=40.0):
    """k points evenly along the room boundary, pushed inside by inset.
    returns [(x, y, angle_into_room)]"""
    if k <= 0:
        return []
    poly = ccw(poly)
    ring = LineString(poly.exterior.coords)
    L = ring.length
    res = []
    coords = list(poly.exterior.coords)
    for i in range(k):
        best = None
        for t in range(10):
            d = (L * (i + 0.5) / k + t * L / (k * 7.0)) % L
            p = ring.interpolate(d)
            # edge direction
            acc = 0.0
            ang = 0.0
            dc = 1e9
            for a, b in zip(coords[:-1], coords[1:]):
                seg = math.hypot(b[0] - a[0], b[1] - a[1])
                if acc <= d <= acc + seg + 1e-9:
                    ang = math.atan2(b[1] - a[1], b[0] - a[0])
                    dc = min(d - acc, acc + seg - d)
                    break
                acc += seg
            ok = dc >= corner and all(math.hypot(p.x - ax, p.y - ay) >= avoid_r for (ax, ay) in avoid)
            if best is None or ok:
                best = (p.x, p.y, ang)
            if ok:
                break
        x, y, ang = best
        nx, ny = -math.sin(ang), math.cos(ang)
        res.append((x + nx * inset, y + ny * inset, ang + math.pi / 2))
    return res


def wall_point(poly, target, inset, keep_corner=45.0):
    """boundary point of poly nearest to target, pushed inside; returns (x, y, angle_into_room)."""
    poly = ccw(poly)
    coords = list(poly.exterior.coords)
    best = None
    tp = Point(target)
    for a, b in zip(coords[:-1], coords[1:]):
        seg = LineString([a, b])
        if seg.length < 1:
            continue
        d = seg.project(tp)
        d = min(max(d, min(keep_corner, seg.length / 2)), seg.length - min(keep_corner, seg.length / 2))
        q = seg.interpolate(d)
        dist = q.distance(tp)
        if best is None or dist < best[0]:
            ang = math.atan2(b[1] - a[1], b[0] - a[0])
            best = (dist, q.x, q.y, ang)
    _, x, y, ang = best
    nx, ny = -math.sin(ang), math.cos(ang)
    return (x + nx * inset, y + ny * inset, ang + math.pi / 2)


def nn_order(start, pts):
    pts = list(pts)
    out = []
    cur = start
    while pts:
        j = min(range(len(pts)), key=lambda i: (pts[i][0] - cur[0]) ** 2 + (pts[i][1] - cur[1]) ** 2)
        cur = pts.pop(j)
        out.append(cur)
    return out


def path_len(pts):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts[:-1], pts[1:]))


def manh(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def ortho(a, b):
    """L-shaped route a->b"""
    if abs(a[0] - b[0]) > abs(a[1] - b[1]):
        mid = (b[0], a[1])
    else:
        mid = (a[0], b[1])
    return [a, mid, b]


def ring_route(ring_poly, a, b):
    """route a->b along the ring (interior tray), returns polyline points."""
    ring = LineString(list(ring_poly.exterior.coords))
    L = ring.length
    ta, tb = ring.project(Point(a)), ring.project(Point(b))
    pa, pb = ring.interpolate(ta), ring.interpolate(tb)

    def sub(t0, t1):
        pts = [ring.interpolate(t0)]
        coords = list(ring.coords)
        acc = 0.0
        cum = [0.0]
        for p, q in zip(coords[:-1], coords[1:]):
            acc += math.hypot(q[0] - p[0], q[1] - p[1])
            cum.append(acc)
        if t0 <= t1:
            for c, p in zip(cum, coords):
                if t0 < c < t1:
                    pts.append(Point(p))
        else:
            for c, p in zip(cum, coords):
                if c > t0:
                    pts.append(Point(p))
            for c, p in zip(cum, coords):
                if c < t1:
                    pts.append(Point(p))
        pts.append(ring.interpolate(t1))
        return [(p.x, p.y) for p in pts]
    d1 = (tb - ta) % L
    d2 = (ta - tb) % L
    if d1 <= d2:
        mid = sub(ta, tb)
    else:
        mid = list(reversed(sub(tb, ta)))
    return [tuple(a)] + mid + [tuple(b)]


def main_axis(poly, trim):
    """long centre line of a room (for busbars), trimmed by `trim` at both ends."""
    mrr = poly.minimum_rotated_rectangle
    cs = list(mrr.exterior.coords)[:4]
    e = [(cs[i], cs[(i + 1) % 4]) for i in range(4)]
    e.sort(key=lambda s: -math.hypot(s[1][0] - s[0][0], s[1][1] - s[0][1]))
    a, b = e[0]
    c, d = e[1]
    # mid line between the two long edges
    p = ((a[0] + d[0]) / 2, (a[1] + d[1]) / 2)
    q = ((b[0] + c[0]) / 2, (b[1] + c[1]) / 2)
    ln = LineString([p, q]).intersection(poly.buffer(-trim))
    if ln.is_empty:
        return None
    if ln.geom_type != 'LineString':
        ln = max(ln.geoms, key=lambda g: g.length)
    return list(ln.coords)


def lines_clip(poly, step, angle=0.0):
    """parallel lines at `step` spacing clipped to poly (mesh), returns list of segments."""
    c = poly.centroid
    rp = affinity.rotate(poly, -angle, origin=c, use_radians=True)
    x0, y0, x1, y1 = rp.bounds
    segs = []
    nx = max(0, int((x1 - x0) / step))
    for i in range(1, nx + 1):
        x = x0 + (x1 - x0) * i / (nx + 1)
        segs.append(LineString([(x, y0 - 10), (x, y1 + 10)]))
    ny = max(0, int((y1 - y0) / step))
    for j in range(1, ny + 1):
        y = y0 + (y1 - y0) * j / (ny + 1)
        segs.append(LineString([(x0 - 10, y), (x1 + 10, y)]))
    out = []
    for s in segs:
        g = s.intersection(rp)
        parts = [g] if g.geom_type == 'LineString' else (list(g.geoms) if hasattr(g, 'geoms') else [])
        for part in parts:
            if part.geom_type == 'LineString' and part.length > 1:
                pr = affinity.rotate(part, angle, origin=c, use_radians=True)
                out.append(list(pr.coords))
    return out


def long_angle(poly):
    mrr = poly.minimum_rotated_rectangle
    cs = list(mrr.exterior.coords)[:4]
    best = max(((cs[i], cs[(i + 1) % 4]) for i in range(4)), key=lambda s: math.hypot(s[1][0] - s[0][0], s[1][1] - s[0][1]))
    return math.atan2(best[1][1] - best[0][1], best[1][0] - best[0][0])


def spread_points(cands, k, seed=None):
    """farthest point sampling of k points from candidates."""
    cands = list(cands)
    if not cands or k <= 0:
        return []
    if len(cands) <= k:
        return cands
    if seed is None:
        cx = sum(p[0] for p in cands) / len(cands)
        cy = sum(p[1] for p in cands) / len(cands)
        seed = (cx, cy)
    first = min(cands, key=lambda p: (p[0] - seed[0]) ** 2 + (p[1] - seed[1]) ** 2)
    out = [first]
    while len(out) < k:
        nxt = max(cands, key=lambda p: min((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 for q in out))
        out.append(nxt)
    return out


def serpentine(pts, angle, start=None):
    """order grid points row by row (boustrophedon) in the frame rotated by angle."""
    if len(pts) <= 2:
        return list(pts)
    ca, sa = math.cos(-angle), math.sin(-angle)
    rot = [((p[0] * ca - p[1] * sa), (p[0] * sa + p[1] * ca), p) for p in pts]
    ys = sorted(r[1] for r in rot)
    gaps = [b - a for a, b in zip(ys[:-1], ys[1:]) if b - a > 1.0]
    tol = (min(gaps) * 0.5) if gaps else 1.0
    rows = []
    for r in sorted(rot, key=lambda r: r[1]):
        if rows and abs(r[1] - rows[-1][-1][1]) <= tol:
            rows[-1].append(r)
        else:
            rows.append([r])
    out = []
    for i, row in enumerate(rows):
        row.sort(key=lambda r: r[0], reverse=bool(i % 2))
        out += [r[2] for r in row]
    if start is not None and len(out) > 1:
        d0 = (out[0][0] - start[0]) ** 2 + (out[0][1] - start[1]) ** 2
        d1 = (out[-1][0] - start[0]) ** 2 + (out[-1][1] - start[1]) ** 2
        if d1 < d0:
            out.reverse()
    return out
