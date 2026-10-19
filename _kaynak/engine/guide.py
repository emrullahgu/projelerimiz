"""Writes CLAUDE_LISP_BROSCO/OKU_BENI.txt (user guide) from the build report."""
import json, os, sys

out = sys.argv[1]
rep = json.load(open(os.path.join(out, '_kaynak', 'build_report.json'), encoding='utf-8'))
CMD = {'01': 'ICTESISAT', '02': 'TOPRAKLAMA', '03': 'PARATONER', '04': 'KUVVETLIAKIM', '05': 'MEKANIK',
       '06': 'SIHHITESISAT', '07': 'YUKLEMECETVELI', '08': 'KOLONSEMASI', '09': 'AYDHESABI'}
NAMES = {'01': 'Elektrik İç Tesisat (aydınlatma ve priz ayrı paftalar)', '02': 'Topraklama', '03': 'Paratoner',
         '04': 'Kuvvetli Akım (güç dağıtım)', '05': 'Mekanik (VRF klima, havalandırma, radyant ısıtma ayrı paftalar)',
         '06': 'Sıhhi Tesisat (temiz-sıcak su, pis su, yağmur suyu ayrı paftalar)', '07': 'Yükleme Cetvelleri',
         '08': 'Kolon Şeması', '09': 'Aydınlatma Hesabı'}
L = []
w = L.append
w('CLD - BROSCO PARSEL 2-3-4-5 MÜHENDİSLİK LISP PAKETİ')
w('=' * 60)
w('')
w('Bu klasördeki tüm dosyalar, komutlar, katmanlar ve bloklar "CLD" önekiyle adlandırılmıştır;')
w('başka bir araçla (ör. CXB önekli dosyalar) hazırlanan LISP\'lerle çakışmaz. BROSCO_LISP ve')
w('CODEX_... klasörlerine dokunulmamıştır.')
w('')
w('KULLANIM')
w('--------')
w('1) İlgili mimari dosyayı açın: "BROSCO <n> NOLU PARSEL MİMARİ.dwg".')
w('2) APPLOAD ile PARSEL_<n> klasöründen istediğiniz CLD_P<n>_0x_*.lsp dosyasını (veya 9 dosyanın hepsini) yükleyin.')
w('   Dosya yüklenir yüklenmez çizim kendiliğinden oluşur, hiçbir soru sorulmaz.')
w('   AutoCAD güvenlik uyarısı verirse "Bir kez yükle" seçin; kalıcı çözüm: Seçenekler > Dosyalar > Güvenilen Konumlar a PARSEL_<n> klasörünü ekleyin.')
w('   Dosya yanlış parselin DWG sinde açılırsa çizmez, uyarı verir (komutu yazarak yine de çizdirilebilir).')
w('3) Çizimler mimarinin SAĞ tarafında, her disiplin ayrı bir satırda olacak şekilde yerleşir:')
w('   her tesisat ve her kat için ayrı çerçeveli pafta (gri mimari altlık + tesisat), satır sonunda lejant,')
w('   notlar ve hesap tabloları. Orijinal mimari paftaların üzerine hiçbir şey çizilmez.')
w('4) Tekrar çizmek için dosyadaki komutu yazın (aşağıdaki liste). Tekrar çizimde o disiplinin "CLD-P<n>-xxx-*"')
w('   katmanları temizlenip yeniden oluşturulur. Geri almak için UNDO (tek adım) kullanılabilir.')
w('5) Katmanlar: CLD-P<n>-ICT-* (iç tesisat), -TOP- (topraklama), -PAR- (paratoner), -KAK- (kuvvetli akım), -MEK- (mekanik),')
w('   -SIH- (sıhhi), -YUK- (yükleme), -KOL- (kolon şeması), -AYH- (aydınlatma hesabı). Gri mimari altlık: CLD-P<n>-xxx-ALTLIK.')
w('   Her pafta kendi lejantını çerçevesi içinde taşır; doğrudan çıktı alınabilir (1/100).')
w('')
w('Not: Mimari çizimler santimetre birimindedir (3 ve 5 nolu parsel WCS XZ düzleminde / Front UCS, 2 ve 4 nolu parsel XY);')
w('LISP ler mimarinin düzlemini otomatik algılar ve aynı düzlemde çizer. Paftalar 1/100 çıktıya göre ölçeklenmiştir.')
w('')
w('HAZIR ÇIKTILAR (LISP uygulanmış)')
w('-------------------------------')
w('Projeler         : her parsel için 9 LISP in uygulandığı DWG (mimari + tüm tesisat paftaları, ayrı katmanlarda).')
w('Projeler PDF     : her parsel için disiplin başına çok sayfalı PDF (CLD_Pn_0x_*.pdf) ve tüm proje seti')
w('                   (CLD_Pn_00_TUM_PROJELER.pdf, yer imli). Plan paftaları 1/100 gerçek ölçekte, uygun ISO kağıda')
w('                   (A0 / B0 / 2A0) basılmıştır; hesap tabloları ölçeksizdir.')
w('')
w('STANDARTLAR VE ODA (EMO / MMO) UYUMU')
w('------------------------------------')
for s_ in [
    'Her paftada EMO / MMO formatında antet: işin adı, yapı sahibi, adres (ada/parsel), pafta adı, ölçek, tarih, pafta no;',
    '  proje müellifi adı, oda sicil no, SMM belge no ve imza alanları imza için boş bırakılmıştır.',
    'Kaçak akım (TS HD 60364-4-41, EMO): tüm tek fazlı son devreler 30 mA (bilgisayar/VRF A tipi), 3 fazlı motor devreleri 300 mA,',
    '  tali pano girişleri 300 mA S tipi (seçici), ADP ana şalterinde ayarlı toroid kaçak akım rölesi (yangın koruma);',
    '  yangın pompası beslemesinde açtırmalı kaçak akım rölesi yoktur (yalnız alarm, TS EN 12845).',
    'Gerilim düşümü: aydınlatma ve priz linyeleri ≤ %1,5, kuvvet ≤ %3, besleme hatları ≤ %1,5 (aşan linyeler otomatik bölündü).',
    'Kısa devre: her panoda Ik3 hesaplandı, şalter kesme kapasiteleri tabloda; trafo kablosunda her paralel hatta ayrı PE.',
    'Yangın pompası: trafo çıkışından ana şalter öncesi + jeneratörden (ATS öncesi) yedek besleme, yumuşak yol verici.',
    'Mekanik (MMO): TS 825 / TS EN 12831 ısı kaybı, TS EN 16798-1 taze hava, TS EN 378-1 soğutucu yoğunluk kontrolü,',
    '  radyant ısıtıcılar ısı kaybına göre boyutlandırıldı, panjurlar yalnız dış cephede.',
    'Sıhhi (MMO): TS EN 806-3 / DIN 1988-300, TS EN 12056-2/3 (iç dere C=1,5), temiz su - pis su kolon şeması,',
    '  yangın dolapları (BYKHY, TS EN 671-1, 25 m kapsama) ve yangın hattı ayrı paftada.',
]:
    w(('      ' + s_.strip()) if s_.startswith('  ') else ('  - ' + s_))
w('')
w('DOSYALAR VE KOMUTLAR')
w('--------------------')
for code in sorted(CMD):
    w(f'  CLD_P<n>_{code}_*.lsp   {NAMES[code]:58s} komut: CLD_P<n>_{CMD[code]}')
w('')
for p in sorted(rep):
    r = rep[p]
    w(f'PARSEL {p}')
    w('-' * 9)
    for s in r['summary']:
        w('  ' + s)
    w('  Dosyalar:')
    for f in r['files']:
        w(f'    {f[0]:42s} {f[1]:5d} çizim komutu  {f[2] / 1024:6.0f} KB')
    w('')
w('MÜHENDİSLİK KABULLERİ (sahada / işverenle teyit edilmelidir)')
w('-----------------------------------------------------------')
for s in [
    'Konum İzmir/Kemalpaşa (KOSBİ): kış dış sıcaklığı 0 °C, yaz 35 °C, yıldırım yoğunluğu Ng = 3 /km²/yıl.',
    'Üretim makine yükleri bilinmediğinden 60 W/m² (hafif imalat) kabul edilmiş, bara kanalı ile dağıtılmıştır.',
    'Aydınlatma TS EN 12464-1: üretim 300 lx (LED highbay 150 W), ofis 500 lx (panel 36 W), lobi 200, WC 200, hol 100 lx.',
    'Zemin özdirenci 100 Ωm kabul edilmiştir; topraklama ölçümü ile doğrulanmalıdır.',
    'Mekanik: idari bölüm VRF ısı pompası + ısı geri kazanımlı taze hava; üretim holü çatı fanı (3 hava değ./h) + radyant ısıtıcı.',
    'Sıhhi: OSB şebekesi ≥ 3 bar, 60 l/kişi·gün, yangın dolabı 2 x 100 l/dk x 60 dk, yağmur suyu hasadı 20 l/m² çatı.',
    'Sıcak su merkezi değildir: ıslak hacimlerde yerel elektrikli ani ısıtıcı / termosifon (elektrik projesinde özel çıkış).',
    'Seksiyonel kapılar mimaride iç içe blok olduğundan kapı motoru linyesi 25 m kabul ile hesaplanmıştır (sahada teyit).',
    'Jeneratör gücü acil yükler + yangın pompası yumuşak yol verme şartının büyüğüne göre seçilmiştir.',
    'Mahaller mimari m² etiketleriyle doğrulanarak çıkarılmıştır; duvarı kapalı olmayan küçük mahaller yaklaşık (etiket alanı) alınmıştır.',
    'Proje çıktıları ön proje / uygulama altlığı niteliğindedir; ilgili mühendis kontrolü ve imzası ile onaya sunulmalıdır.',
]:
    w('  - ' + s)
w('')
w('GITHUB')
w('------')
w('Paket (DWG ler hariç - GitHub 100 MB dosya sınırı) herkese açık depoda: https://github.com/emrullahgu/projelerimiz')
w('')
w('KAYNAK')
w('------')
w('_kaynak/ klasöründe LISP çekirdeği (cld_core.lsp, cld_sym.lsp) ve tüm hesapları yapan Python motoru (engine/) bulunur.')
w('Mimari değişirse: DWG verisi accoreconsole ile yeniden dökülüp "python engine/build.py <dump> <bu klasör>" çalıştırılır.')
open(os.path.join(out, 'OKU_BENI.txt'), 'w', encoding='utf-8-sig').write('\n'.join(L) + '\n')
print('ok')
