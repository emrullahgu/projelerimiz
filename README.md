# Projelerimiz – BROSCO 2-3-4-5 Nolu Parsel Tesisat Projeleri (CLD)

BROSCO 2, 3, 4 ve 5 nolu parsel mimari projelerine göre otomatik hazırlanmış tesisat projeleri.
Her parsel için 9 disiplin vardır:

| No | Disiplin | Komut |
|----|----------|-------|
| 01 | Elektrik İç Tesisat (aydınlatma ve priz ayrı paftalarda) | `CLD_P<n>_ICTESISAT` |
| 02 | Topraklama | `CLD_P<n>_TOPRAKLAMA` |
| 03 | Paratoner (yıldırımdan korunma) | `CLD_P<n>_PARATONER` |
| 04 | Kuvvetli Akım (güç dağıtım) | `CLD_P<n>_KUVVETLIAKIM` |
| 05 | Mekanik (VRF, havalandırma ve radyant ısıtma ayrı paftalarda) | `CLD_P<n>_MEKANIK` |
| 06 | Sıhhi Tesisat (temiz/sıcak su, pis su, yağmur suyu, yangın dolabı) | `CLD_P<n>_SIHHITESISAT` |
| 07 | Yükleme Cetvelleri | `CLD_P<n>_YUKLEMECETVELI` |
| 08 | Kolon Şeması (tek hat) | `CLD_P<n>_KOLONSEMASI` |
| 09 | Aydınlatma Hesabı (TS EN 12464-1) | `CLD_P<n>_AYDHESABI` |

## Klasörler

- `PARSEL_2` … `PARSEL_5`: AutoLISP dosyaları (`CLD_P<n>_0x_*.lsp`). İlgili mimari DWG açıkken APPLOAD ile
  yüklenince çizim kendiliğinden oluşur; soru sorulmaz.
- `Projeler PDF/PARSEL_<n>`: çizilmiş paftaların PDF leri. Her disiplin için bir PDF, bir de yer imli tüm set
  (`CLD_P<n>_00_TUM_PROJELER.pdf`). Plan paftaları 1/100 gerçek ölçektedir.
- `Projeler/`: LISP lerin uygulandığı DWG ler. Dosyalar 120–350 MB olduğundan (GitHub sınırı 100 MB) bu depoya
  yüklenmedi; yerel klasörde durur.
- `_kaynak/`: LISP çekirdeği (`cld_core.lsp`, `cld_sym.lsp`), hesapları yapan Python motoru (`engine/`) ve
  AutoCAD Core Console araçları (`tools/`).
- `OKU_BENI.txt`: kullanım kılavuzu, mühendislik kabulleri ve parsel özetleri.

## Standartlar

- **Elektrik (EMO):**
  - Elektrik İç Tesisleri Yönetmeliği, TS HD 60364 (4-41, 5-52, 5-54), TS EN 12464-1 ve TS EN 1838.
  - Topraklamalar Yönetmeliği, TS EN 62305-3/4 ve TS EN 50522.
  - Kaçak akım koruması kademelidir: 30 mA son devre, 300 mA S pano girişi, ADP de toroid röle. Yangın pompasında kaçak akım rölesi yoktur.
- **Mekanik (MMO):** TS 825, TS EN 12831, TS EN 16798-1, TS EN 378-1 ve TS 3419.
- **Sıhhi (MMO):**
  - TS EN 806-3, DIN 1988-300, TS EN 12056-2/3 ve TS EN 12845.
  - Binaların Yangından Korunması Hakkında Yönetmelik ve TS EN 671-1.
- Her paftada EMO / MMO antedi vardır. Müellif adı, sicil no, SMM no ve imza alanları boştur.

Çıktılar ön proje / uygulama altlığıdır. İlgili mühendisin kontrol ve imzası ile onaya sunulmalıdır.

## Yeniden üretme

```
python _kaynak/engine/build.py <dump_klasoru> <bu_klasor> 2 3 4 5
```

Mimari DWG verisi `_kaynak/tools/cldx_dump.lsp` ile AutoCAD Core Console da dökülür.
`_kaynak/tools/final_run.ps1` LISP leri DWG lere uygular, sonucu kaydeder ve PDF leri basar.
`_kaynak/tools/publish.py` sonuçları `Projeler` ve `Projeler PDF` klasörlerine toplar.
