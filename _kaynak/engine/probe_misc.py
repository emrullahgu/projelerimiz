import sys, re, collections
sys.path.insert(0, '.')
from dwgdata import Dwg
from arch import Arch, FLOOR_TITLE
d = Dwg(sys.argv[1]); A = Arch(d)
fr = A.frames()
sec = [t for t in d.texts if re.search(r'KES[İI]T[İI]|GÖRÜNÜŞ', t['s']) and t['h'] >= 30]
kots = collections.Counter()
for t in sec:
    F = [r for r in fr if r[0] <= t['px'] <= r[2] and r[1] <= t['py'] <= r[3]]
    if not F: continue
    r = min(F, key=lambda r: (r[2]-r[0])*(r[3]-r[1]))
    for u in d.texts:
        if r[0] <= u['px'] <= r[2] and r[1] <= u['py'] <= r[3]:
            m = re.match(r'^\s*[+±]?\s*([0-9]{1,2}[.,][0-9]{2})\s*$', u['s'])
            if m: kots[float(m.group(1).replace(',', '.'))] += 1
print('section kots:', sorted(kots.items()))
c = collections.Counter()
for ins in d.inserts:
    if re.search(r'tefri|TEFR|^4$|M_tefris|dograma|M_duvar', ins['layer'], re.I):
        b = d.insert_bbox(ins)
        if b: c[(ins['name'], ins['layer'], round(b[2]-b[0]), round(b[3]-b[1]))] += 1
for k, v in c.most_common(40): print(v, k, d.block_texts(k[0])[:3])
