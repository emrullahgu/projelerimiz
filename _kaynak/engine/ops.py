"""CLD engine - drawing operation list (consumed by the LISP player cld:play)."""
import math

TABLE_PAD = 0.6
TABLE_CHAR = 0.66


class Ops:
    def __init__(self, prefix):
        self.prefix = prefix          # e.g. 'CLD-ICT-'
        self.layers = []
        self.ops = []

    def layer(self, name, color, ltype=None, lw=-3):
        full = self.prefix + name
        if not any(l[0] == full for l in self.layers):
            self.layers.append((full, color, ltype, lw))
        return full

    def L(self, lay, a, b):
        self.ops.append(('L', lay, a[0], a[1], b[0], b[1]))

    def P(self, lay, pts, closed=False, w=0.0):
        pts = [(p[0], p[1]) for p in pts]
        # drop repeated vertices and degenerate (< 1 cm) polylines
        pts = [q for i, q in enumerate(pts) if i == 0 or abs(q[0] - pts[i - 1][0]) + abs(q[1] - pts[i - 1][1]) > 0.05]
        if len(pts) >= 2 and sum(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(pts, pts[1:])) > 1.0:
            self.ops.append(('P', lay, bool(closed), float(w), pts))

    def I(self, lay, blk, p, ang=0.0, sc=1.0):
        self.ops.append(('I', lay, blk, p[0], p[1], float(ang), float(sc)))

    def C(self, lay, p, r):
        self.ops.append(('C', lay, p[0], p[1], float(r)))

    def D(self, lay, p, r):
        self.ops.append(('D', lay, p[0], p[1], float(r)))

    def T(self, lay, p, h, s, j=0):
        self.ops.append(('T', lay, p[0], p[1], float(h), int(j), str(s)))

    def TB(self, lay, p, h, title, rows):
        rows = [[str(c) for c in r] for r in rows]
        self.ops.append(('TB', lay, p[0], p[1], float(h), str(title or ''), rows))
        return table_size(h, title, rows)

    def BK(self, name, plines, texts):
        self.ops.insert(0, ('BK', name, plines, texts))

    def extend(self, other, dx, dy):
        """append other's ops translated by (dx, dy); merges layer tables."""
        for l in other.layers:
            if not any(x[0] == l[0] for x in self.layers):
                self.layers.append(l)
        for o in other.ops:
            k = o[0]
            if k == 'L':
                self.ops.append(('L', o[1], o[2] + dx, o[3] + dy, o[4] + dx, o[5] + dy))
            elif k == 'P':
                self.ops.append(('P', o[1], o[2], o[3], [(x + dx, y + dy) for (x, y) in o[4]]))
            elif k == 'I':
                self.ops.append(('I', o[1], o[2], o[3] + dx, o[4] + dy, o[5], o[6]))
            elif k in ('C', 'D'):
                self.ops.append((k, o[1], o[2] + dx, o[3] + dy, o[4]))
            elif k == 'T':
                self.ops.append(('T', o[1], o[2] + dx, o[3] + dy, o[4], o[5], o[6]))
            elif k in ('TB', 'NT'):
                self.ops.append((k, o[1], o[2] + dx, o[3] + dy, o[4], o[5], o[6]))
            elif k == 'BK':
                self.ops.insert(0, o)

    def NT(self, lay, p, h, title, lines):
        self.ops.append(('NT', lay, p[0], p[1], float(h), str(title or ''), [str(s) for s in lines]))
        return notes_size(h, title, lines)


def table_size(h, title, rows):
    """(width, height) exactly as cld:table draws it."""
    pad = TABLE_PAD * h
    rh = 2.0 * h
    ncol = max(len(r) for r in rows) if rows else 0
    widths = []
    for c in range(ncol):
        mx = max((len(r[c]) if c < len(r) else 0) for r in rows)
        widths.append(2 * pad + TABLE_CHAR * h * mx)
    H = (1.5 * rh if title else 0) + rh * len(rows) + 2.0 * h
    return sum(widths), H


def notes_size(h, title, lines):
    w = max([len(s) for s in lines] + [len(title or '') * 1.3]) * 0.62 * h
    H = (2.2 * h if title else 0) + 1.7 * h * len(lines) + h
    return w, H


class Column:
    """vertical stacking cursor for tables / notes inside a discipline zone."""
    def __init__(self, ops, x, y, h, gap):
        self.o, self.x, self.y, self.h, self.gap = ops, x, y, h, gap
        self.top = y
        self.maxw = 0.0
        self.cols = []
        self.colmax = None

    def table(self, lay, title, rows, h=None):
        h = h or self.h
        w, H = table_size(h, title, rows)
        self._fit(H)
        self.o.TB(lay, (self.x, self.y), h, title, rows)
        self.y -= H + self.gap
        self.maxw = max(self.maxw, w)
        return w, H

    def notes(self, lay, title, lines, h=None):
        h = h or self.h
        w, H = notes_size(h, title, lines)
        self._fit(H)
        self.o.NT(lay, (self.x, self.y), h, title, lines)
        self.y -= H + self.gap
        self.maxw = max(self.maxw, w)
        return w, H

    def _fit(self, H):
        # wrap to a new column if the stack would get taller than colmax
        if self.colmax and (self.top - self.y) + H > self.colmax and self.y < self.top:
            self.x += self.maxw + 2 * self.gap
            self.y = self.top
            self.maxw = 0.0

    def width_used(self, x0):
        return self.x + self.maxw - x0
