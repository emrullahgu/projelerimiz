"""CLD engine - writes one self-contained AutoLISP file per parcel and discipline."""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)

_SUP = {'⁻': '-', '¹': '1', '²': '2', '³': '3', '⁶': '6'}


def lisp_str(s):
    s = str(s)
    out = []
    for ch in s:
        if ch == '\\':
            out.append('\\\\')
        elif ch == '"':
            out.append('\\"')
        elif ch in '\r\n\t':
            out.append(' ')
        elif ord(ch) < 128:
            out.append(ch)
        else:
            if ch in ('⁻', '¹', '⁶') and ch in _SUP:
                out.append(_SUP[ch])
                continue
            out.append('\\\\U+%04X' % ord(ch))
    return '"' + ''.join(out) + '"'


def num(x, d=1):
    v = round(float(x), d)
    if v == int(v):
        return f'{int(v)}.0'
    return f'{v:.{d}f}'.rstrip('0')


def pt(p):
    return f'({num(p[0])} {num(p[1])})'


def op_lisp(o):
    k = o[0]
    if k == 'L':
        return f'("L" {lisp_str(o[1])} {num(o[2])} {num(o[3])} {num(o[4])} {num(o[5])})'
    if k == 'P':
        return f'("P" {lisp_str(o[1])} {"T" if o[2] else "nil"} {num(o[3])} (' + ' '.join(pt(p) for p in o[4]) + '))'
    if k == 'I':
        return f'("I" {lisp_str(o[1])} {lisp_str(o[2])} {num(o[3])} {num(o[4])} {num(o[5], 4)} {num(o[6], 3)})'
    if k in ('C', 'D'):
        return f'("{k}" {lisp_str(o[1])} {num(o[2])} {num(o[3])} {num(o[4])})'
    if k == 'T':
        return f'("T" {lisp_str(o[1])} {num(o[2])} {num(o[3])} {num(o[4])} {int(o[5])} {lisp_str(o[6])})'
    if k == 'TB':
        rows = ' '.join('(' + ' '.join(lisp_str(c) for c in r) + ')' for r in o[6])
        return f'("TB" {lisp_str(o[1])} {num(o[2])} {num(o[3])} {num(o[4])} {lisp_str(o[5])} ({rows}))'
    if k == 'NT':
        lines = ' '.join(lisp_str(c) for c in o[6])
        return f'("NT" {lisp_str(o[1])} {num(o[2])} {num(o[3])} {num(o[4])} {lisp_str(o[5])} ({lines}))'
    if k == 'BK':
        pls = ' '.join('(' + ('T' if c else 'nil') + ' ' + ' '.join(pt(q) for q in pts) + ')' for (c, pts) in o[2])
        txs = ' '.join(f'({num(x)} {num(y)} {num(h)} {lisp_str(t)})' for (x, y, h, t) in o[3])
        return f'("BK" {lisp_str(o[1])} ({pls}) ({txs}))'
    raise ValueError(k)


def ascii_comment(s):
    tr = str.maketrans('çğıöşüÇĞİÖŞÜ²³°Øı', 'cgiosuCGIOSU23oOi')
    s = s.translate(tr)
    return ''.join(ch if ord(ch) < 128 else '?' for ch in s)


def read_src(name):
    s = open(os.path.join(SRC, name), encoding='utf-8').read()
    # sources are kept ASCII; guard anyway
    return ''.join(ch if ord(ch) < 128 else '?' for ch in s)


def defined_blocks():
    src = open(os.path.join(SRC, 'cld_sym.lsp'), encoding='utf-8').read()
    names = set(re.findall(r'cld:defblk "([A-Z0-9_]+)"', src))
    names |= set(re.findall(r'\("(CLD_S_CK_[A-Z]+)" "', src))
    return names


def write_lisp(path, parcel, code, short, title, ops, ext, info, summary_lines, cmd):
    known = defined_blocks() | {o[1] for o in ops.ops if o[0] == 'BK'}
    missing = sorted({o[2] for o in ops.ops if o[0] == 'I'} - known)
    if missing:
        raise ValueError(f'{path}: undefined blocks {missing}')
    tag = f'P{parcel}_{short}'
    chunks = [ops.ops[i:i + 120] for i in range(0, len(ops.ops), 120)]
    fn_prefix = f'cld:ops-{tag.lower()}-'
    lines = []
    w = lines.append
    w(';;; ' + '=' * 74)
    w(f';;; CLD_P{parcel}_{code}_{short}.lsp')
    w(ascii_comment(f';;; PARSEL {parcel} - {title}'))
    w(ascii_comment(f';;; Isveren : {info.get("isveren", "")}'))
    w(ascii_comment(f';;; Konum   : {info.get("mahalle", "")} / {info.get("ilce", "")} / {info.get("il", "")}'))
    w(';;; Kaynak  : BROSCO ' + str(parcel) + ' NOLU PARSEL MIMARI.dwg (mimari paftalar)')
    w(';;; Kullanim: APPLOAD ile yukleyin -> cizim otomatik olusur.')
    w(f';;;          Yeniden cizmek icin komut: {cmd[2:]}')
    w(f';;;          Tum ciktilar "{ops.prefix}*" katmanlarindadir; yeniden calistirmada bu katmanlar temizlenir.')
    w(';;;          Guvenlik uyarisi gelirse "Bir kez yukle" deyin veya klasoru Secenekler > Dosyalar >')
    w(';;;          Guvenilen Konumlar (TRUSTEDPATHS) listesine ekleyin.')
    w(';;; Uretici : CLD (Claude) otomatik muhendislik motoru - tum isimler CLD onekli.')
    for s in summary_lines:
        w(ascii_comment(';;;   ' + s))
    w(';;; ' + '=' * 74)
    w('')
    w(read_src('cld_core.lsp'))
    w('')
    w(read_src('cld_sym.lsp'))
    w('')
    w(f'(setq *cld-u* 100.0)')
    w(f'(setq *cld-ext* (list {num(ext[0], 3)} {num(ext[1], 3)} {num(ext[2], 3)}))')
    w('')
    lay_ops = ' '.join(f'("LY" {lisp_str(n)} {c} {lisp_str(lt) if lt else "nil"} {lw})' for (n, c, lt, lw) in ops.layers)
    w(f'(defun {fn_prefix}layers () (cld:play (quote ({lay_ops}))))')
    for i, ch in enumerate(chunks):
        body = '\n   '.join(op_lisp(o) for o in ch)
        w(f'(defun {fn_prefix}{i + 1} () (cld:play (quote (\n   {body}))))')
    w('')
    w(f'(defun {cmd} ( / *error* olderr)')
    w('  (setq *error* cld:err)')
    w(f'  (setq *cld-u* 100.0 *cld-ext* (list {num(ext[0], 3)} {num(ext[1], 3)} {num(ext[2], 3)}))')
    w(f'  (cld:begin {lisp_str(ops.prefix + "*")})')
    w(f'  (cld:unlock {lisp_str(ops.prefix + "*")})')
    legacy = 'CLD-' + ops.prefix.split('-')[2] + '-*'      # layers of the first (parcel-less) generation
    w(f'  (cld:unlock {lisp_str(legacy)})')
    w(f'  (cld:clear {lisp_str(legacy)})')
    w(f'  ({fn_prefix}layers)')
    w(f'  (cld:clear {lisp_str(ops.prefix + "*")})')
    w('  (cld:def-symbols)')
    for i in range(len(chunks)):
        w(f'  ({fn_prefix}{i + 1})')
    w(f"  (cld:end {lisp_str(ascii_comment(f'CLD: Parsel {parcel} - {title} cizildi'))})")
    w('  (princ))')
    w('')
    others = ' '.join(f'"{o}"' for o in ('2', '3', '4', '5') if o != str(parcel))
    w(f'(if (cld:wrong-dwg "{parcel}" (list {others}))')
    w(f'  (princ "\\nCLD UYARI: Bu dosya PARSEL {parcel} icindir; acik cizim baska bir parsele ait gorunuyor. Yine de cizmek icin {cmd[2:]} yazin.")')
    w(f'  (progn (princ "\\nCLD: Parsel {parcel} {short} yukleniyor, cizim olusturuluyor...") ({cmd})))')
    w(f'(princ "\\nCLD: Yeniden cizmek icin komut: {cmd[2:]}")')
    w('(princ)')
    txt = '\n'.join(lines) + '\n'
    txt = ''.join(ch if ord(ch) < 128 else '?' for ch in txt)
    open(path, 'w', encoding='ascii', newline='\r\n').write(txt)
    return len(ops.ops)
