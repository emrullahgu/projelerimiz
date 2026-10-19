"""CLD engine - the nine discipline builders (separate sheets, per-sheet legends)."""
import math
from collections import Counter

import geo
from geo import m, U
from ops import Ops
from elec import LUM, BUS_DF
from draw import (DISC, H_TAB, H_LBL, S, Sheet, layout_row, zone_std, arrow_label, floors_with_rooms,
                  f0, f1, f2, kw)


# =============================================================== 01 ICT
def build_ict(P, ctx):
    e = P.elec
    pre = f'CLD-P{P.parcel}-ICT-'
    leg_ayd = [
        ('CLD_S_HB', 1.6, LUM['HB'][0]), ('CLD_S_PNL', 1.0, LUM['PNL'][0]), ('CLD_S_DL', S, LUM['DL'][0]),
        ('CLD_S_DLB', S, LUM['DLB'][0]), ('CLD_S_ETJ', 1.0, LUM['ETJ'][0]), ('CLD_S_ACIL', S, LUM['ACL'][0]),
        ('CLD_S_EXIT', S, LUM['EXT'][0]), ('', 1, 'AK: 3 saat acil kitli armatür (sürekli faz ile beslenir)'),
        ('CLD_S_ANH1', S, 'Adi anahtar (h=110 cm)'), ('CLD_S_ANH2', S, 'Komütatör anahtar'), ('CLD_S_VAV', S, 'Vavien anahtar'),
        ('CLD_S_TP', S, 'Tali dağıtım panosu (UTP / İDP)'),
        ('#' + pre + 'LINYE-AYD', 1, 'Aydınlatma linyesi, ok: panoya dönüş, etiket PANO/LİNYE'),
    ]
    leg_prz = [
        ('CLD_S_PRIZ', S, 'Topraklı priz 16 A (h=40 cm, tezgah h=110 cm)'),
        ('CLD_S_PRIZU', S, 'Bilgisayar prizi (ayrı linye, UPS hazırlığı)'), ('CLD_S_PRIZE', S, 'Etanj priz IP44'),
        ('CLD_S_PGRUP', 1.6, 'Endüstriyel priz grubu CEE 32A+16A+2x16A (iç koruma, h=150 cm)'),
        ('CLD_S_CK_ISITICI', S, 'Ani su ısıtıcı çıkışı (IS) - ayrı linye'),
        ('CLD_S_CK_TERMOSIFON', S, 'Elektrikli termosifon çıkışı (TS) - ayrı linye'),
        ('CLD_S_CK_BULASIK', S, 'Bulaşık makinesi çıkışı (B) - ayrı linye'),
        ('CLD_S_CK_ASPIRATOR', S, 'Havalandırma cihazı / aspiratör çıkışı (A) - ayrı linye'),
        ('CLD_S_TP', S, 'Tali dağıtım panosu (UTP / İDP)'),
        ('#' + pre + 'LINYE-PRIZ', 1, 'Priz / kuvvet linyesi, ok: panoya dönüş'),
    ]
    sheets = []
    for kind in ('AYD', 'PRZ'):
        for fk in floors_with_rooms(P):
            o = Ops(pre)
            LA = o.layer('AYDINLATMA', 2)
            LAC = o.layer('ACIL', 1)
            LP = o.layer('PRIZ', 4)
            LK = o.layer('OZEL-CIKIS', 6)
            LS = o.layer('ANAHTAR', 3)
            LLA = o.layer('LINYE-AYD', 2, 'CLD_KESIK', 13)
            LLP = o.layer('LINYE-PRIZ', 4, 'CLD_UZUNKESIK', 13)
            LPN = o.layer('PANO', 1, None, 50)
            LT = o.layer('YAZI', 7)
            for code, pn in e.panels.items():
                if pn.floor == fk and pn.kind in ('IDP', 'UTP'):
                    o.I(LPN, pn.blk, (pn.x, pn.y), pn.ang, S)
                    o.T(LPN, (pn.x + m(0.5), pn.y + m(0.6)), 30.0, code, 0)
            if kind == 'AYD':
                for l in e.lums:
                    if l.floor != fk:
                        continue
                    sc = 1.6 if l.kod == 'HB' else (1.0 if l.kod in ('PNL', 'ETJ') else S)
                    o.I(LAC if l.kod in ('ACL', 'EXT') else LA, LUM[l.kod][3], (l.x, l.y), 0.0, sc)
                    if l.acil and l.kod == 'HB':
                        o.T(LAC, (l.x + m(0.5), l.y - m(0.5)), H_LBL * 0.8, 'AK', 0)
                for w in e.sws:
                    if w.floor == fk:
                        o.I(LS, w.blk, (w.x, w.y), w.ang, S)
                kinds = ('A', 'AC')
            else:
                for s_ in e.outs:
                    if s_.floor == fk:
                        o.I(LK if s_.kind in ('K', 'K3', 'G') else LP, s_.blk, (s_.x, s_.y), s_.ang, 1.6 if s_.kind == 'G' else S)
                kinds = ('P', 'G', 'K')
            for c in e.circuits:
                pn = e.panels[c.panel]
                if c.kind not in kinds or pn.floor != fk or not c.pts:
                    continue
                if len(c.pts) == 1 and abs(c.pts[0][0] - pn.x) < 1 and abs(c.pts[0][1] - pn.y) < 1:
                    continue
                lay = LLA if c.kind in ('A', 'AC') else LLP
                parts, cur = [], [c.pts[0]]
                for q in c.pts[1:]:
                    if math.hypot(q[0] - cur[-1][0], q[1] - cur[-1][1]) > m(12.0):
                        parts.append(cur)
                        cur = [q]
                    else:
                        cur.append(q)
                parts.append(cur)
                for part in parts:
                    if len(part) > 1:
                        o.P(lay, part, False, 0.0)
                    arrow_label(o, lay, LT, part[0], (pn.x, pn.y), f'{c.panel}/{c.code}')
            if kind == 'AYD':
                sheets.append(Sheet('AYDINLATMA TESİSATI PLANI', fk, o, leg_ayd))
            else:
                sheets.append(Sheet('PRİZ VE KUVVET TESİSATI PLANI', fk, o, leg_prz))

    def tables(col, LTB):
        rows = [['PANO', 'LİNYE', 'TÜR', 'AÇIKLAMA', 'ADET', 'GÜÇ (W)', 'FAZ', 'SİGORTA', 'KAÇAK AKIM', 'KABLO', 'L (m)', '%e']]
        for c in e.circuits:
            rows.append([c.panel, c.code, {'A': 'Aydınlatma', 'AC': 'Acil ayd.', 'P': 'Priz', 'G': 'End. priz', 'K': 'Kuvvet'}[c.kind],
                         c.desc[:52], str(c.nl or c.no), f0(c.W), c.phase, c.brk, c.rcd, c.cable, f1(c.L), f2(c.du)])
        for i in range(0, len(rows) - 1, 45):
            col.table(LTB, 'LİNYE LİSTESİ' + (f' ({i // 45 + 1})' if len(rows) > 46 else ''), [rows[0]] + rows[1 + i:1 + i + 45])
        col.notes(LTB, 'NOTLAR', [
            '1- Tesisat Elektrik İç Tesisleri Yönetmeliği, TS HD 60364 ve TS EN 12464-1 esas alınarak hesaplanmıştır.',
            '2- Aydınlatma ve priz tesisatı ayrı paftalarda gösterilmiştir; linye etiketi "PANO/LİNYE", ok yönü panoyu gösterir.',
            '3- Kesitler IEC 60364-5-52 C yöntemi x 0,80 (ofis) / x 0,71 (üretim holü tavası, 40 °C) ile seçilmiştir; gerilim düşümü aydınlatma ve prizde ≤ %1,5, kuvvette ≤ %3 olacak şekilde linyeler bölünmüştür.',
            '4- Kaçak akım: tüm tek fazlı son devreler (priz, aydınlatma, ıslak hacim, özel çıkış) 30 mA, bilgisayar/VRF A tipi; 3 fazlı motor devreleri 300 mA; pano girişleri 300 mA S (seçici) - TS HD 60364-4-41 411.3.3, EMO.',
            '5- Ofis ve ıslak hacimlerde sıva altı spiral boru, üretim alanında galvaniz kablo tavası / boru kullanılacaktır.',
            '6- "AK" acil kitli armatürler kontaktör öncesinden sürekli faz ile beslenir (NYM 4x..: L anahtarlı + L sürekli, TS EN 50172).',
            '7- Acil ve yönlendirme armatürleri 3 saat bataryalıdır (Binaların Yangından Korunması Hakkında Yönetmelik, TS EN 1838).',
            '8- Endüstriyel priz grubu kutusu içinde 4P C32, C16 ve 2xB16 sigortalar ile 30 mA (A tipi) kaçak akım rölesi bulunur.',
            '9- Anahtarlar sahada kapı açılış yönüne göre kapı kanadının arkasında kalmayacak şekilde yerleştirilecektir.',
            '10- Üretim alanı aydınlatması tali panodan kontaktör + saat rölesi ile kumanda edilir.',
        ])
    return layout_row(P, ctx, '01', DISC[0][2], pre, sheets, zone_std(leg_ayd + leg_prz, tables))


# =============================================================== 02 TOP
def build_top(P, ctx):
    ea, e = P.earth, P.elec
    pre = f'CLD-P{P.parcel}-TOP-'
    o = Ops(pre)
    LR = o.layer('TEMEL-SERIT', 30, None, 50)
    LM = o.layer('AG', 30, 'CLD_KESIK', 30)
    LF = o.layer('FILIZ', 1)
    LE = o.layer('ESPOTANSIYEL', 6)
    LTR = o.layer('TRAFO', 1, None, 35)
    LT = o.layer('YAZI', 7)
    o.P(LR, ea.ring, True, 8.0)
    for seg in ea.mesh:
        o.P(LM, seg, False, 4.0)
    for seg in ea.links:
        o.P(LR, seg, False, 8.0)
    for kind, x, y in ea.lugs:
        o.I(LF, 'CLD_S_TOP_FILIZ', (x, y), 0.0, S)
    o.I(LE, 'CLD_S_TOP_EPB', ea.aeb, 0.0, S)
    o.T(LE, (ea.aeb[0] + m(0.6), ea.aeb[1] + m(0.4)), 25.0, 'AEB', 0)
    o.L(LE, ea.aeb, (e.panels['ADP'].x, e.panels['ADP'].y))
    for (fk, x, y, a, rid) in ea.yeb:
        if fk == 'ZK':
            o.I(LE, 'CLD_S_TOP_YEB', (x, y), a, S)
    for i, (x, y) in enumerate(ea.down):
        nx, ny = ea.down_n[i]
        o.I(LF, 'CLD_S_TOP_OLCU', (x + nx * m(0.5), y + ny * m(0.5)), 0.0, S)
        o.I(LF, 'CLD_S_TOP_KAZIK', (x + nx * m(1.2), y + ny * m(1.2)), 0.0, S)
    for seg in ea.rod_links:
        o.P(LR, seg, False, 8.0)
    o.P(LTR, ea.trafo_ring, True, 8.0)
    for (x, y) in ea.trafo_rods:
        o.I(LTR, 'CLD_S_TOP_KAZIK', (x, y), 0.0, S)
    for seg in ea.trafo_links:
        o.P(LTR, seg, False, 8.0)
    o.T(LTR, (e.trafo_pt[0] - m(3), e.trafo_pt[1] + m(3.2)), 25.0, 'TRAFO KORUMA TOPRAKLAMASI (ring + 4 kazık, 2 bağlantı)', 0)
    leg = [
        ('#' + pre + 'TEMEL-SERIT', 1, 'Temel topraklama ringi / bağlantı şeridi St/tZn 30x3,5 mm (temel betonu içinde)'),
        ('#' + pre + 'AG', 1, 'Temel topraklama ağı (göz en fazla 20x20 m, DIN 18014)'),
        ('CLD_S_TOP_FILIZ', S, 'Bağlantı filizi: çelik kolon / iniş iletkeni / AEB (min 1,5 m çıkış)'),
        ('CLD_S_TOP_OLCU', S, 'Ölçü kutusu (iniş iletkeni bağlantısı)'),
        ('CLD_S_TOP_KAZIK', S, 'Topraklama kazığı Ø20 mm, L=2,0 m bakır kaplı çelik'),
        ('CLD_S_TOP_EPB', S, 'Ana eşpotansiyel barası (AEB) - ADP yanında'),
        ('CLD_S_TOP_YEB', S, 'Yerel (tamamlayıcı) eşpotansiyel barası - ıslak hacim'),
    ]
    sheets = [Sheet('TEMEL TOPRAKLAMA VE EŞPOTANSİYEL PLANI', 'ZK', o, leg)]
    up = [y for y in ea.yeb if y[0] != 'ZK']
    for fk in sorted(set(y[0] for y in up)):
        o2 = Ops(pre)
        LE2 = o2.layer('ESPOTANSIYEL', 6)
        for (k, x, y, a, rid) in up:
            if k == fk:
                o2.I(LE2, 'CLD_S_TOP_YEB', (x, y), a, S)
        sheets.append(Sheet('EŞPOTANSİYEL BAĞLANTI PLANI', fk, o2, [leg[-1]]))
    r = ea.res

    def tables(col, LTB):
        col.table(LTB, 'TOPRAKLAMA DİRENCİ HESABI', [
            ['BÜYÜKLÜK', 'DEĞER', 'AÇIKLAMA'],
            ['Zemin özdirenci ρ', f'{f0(r["rho"])} Ωm', 'Kabul (nemli killi/kumlu zemin) - sahada ölçülerek teyit edilecek'],
            ['Bina taban alanı A', f'{f1(r["A"])} m²', 'Mimari zemin kat konturu'],
            ['Eşdeğer çap D = 1,13·√A', f'{f2(r["D"])} m', ''],
            ['Ağ tipi temel topraklayıcı R = ρ/(2D)', f'{f2(r["R_f"])} Ω', 'Ağ (mesh) topraklayıcı formülü'],
            ['Kazık (ölçü noktası) R = ρ/(2πL)·ln(4L/d)', f'{f1(r["R_rod"])} Ω', f'{r["nrod"]} adet, ağın potansiyel hunisinde - hesaba katılmadı'],
            ['Bina topraklama direnci', f'{f2(r["R_tot"])} Ω', 'R = R(ağ)'],
            ['Trafo koruma ringi R = 2ρ/(3D) // 4 kazık', f'{f2(r["R_tr"])} Ω', 'Ring 6x5 m + 4 kazık'],
            ['Birleşik (ortak) topraklama', f'{f2(r["R_comb"])} Ω',
             'Trafo ringi ağa yakın (~3 m) → paralel kabul edilmedi, R = R(ağ). Hedef ≤ 2 Ω (TN-C-S), yıldırım ≤ 10 Ω → ' +
             ('UYGUN' if r['ok'] else 'UYGUN DEĞİL - ilave kazık / ağ')],
            ['OG toprak arızası: U(E) = r·I(F)·R ≤ 2·U(Tp)', f'2 x 117 = {f0(r["U_lim"])} V',
             f'TS EN 50522, t(F)=1 s, r=1 (güvenli yan) → I(F) ≤ {f0(r["I_F_max"])} A olmalı; '
             'dağıtım şirketinden alınan I(F) bu değeri aşarsa global topraklama / dokunma gerilimi önlemleri uygulanacaktır'],
        ])
        col.table(LTB, 'MALZEME ÖZETİ', [
            ['MALZEME', 'MİKTAR'],
            ['St/tZn 30x3,5 mm şerit (ring + ağ + bağlantı + trafo + kazık bağlantısı + filiz)', f'{f0(r["strip"])} m'],
            ['Bağlantı filizi (kolon + iniş + AEB)', f'{len(ea.lugs)} adet'],
            ['Ölçü kutusu', f'{len(ea.down)} adet'],
            ['Topraklama kazığı Ø20x2000 mm', f'{len(ea.down) + 4} adet'],
            ['Yerel eşpotansiyel barası', f'{len(ea.yeb)} adet'],
            ['Ana eşpotansiyel barası', '1 adet'],
        ])
        col.notes(LTB, 'NOTLAR', [
            '1- Elektrik Tesislerinde Topraklamalar Yönetmeliği ve TS EN 62305-3 e uygundur; sistem TN-C-S tesis edilecektir.',
            '2- Temel topraklama şeridi temel betonu içinde, betondan en az 5 cm örtülü ve dikine yerleştirilecektir.',
            '3- Her kolon ankrajı, her iniş iletkeni ve AEB filiz + bağlantı şeridi ile ağa bağlanır (çizimde gösterilmiştir).',
            '4- Şerit ekleri cıvatalı klemens veya kaynak ile yapılacak, kaynak yerleri korozyona karşı korunacaktır.',
            '5- Çelik kolonlar, metal borular, kablo tavaları ve makine gövdeleri AEB üzerinden eşpotansiyele bağlanacaktır.',
            '6- Islak hacimlerde metal lavabo/borular yerel eşpotansiyel barasına 4 mm² NYAF ile bağlanacaktır.',
            '7- Trafo koruma ringi temel ağına iki ayrı şeritle bağlanmıştır (birleşik topraklama).',
            '8- İşletmeye almadan önce topraklama ölçümü yapılıp rapor edilecektir; değer aşılırsa ilave kazık çakılacaktır.',
        ])
    return layout_row(P, ctx, '02', DISC[1][2], pre, sheets, zone_std(leg, tables))


# =============================================================== 03 PAR
def build_par(P, ctx):
    ea, b = P.earth, P.b
    rk = ea.risk
    r = ea.res
    pre = f'CLD-P{P.parcel}-PAR-'
    o = Ops(pre)
    LA = o.layer('YAKALAMA', 1, None, 35)
    LC = o.layer('CUBUK', 1)
    LI = o.layer('INIS', 2, 'CLD_KESIK', 35)
    o.layer('KLEMENS', 2)
    LT = o.layer('YAZI', 7)
    rox, roy = ea.roof_ofs
    o.P(LA, ea.roof, True, 6.0)
    for seg in ea.roof_mesh:
        o.P(LA, seg, False, 4.0)
    for p in ea.rods:
        o.I(LC, 'CLD_S_PAR_UC', p, 0.0, S)
    for p in ea.equip_rods:
        o.I(LC, 'CLD_S_PAR_UC', p, 0.0, S)
    for seg in ea.equip_links:
        o.P(LA, seg, False, 4.0)
    for (x, y) in ea.down:
        o.I(LI, 'CLD_S_PAR_INIS', (x + rox, y + roy), 0.0, S)
    if ea.equip_rods:
        p = ea.equip_rods[0]
        o.T(LT, (p[0] + m(0.6), p[1] + m(0.6)), H_LBL, f'çatı fanı yanında yakalama çubuğu h=1,5 m, ağa bağlı (s ≥ {f2(rk["s_eq"])} m)', 0)
    roofkey = ea.roof_key
    if roofkey != 'CT':
        f = b.floor(roofkey)
        o2 = Ops(pre)
        o2.extend(o, f.ofs[0] - rox, f.ofs[1] - roy)
        o = o2
    o3 = Ops(pre)
    LI3 = o3.layer('INIS', 2, 'CLD_KESIK', 35)
    LK3 = o3.layer('KLEMENS', 2)
    LT3 = o3.layer('YAZI', 7)
    for i, (x, y) in enumerate(ea.down):
        nx, ny = ea.down_n[i]
        o3.I(LK3, 'CLD_S_PAR_KLEMENS', (x + nx * m(0.3), y + ny * m(0.3)), 0.0, S)
        o3.I(LI3, 'CLD_S_PAR_INIS', (x + nx * m(0.9), y + ny * m(0.9)), 0.0, S)
        o3.T(LT3, (x + nx * m(1.5), y + ny * m(1.5)), H_LBL, f'İ{i + 1}', 0)
    leg_roof = [
        ('#' + pre + 'YAKALAMA', 1, 'Yakalama iletkeni Ø8 mm Al/galvaniz, klips aralığı 1 m'),
        ('CLD_S_PAR_UC', S, 'Yakalama çubuğu: köşe / mahya h=1,0 m, çatı fanı yanında h=1,5 m'),
        ('CLD_S_PAR_INIS', S, 'İniş iletkeni Ø8 mm (veya sürekliliği sağlanmış çelik kolon)'),
    ]
    leg_zk = [
        ('CLD_S_PAR_INIS', S, 'İniş iletkeni Ø8 mm (veya sürekliliği sağlanmış çelik kolon)'),
        ('CLD_S_PAR_KLEMENS', S, 'Ölçü (ayırma) klemensi h=0,5 m, temel topraklamasına bağlı'),
    ]
    sheets = [Sheet(f'ÇATI YAKALAMA SİSTEMİ (Faraday ağı {rk["mesh"]}x{rk["mesh"]} m, LPL {rk["lvl"]})', roofkey, o, leg_roof),
              Sheet('İNİŞ İLETKENLERİ VE ÖLÇÜ KLEMENSLERİ', 'ZK', o3, leg_zk)]

    def tables(col, LTB):
        col.table(LTB, 'YILDIRIM RİSK DEĞERLENDİRMESİ (verim yöntemi, IEC 61024-1-1 / TS EN 62305 seviyeleri)', [
            ['BÜYÜKLÜK', 'DEĞER', 'AÇIKLAMA'],
            ['Taban alanı / çevre / yükseklik', f'{f0(rk["A"])} m² / {f1(rk["P"])} m / {f2(rk["H"])} m', 'Mimari plan ve kesit'],
            ['Eşdeğer toplama alanı Ad', f'{f0(rk["Ad"])} m²', 'Taban konturu 3H kadar genişletilerek'],
            ['Yıldırım düşme yoğunluğu Ng', f'{f1(rk["Ng"])} /km²/yıl', 'İzmir bölgesi (~30 gök gürültülü gün)'],
            ['Konum katsayısı Cd', f'{f1(rk["Cd"])}', 'OSB içinde benzer yükseklikte yapılarla çevrili'],
            ['Beklenen yıllık düşme Nd', f'{rk["Nd"]:.4f}'.replace('.', ','), 'Nd = Ng · Ad · Cd · 10^-6'],
            ['Kabul edilebilir sıklık Nc', f'{rk["Nc"]:.4f}'.replace('.', ','), 'Sanayi yapısı'],
            ['Gerekli verim E = 1 - Nc/Nd', f'{rk["E"]:.3f}'.replace('.', ','), 'Seçim: E ≤ 0,80 IV, ≤ 0,90 III, ≤ 0,95 II, ≤ 0,98 I'],
            ['Koruma seviyesi', f'LPL {rk["lvl"]}', rk['note'] or f'Sistem verimi {rk["eff"]:.2f}'.replace('.', ',')],
            ['Yuvarlanan küre yarıçapı', f'{rk["r"]} m', ''],
            ['Ağ (göz) boyutu', f'{rk["mesh"]} x {rk["mesh"]} m', ''],
            ['İniş iletkeni aralığı / adedi', f'≤ {rk["dc"]} m / {rk["n"]} adet', f'en büyük aralık {f1(rk["c"])} m, tüm köşelerde iniş'],
            ['kc = 1/(2n) + 0,1 + 0,2·(c/h)^(1/3)', f2(rk['kc']), 'TS EN 62305-3 Ek C'],
            ['Ayırma mesafesi s = ki·kc/km·l', f'{f2(rk["s"])} m (l=H)', f'çatı cihazları: {f2(rk["s_eq"])} m (l={f1(rk["l_eq"])} m), ki={f2(rk["ki"])}, km=1'],
        ])
        col.table(LTB, 'MALZEME ÖZETİ', [
            ['MALZEME', 'MİKTAR'],
            ['Yakalama iletkeni Ø8 mm (çevre + ağ)', f'{f0(r["air"])} m'],
            ['İniş iletkeni Ø8 mm', f'{f0(r["down_len"])} m ({rk["n"]} adet)'],
            ['Yakalama çubuğu h=1,0 m (köşe / mahya)', f'{len(ea.rods)} adet'],
            ['Yakalama çubuğu h=1,5 m (çatı fanı yanında, ağa bağlı)', f'{len(ea.equip_rods)} adet'],
            ['İletken tutucu klips (1 m aralık)', f'{f0(r["clips"])} adet'],
            ['Ölçü (ayırma) klemensi - ölçü kutusu TOPRAKLAMA paftasında', f'{rk["n"]} adet'],
        ])
        col.notes(LTB, 'NOTLAR', [
            '1- Koruma seviyesi verim yöntemiyle (IEC 61024-1-1) belirlenmiş; tesisat TS EN 62305-3/4 e göre Faraday ağı yöntemiyle tasarlanmıştır.',
            '2- Metal çatı paneli kalınlığı ≥ 0,5 mm ise doğal yakalama ucu olarak kullanılabilir (delinme kabul edilirse).',
            '3- Çelik kolonların ankrajları temel topraklamasına bağlı olduğundan doğal iniş iletkeni olarak kullanılabilir.',
            '4- Çatı fanları yanlarındaki h=1,5 m yakalama çubukları ile korunur; ağ iletkenleri fanların çevresinden en az s mesafesiyle dolaştırılmıştır.',
            '5- Tüm bağlantılar TS EN 62561 belgeli klemenslerle yapılacak, ölçü klemensleri ölçü kutusu içinde olacaktır.',
            '6- Gelen enerji/iletişim hatlarına ADP de Tip 1+2 parafudr (SPD) konulacaktır (TS EN 62305-4).',
        ])
    return layout_row(P, ctx, '03', DISC[2][2], pre, sheets, zone_std(leg_roof + leg_zk, tables))


# =============================================================== 04 KAK
def build_kak(P, ctx):
    e, b = P.elec, P.b
    t = e.tot
    pre = f'CLD-P{P.parcel}-KAK-'
    leg = [
        ('CLD_S_ADP', S, 'Ana dağıtım panosu (ADP) - kompakt şalter, ölçü, SPD'),
        ('CLD_S_TP', S, 'Tali dağıtım panosu'), ('CLD_S_KMP', S, 'Kompanzasyon panosu (otomatik, harmonik filtreli)'),
        ('CLD_S_OAP', S, 'Mekanik / yangın pompa panosu'), ('CLD_S_KOLON', S, 'Kat kolon (dikey besleme) geçişi'),
        ('CLD_S_TRAFO', 1.0, 'Köşk tipi trafo merkezi'), ('CLD_S_JEN', 1.0, 'Dizel jeneratör grubu + otomatik transfer'),
        ('CLD_S_PRJ', S, LUM['PRJ'][0]),
        ('#' + pre + 'BESLEME', 1, 'Besleme kablosu güzergahı (kablo tavası, NYY / FE180)'),
        ('#' + pre + 'BARA', 1, 'Makine besleme bara kanalı (busbar) 3P+N+PE'),
    ]
    sheets = []
    for fk in floors_with_rooms(P):
        o = Ops(pre)
        LPN = o.layer('PANO', 1, None, 50)
        LB = o.layer('BESLEME', 1, 'CLD_UZUNKESIK', 50)
        LBR = o.layer('BARA', 6, None, 70)
        LTR = o.layer('TRAFO-JEN', 1, None, 50)
        LPJ = o.layer('CEPHE-AYD', 2)
        LT = o.layer('YAZI', 7)
        f = b.floor(fk)
        for code, pn in e.panels.items():
            if pn.floor == fk:
                o.I(LPN, pn.blk, (pn.x, pn.y), pn.ang, S)
                o.T(LPN, (pn.x + m(0.6), pn.y + m(0.6)), 30.0, code, 0)
            if not pn.route:
                continue
            if fk == 'ZK':
                if geo.path_len(pn.route) > m(0.1):
                    o.P(LB, pn.route, False, 6.0)
                mid = pn.route[len(pn.route) // 2]
                if pn.feeder:
                    o.T(LT, (mid[0] + m(0.3), mid[1] + m(0.3)), H_LBL, f'{code}: {pn.feeder["cable"]}', 0)
                if pn.floor != 'ZK':
                    end = pn.route[-1]
                    near = [q for q in e.panels.values() if q.floor == 'ZK' and math.hypot(q.x - end[0], q.y - end[1]) < m(0.8)]
                    if near:
                        # riser exit coincides with a ground-floor panel: offset the symbol with a short stub
                        q = near[0]
                        sym = (q.x + math.cos(q.ang) * m(1.0), q.y + math.sin(q.ang) * m(1.0))
                        if any(math.hypot(r.x - sym[0], r.y - sym[1]) < m(0.8) for r in e.panels.values() if r.floor == 'ZK'):
                            sym = (q.x - math.sin(q.ang) * m(1.0), q.y + math.cos(q.ang) * m(1.0))
                        o.P(LB, [end, sym], False, 6.0)
                        end = sym
                    o.I(LPN, 'CLD_S_KOLON', end, 0.0, S)
                    o.T(LT, (end[0] + m(0.5), end[1] - m(0.6)), H_LBL, f'{code} kolon çıkışı (+{f2(b.floor(pn.floor).kot)})', 0)
            elif pn.floor == fk:
                rz = f.from_zk(pn.route[-1])
                if math.hypot(rz[0] - pn.x, rz[1] - pn.y) < m(0.8):
                    # riser coincides with the panel: show it beside the panel with a short stub
                    rz = (pn.x + math.cos(pn.ang) * m(1.0), pn.y + math.sin(pn.ang) * m(1.0))
                o.I(LPN, 'CLD_S_KOLON', rz, 0.0, S)
                o.P(LB, geo.ortho(rz, (pn.x, pn.y)), False, 6.0)
                o.T(LT, (rz[0] + m(0.5), rz[1] - m(0.6)), H_LBL, f'{code} kolon girişi - {pn.feeder.get("cable", "")}', 0)
        if fk == 'ZK':
            for bb in e.busbars:
                if bb['pts']:
                    o.P(LBR, bb['pts'], False, 15.0)
                    p = bb['pts'][0]
                    o.T(LT, (p[0] + m(0.5), p[1] + m(0.6)), 25.0, f'{bb["code"]}: {bb["desc"]}', 0)
                    o.P(LB, bb['route'], False, 6.0)
                    o.T(LT, (p[0] + m(0.5), p[1] - m(0.9)), H_LBL, f'besleme {bb["cable"]}', 0)
            tx, ty = e.trafo_pt
            o.I(LTR, 'CLD_S_TRAFO', (tx, ty), 0.0, 1.0)
            o.T(LTR, (tx + m(3.5), ty), 30.0, f'KÖŞK TİPİ TRAFO 34,5/0,4 kV {t["trafo"]} kVA', 7)
            gx, gy = e.gen_pt
            o.I(LTR, 'CLD_S_JEN', (gx, gy), 0.0, 1.0)
            o.T(LTR, (gx + m(2.5), gy), 30.0, f'DİZEL JENERATÖR {t["gen"]} kVA + ATS', 7)
            adp = e.panels['ADP']
            o.P(LB, [(tx, ty), (adp.x, adp.y)], False, 10.0)
            o.T(LT, ((tx + adp.x) / 2 + m(0.3), (ty + adp.y) / 2 + m(0.3)), H_LBL, f'trafo-ADP: {t["tr_cable"]}', 0)
            o.P(LB, [(gx, gy), (adp.x, adp.y)], False, 10.0)
            if e.gen_ypp_route:
                o.P(LB, e.gen_ypp_route, False, 6.0)
                mq = e.gen_ypp_route[len(e.gen_ypp_route) // 2]
                o.T(LT, (mq[0] + m(0.3), mq[1] - m(0.9)), H_LBL, f'JEN-YPP yedek besleme: {e.gen_ypp["cable"]}', 0)
            for (x, y) in e.facade:
                o.I(LPJ, 'CLD_S_PRJ', (x, y), 0.0, S)
        sheets.append(Sheet('GÜÇ DAĞITIM PLANI (pano, besleme hattı, bara kanalı)', fk, o, leg))
    loads = e._loads

    def tables(col, LTB):
        rows = [['PANO', 'BESLEME', 'KURULU (kW)', 'TALEP (kW)', 'I (A)', 'KORUMA', 'KABLO', 'L (m)', '%e', 'Ik3 (kA)']]
        rows.append(['ADP', 'TRAFO', kw(t['inst']), kw(t['demand']), f1(t['I_dem']), f'{t["main_brk"]} A kompakt + toroid KAKR', t['tr_cable'],
                     f1(t['tr_L']), f2(t['tr_du']), f1(e.ik_adp)])
        for code, pn in e.panels.items():
            if code in ('ADP', 'KMP') or not pn.feeder:
                continue
            fd = pn.feeder
            src = 'TRAFO (ana şalter öncesi) - normal' if code == 'YPP' else 'ADP'
            rows.append([code, src, kw(loads[code]['inst']), kw(fd['P']), f1(fd['I']), fd['prot'], fd['cable'], f1(fd['L']), f2(fd['du']),
                         f1(fd.get('Ik', 0))])
            if code == 'YPP' and e.gen_ypp:
                g = e.gen_ypp
                rows.append(['YPP', 'JENERATÖR (ATS öncesi) - yedek', kw(g['P']), kw(g['P']), f1(g['I']), f'aM sigorta {g["In"]} A, TS-YP',
                             g['cable'], f1(g['L']), f2(g['du']), '-'])
        for bb in e.busbars:
            rows.append([bb['code'], 'ADP', kw(bb['P']), kw(bb['Pd']), f1(bb['Id']), f'{bb["In"]} A + {bb["rcd"]}', bb['cable'], f1(bb['L']), f2(bb['du']),
                         f1(bb.get('Ik', 0))])
        cp = e.cephe
        rows.append(['CEPHE AYD.', 'ADP', kw(cp['P']), kw(cp['P']), f1(cp['I']), f'{cp["In"]} A + 300 mA, fotosel', cp['cable'], f1(cp['L']), f2(cp['du']), '-'])
        col.table(LTB, 'BESLEME HATLARI - KABLO VE GERİLİM DÜŞÜMÜ HESABI', rows)
        col.table(LTB, 'GÜÇ, TRAFO, KOMPANZASYON VE JENERATÖR SEÇİMİ', [
            ['BÜYÜKLÜK', 'DEĞER', 'AÇIKLAMA'],
            ['Toplam kurulu güç', f'{kw(t["inst"])} kW', 'Tüm panolar + bara kanalları + cephe + yangın pompası'],
            ['Makine yük yoğunluğu (kabul)', f'{f0(e.machine_density)} W/m²', 'Hafif imalat / montaj (makine listesi gelince güncellenecek)'],
            ['Toplam talep gücü', f'{kw(t["demand"])} kW', f'Eşzamanlılık: makine {f1(BUS_DF)} - aydınlatma 0,9 - priz 0,6 - ofis 0,8; yangın pompası hariç'],
            ['Gerekli görünür güç', f'{f1(t["S_need"])} kVA', 'cosφ=0,95 (kompanzasyon sonrası), %20 rezerv'],
            ['Trafo', f'{t["trafo"]} kVA, 34,5/0,4 kV, Dyn11, uk=%{t["uk"] * 100:.0f}', 'Köşk tipi, OSB OG şebekesinden'],
            ['Trafo sekonder akımı', f'{f1(t["In_tr"])} A', f'ADP ana şalteri {t["main_brk"]} A kompakt şalter'],
            ['Trafo - ADP kablosu', t['tr_cable'], f'Iz·k = {f0(t["tr_Iz"])} A ≥ {t["main_brk"]} A (paralel ve tava katsayıları dahil)'],
            ['ADP kısa devre akımı', f'{f1(e.ik_adp)} kA (sonsuz şebeke: {f1(t["ik"])} kA)', 'Ik3 = c·Un/(√3·Z), c=1,05; ADP şalterleri Icu ≥ 25 kA, tali panolar tabloda Ik3 değerinin üzerinde (≥ 10 kA)'],
            ['Kaçak akım koruması', 'ADP: toroid KAKR 0,3-3 A ayarlı', 'Tali pano girişleri 300 mA S (seçici), son devreler 30 mA (priz, aydınlatma, ıslak hacim), 3 faz motor 300 mA; yangın pompası beslemesinde KAKR yok (yalnız alarm)'],
            ['Kompanzasyon gücü', f'{f1(t["Qc"])} kVAr → {t["kmp"]} kVAr', 'cosφ 0,80 → 0,98, reaktif rölesi + harmonik filtre'],
            ['Acil (jeneratör) yükleri', f'{kw(t["em"])} kW', f'İdari bölüm panoları {kw(t["em_idp"])} kW + yangın pompası {kw(t["ypp"])} kW'],
            ['Jeneratör çalışma gücü', f'{f1(t["gen_run"])} kVA', 'cosφ 0,8, %25 rezerv'],
            ['Pompa yol alma kontrolü', f'{f1(t["gen_start"])} kVA', f'idari yük + yangın pompası yumuşak yol verici ile (~3 x In ≈ {f1(t["start_kva"])} kVA)'],
            ['Jeneratör', f'{t["gen"]} kVA dizel, ATS', 'İki şartın büyüğüne göre standart güç'],
        ])
        col.notes(LTB, 'NOTLAR', [
            '1- Hesaplar Elektrik İç Tesisleri Yönetmeliği ve TS HD 60364 e göredir. Besleme hatlarında gerilim düşümü ≤ %1,5.',
            '2- Kesitler IEC 60364-5-52 C yöntemi değerleri x 0,71 (tava gruplama 0,82 x 40 °C ortam 0,87) ile seçilmiştir.',
            '3- Makine güçleri bilinmediğinden üretim alanında 60 W/m² kabul edilmiş, bara kanalı ile esnek dağıtım öngörülmüştür.',
            '4- Yangın pompası ADP ana şalteri ÖNCESİNDEN ayrı devre, aM sigorta ve FE180/E90 yangına dayanıklı kablo ile beslenir (TS EN 12845).',
            '5- Yangın pompası panosu ayrıca jeneratör çıkışından (ATS öncesi) FE180 kablo ile yedeklenir; YPP içinde şebeke/jeneratör transfer şalteri (TS-YP) ve yumuşak yol verici bulunur.',
            '5a- İdari bölüm panoları ADP içindeki ATS sonrası acil baradan (jeneratör destekli) beslenir.',
            '6- 16 mm² üzeri beslemelerde ayrı PE iletkeni çekilir (TN-S, TS HD 60364-5-54).',
            '6a- Kaçak akım koruması TS HD 60364-4-41 ve EMO proje esaslarına göre kademelidir: ADP toroid KAKR (yangın koruma, gecikmeli) → tali pano girişi 300 mA S tipi → son devre 30 mA.',
            '6b- Kısa devre akımları trafo empedansı ve kablo empedansları ile hesaplanmıştır; şalter kesme kapasiteleri (Icu) tablodaki Ik3 değerinden büyük seçilecektir.',
            '7- Trafo merkezi ve OG tesisleri ayrı bir OG projesi ile OSB / dağıtım şirketi onayına sunulacaktır.',
        ])
    return layout_row(P, ctx, '04', DISC[3][2], pre, sheets, zone_std(leg, tables))


# =============================================================== 05 MEK
def build_mek(P, ctx):
    mech = P.mech
    pre = f'CLD-P{P.parcel}-MEK-'
    leg_vrf = [
        ('CLD_S_KASET', 1.0, 'VRF 4 yönlü kaset tipi iç ünite (asma tavan)'), ('CLD_S_VRFOUT', 1.0, 'VRF / multi-split dış ünite'),
        ('#' + pre + 'SOGUTUCU', 1, 'Soğutucu akışkan boru hattı (Cu, izoleli)'),
    ]
    leg_hav = [
        ('CLD_S_HRV', 1.0, 'Isı geri kazanımlı havalandırma cihazı (HRV, η ≥ %75)'),
        ('CLD_S_MENFEZ', 1.0, 'Taze hava üfleme anemostadı'), ('CLD_S_EMIS', 1.0, 'Egzoz / emiş menfezi'),
        ('CLD_S_SIGFAN', 1.0, 'WC egzoz fanı / sığınak havalandırma cihazı'),
        ('CLD_S_CATIFAN', 1.0, 'Çatı tipi aspiratör (biri frekans invertörlü)'), ('CLD_S_PANJUR', 1.0, 'Taze hava panjuru (motorlu damperli)'),
        ('#' + pre + 'KANAL-TAZE', 1, 'Taze hava kanalı'), ('#' + pre + 'KANAL-EGZOZ', 1, 'Egzoz kanalı'),
    ]
    rt_kw = sorted({h['unit_kw'] for h in mech.halls})
    leg_isi = [('CLD_S_RADYANT', 1.0, 'Doğalgazlı radyant tüp ısıtıcı ' + '/'.join(f'{k:g}'.replace('.', ',') for k in rt_kw) + ' kW (h=5-6 m)')]
    sheets = []
    SHEETS = (('VRF', ('VRF', 'OU'), 'VRF KLİMA TESİSATI PLANI', leg_vrf),
              ('HAV', ('DIF', 'EMI', 'WCE', 'HRV', 'CF', 'LV', 'FAN'), 'HAVALANDIRMA TESİSATI PLANI', leg_hav),
              ('ISI', ('RT',), 'ISITMA (RADYANT) TESİSATI PLANI', leg_isi))
    for kind, kinds, title, leg in SHEETS:
        for fk in floors_with_rooms(P):
            o = Ops(pre)
            LV = o.layer('VRF', 5)
            LR = o.layer('SOGUTUCU', 6, 'CLD_NOKTALI', 18)
            LS = o.layer('KANAL-TAZE', 4, 'CLD_KESIK', 25)
            LE = o.layer('KANAL-EGZOZ', 3, 'CLD_UZUNKESIK', 25)
            LF = o.layer('FAN-PANJUR', 2)
            LH = o.layer('ISITICI', 1)
            LT = o.layer('YAZI', 7)
            n = 0
            for u in mech.units:
                if u.floor != fk or u.kind not in kinds:
                    continue
                lay = {'VRF': LV, 'OU': LV, 'DIF': LS, 'EMI': LE, 'WCE': LE, 'HRV': LS, 'CF': LF, 'LV': LF, 'FAN': LF, 'RT': LH}[u.kind]
                o.I(lay, u.blk, (u.x, u.y), u.ang, 1.0)
                n += 1
                o.T(LT, (u.x + m(0.6), u.y + m(0.6)), H_LBL if u.kind not in ('DIF', 'EMI', 'WCE') else H_LBL * 0.8, u.label, 0)
            if kind == 'VRF':
                for (pf, pts) in mech.pipes:
                    if pf == fk:
                        o.P(LR, pts, False, 0.0)
            elif kind == 'HAV':
                for (df, dk, pts) in mech.ducts:
                    if df == fk:
                        o.P(LS if dk == 'SUP' else LE, pts, False, 0.0)
            if n == 0:
                continue
            sheets.append(Sheet(title, fk, o, leg))
    s = mech.sum

    def tables(col, LTB):
        rows = [['KAT', 'MAHAL', 'ALAN (m²)', 'SOĞUTMA (W)', 'ISITMA (W)', 'DIŞ CEPHE (m)', 'İÇ ÜNİTE', 'KİŞİ', 'TAZE HAVA (m³/h)']]
        for r in mech.rows:
            if r['kind'] != 'VRF':
                continue
            rm = r['room']
            rows.append([rm.floor, rm.name[:22], f1(rm.A), f0(r['Qc']), f0(r['Qh']), f1(r['Lx']), f'{r["n"]} x {f1(r["cap"])} kW', str(r['pers']), f0(r['fresh'])])
        rows.append(['', 'TOPLAM', '', f0(sum(r['Qc'] for r in mech.rows)), f0(sum(r['Qh'] for r in mech.rows)), '', f'{f1(s["vrf_in"])} kW', '',
                     f0(sum(r['fresh'] for r in mech.rows))])
        col.table(LTB, 'İDARİ BÖLÜM ISITMA / SOĞUTMA YÜKLERİ VE VRF SEÇİMİ (TS EN 12831 / TS 825)', rows)
        rows = [['CİHAZ', 'KAPASİTE', 'AÇIKLAMA']]
        for (ci, tin, tout, ratio) in s['comb']:
            rows.append([f'Dış ünite sistem {ci}', f'{f1(tout)} kW', f'iç ünite toplamı {f1(tin)} kW, kombinasyon oranı %{ratio * 100:.0f} (hedef %50-130)'])
        rows += [[f'HRV ({k})', f'{v} m³/h', 'Taze hava 7 l/s·kişi + 0,7 l/s·m² (TS EN 16798-1 Kat. II)'] for k, v in s['hrv'].items()]
        rows += [[f'WC egzoz fanı ({k})', f'{v} m³/h', 'Islak hacimler 10 hava değişimi, cepheye atış'] for k, v in s['exh'].items()]
        col.table(LTB, 'MERKEZİ CİHAZLAR', rows)
        rows = [['SİSTEM', 'TAHMİNİ ŞARJ (kg)', 'BORU (m)', 'EN KÜÇÜK MAHAL', 'HACİM (m³)', 'kg/m³', 'SINIR', 'DURUM']]
        for q in s.get('refr', []):
            rows.append([f'Sistem {q["sys"]}', f1(q['charge']), f0(q['Lp']), q['room'][:22], f1(q['V']), f2(q['c']), '0,44 (R410A)',
                         'UYGUN' if q['ok'] else 'SINIR AŞILIYOR → ek önlem: mahalde kaçak dedektörü + alarm + otomatik kesme vanası (TS EN 378-3)'])
        if len(rows) > 1:
            col.table(LTB, 'SOĞUTUCU AKIŞKAN YOĞUNLUK KONTROLÜ (TS EN 378-1)', rows)
        rows = [['HOL', 'ALAN (m²)', 'HACİM (m³)', 'YAZ HAVA DEĞ.', 'EGZOZ (m³/h)', 'ÇATI FANI', 'PANJUR', 'v panjur (m/s)', 'KIŞ (m³/h)',
                 'ISI KAYBI (kW)', 'RADYANT', 'KURULU (kW)']]
        for h in mech.halls:
            rows.append([h['room'].name, f1(h['room'].A), f0(h['V']), f'{f1(h["ach"])} /h', f0(h['Q']), f'{h["n"]} x {f0(h["fan"])} m³/h',
                         f'{h["n_lv"]} x {h["lv_size"]}', f1(h['v_lv']), f0(h['q_win']), f1(h['Qh'] / 1000),
                         f'{h["nh"]} x {f0(h["unit_kw"])} kW', f0(h['nh'] * h['unit_kw'])])
        col.table(LTB, 'ÜRETİM HOLLERİ HAVALANDIRMA VE ISITMA', rows)
        col.notes(LTB, 'NOTLAR', [
            '1- Hesaplar MMO proje hazırlama esasları ve TS 825, TS EN 12831, TS EN 16798-1, TS EN 378, TS 3419 e göredir. Dış hava: kış 0 °C (İzmir), yaz 35 °C KT. İç: ofis 22 °C, hol 16 °C.',
            '2- U değerleri: duvar 0,60, çatı 0,40, döşeme 0,60, pencere 2,10, sandviç panel 0,45 W/m²K.',
            '3- Isı kaybına %10 artırım, 0,5 1/h sızma ve HRV sonrası taze hava ısı ihtiyacı eklenmiştir.',
            '4- Hol çatı fanları yazın 3 1/h çalışır; kışın yalnız invertörlü fan düşük devirde 0,7 1/h (tabloda KIŞ) sağlar, ısıtıcılarla kilitlenir; panjurlar motorlu damperlidir.',
            '4a- Panjurlar yalnız holün dış cephe duvarlarına, serbest kesit hızı ≤ 2,2 m/s olacak sayı ve boyutta yerleştirilmiştir.',
            '4b- Radyant ısıtıcı adedi en az 1 adet / 180 m² kapsama ile, birim güç ısı kaybı + %15 ile seçilmiştir.',
            '5- VRF boru çapları ve soğutucu şarjı üretici seçim programı ile kesinleştirilecek; borular kauçuk köpüğü ile izole edilecek, TS EN 378 sınırı aşılırsa kaçak dedektörü konacaktır.',
            '6- Radyant ısıtıcılar için ayrı doğalgaz iç tesisat projesi (İZMİRGAZ / OSB onaylı) hazırlanacaktır.',
            '7- Sığınak havalandırması Sığınak Yönetmeliği ne göre el/elektrik tahrikli cihaz + kum filtresi ile yapılacaktır.',
        ])
    return layout_row(P, ctx, '05', DISC[4][2], pre, sheets, zone_std(leg_vrf + leg_hav + leg_isi, tables))


# =============================================================== 06 SIH
def build_sih(P, ctx):
    pl, b = P.plumb, P.b
    s = pl.sum
    pre = f'CLD-P{P.parcel}-SIH-'
    blk = {'KLOZET': 'CLD_S_KLOZET', 'LAVABO': 'CLD_S_LAVABO', 'ABDEST': 'CLD_S_ABDEST', 'EVIYE': 'CLD_S_LAVABO',
           'BULASIK': 'CLD_S_CK_BULASIK', 'DUS': 'CLD_S_DUS', 'YS': 'CLD_S_YS', 'PISUVAR': 'CLD_S_LAVABO'}
    leg_su = [
        ('#' + pre + 'TEMIZ-SU', 1, 'Temiz su hattı PPR-C PN20 (v ≤ 2 m/s)'), ('#' + pre + 'SICAK-SU', 1, 'Sıcak su hattı PPR-C PN20, izoleli'),
        ('CLD_S_TSK', S, 'Temiz su kolonu (TSK)'), ('CLD_S_SUSAYAC', S, 'Su sayacı + vana grubu'),
        ('CLD_S_CK_ISITICI', S, 'Yerel sıcak su ısıtıcısı (ASI ani ısıtıcı / TS termosifon)'),
        ('CLD_S_KLOZET', 1.0, 'Klozet (mimaride olmayanlar CLD ekledi)'), ('CLD_S_LAVABO', 1.0, 'Lavabo / eviye'),
        ('CLD_S_ABDEST', 1.0, 'Abdest (ayak yıkama) bataryası'),
    ]
    leg_pis = [
        ('#' + pre + 'PIS-SU', 1, 'Pis su hattı PVC / PP sessiz boru, %2 eğim'), ('CLD_S_PK', S, 'Pis su kolonu (PK)'),
        ('CLD_S_YS', S, 'Yer süzgeci Ø50'), ('CLD_S_ROGAR', 1.0, 'Muayene bacası (rögar) 60x60'),
    ]
    leg_yag = [
        ('#' + pre + 'YAGMUR-SUYU', 1, 'Yağmur suyu hattı PVC, %1 eğim'), ('CLD_S_YK', S, 'Yağmur iniş borusu Ø100 (YK)'),
        ('CLD_S_DEPO', 2.0, 'Yağmur suyu toplama deposu (taşma: OSB yağmur suyu hattı)'),
    ]
    leg_yng = [
        ('CLD_S_YD', 1.0, 'Yangın dolabı TS EN 671-1, 25 mm x 30 m hortum makaralı, h=1,5 m'),
        ('#' + pre + 'YANGIN', 1, 'Yangın suyu hattı siyah çelik / galvaniz, kırmızı boyalı'),
        ('CLD_S_DEPO', 2.0, 'Yangın suyu deposu + pompa istasyonu (TS EN 12845)'),
    ]
    sheets = []
    for kind, title, leg in (('SU', 'TEMİZ SU VE SICAK SU TESİSATI PLANI', leg_su), ('PIS', 'PİS SU TESİSATI PLANI', leg_pis),
                             ('YAG', 'YAĞMUR SUYU TESİSATI PLANI', leg_yag), ('YNG', 'YANGIN DOLABI TESİSATI PLANI', leg_yng)):
        for fk in floors_with_rooms(P):
            if kind == 'YAG' and fk != 'ZK':
                continue
            o = Ops(pre)
            LCW = o.layer('TEMIZ-SU', 5, None, 25)
            LHW = o.layer('SICAK-SU', 1, 'CLD_KESIK', 25)
            LDR = o.layer('PIS-SU', 32, None, 35)
            LRW = o.layer('YAGMUR-SUYU', 140, 'CLD_UZUNKESIK', 35)
            LFX = o.layer('VITRIFIYE', 7)
            LST = o.layer('KOLON', 6)
            LFW = o.layer('YANGIN', 1, None, 35)
            LT = o.layer('YAZI', 7)
            n = 0
            if kind == 'YNG':
                for c in pl.cabinets:
                    if c['floor'] == fk:
                        o.I(LFW, 'CLD_S_YD', (c['x'], c['y']), c['ang'], 1.0)
                        n += 1
                for (lf, pts, dia) in pl.fire_lines:
                    if lf == fk:
                        o.P(LFW, pts, False, 6.0)
                        if geo.path_len(pts) > m(3.0):
                            mq = pts[len(pts) // 2]
                            o.T(LT, (mq[0] + m(0.2), mq[1] + m(0.2)), H_LBL * 0.8, f'Ø{dia}', 0)
                for (rk_, rp, rz) in getattr(pl, 'risers_fire', []):
                    if rk_ == fk:
                        o.I(LFW, 'CLD_S_TSK', rp, 0.0, S)
                        o.T(LT, (rp[0] + m(0.5), rp[1] + m(0.4)), 22.0, 'YK-YNG Ø80 yangın kolonu (ZK dan)', 0)
                    elif fk == 'ZK':
                        o.I(LFW, 'CLD_S_TSK', rz, 0.0, S)
                        o.T(LT, (rz[0] + m(0.5), rz[1] + m(0.4)), 22.0, f'Ø80 yangın kolonu → {b.floor(rk_).name}', 0)
                if fk == 'ZK':
                    o.I(LFW, 'CLD_S_DEPO', pl.fire_tank_pt, 0.0, 2.0)
                    o.T(LT, (pl.fire_tank_pt[0] + m(1.5), pl.fire_tank_pt[1] + m(1.0)), 25.0, f'YANGIN SUYU DEPOSU {s["fire_tank"]} m³', 0)
                    o.I(LFW, 'CLD_S_OAP', pl.pump_pt, 0.0, S)
                    o.T(LT, (pl.pump_pt[0] + m(0.6), pl.pump_pt[1] - m(0.8)), 25.0,
                        f'YANGIN POMPA İSTASYONU {f1(s["fire_kw"])} kW + jokey {f1(s["jockey_kw"])} kW (YPP)', 0)
                if n == 0:
                    continue
                sheets.append(Sheet(title, fk, o, leg))
                continue
            for x in pl.fx:
                if x.floor != fk:
                    continue
                if kind == 'SU' and x.gen and x.tip != 'YS':
                    o.I(LFX, blk[x.tip], (x.x, x.y), 0.0, 1.0)
                if kind == 'PIS' and x.tip == 'YS':
                    o.I(LFX, blk['YS'], (x.x, x.y), 0.0, S)
            want = {'SU': ('CW', 'HW'), 'PIS': ('DR', 'SW'), 'YAG': ('RW',)}[kind]
            for (lf, lk, pts, dia) in pl.lines:
                if lf != fk or lk not in want:
                    continue
                lay = {'CW': LCW, 'HW': LHW, 'DR': LDR, 'SW': LDR, 'RW': LRW}[lk]
                o.P(lay, pts, False, 0.0)
                n += 1
                if len(pts) >= 2 and geo.path_len(pts) > m(1.5):
                    a, c = pts[-2], pts[-1]
                    o.T(LT, ((a[0] + c[0]) / 2 + m(0.2), (a[1] + c[1]) / 2 + m(0.2)), H_LBL * 0.8, f'Ø{dia}', 0)
            for st in pl.stacks:
                if fk not in st['floors'] or kind == 'YAG':
                    continue
                f = b.floor(fk)
                x, y = f.from_zk((st['x'], st['y']))
                if kind == 'PIS':
                    o.I(LST, 'CLD_S_PK', (x, y), 0.0, S)
                    o.T(LT, (x + m(0.5), y + m(0.4)), 22.0, f'{st["code"]} Ø{st["dia"]}', 0)
                else:
                    o.I(LST, 'CLD_S_TSK', (x + m(0.25), y), 0.0, S)
                    o.T(LT, (x + m(0.5), y + m(0.4)), 22.0, f'TSK Ø{st["cw"]}', 0)
            if kind == 'SU':
                for h in pl.heaters:
                    if h['floor'] == fk:
                        o.I(LHW, 'CLD_S_CK_ISITICI', (h['x'], h['y']), h['ang'], S)
                        o.T(LT, (h['x'] + m(0.4), h['y'] - m(0.5)), H_LBL * 0.8, h['kind'], 0)
                        n += 1
            if fk == 'ZK' and kind == 'PIS':
                for r in pl.rogars:
                    o.I(LDR, 'CLD_S_ROGAR', (r['x'], r['y']), 0.0, 1.0)
                    o.T(LT, (r['x'] + m(0.6), r['y'] + m(0.6)), 22.0, r['code'], 0)
                if pl.rogars:
                    o.T(LT, (pl.osb[0] + m(0.6), pl.osb[1] - m(0.8)), 22.0, 'OSB KANALİZASYON BAĞLANTISI', 0)
                n += 1
            if fk == 'ZK' and kind == 'YAG':
                for d in pl.downpipes:
                    o.I(LRW, 'CLD_S_YK', (d['x'], d['y']), 0.0, S)
                o.P(LRW, pl.rain_ring, True, 0.0)
                rr = pl.rain_ring[len(pl.rain_ring) // 3]
                o.T(LT, (rr[0] + m(0.3), rr[1] + m(0.3)), 22.0, f'Toplama kollektörü Ø{s["ring_dia"]} PVC %1', 0)
                o.I(LRW, 'CLD_S_DEPO', pl.tank, 0.0, 2.0)
                o.T(LT, (pl.tank[0] + m(1.5), pl.tank[1] + m(1.0)), 25.0, f'YAĞMUR SUYU TOPLAMA DEPOSU {s["rain_tank"]} m³', 0)
                o.T(LT, (pl.overflow[0] + m(0.5), pl.overflow[1]), 22.0, f'taşma Ø{s["inlet_dia"]} → OSB yağmur suyu hattı', 0)
                n += 1
            if fk == 'ZK' and kind == 'SU':
                o.I(LCW, 'CLD_S_SUSAYAC', pl.meter, 0.0, S)
                o.T(LT, (pl.meter[0] + m(0.6), pl.meter[1] + m(0.4)), 22.0, f'SU SAYACI - OSB şebeke girişi Ø{s["main"]}', 0)
                n += 1
            if n == 0:
                continue
            sheets.append(Sheet(title, fk, o, leg))

    def tables(col, LTB):
        rows = [['KAT', 'MAHAL', 'ARMATÜRLER', 'YB (LU)', 'DU (l/s)', 'KOLON']]
        for rr in pl.room_rows:
            c = Counter(x.tip for x in rr['fxs'])
            rows.append([rr['room'].floor, rr['room'].name[:22], ', '.join(f'{v} {k.lower()}' for k, v in c.items()), str(rr['LU']), f1(rr['DU']), rr['stack']])
        col.table(LTB, 'ARMATÜR YÜKLERİ (TS EN 806-3 / TS EN 12056-2)', rows)
        rows = [['KOLON', 'KATLAR', 'Σ YB', 'Qd (l/s)', 'TEMİZ SU', 'SICAK SU', 'Σ DU', 'Qww (l/s)', 'PİS SU KOLONU']]
        for st in pl.stacks:
            rows.append([st['code'], ', '.join(st['floors']), str(st['LU']), f2(st['qd']), f'Ø{st["cw"]}',
                         f'{st["n_heat"]} yerel ısıtıcı' if st.get('n_heat') else '-', f1(st['DU']), f2(st['Q']), f'Ø{st["dia"]}'])
        col.table(LTB, 'KOLON HESAPLARI (Qww = max(K·√ΣDU, DUmax), K = 0,7)', rows)
        rows = [['OLUK', 'TİP', 'ALAN (m²)', 'C', 'Q (l/s)', 'Ø100 (adet)', 'KAPASİTE (l/s)']]
        for g in s.get('gutters', []):
            rows.append([g['code'], g['kind'], f0(g['A']), f1(g['C']), f1(g['Q']), str(len(g.get('pts', []))), f1(4.5 * len(g.get('pts', [])))])
        if len(rows) > 1:
            col.table(LTB, 'YAĞMUR OLUKLARI - ALAN VE İNİŞ HESABI (TS EN 12056-3)', rows)
        col.table(LTB, 'GENEL HESAPLAR', [
            ['BÜYÜKLÜK', 'DEĞER', 'AÇIKLAMA'],
            ['Kullanıcı sayısı', f'{s["pers"]} kişi', 'Mimari proje notu'],
            ['Günlük kullanım suyu', f'{f2(s["daily"])} m³/gün', '60 l/kişi·gün + temizlik'],
            ['Kullanım suyu deposu', f'{s["tank_dom"]} m³', '1,5 günlük'],
            ['Toplam yük birimi / anlık debi', f'{s["LU"]} YB / {f2(s["qd"])} l/s', 'DIN 1988-300'],
            ['Ana besleme borusu', f'Ø{s["main"]} PPR-C PN20', 'v ≤ 2 m/s, OSB şebekesi ≥ 3 bar kabul'],
            ['Hidrofor', f'2 x {f1(s["hyd_kw"])} kW, H={f0(s["H"])} mSS', '1 asil + 1 yedek, frekans kontrollü'],
            ['Yangın suyu deposu', f'{s["fire_tank"]} m³', '2 dolap x 100 l/dk x 60 dk'],
            ['Yangın pompası', f'{f1(s["fire_kw"])} kW + jokey {f1(s["jockey_kw"])} kW', 'Elektrikli (alternatif dizel), TS EN 12845'],
            ['Çatı alanı / yağmur debisi', f'{f0(s["A_roof"])} m² / {f1(s["Qr"])} l/s', 'r = 0,030 l/s·m², C: saçak 1,0 / iç dere 1,5 (TS EN 12056-3)'],
            ['Yağmur iniş borusu (gerekli / yerleştirilen)', f'{s["n_req"]} / {s["n_yk"]} adet Ø100', 'Ø100 kapasite 4,5 l/s, her oluk kendi alanına göre'],
            ['Yangın dolabı', f'{s["n_cab"]} adet', 'Her nokta ≤ 25 m kapsama (30 m hortum), çıkış kapılarına yakın - BYKHY Md. 93'],
            ['Toplama kollektörü / depo girişi', f'Ø{s["ring_dia"]} / Ø{s["inlet_dia"]} PVC', 'Manning, %1 eğim, tam dolu'],
            ['Yağmur suyu toplama deposu', f'{s["rain_tank"]} m³', '20 l/m² çatı (KOSBİ yağmur suyu hasadı), taşma OSB hattına'],
        ])
        col.notes(LTB, 'NOTLAR', [
            '1- Pis su sistemi TS EN 12056-2 Sistem I (K=0,7) ile hesaplanmış, tüm kolonlar çatıdan havalandırılacaktır.',
            '2- Yatay pis su hatları en az %2, yağmur suyu hatları %1 eğimle; her yön değişiminde rögar / temizleme kapağı olacaktır.',
            '3- Merkezi sıcak su yoktur: her ıslak hacimde yerel elektrikli ani ısıtıcı (ASI) / 80 l termosifon (TS) bulunur (elektrik projesinde özel çıkış), termosifon 60 °C (lejyonella).',
            '4- İç dere (orta oluk) inişleri risk katsayısı C=1,5 ile hesaplanmış, bina içinden kolon hizasında indirilip döşeme altından kollektöre bağlanmıştır; taşma ağzı oluk projesinde verilecektir.',
            '5- Vitrifiye yerleri mimariden alınmıştır; mimaride bulunmayanlar CLD tarafından eklenmiştir, sahada teyit edilecektir.',
            '6- Yangın dolapları Binaların Yangından Korunması Hakkında Yönetmelik ve TS EN 671-1 e göre; yangın hattı pompa istasyonundan Ø80 ana hat, Ø50 branşman ile beslenir.',
            '7- Hesaplar MMO sıhhi tesisat proje hazırlama esasları, TS EN 806-3, TS EN 12056-2/3, DIN 1988-300 ve TS EN 12845 e göredir.',
        ])
    std = zone_std(leg_su + leg_pis + leg_yag + leg_yng, tables)

    def zone(o, x, y, colmax):
        w1, h1 = riser_diagram(o, x, y, P, pre)
        w2, h2 = std(o, x + w1 + 400, y, colmax)
        return w1 + 400 + w2, max(h1, h2)
    return layout_row(P, ctx, '06', DISC[5][2], pre, sheets, zone)


def riser_diagram(o, x, y, P, pre):
    """temiz su / pis su kolon şeması (MMO): one vertical per stack, floor levels, branch loads."""
    pl, b = P.plumb, P.b
    LS = o.layer('KOLON-SEMASI', 7, None, 25)
    LCW = o.layer('TEMIZ-SU', 5, None, 25)
    LDR = o.layer('PIS-SU', 32, None, 35)
    LT = o.layer('YAZI', 7)
    floors = sorted([f for f in b.floors if f.rooms], key=lambda f: f.kot)
    if not pl.stacks or not floors:
        return 0.0, 0.0
    fh = 1400.0
    col_w = 2200.0
    x0 = x + 900
    top = y - 300
    o.T(LT, (x, y), 40.0, 'TEMİZ SU VE PİS SU KOLON ŞEMASI', 0)
    ybase = top - 300 - fh * len(floors)
    W = 900 + col_w * len(pl.stacks)
    for j, f in enumerate(floors):
        fy = ybase + j * fh
        o.L(LS, (x, fy), (x + W, fy))
        o.T(LT, (x + 20, fy + 40), 28.0, f'{f.name} {"±" if f.kot == 0 else "+"}{f2(f.kot)}', 0)
    for i, st in enumerate(pl.stacks):
        cx = x0 + i * col_w
        fis = [j for j, f in enumerate(floors) if f.key in st['floors']]
        if not fis:
            continue
        ytop = ybase + max(fis) * fh + 900
        o.P(LDR, [(cx, ybase - 500), (cx, ytop + 300)], False, 12.0)
        o.T(LT, (cx + 30, ytop + 330), 22.0, 'havalık (çatıdan)', 0)
        o.T(LT, (cx - 100, ytop + 450), 30.0, f'{st["code"]} Ø{st["dia"]}', 0)
        rog = next((r['code'] for r in pl.rogars if r['stack'] == st['code']), '')
        o.P(LDR, [(cx, ybase - 500), (cx + 700, ybase - 500)], False, 12.0)
        o.T(LT, (cx + 720, ybase - 520), 22.0, f'→ {rog} rögar', 0)
        o.P(LCW, [(cx + 250, ybase - 300), (cx + 250, ybase + max(fis) * fh + 600)], False, 6.0)
        o.T(LT, (cx + 280, ybase - 280), 20.0, f'TSK Ø{st["cw"]} ← sayaç/hidrofor', 0)
        for j in fis:
            f = floors[j]
            fy = ybase + j * fh + 500
            rows = [rr for rr in pl.room_rows if rr['stack'] == st['code'] and rr['room'].floor == f.key]
            c = Counter(xx.tip for rr in rows for xx in rr['fxs'])
            du = sum(rr['DU'] for rr in rows)
            lu = sum(rr['LU'] for rr in rows)
            o.P(LDR, [(cx, fy), (cx + 900, fy)], False, 8.0)
            o.P(LCW, [(cx + 250, fy + 150), (cx + 900, fy + 150)], False, 4.0)
            o.T(LT, (cx + 950, fy + 60), 20.0, ', '.join(f'{v} {k.lower()}' for k, v in c.items())[:44], 0)
            o.T(LT, (cx + 950, fy + 10), 20.0, f'ΣDU {f1(du)} l/s - ΣYB {lu}', 0)
    return W + 300, (y - ybase) + 700



# =============================================================== 07 YUK
def pick_brk(kvar):
    I = kvar * 1000 / (1.732 * 400) * 1.43
    for v in (16, 25, 32, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 630):
        if v >= I:
            return v
    return 630


def build_yuk(P, ctx):
    e = P.elec
    pre = f'CLD-P{P.parcel}-YUK-'
    loads = e._loads

    def tables(col, LTB):
        order = [k for k in e.panels if k.startswith('UTP')] + [k for k in e.panels if k.startswith('IDP')]
        for code in order:
            pn = e.panels[code]
            cs = [c for c in e.circuits if c.panel == code]
            rows = [['LİNYE', 'AÇIKLAMA', 'AYD. (ad)', 'PRİZ/ÇIKIŞ (ad)', 'GÜÇ (W)', 'R (W)', 'S (W)', 'T (W)', 'SİGORTA', 'K.AKIM', 'KABLO']]
            tot = {'R': 0.0, 'S': 0.0, 'T': 0.0}
            for c in cs:
                ph = {'R': '', 'S': '', 'T': ''}
                if c.phase == 'RST':
                    for k in ph:
                        ph[k] = f0(c.W / 3)
                        tot[k] += c.W / 3
                else:
                    ph[c.phase] = f0(c.W)
                    tot[c.phase] += c.W
                rows.append([c.code, c.desc[:46], str(c.nl) if c.nl else '', str(c.no) if c.no else '', f0(c.W), ph['R'], ph['S'], ph['T'], c.brk, c.rcd, c.cable])
            inst = sum(c.W for c in cs)
            dem = loads[code]['demand']
            rows.append(['', 'KURULU GÜÇ', '', '', f0(inst), f0(tot['R']), f0(tot['S']), f0(tot['T']), '', '', ''])
            rows.append(['', 'TALEP GÜCÜ', '', '', f0(dem), '', '', '', '', '', ''])
            fd = pn.feeder
            rows.append(['', f'BESLEME: {fd.get("cable", "")}, giriş {fd.get("In", "")} A + {fd.get("rcd", "")}' + (' (acil bara)' if pn.acil else ''), '', '', '', '', '', '', '', '', ''])
            rows.append(['', f'Ik3 ≈ {f1(fd.get("Ik", 0))} kA → şalter Icu ≥ {fd.get("Icu", 10)} kA', '', '', '', '', '', '', '', '', ''])
            imb = (max(tot.values()) - min(tot.values())) / (max(tot.values()) or 1) * 100
            rows.append(['', f'Faz dengesizliği %{f1(imb)}', '', '', '', '', '', '', '', '', ''])
            col.table(LTB, f'{code} - {pn.name} YÜKLEME CETVELİ', rows)
        rows = [['ÇIKIŞ', 'AÇIKLAMA', 'KURULU (W)', 'TALEP (W)', 'KORUMA', 'KABLO']]
        for code, pn in e.panels.items():
            if code in ('ADP', 'KMP', 'YPP') or not pn.feeder:
                continue
            rows.append([code, pn.name + (' (acil bara)' if pn.acil else ''), f0(loads[code]['inst']), f0(pn.feeder['P']), pn.feeder['prot'], pn.feeder['cable']])
        for bb in e.busbars:
            rows.append([bb['code'], bb['desc'], f0(bb['P']), f0(bb['Pd']), f'{bb["In"]} A + {bb["rcd"]}', bb['cable']])
        t = e.tot
        rows.append(['CEPHE', 'Cephe projektörleri', f0(e.cephe['P']), f0(e.cephe['P']), '16 A + 300 mA', e.cephe['cable']])
        rows.append(['KMP', f'Kompanzasyon {t["kmp"]} kVAr', '', '', f'{pick_brk(t["kmp"])} A', ''])
        ypp = e.panels.get('YPP')
        dem_wo = t['demand']
        rows.append(['', 'TOPLAM (yangın pompası hariç)', f0(t['inst'] - t['ypp']), f0(dem_wo), f'ANA: {t["main_brk"]} A', f'Trafo {t["trafo"]} kVA'])
        if ypp and ypp.feeder:
            rows.append(['YPP', 'Yangın pompa panosu - ANA ŞALTER ÖNCESİ ayrı devre', f0(t['ypp']), f0(t['ypp']), ypp.feeder['prot'], ypp.feeder['cable']])
        col.table(LTB, 'ADP - ANA DAĞITIM PANOSU YÜKLEME CETVELİ', rows)
        col.notes(LTB, 'NOTLAR', [
            f'1- Aydınlatma eşzamanlılığı 0,9, priz ve kuvvet 0,6, idari panolar 0,8, makine bara kanalları {f1(BUS_DF)} alınmıştır.',
            '2- Priz başına 300 W, endüstriyel priz grubu 5 kW, özel çıkışlar cihaz etiket gücü ile hesaplanmıştır.',
            '3- Faz dağılımı en yüklü linyeden başlayarak en az yüklü faza atanmış, takas ile iyileştirilmiştir; birkaç büyük tek fazlı yükü olan küçük panolarda dengesizlik %10 u aşabilir.',
            '4- Tali pano ana şalterleri en büyük çıkış sigortasının en az 1,6 katı seçilmiştir (seçicilik).',
            '5- Yangın pompası yangın anında üretim durduğu için trafo talep gücüne eklenmemiş, ana şalter öncesinden beslenmiştir.',
        ])
    return layout_row(P, ctx, '07', DISC[6][2], pre, [], zone_std([], tables))


# =============================================================== 08 KOL
def build_kol(P, ctx):
    e, b = P.elec, P.b
    t = e.tot
    pre = f'CLD-P{P.parcel}-KOL-'

    def diagram(o, x0, y, colmax):
        LS = o.layer('SEMA', 7, None, 35)
        LK = o.layer('KAT', 8, 'CLD_KESIK', 18)
        LT = o.layer('YAZI', 7)
        floors = sorted(b.floors, key=lambda f: f.kot)
        band = 2600.0
        band0 = 5000.0           # ground floor band: trafo/jen/YPP/KMP, ADP, both buses and the ZK panels
        base_y = y - 400 - band0 - band * (len(floors) - 1)

        def fy_of(i):
            return base_y + (0.0 if i == 0 else band0 + (i - 1) * band)
        normal = [(c, pn) for c, pn in e.panels.items() if c not in ('ADP', 'KMP', 'YPP') and not pn.acil]
        normal += [(bb['code'], bb) for bb in e.busbars]
        normal += [('CEPHE', dict(cephe=True, **e.cephe))]
        acil = [(c, pn) for c, pn in e.panels.items() if c not in ('ADP', 'KMP', 'YPP') and pn.acil]
        outs = normal + acil
        W = max(26000.0, 9600 + 1900.0 * len(outs))
        for i, f in enumerate(floors):
            fy = fy_of(i)
            o.L(LK, (x0, fy), (x0 + W, fy))
            o.T(LT, (x0 + 50, fy + 60), 45.0, f'{f.name}  ({"±" if f.kot == 0 else "+"}{f2(f.kot)} m)', 0)
        o.L(LK, (x0, fy_of(len(floors))), (x0 + W, fy_of(len(floors))))
        gy = base_y + 2000
        tx = x0 + 1800

        def box_(cx, cy, w, h, lines):
            o.P(LS, [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2), (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)], True, 4.0)
            for k, s_ in enumerate(lines):
                if s_:
                    o.T(LT, (cx, cy + h / 2 - 70 - k * 50), 32.0 if k == 0 else 25.0, s_, 1)
        box_(tx, gy - 300, 1700, 600, ['TRAFO', f'{t["trafo"]} kVA 34,5/0,4 kV', f'Dyn11 uk=%{t["uk"] * 100:.0f}'])
        box_(tx, gy + 650, 1700, 450, ['JENERATÖR', f'{t["gen"]} kVA'])
        ax = x0 + 5600
        box_(ax, gy, 2800, 1300, ['ADP', 'ANA DAĞITIM PANOSU', f'Ana şalter {t["main_brk"]} A + toroid KAKR', f'Ik ≈ {f1(t["ik"])} kA',
                                  'SPD Tip 1+2, analizör, ATS', f'Kurulu {kw(t["inst"])} kW', f'Talep {kw(t["demand"])} kW'])
        o.L(LS, (tx + 850, gy - 300), (ax - 1400, gy - 300))
        o.T(LT, (tx + 900, gy - 260), 22.0, t['tr_cable'], 0)
        o.L(LS, (tx + 850, gy + 650), (ax - 1400, gy + 300))
        o.T(LT, (tx + 900, gy + 690), 22.0, 'jeneratör → ATS (acil bara)', 0)
        box_(ax, gy - 1050, 1800, 450, ['KMP', f'Kompanzasyon {t["kmp"]} kVAr'])
        o.L(LS, (ax, gy - 650), (ax, gy - 825))
        # fire pump: tapped before the ADP main breaker, backed up from the generator terminals (ahead of the ATS)
        ypp = e.panels.get('YPP')
        if ypp is not None and ypp.feeder:
            px = tx + 1000
            o.L(LS, (px, gy - 600), (px, gy - 1200))
            box_(px, gy - 1500, 1700, 600, ['YPP', 'YANGIN POMPA PANOSU', 'TS-YP şebeke / jeneratör', ypp.feeder['prot'], ypp.feeder['cable']])
            o.T(LT, (px + 60, gy - 800), 20.0, 'ana şalter öncesi (KAKR yok)', 0)
            if e.gen_ypp:
                o.P(LS, [(tx - 850, gy + 650), (tx - 1050, gy + 650), (tx - 1050, gy - 1500), (px - 850, gy - 1500)], False, 4.0)
                o.T(LT, (tx - 1000, gy - 1100), 20.0, 'jeneratör yedek (ATS öncesi)', 0)
                o.T(LT, (tx - 1000, gy - 1150), 20.0, e.gen_ypp['cable'], 0)
        xs = ax + 2400
        step = max(1700.0, (W - 9600) / max(1, len(outs)))
        bus_n = gy + 750
        bus_a = gy + 950
        n_norm = len(normal)
        if n_norm:
            # normal bus: from the ADP top straight up, ends at the last normal column
            o.L(LS, (ax + 1000, gy + 650), (ax + 1000, bus_n))
            o.P(LS, [(ax + 1000, bus_n), (xs + step * (n_norm - 1) + 150, bus_n)], False, 10.0)
            o.T(LT, (ax + 1050, bus_n - 80), 25.0, 'ŞEBEKE BARASI', 0)
        if acil:
            # emergency bus: leaves the ADP (ATS) below the normal bus, spans only the emergency columns
            xa = xs + step * (n_norm - 0.5)
            o.P(LS, [(ax + 1400, gy - 400), (xa, gy - 400), (xa, bus_a)], False, 4.0)
            o.P(LS, [(xa, bus_a), (xs + step * (len(outs) - 1) + 150, bus_a)], False, 10.0)
            o.T(LT, (xa + 50, bus_a + 40), 25.0, 'ACİL BARA (ATS - jeneratör destekli)', 0)
            o.T(LT, (ax + 1450, gy - 360), 20.0, 'ATS çıkışı', 0)
        loads = e._loads
        fkeys = [f.key for f in floors]
        for i, (code, pn) in enumerate(outs):
            cx = xs + step * i
            fd = {}
            if isinstance(pn, dict) and pn.get('cephe'):
                fl = 'ZK'
                lines = ['CEPHE AYD.', f'{len(e.facade)} x projektör', f'P={kw(pn["P"])} kW', f'{pn["In"]} A + fotosel',
                         f'L={f1(pn["L"])} m %e={f2(pn["du"])}']
                fd = pn
            elif isinstance(pn, dict):
                fl = 'ZK'
                lines = [code, f'{pn["rating"]} A bara kanalı', f'P={kw(pn["P"])} kW', f'{pn["In"]} A + {pn.get("rcd", "300 mA S")}', f'L={f1(pn["L"])} m %e={f2(pn["du"])}']
                fd = pn
            else:
                fl = pn.floor
                fd = pn.feeder or {}
                lines = [code, pn.name[:26], f'Kurulu {kw(loads.get(code, {}).get("inst", 0))} kW',
                         f'Giriş {fd.get("In", "-")} A + 300 mA S', f'{len(pn.circuits)} linye' if pn.circuits else '']
            fi = fkeys.index(fl) if fl in fkeys else 0
            py = fy_of(fi) + 1300 if fi else bus_a + 1300
            src_y = bus_a if (not isinstance(pn, dict) and pn.acil) else bus_n
            o.L(LS, (cx, src_y), (cx, py - 550))
            box_(cx, py, step * 0.85, 1100, lines)
            if fd.get('cable'):
                ly = (src_y + py - 550) / 2
                o.T(LT, (cx + 40, ly), 20.0, fd['cable'], 0)
                o.T(LT, (cx + 40, ly - 40), 20.0, f'L={f1(fd["L"])} m %e={f2(fd["du"])}', 0)
        o.T(LT, (x0 + 50, base_y - 300), 30.0, 'Topraklama: ADP PE barası → AEB → temel topraklama ağı (birleşik topraklama, R ≤ 2 Ω)', 0)
        o.T(LT, (x0 + 50, base_y - 380), 25.0, 'Kablolar Cu, IEC 60364-5-52 C yöntemi x düzeltme katsayıları, gerilim düşümü ≤ %1,5. Değerler yükleme cetvelleri ile uyumludur.', 0)
        return W + 400, (y - base_y) + 500
    return layout_row(P, ctx, '08', DISC[7][2], pre, [], diagram)


# =============================================================== 09 AYH
def build_ayh(P, ctx):
    e, b = P.elec, P.b
    pre = f'CLD-P{P.parcel}-AYH-'

    def tables(col, LTB):
        rows = [['KAT', 'MAHAL', 'ALAN (m²)', 'h (m)', 'hm (m)', 'k', 'η', 'MF', 'Em (lx)', 'ARMATÜR', 'Φ (lm)', 'N hesap', 'N seçilen',
                 'E (lx)', 'W/m²', 'DURUM']]
        for f in b.floors:
            for r in f.rooms:
                c = e.calc.get(r.id)
                if not c:
                    continue
                ok = c['E_real'] >= c['E'] * 0.98
                rows.append([f.key, r.name[:22], f1(c['A']), f2(c['h']), f2(c['hm']), f2(c['k']), f2(c['uf']), f2(c['MF']), str(c['E']),
                             c['kod'], f0(c['lm']), f1(c['N']), str(c['n']), f0(c['E_real']), f1(c['Wm2']), 'UYGUN' if ok else 'YETERSİZ'])
        for i in range(0, len(rows) - 1, 50):
            col.table(LTB, 'AYDINLATMA HESAP TABLOSU (Lümen metodu)' + (f' ({i // 50 + 1})' if len(rows) > 51 else ''), [rows[0]] + rows[1 + i:1 + i + 50])
        tot_W = sum(LUM[l.kod][1] for l in e.lums)
        tot_A = sum(r.A for f in b.floors for r in f.rooms)
        col.table(LTB, 'ARMATÜR LİSTESİ', [['KOD', 'AÇIKLAMA', 'ADET', 'GÜÇ (W)']] +
                  [[k, LUM[k][0], str(sum(1 for l in e.lums if l.kod == k)), f0(sum(LUM[k][1] for l in e.lums if l.kod == k))]
                   for k in LUM if any(l.kod == k for l in e.lums)] + [['', 'TOPLAM', str(len(e.lums)), f0(tot_W)]])
        col.notes(LTB, 'HESAP YÖNTEMİ', [
            'N = Em · A / (Φ · η · MF)     k = 2·A / (hm · Ç)     E = N · Φ · η · MF / A ≥ Em',
            'Em: TS EN 12464-1 bakım aydınlık düzeyi, η: kullanım faktörü (yansıma tavan/duvar/zemin 0,7/0,5/0,2),',
            'MF: bakım faktörü (temiz ortam 0,80 - üretim/teknik 0,70), hm: armatür - çalışma düzlemi (0,85 m) arası, Ç: mahal çevresi.',
            f'Toplam aydınlatma gücü {kw(tot_W)} kW, ortalama güç yoğunluğu {f1(tot_W / max(1, tot_A))} W/m².',
            'Acil aydınlatma: kaçış yolları ≥ 1 lx, yüksek riskli alanlar ≥ %10 Em, süre 3 saat (TS EN 1838, BYKHY).',
            f'Armatür yerleşimi ayrı "AYDINLATMA TESİSATI PLANI" paftalarında (CLD-P{P.parcel}-ICT-* katmanları) gösterilmiştir.',
        ])
    return layout_row(P, ctx, '09', DISC[8][2], pre, [], zone_std([], tables))


BUILDERS = {'01': build_ict, '02': build_top, '03': build_par, '04': build_kak, '05': build_mek,
            '06': build_sih, '07': build_yuk, '08': build_kol, '09': build_ayh}
