<img src="assets/markdify-logo.png" alt="Markdify" width="120" align="right">

# Markdify

PDF, Word, PowerPoint, Excel, e-kitap ve görüntü dosyalarını [Docling](https://github.com/docling-project/docling)
ile **Markdown / JSON / düz metin / HTML** biçimine çeviren masaüstü uygulaması.

## Kurulum

### Yol 1 — Kurulum sihirbazı (önerilen)

`Markdify-Setup-<sürüm>.exe` dosyasını çalıştırıp sihirbazı izleyin. Sihirbaz uygulama
dosyalarını kopyalar, ardından Python'u, sanal ortamı ve paketleri kurar; Başlat menüsü
ile masaüstü kısayollarını ve **Programlar listesinde bir kaldırma girdisi** oluşturur.

Kurulumu kaldırmak: *Ayarlar → Uygulamalar → Markdify → Kaldır*. Sanal ortam, günlükler
ve ayarlar da temizlenir.

### Yol 2 — Depodan (geliştirici)

Depoyu klonlayıp **`kur.bat`** dosyasına çift tıklayın. Betik aynı adımları uygular ama
kaldırma girdisi oluşturmaz.

Her iki yolda da:

1. Python yoksa kurulur (winget ile)
2. Klasör içinde izole bir sanal ortam (`.venv`) oluşturulur
3. Paketler kurulur (docling ~2 GB, internet hızına göre 10–30 dakika)
4. LibreOffice yoksa kurulur (isteğe bağlı)

Kurulum sonrası **“Markdify”** kısayolundan başlatın.

> Kurulum klasörünün yolu ASCII olmalıdır (varsayılan `C:\Markdify`). Türkçe karakterli
> bir yol seçerseniz sihirbaz uyarır; bkz. [Bilinen kısıt](#bilinen-kısıt-ascii-olmayan-kurulum-yolu).

### Kurulum sihirbazını derlemek

```powershell
winget install -e --id JRSoftware.InnoSetup
powershell -ExecutionPolicy Bypass -File installer\build.ps1
```

Çıktı `dist\Markdify-Setup-<sürüm>.exe` olur (~2,8 MB). Python paketleri sihirbaza
**gömülmez**: gömülü hâli ~2,5 GB'lık bir dosya demek olurdu ve GitHub'ın 100 MB dosya
sınırını aşardı. Paketler kurulum sırasında indirilir.

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

### İlerleme takibi

Alt taraftaki çubuk **toplu iş** ilerlemesini gösterir ve gerçektir: tamamlanan
dosya sayısı / toplam. Dosya listesinde işlenmekte olan satırın altında ise
hareketli bir çubuk ile birlikte **geçen süre** ve PDF'lerde **sayfa sayısı**
görünür; tamamlanan satırlarda süre kalır.

> Satır çubuğu bilerek **yüzdesiz**dir. Docling dönüştürme sırasında ilerleme
> bildirmez — ne geri çağrı, ne olay, ne de ilerleme parametresi vardır; sayfalar
> dışarıdan erişilemeyen bir nesnede işlenir. Dolayısıyla tek bir dosya için
> gösterilecek herhangi bir yüzde uydurma olurdu. Onun yerine yalnızca gerçekten
> ölçülen bilgiler gösterilir.

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
├── installer/
│   ├── markdify.iss        # Inno Setup kurulum sihirbazı tanımı
│   └── build.ps1           # sihirbazı derler -> dist\Markdify-Setup-*.exe
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
  (`conversion.warm_extension_cache`), elle bakım gerektirmez. **Bu okuma arayüz
  iş parçacığından yapılmamalıdır:** ilk `import docling` ~5 saniye sürer (torch
  zinciri) ve Windows pencereyi "yanıt vermiyor" olarak işaretler. Açılışta arka
  planda ısıtılır; `supported_extensions()` asla bloklamaz, hazır değilse eşdeğer
  bir yerleşik listeyi döner.
- Hazır olma sinyali için "modül `sys.modules` içinde mi" diye bakmayın: Python
  modülü içe aktarım **bitmeden** oraya koyar, bu yüzden o kontrol yarış oluşturur
  ve arayüz iş parçacığı arka plandaki içe aktarımın import kilidinde bloke olur.
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
- Python'u ararken **PATH'e güvenmeyin**. Windows, PATH'in başına Microsoft Store
  yönlendirme kısayolları koyar (`WindowsApps\python.exe`); bunlar gerçek Python değildir,
  çalıştırılınca "Python bulunamadı" yazarlar. `py` başlatıcısı da her kurulumda bulunmaz.
  Güvenilir kaynak kayıt defterindeki `SOFTWARE\Python\PythonCore\<sürüm>\InstallPath`
  girdisidir (bkz. `installer\markdify.iss` içindeki `PythonFromRegistry`).
- PowerShell betiklerini **UTF-8 BOM** ile kaydedin. Windows PowerShell 5.1 BOM'suz
  dosyaları ANSI okur; Türkçe karakterler dizgeyi kırar ve betik sözdizimi hatasıyla
  hiç çalışmaz.
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
