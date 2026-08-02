<img src="assets/markdify-logo.png" alt="Markdify" width="120" align="right">

# Markdify

PDF, Word, PowerPoint, Excel, e-kitap ve görüntü dosyalarını [Docling](https://github.com/docling-project/docling)
ile **Markdown / JSON / düz metin / HTML** biçimine çeviren masaüstü uygulaması.

## Kurulum (yeni bilgisayar)

Bu klasörü hedef bilgisayara kopyalayın ve **`kur.bat`** dosyasına çift tıklayın. Betik:

1. Python yoksa kurar (winget ile)
2. Klasör içinde izole bir sanal ortam (`.venv`) oluşturur
3. Gerekli paketleri kurar (docling ~2 GB, ilk kurulum uzun sürer)
4. LibreOffice yoksa kurar (isteğe bağlı)
5. Masaüstüne konsolsuz bir kısayol ekler

Kurulum sonrası masaüstündeki **“Markdify”** kısayolundan başlatın.

## Kullanım

Pencere üç sütundan oluşur: **dosya listesi**, **kaynak belge** (özgün PDF/görüntü) ve
**dönüşüm çıktısı**. Böylece özgün belgeyle çıktıyı yan yana karşılaştırabilirsiniz.

| İşlem | Nasıl |
|---|---|
| Dosya ekleme | “Dosya Ekle”, “Klasör Ekle” veya pencereye sürükle-bırak |
| Çıktı biçimi | Üst çubuktaki açılır menü (Markdown / JSON / Düz metin / HTML) |
| Dönüştürme | “Dönüştür”; işlem sürerken aynı düğme “Durdur” olur |
| Sonucu görme | Listeden dosyaya tıklayın, sağ panelde açılır |
| Kaydetme | “Kaydet” (seçili) veya “Tümünü Kaydet” (toplu, klasöre) |
| Ayarlar | ⚙ düğmesi — PDF arka ucu, OCR, tema |
| Sorun giderme | Sağ alttaki “Günlük” düğmesi (`logs/markdify.log`) |

### Kaynak belge sütunu

Ortadaki sütun özgün belgeyi sayfa sayfa gösterir: ◀ ▶ ile sayfa gezinme, − / + ile
yakınlaştırma, ⤢ ile genişliğe sığdırma. Fare tekerleği kaydırır, **Ctrl + tekerlek**
yakınlaştırır, **Shift + tekerlek** yatay kaydırır. “Aç” düğmesi belgeyi sistemin
varsayılan uygulamasında açar.

- **PDF** ve **görüntü** dosyaları doğrudan gösterilir (`pypdfium2` + Pillow ile; ek
  bağımlılık gerekmez, ikisi de docling ile birlikte gelir).
- **Word/PowerPoint/Excel/ODF** belgeleri doğrudan çizilemez; LibreOffice kuruluysa
  tek düğmeyle geçici bir PDF'e çevrilip gösterilir (geçici dosya kapanışta silinir).
- Diğer türlerde açıklayıcı bir mesaj görünür.

Sütuna ihtiyaç duymuyorsanız üst çubuktaki **Kaynak** anahtarıyla gizleyebilirsiniz;
tercih kaydedilir ve çıktı sütunu boşalan alanı kullanır.

### Önizleme ve Düzenle sekmeleri

Sağ paneldeki sekme düğmesi iki görünüm arasında geçiş yapar:

**Önizleme** — markdown'ı biçimlendirilmiş gösterir: başlıklar gerçek başlık boyutlarında,
tablolar hizalanmış kutu çizgileriyle, listeler girintili madde imleriyle, kalın/italik/kod/
bağlantı/üstü çizili biçimleri uygulanmış olarak. Salt okunurdur ama metin seçilip
kopyalanabilir (Ctrl+C / Ctrl+A). Pencere genişletilip daraltıldığında tablo sütunları
otomatik yeniden hizalanır.

**Düzenle** — ham markdown üzerinde tam düzenleme: yazma, silme, değiştirme, ↶ Geri Al,
↷ Yinele ve **Sıfırla** (dönüşümün özgün hâline döner). Düzenlemeler “Kaydet” ve
“Tümünü Kaydet” ile diske yazılan metne yansır.

Kaydedilmemiş bir değişiklik varsa sekmelerin yanında “● düzenlendi” göstergesi çıkar;
kaydedilmemiş düzenlemeyle çıkmaya çalışırsanız uygulama onay ister.

> Not: Düzenleyici **her zaman tam metni** tutar. Önizleme çok büyük belgelerde
> (200.000 karakter üstü) çizim hızını korumak için kısaltılır; bu yalnızca görünümü
> etkiler, kaydedilen içeriği değil.

Markdown biçimlendirmesi yalnızca çıktı biçimi **Markdown** iken uygulanır; JSON, düz
metin ve HTML çıktıları ham hâlleriyle gösterilir.

## Bilinen kısıt: ASCII olmayan kurulum yolu

Docling'in yüksek kaliteli PDF ayrıştırıcısı `docling-parse`, yerel bir C++ eklentisidir
ve kaynak dosyalarını **dar (narrow) karakterli yol** ile açar. Kurulum yolunda Türkçe
karakter varsa (örn. `C:\Users\Kullanıcı\...`) bu dosyaları bulamaz ve **her PDF dönüşümü**
şu hatayla başarısız olur:

```
DocumentLoadError: filename does not exists: ...\pdf_resources\glyphs\\standard\additional.dat
```

Uygulama bu durumu **açılışta kendisi tespit eder** ve otomatik olarak `pypdfium2`
arka ucuna düşer — dönüşüm çalışmaya devam eder, yalnızca düzen/tablo doğruluğu
bir miktar düşer.

Tam kaliteyi korumak için uygulamanın **ASCII adlı bir klasörde** kurulu olması yeterlidir
(örn. `C:\dev\markdify`). Sanal ortam klasörün içinde oluşturulduğu için, kullanıcı
adında Türkçe karakter olması sorun yaratmaz — belirleyici olan uygulamanın yoludur.

Etkin arka ucu Ayarlar penceresinde görebilir, dilerseniz elle sabitleyebilirsiniz.

## LibreOffice

Yalnızca Word belgelerindeki **DrawingML** (çizim/şekil) nesnelerinin tam dönüşümü için
gerekir. Kurulu değilse uygulama bir uyarı şeridi gösterir ve tek düğmeyle kurar.
PDF dönüşümleri bundan etkilenmez.

## Proje yapısı

```
markdify/
├── app.py                  # giriş noktası (günlükleme + pencere)
├── assets/
│   ├── markdify-logo.png   # kaynak logo (kare, saydam)
│   └── markdify.ico        # pencere ve kısayol ikonu (16–256 px)
├── markdify/
│   ├── config.py           # yollar, ayar kalıcılığı, günlükleme
│   ├── environment.py      # bağımlılık tespiti ve kurulumu
│   ├── conversion.py       # arka uç seçimi ve dönüştürme motoru
│   ├── markdown_view.py    # markdown ayrıştırıcı + biçimli görüntüleyici
│   ├── source_view.py      # kaynak belge (PDF/görüntü) sayfa önizlemesi
│   └── ui.py               # CustomTkinter ana pencere
├── requirements.txt
├── setup.ps1               # kurulum betiği
├── kur.bat                 # setup.ps1 için çift tıklanabilir sarmalayıcı
├── settings.json           # kullanıcı tercihleri (otomatik oluşur)
└── logs/                   # dönen günlük dosyaları (otomatik oluşur)
```

## Geliştirici notları

```bash
.venv\Scripts\python.exe app.py -v     # ayrıntılı günlükle çalıştır (konsollu)
.venv\Scripts\pythonw.exe app.py       # konsolsuz (kısayolun yaptığı)
```

- Dönüştürme daima ayrı bir iş parçacığında çalışır; `_conversion_worker`'ın `finally`
  bloğu, hata ne olursa olsun arayüzün “çalışıyor” durumunda kilitlenmemesini garanti eder.
- Desteklenen uzantı listesi docling'in kendi kayıt defterinden okunur
  (`conversion.supported_extensions`), elle bakım gerektirmez.
- Markdown görüntüleyici dış bağımlılık kullanmaz; `CTkTextbox` etiketlerde `font`
  seçeneğini yasakladığı için doğrudan `tkinter.Text` sarmalanır ve CTk teması elle
  uygulanır (`MarkdownView.apply_theme`).
- Kirlilik (“düzenlendi”) göstergesi Tk'nin `edit_modified` bayrağından okunur.
  `<<Modified>>` olaylarını bir boole bayrağıyla bastırmayın: Tk bu olayı gecikmeli
  gönderir, bayrak o an temizlenmiş olur ve program tarafından yapılan yükleme
  kullanıcı düzenlemesi gibi görünür.
- Tablo etiketlerinde satır aralığı sıfırdır; aksi hâlde dikey kenarlık karakterleri
  birbirine değmez ve kenarlıklar kesik görünür.
- Önizlemede bir tablo hücresi `MAX_CELL_LINES` satırı aşarsa “…” ile kısaltılır.
  PDF içindekiler tablolarındaki boşluksuz nokta dizileri aksi hâlde satır yüksekliğini
  patlatır. Kısaltma yalnızca görünümdedir; kaydedilen metin tamdır.
- `SourceView` açtığı PDF/görüntü tanıtıcısını dosya değişiminde ve kapanışta kapatır.
  Windows'ta kapatılmayan tanıtıcı dosyayı kilitler (taşıma/silme engellenir).
- Görev çubuğu ikonu için pencere ikonunu ayarlamak **yetmez**: uygulama `pythonw.exe`
  ile çalıştığından Windows onu Python'la aynı grupta sayar. `config.configure_runtime_env`
  içindeki `SetCurrentProcessExplicitAppUserModelID` çağrısı bunu çözer ve pencere
  oluşturulmadan önce çalışmalıdır.

## Lisans

[MIT](LICENSE) — serbestçe kullanabilir, değiştirebilir ve dağıtabilirsiniz; tek şart
telif bildiriminin korunmasıdır. Yazılım "olduğu gibi", garanti verilmeden sunulur.

Kullanılan başlıca bileşenler ve lisansları: [Docling](https://github.com/docling-project/docling)
(MIT), [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) (MIT),
[pypdfium2](https://github.com/pypdfium2-team/pypdfium2) (BSD-3-Clause / Apache-2.0),
[Pillow](https://github.com/python-pillow/Pillow) (MIT-CMU). LibreOffice yalnızca harici
bir program olarak çağrılır, koda bağlanmaz.
- Model önbelleği varsayılan Hugging Face konumunda kalır; o katman saf Python G/Ç
  kullandığı için ASCII olmayan yollardan etkilenmez.
