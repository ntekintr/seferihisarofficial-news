# Seferihisar Official

Seferihisar, Sığacık, Ürkmez, Doğanbey, Akarca, Ulamış ve Orhanlı için kaynaklı yerel haber ve **gelecek etkinlik** otomasyonu. Bu ilk sürüm; araştırma motoru, kalıcı etkinlik takvimi, kaynak odaklı Türkçe içerik hazırlığı, Instagram görselleri, mobil izleme paneli ve kapalı Meta yayın altyapısını birlikte sunar.

**Gerçek Instagram yayını varsayılan olarak kapalıdır.** Belediye veya kamu kurumu adına yayın yapmaz. Önizlemedeki örnekler gerçek haber ve etkinlik değildir.

## İlk sürümde çalışan özellikler

- RSS / Atom, schema.org JSON-LD ve tarih bilgisi açık HTML haberlerinden toplama; yıl dahil açıkça etiketlenmiş Türkçe etkinlik tarihleri, robots.txt kontrolü, hız sınırı ve kaynak başına sınırlı tarama.
- 19 içerik kategorisi; yerellik, kaynak, tarih ve hassas konu denetimi. Eski veya doğrulanmamış haberler dışarıda tutulur.
- Etkinlik adı, tarih/saat, konum, organizatör, ücret, bilet ve kaynak alanları. Açıklanmayan bilgiler açıkça eksik gösterilir; tarihler tahmin edilmez.
- Gelecek etkinliklerin eski kaynak sayfalarını yeniden ziyaret etme, kalıcı kimlikle tarih değişikliği/iptal takibi, eski kartların geçersizleşmesi ve tekrar önleme.
- 7 / 30 gün görünümü, üç gün kala / etkinlik günü hatırlatmaları, haftalık ve aylık seçkiler, indirilebilir `.ics` takvim.
- 1080 × 1350 gönderi / kaydırmalı gönderi ve 1080 × 1920 story serileri. Özgün grafik şablonları; gerçek olay fotoğrafı izlenimi veren yapay görsel kullanılmaz.
- Türkçe açıklamalar, kaynak atfı, etiketler ve şablon başlıklar. Gemini anahtarı varsa isteğe bağlı önem sıralaması; AI hiçbir olguyu veya yayın onayını değiştiremez.
- GitHub Pages için statik panel: haberler, etkinlikler, indirilebilir görseller/açıklamalar, hazırlık ve yayın geçmişi, kaynaklar, çalışma geçmişi ve hatalar.
- 15 dakikada bir GitHub Actions, ayrı `automation-state` dalında SQLite, eşzamanlı çalışmaları sıraya alma, bütünlük kontrolü ve çakışmalarda veri kaybetmek yerine durma.
- Resmî Meta API: JPEG gönderi, carousel, tek story ve ayrı kalıcı işlerden oluşan story serisi. Yayın öncesi görsellerin erişilebilirliğini kontrol etme; belirsiz yayın sonucunda otomatik tekrar gönderimini engelleme.

## Çalıştırma

Python 3.11+; üretim ve CI Python 3.12 kullanır.

```bash
python -m pip install -e '.[test]'
python -m pytest -q
python -m seferihisar.cli demo --public work/demo-site
python -m http.server 8000 --directory work/demo-site
```

Demo ayrı `work/demo.sqlite` kullanır ve ekranda açıkça **ÖRNEK VERİ** yazar. Demo yayınlanamaz. Canlı araştırma:

```bash
python -m seferihisar.cli run
```

API anahtarı olmadan haber toplama, takvim, şablon içerikleri ve JPEG tasarımları çalışır. Gemini isteğe bağlıdır; kota/hata durumunda temel motor çalışmaya devam eder. Hiçbir ücretli servis zorunlu değildir. Kamuya açık depolarda standart GitHub Actions koşucuları ve Pages ücretsiz kullanım koşullarına tabidir; koşulların değişmeyeceği garanti edilmez.

## GitHub üzerinde çalışma

PR `main` dalına alındığında CI doğrular; zamanlanmış otomasyon **yalnız main üzerinde** çalışır. GitHub Actions etkin olmalı ve iş akışının depo içeriği / Pages yazma izinleri bulunmalıdır. İş akışı Pages'i Actions yayın kaynağı olarak etkinleştirmeyi dener; hesap politikası bunu engellerse hesap yöneticisi yetkilendirmesi gerekir. İlk çalışmayı Actions → **Research and prepare Seferihisar content** → Run workflow ile başlatabilirsiniz; normalde sonraki zamanlama kendiliğinden çalışır.

Panel adresi, Pages etkinleştirildikten sonra: `https://ntekintr.github.io/seferihisarofficial-news/`.

Zamanlama dakika 07/22/37/52'dedir; GitHub görevleri geciktirebilir veya atlayabilir. Hatırlatmalar saat eşitliğine bağlı değildir: gecikmiş çalışma üç günlük pencereyi yakalar ve gerçek kalan günü yazar. Panel bir saatten eski akışta uyarı gösterir. Saatler **Europe/Istanbul**; GitHub cron UTC'dir. Kullanıcının bilgisayarına ihtiyaç yoktur.

`automation-state` bir cache/artifact değildir; süresi dolmaz. Veritabanı her çalışmada geri yüklenir, değişiklikler ayrı Git commit'iyle kaydedilir. Kod dalına veritabanı veya anahtar yazılmaz. Dalın ve iş akışı yazma izninin silinmesi sistemi durdurur; boş veritabanıyla sessiz devam etmez.

## Kaynak erişimi ve doğrulama sınırı

`config/sources.json` içinde üç resmî kurum başlangıçta etkindir. Robots kontrolü her çalışma sırasında yapılır. ESHOT, İZSU, GDZ, AFAD, Meteoroloji ve bilet platformları erişim/format incelemesi tamamlanana kadar kapalıdır. Yerel medya, organizatör, dernek ve sosyal kaynaklar yalnız izin verilen RSS/API/HTML yöntemleriyle eklenmelidir. Giriş, CAPTCHA, ücret duvarı veya erişim kuralı aşılmaz.

Yeni RSS ve organizatör/medya bağlantıları aday olarak bulunur. Adayların güvenilirliği ve kullanım koşulları kendiliğinden onaylanmaz; uygunluk incelemesinden sonra yapılandırmaya eklenir. Sosyal platformların API erişimleri için hesap yetkilendirmesi gerekir.

**Bu teslim ortamının ağ politikası belediye, bilet ve Meta sunucularına erişime izin vermediğinden canlı kaynak formatları ve canlı Meta yayını doğrulanmamıştır.** Kaynakların yapılandırmada bulunması onların sayfalarında desteklenen yapılandırılmış veri olduğu anlamına gelmez. Tarayıcı ve parser testleri kayıtlı örneklerle yapılmıştır. Yapılandırılmış tarihi olmayan etkinlik, yalnız afiş görselinde bulunan tarih ve dinamik/bilet sitesi özel API'leri ilk sürümde çıkarılmaz. Sayfa kaybolması iptal sayılmaz; iptal veya erteleme için açık kaynak bilgisi gerekir.

Güvenilir olarak yapılandırılan birincil kaynağın duyurusu kanıt olarak kullanılır; bu, bağımsız birden fazla kaynakla bütün iddiaların doğrulandığı anlamına gelmez. Yeterli bilgi yoksa içerik yayın kuyruğuna alınmaz. AI editörü bu sürümde serbest haber yeniden yazımı yapmaz; haber metni kaynağa atıflı alıntı ve deterministik şablonlardan hazırlanır. İsteğe bağlı AI yalnız önem puanı üretir.

## İnsan incelemesi ve kamuya açık veri

Suç, ölüm, siyasi iddia ve kişisel itibara ilişkin işaretlenen içerik **insan incelemesi gerekir** durumuna düşer; otomatik yayınlanmaz. Açık panel yalnız dışarıda tutulan içerik sayısını gösterir. Ham metin, kişi adı, özel URL, token veya anahtar yayımlanmaz; kalıcı durumda yalnız hash, neden ve zaman saklanır.

Bu ilk sürümde hassas içeriği yayımlamayı onaylayan bir arayüz yoktur: bu içerikler kapalı kalır. Kimlik doğrulamalı özel inceleme paneli, içerik saklama politikası ve olay bazlı güvenlik onayı olmadan hassas içerik otomasyonunu açmayın. Anahtar sözcük filtresi eksiksiz bir içerik sınıflandırıcısı değildir; canlı yayına geçişte kaynak bazlı içerik incelemesi gerekir.

Pages izleme ve indirme içindir; tarayıcıdan veri değiştirme veya token girişi yapılmaz. Gelecekte özel API/panel, `Store`, editör ve outbox katmanlarını yeniden kullanabilir.

## Kontrollü Instagram aktivasyonu

Resmî Instagram API with **Facebook Login** yolu kullanılır. Uygun profesyonel Instagram hesabı, bağlı Facebook Sayfası, Meta uygulaması, ilgili yayın izinleri ve geçerli token gerekir. Story yayın erişimi hesap türü/Meta izinlerine bağlıdır. API sürümü yapılandırılabilir; gerçek yetki testi sırasında güncel Meta gereksinimleri doğrulanmalıdır.

1. Yetkili hesabın testlerini tamamlayın; kamuya erişilebilir Pages JPEG'lerini ve test hesabında gönderi/carousel/story yayınını doğrulayın.
2. GitHub Secrets: `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_USER_ID`. Token'a panelde yer verilmez. İsteğe bağlı `GEMINI_API_KEY` ayrı secrettır.
3. GitHub Variables: `SITE_URL` = Pages adresi; testten sonra `META_TESTS_COMPLETED=true`, kontrollü aktivasyon onayından sonra `INSTAGRAM_PUBLISH_ENABLED=true`. `META_GRAPH_VERSION` istenirse değiştirilebilir (başlangıç `v25.0`).
4. `instagram-production` environment için yetkili kullanıcı onayı ve main kısıtı yapılandırın. **Controlled Instagram publication** işini `PUBLISH` teyidi ve `feed` veya `story` formatıyla çalıştırın.

Her çağrı en fazla **bir gönderi veya bir story karesi** yayınlar; 45 dakika aralık kontrolü vardır. Story serisinin her karesi ayrı iş ve kimlikle saklanır. Otomatik araştırma işi hiçbir durumda Meta token'ı almaz ve yayın komutu çalıştırmaz. Belirsiz/yarıda kalmış yayın, Meta üzerinden kontrol edilmeden yeniden kuyruğa konmaz. Yayın talebi Meta'ya gitmeden önce Git'e kalıcı kaydedilir; runner kaybı aynı talebin tekrarlanmasına neden olmaz. Otomatik gerçek yayın zamanlayıcısı bu sürümde etkin değildir.

## Yapı

```text
seferihisar/collect.py       İzinli toplama ve aday keşfi
seferihisar/editor.py        Olgu kontrolleri ve Türkçe içerik
seferihisar/schedule.py      Etkinlik yaşam döngüsü ve yayın hazırlıkları
seferihisar/render.py        JPEG görsel kimlik
seferihisar/store.py         SQLite, tekrar önleme ve outbox
seferihisar/state_git.py     Kalıcı dal, backup ve yazma çakışması koruması
seferihisar/instagram.py     Kapalı resmî Meta adaptörü
seferihisar/pipeline.py      Orkestrasyon ve güvenli Pages dışa aktarımı
site/                       Mobil uyumlu statik izleme paneli
.github/workflows/          CI, araştırma/Pages ve kontrollü yayın
tests/                      Yaşam döngüsü, güvenlik, API ve kalıcılık testleri
```

Sonraki canlı doğrulama işi: kaynaklara ağ izni verip gerçek kaynak formatlarını kontrol etmek, gerekli özel adaptörleri eklemek ve Meta test hesabını yetkilendirmek. Bu işlemler yapılmadan gerçek güncel haber toplandığı veya Instagram'a yayın yapıldığı iddia edilmez.
