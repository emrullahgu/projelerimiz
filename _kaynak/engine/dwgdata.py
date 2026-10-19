"""CLD engine - DWG dump reader (output of cldx_dump.lsp v3).

All coordinates are WCS drawing units. Block geometry is kept in block space and
expanded on demand through INSERT transforms (nested, mirrored OCS aware).
"""
import math
import re
from collections import defaultdict, Counter

_FMT = re.compile(r'\\[ACcFfHhQTWp][^;]*;')


def clean_text(s):
    s = s.replace('\\P', ' ').replace('\\~', ' ')
    s = _FMT.sub('', s)
    s = re.sub(r'\\[LlOoKk]', '', s)
    s = s.replace('{', '').replace('}', '')
    s = s.replace('%%c', 'Ø').replace('%%C', 'Ø').replace('%%d', '°').replace('%%p', '±').replace('%%%', '%')
    s = re.sub(r'%%[uUoO]', '', s)
    s = re.sub(r'\\U\+([0-9A-Fa-f]{4})', lambda m: chr(int(m.group(1), 16)), s)
    return re.sub(r'\s+', ' ', s).strip()


def _pts(s):
    out = []
    for tok in s.split(';'):
        if not tok:
            continue
        f = tok.split(',')
        try:
            out.append((float(f[0]), float(f[1]), float(f[2]) if len(f) > 2 else 0.0))
        except ValueError:
            pass
    return out


def bulge_pts(verts, closed):
    """verts: [(x,y,bulge)] -> list of (x,y) with arcs sampled."""
    res = []
    n = len(verts)
    rng = range(n if closed else n - 1)
    for i in rng:
        x1, y1, b = verts[i]
        x2, y2, _ = verts[(i + 1) % n]
        res.append((x1, y1))
        if abs(b) > 1e-6:
            ang = 4 * math.atan(b)
            ch = math.hypot(x2 - x1, y2 - y1)
            if ch < 1e-9:
                continue
            r = ch / (2 * math.sin(abs(ang) / 2))
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            d = r * math.cos(abs(ang) / 2)
            nx, ny = -(y2 - y1) / ch, (x2 - x1) / ch
            sgn = 1 if b > 0 else -1
            cx, cy = mx + sgn * nx * d, my + sgn * ny * d
            a1 = math.atan2(y1 - cy, x1 - cx)
            k = max(2, int(abs(ang) / 0.26))
            for j in range(1, k):
                a = a1 + ang * j / k
                res.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    if not closed and n:
        res.append(verts[-1][:2])
    return res


class Dwg:
    def __init__(self, path, encoding='cp1254'):
        self.hdr = {}
        self.layers = {}
        self.texts = []          # model space
        self.btexts = defaultdict(list)
        self.inserts = []        # model space
        self.binserts = defaultdict(list)
        self.geo = []            # model space: (layer, kind, pts, closed)
        self.bgeo = defaultdict(list)
        self.blocks = {}
        self.plines = []
        self.counts = Counter()
        last_ins = {}
        for line in open(path, encoding=encoding, errors='replace'):
            r = line.rstrip('\r\n').split('\t')
            t = r[0]
            if t == 'HDR':
                self.hdr.setdefault(r[1], []).append(r[2] if len(r) > 2 else '')
            elif t == 'LAY':
                self.layers[r[1]] = (int(r[2]), int(r[3]))
            elif t in ('TXT', 'MTX'):
                d = dict(kind=t, owner=r[1], layer=r[2], x=float(r[3]), y=float(r[4]), h=float(r[5]),
                         raw=r[6] if len(r) > 6 else '')
                d['s'] = clean_text(d['raw'])
                if len(r) > 10:
                    d['x11'], d['y11'] = float(r[7]), float(r[8])
                    d['j72'], d['j73'] = int(r[9]), int(r[10])
                    d['rot'] = float(r[11]) if len(r) > 11 and r[11] else 0.0
                    if t == 'TXT' and (d['j72'] or d['j73']):
                        d['px'], d['py'] = d['x11'], d['y11']
                    else:
                        d['px'], d['py'] = d['x'], d['y']
                    if t == 'MTX':
                        d['attach'] = d['j72']
                else:
                    d['px'], d['py'] = d['x'], d['y']
                    d['j72'] = d['j73'] = 0
                    d['rot'] = 0.0
                d['cx'], d['cy'] = self._text_center(d)
                (self.texts if d['owner'] == '*MS' else self.btexts[d['owner']]).append(d)
            elif t == 'INS':
                d = dict(owner=r[1], layer=r[2], x=float(r[3]), y=float(r[4]), name=r[5], sx=float(r[6]),
                         rot=float(r[7]), sy=float(r[8]) if len(r) > 8 and r[8] else float(r[6]),
                         ez=float(r[9]) if len(r) > 9 and r[9] else 1.0, handle=r[10] if len(r) > 10 else '',
                         atts={})
                (self.inserts if d['owner'] == '*MS' else self.binserts[d['owner']]).append(d)
                last_ins[d['handle']] = d
            elif t == 'ATT':
                h = r[4] if len(r) > 4 else ''
                if h in last_ins:
                    last_ins[h]['atts'][r[2]] = clean_text(r[3])
            elif t in ('GL', 'GA', 'GC', 'GE', 'GS'):
                pts = [(p[0], p[1]) for p in _pts(r[3])]
                g = (r[2], t, pts, t == 'GC')
                (self.geo if r[1] == '*MS' else self.bgeo[r[1]]).append(g)
            elif t == 'GP':
                closed = r[3] == '1'
                verts = []
                for tok in r[4].split(';'):
                    if not tok:
                        continue
                    f = tok.split(',')
                    try:
                        verts.append((float(f[0]), float(f[1]), float(f[2]) if len(f) > 2 else 0.0))
                    except ValueError:
                        pass
                if not verts:
                    continue
                pts = bulge_pts(verts, closed)
                g = (r[2], 'GP', pts, closed)
                (self.geo if r[1] == '*MS' else self.bgeo[r[1]]).append(g)
            elif t == 'PL':
                pass
            elif t == 'BLK':
                name, flags = r[1], int(r[2])
                base = (0.0, 0.0)
                rest = r[3:]
                if rest and ',' in rest[0]:
                    bx, by = rest[0].split(',')[:2]
                    base = (float(bx), float(by))
                    rest = rest[1:]
                bb = None
                if len(rest) >= 4 and rest[0]:
                    try:
                        bb = tuple(float(v) for v in rest[:4])
                    except ValueError:
                        bb = None
                self.blocks[name] = dict(flags=flags, base=base, bbox=bb)
            elif t == 'CNT':
                self.counts[r[1]] = int(r[2])
        u = self.hdr.get('INSUNITS', ['0'])[0]
        self.insunits = int(float(u)) if u else 0

    @staticmethod
    def _text_center(d):
        h = d['h']
        s = d['s']
        w = 0.62 * h * max(1, len(s))
        x, y = d['px'], d['py']
        if d['kind'] == 'TXT':
            j = d.get('j72', 0)
            v = d.get('j73', 0)
            if j in (0, 3, 5):
                x += w / 2
            elif j == 2:
                x -= w / 2
            if v in (0, 1):
                y += h / 2
            elif v == 3:
                y -= h / 2
        else:
            a = d.get('attach', 1) or 1
            col = (a - 1) % 3
            row = (a - 1) // 3
            x += [w / 2, 0, -w / 2][col]
            y += [-h / 2, 0, h / 2][row]
        return x, y

    # ------------------------------------------------------------ transforms
    def xform(self, ins):
        """returns f(x,y)->(X,Y) mapping block coords to WCS for an insert."""
        bx, by = self.blocks.get(ins['name'], {}).get('base', (0.0, 0.0))
        c, s = math.cos(ins['rot']), math.sin(ins['rot'])
        sx, sy = ins['sx'], ins['sy']
        mir = ins['ez'] < 0
        ix, iy = (-ins['x'], ins['y']) if mir else (ins['x'], ins['y'])

        def f(x, y):
            x, y = (x - bx) * sx, (y - by) * sy
            X, Y = ix + c * x - s * y, iy + s * x + c * y
            return (-X, Y) if mir else (X, Y)
        return f

    def expand(self, ins, depth=0, layer=None):
        """geometry of an insert in WCS: list of (layer, kind, pts, closed)."""
        out = []
        if depth > 5:
            return out
        f = self.xform(ins)
        L = layer or ins['layer']
        for (lay, kind, pts, closed) in self.bgeo.get(ins['name'], []):
            out.append((L if lay == '0' else lay, kind, [f(x, y) for (x, y) in pts], closed))
        for sub in self.binserts.get(ins['name'], []):
            sub_geo = self.expand(sub, depth + 1, L if sub['layer'] == '0' else sub['layer'])
            out.extend((g[0], g[1], [f(x, y) for (x, y) in g[2]], g[3]) for g in sub_geo)
        return out

    def insert_bbox(self, ins):
        g = self.expand(ins)
        xs = [p[0] for gg in g for p in gg[2]]
        ys = [p[1] for gg in g for p in gg[2]]
        if not xs:
            return None
        return (min(xs), min(ys), max(xs), max(ys))

    def block_texts(self, name, depth=0):
        out = [t['s'] for t in self.btexts.get(name, [])]
        if depth < 4:
            for sub in self.binserts.get(name, []):
                out += self.block_texts(sub['name'], depth + 1)
        return out
