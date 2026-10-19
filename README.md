# Seferihisar Official

Seferihisar, Sığacık, Ürkmez, Doğanbey, Akarca, Ulamış ve Orhanlı için kaynaklı yerel haber ve **gelecek etkinlik** otomasyonu. Araştırma motoru, kalıcı etkinlik takvimi, kaynak odaklı Türkçe içerik hazırlığı, görsel denetimi, mobil izleme paneli ve ayrı Instagram/Facebook yayın işlerinden oluşur. Bilgisayarın açık olması gerekmez.

Güzelbahçe, Urla, Yelki ve Özdere'deki konser, festival, tiyatro, sinema ve diğer etkinlikler de kapsamdadır. Çevre yerleşimlerde ulaşım, kesinti, hava uyarısı ve benzeri önemli kamu gelişmeleri alınır; her gündelik haber akışa eklenmez.

**Yeni kurulumda gerçek yayın varsayılan olarak kapalıdır.** Bu deponun mevcut üretimi kullanıcı yetkisiyle etkinleştirilmiştir; demo ve üretim birbirinden ayrıdır. Belediye veya kamu kurumu adına yayın yapmaz. Demo önizlemesindeki örnekler gerçek haber ve etkinlik değildir.

[Sistem rehberi ve öğrenilenler](docs/system-handbook.md), güncel kod haritasını, yayın sınırlarını, kanıt türlerini ve geçmiş hatalardan çıkan kuralları bir araya getirir. Canlı durum, [panel](https://ntekintr.github.io/seferihisarofficial-news/) ve tarihli üretim kanıtından okunur; bir kurulum örneğindeki kapalı varsayılan canlı ayarın yerine yazılmaz.

## Çalışan özellikler ve sınırlar

- RSS / Atom, schema.org JSON-LD ve tarih bilgisi açık HTML haberlerinden toplama; yıl dahil açıkça etiketlenmiş Türkçe etkinlik tarihleri, robots.txt kontrolü, hız sınırı ve kaynak başına sınırlı tarama.
- Konu kategorileri, yerellik, kaynak, tarih ve hassas konu denetimi. Haber yaşı ve olayın gerçek geçerliliği yayın anında yeniden kontrol edilir.
- Etkinlik adı, tarih/saat, konum, organizatör, ücret, bilet ve kaynak alanları. Açıklanmayan bilgiler açıkça eksik gösterilir; tarihler tahmin edilmez.
- Gelecek etkinliklerin eski kaynak sayfalarını yeniden ziyaret etme, kalıcı kimlikle tarih değişikliği/iptal takibi, eski kartların geçersizleşmesi ve tekrar önleme.
- 7 / 30 gün görünümü, üç gün kala / etkinlik günü hatırlatmaları, haftalık ve aylık seçkiler, indirilebilir `.ics` takvim.
- 1080 × 1350 gönderi / kaydırmalı gönderi ve 1080 × 1920 story kartları. Sabit logo/şeritler, kaynak bilgisi yalnız açıklamada. Gerçek haber fotoğrafı için kaynak ve konu eşleşmesi gerekir; kanıtlanamayan haber görseli yerine bilgi kartı kullanılır. Etkinlik görselleri ayrıca yazı ve sahne kontrolünden geçer.
- Türkçe açıklamalar, kaynak atfı, etiketler ve şablon başlıklar. Gemini anahtarı varsa isteğe bağlı önem sıralaması; AI hiçbir olguyu veya yayın onayını değiştiremez.
- GitHub Pages için statik panel: haberler, etkinlikler, indirilebilir görseller/açıklamalar, hazırlık ve yayın geçmişi, kaynaklar, çalışma geçmişi ve hatalar.
- 15 dakikalık GitHub Actions zamanlaması (gecikme/düşme ihtimali vardır), ayrı `automation-state` dalında SQLite, eşzamanlı çalışmaları sıraya alma, bütünlük kontrolü ve çakışmalarda veri kaybetmek yerine durma.
- Resmî Meta API: JPEG gönderi, carousel, tek story ve ayrı kalıcı işlerden oluşan story serisi. Yayın öncesi görsellerin erişilebilirliğini kontrol etme; belirsiz yayın sonucunda otomatik tekrar gönderimini engelleme.
- Otomatik haber akışında günde en fazla iki gönderi ve her birine ilk eşleşen story; Facebook teslimleri aynı içeriğe bağlı ayrı kaydedilir. Türkiye saati 08:00 hedefli günlük hava story'si bağımsızdır ve bu haber sayacını tüketmez. Zamanlayıcı gecikmesi ve dış servis erişimi nedeniyle kesin dakika/kesintisiz çalışma garantisi verilmez.

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

Araştırma işi yalnız `contents: read` izni kullanır. Doğrulanmış SQLite çıktısı kısa ömürlü bir artifact ile ayrı kalıcılık işine aktarılır; yalnız bu iş `contents: write` kullanır. Pages dağıtım işinde `contents: read`, `pages: write` ve Pages için gerekli `id-token: write` bulunur. Dağıtım kalıcılık başarılı olduktan sonra başlar. Güvenlik denetimi veya araştırma başarısızsa yeni durum ve Pages çıktısı yüklenmez; önceki kalıcı durum korunur. Artifact kalıcı veri kaynağı değildir.

CI ve tüm checkout adımlarında `persist-credentials: false` kullanılır. Depo yazma token'ı yalnız kalıcılık komutunun Git alt sürecine verilir; `.git/config` veya komut satırına yazılmaz. AI ve Meta anahtarları yalnız ilgili çalışma adımlarının ortamında bulunur. Dış GitHub Actions sürümleri tam commit SHA'sına sabitlenmiştir.

## Kaynak erişimi ve doğrulama sınırı

Güncel etkin/güvenilir kaynak listesi `config/sources.json`, incelenmiş diğer adresler `config/source_catalog.json` içindedir. Belediye ve kamu duyuruları, yerel/ulusal basın, kültür/etkinlik, eğitim, meslek kuruluşu, hizmet ve izinli Instagram kaynakları birlikte değerlendirilir. Yapılandırılmış okuyucu sayısı çalışan kaynak sayısı değildir. Kaynağın son `ok`, `empty`, `partial` veya `failed` sonucu paneldeki tarihli sağlık verisinden okunur. [Kaynak kapsama raporu](docs/source-coverage.md) tarihli araştırma kaydıdır; bütün ilçenin eksiksiz kapsandığı anlamına gelmez.

İzmir Art'ın sitenin kullandığı kamuya açık etkinlik JSON'u, her seansın açık UTC tarihlerini ve gerçek mekân adresini kullanır. Bazı gezici etkinliklerde yanlış kalan ilçe kimliği esas alınmaz. Tarih/saat çelişkisi, eksik seans kimliği veya bölge dışı adres varsa kayıt alınmaz. Ücret ve iptal bilgisi yalnız açık kaynak alanlarından okunur. Menderes'in genel RSS'i idarî belgeler içerdiğinden gerçek WordPress haber/duyuru koleksiyonları kullanılır; test haber koleksiyonu kullanılmaz. Bu koleksiyonun boş olması okuyucu hatası değildir.

Kaymakamlık'ta gerçek haber kartları ve detay sayfasının açık tarih/metin alanları; Urla'da haber gövdesi ve onun kendi yayın zamanı okunur. Haber tarihleri menü, başka haber kartı veya etkinlik tarihi alanından alınmaz. Yeni Haber'in Yaşam, Bölgesel ve Gündem listeleri; Haberler.com ve Habertürk'te çevre ilçelerin listeleri aynı kaynak başına sayfa bütçesini paylaşır. Haberler.com'un ayrı Yelki listesi vardır. Habertürk Özdere için arama terimini koruyan sitedeki arama bağlantısı ve haber kartı biçimi kullanılır. Bir listede bölge adı geçmesi tek başına bütün haberlerinin alınacağı anlamına gelmez: haberin içeriği de yerellik ve konu kontrolünden geçer.

Yeni Haber, Gündem, Habertürk, DHA, İzmir Büyükşehir ve İZSU için her alan adında bir çalışma boyunca en fazla bir ek geçici hata denemesi vardır. 403/404, robots yasağı ve uzun/belirsiz Retry-After yanıtı aşılmaz; kota/erişim engelini aşmak için kimlik veya tarayıcı değiştirilmez.

Gündem'in kendi sitesinde sunduğu RSS yayını, ana sayfasını ve her eski haber detayını ayrıca yüklemeden okunur. RSS içeriğinde yılıyla birlikte açıkça etiketlenmiş etkinlik tarihi varsa takvime alınabilir. Daha önce kaydedilmiş gelecek etkinliklerin detayları iptal/tarih değişikliği kontrolü için yine ziyaret edilir.

Robots kontrolü web kaynaklarının her çalışmasında yapılır. Bazı incelenmiş kaynaklarda yalnız `robots.txt` dosyasının 404/410 yanıtına özel istisna vardır; açık engelleme kuralı, 403/429/5xx veya ağ hatası aşılmaz. ESHOT tarihli duyuru/haberleri, İZSU kurum haberleri, GDZ planlı kesintileri, AFAD, MGM uyarıları ve yapılandırılmış bilet/etkinlik okuyucuları kendi doğrulanabilir tarih/alanlarını kullanır. Her kaynağın anlık erişimi ayrıca kontrol edilir. Tarihsiz duyuru ve doğrulanmamış canlı hizmet bilgisi tahminle tamamlanmaz. Sosyal kaynaklar izinli API ve mevcut hesap yetkisi gerektirir. Giriş, CAPTCHA, ücret duvarı veya erişim kuralı aşılmaz.

Yeni RSS ve organizatör/medya bağlantıları aday olarak bulunur. Adayların güvenilirliği ve kullanım koşulları kendiliğinden onaylanmaz; uygunluk incelemesinden sonra yapılandırmaya eklenir. Sosyal platformların API erişimleri için hesap yetkilendirmesi gerekir.

İlk kaynak kontrolleri 11 Ekim 2026'da başlamış, daha sonraki sürümlerde kaynak ve gerçek Meta teslim kontrolleri eklenmiştir. [Kaynak doğrulama notları](docs/source-validation.md) ve [sistem rehberi](docs/system-handbook.md) tarihli kanıtı mevcut yetenekten ayırır. Her taramada yeni uygun içerik çıkması garanti değildir; RSS/API sonuçları sınırlı bir pencere sunar. Etkinlik tarihi kaynak haberin yayım tarihinden veya yalnız afiş görüntüsünden tahmin edilmez. Sayfa kaybolması iptal sayılmaz; iptal/erteleme için açık kaynak bilgisi gerekir.

Güvenilir olarak yapılandırılan birincil kaynağın duyurusu kanıt olarak kullanılır; bu, bağımsız birden fazla kaynakla bütün iddiaların doğrulandığı anlamına gelmez. Yeterli bilgi yoksa içerik yayın kuyruğuna alınmaz. AI editörü bu sürümde serbest haber yeniden yazımı yapmaz; haber metni kaynağa atıflı alıntı ve deterministik şablonlardan hazırlanır. İsteğe bağlı AI yalnız önem puanı üretir.

Kaynağa erişim/robots/ayrıştırma kontrolü başarısızsa o kaynağın hazır içerikleri `blocked_source` durumuna alınır; yeni haber, duyuru, hatırlatma veya seçki üretilmez. Haber veya etkinliğin son başarılı görülmesi bir saatten eskiyse de hazırlık ve kontrollü yayın durur. Eski kayıtlar panelde son kontrol zamanı ve yeniden doğrulama uyarısıyla gösterilir; takvimdeki eski etkinlikler geçici (`TENTATIVE`) işaretlenir. Sayfa 404 yanıtı verdi diye iptal uydurulmaz. Kaynak geri geldiğinde yalnız güncel bilgilerle hazırlık devam eder; geçmiş günün “3 gün kaldı” kartı yeniden yayınlanamaz.

## İnsan incelemesi ve kamuya açık veri

Suç, ölüm, siyasi iddia ve kişisel itibara ilişkin işaretlenen içerik **insan incelemesi gerekir** durumuna düşer; otomatik yayınlanmaz. Açık panel yalnız dışarıda tutulan içerik sayısını gösterir. Ham metin, kişi adı, özel URL, token veya anahtar yayımlanmaz; kalıcı durumda yalnız hash, neden ve zaman saklanır.

Bu ilk sürümde hassas içeriği yayımlamayı onaylayan bir arayüz yoktur: bu içerikler kapalı kalır. Kimlik doğrulamalı özel inceleme paneli, içerik saklama politikası ve olay bazlı güvenlik onayı olmadan hassas içerik otomasyonunu açmayın. Anahtar sözcük filtresi eksiksiz bir içerik sınıflandırıcısı değildir; canlı yayına geçişte kaynak bazlı içerik incelemesi gerekir.

Pages izleme ve indirme içindir; tarayıcıdan veri değiştirme veya token girişi yapılmaz. Gelecekte özel API/panel, `Store`, editör ve outbox katmanlarını yeniden kullanabilir.

Pages çıktısı temiz bir geçici dizinde yeniden kurulur. Yalnız `index.html`, `style.css`, `app.js`, `data.json`, `events.ics`, `.nojekyll` ve üretilmiş JPEG'ler kabul edilir. Önceki çıktıdaki `.env`, veritabanı, log veya diğer dosyalar taşınmaz; JSON alanları açık bir izin listesiyle seçilir. Kaynak metninde/URL'sinde yapılandırılmış anahtar veya tanınan credential biçimi bulunursa içerik dışarıda tutulur. Çıktı ve SQLite için ikinci denetim başarısızsa upload/commit engellenir. Bu filtreler tüm olası gizli verileri kendiliğinden tanıyan bir sınıflandırıcı değildir; resmî kaynak yapılandırması ve kamuya açık veri politikası temel sınırdır.

## Kontrollü Instagram aktivasyonu

Resmî Instagram API with **Facebook Login** yolu kullanılır. Uygun profesyonel Instagram hesabı, bağlı Facebook Sayfası, Meta uygulaması, ilgili yayın izinleri ve geçerli token gerekir. Story yayın erişimi hesap türü/Meta izinlerine bağlıdır. API sürümü yapılandırılabilir; gerçek yetki testi sırasında güncel Meta gereksinimleri doğrulanmalıdır.

1. Yetkili hesabın testlerini tamamlayın; kamuya erişilebilir Pages JPEG'lerini ve test hesabında gönderi/carousel/story yayınını doğrulayın.
2. GitHub Secrets: `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_USER_ID`. Token'a panelde yer verilmez. İsteğe bağlı `GEMINI_API_KEY` ayrı secrettır.
3. GitHub Variables: `SITE_URL` = Pages adresi; testten sonra `META_TESTS_COMPLETED=true`, kontrollü aktivasyon onayından sonra `INSTAGRAM_PUBLISH_ENABLED=true`. `META_GRAPH_VERSION` istenirse değiştirilebilir (başlangıç `v25.0`).
4. `instagram-production` ortamında `main` kısıtını koruyun. Tam otonom yayın aktivasyonu kullanıcı tarafından onaylandıktan sonra her çalışmada manuel reviewer bekleme kuralı kaldırılır. **Controlled Instagram publication**, başarılı ana dal araştırması ve panel yayını sonrasında otomatik kontrol yapar; manuel `PUBLISH` teyidiyle `automatic`, `feed` veya `story` modu da kullanılabilir.

[Saatli yayın düzeni](docs/automatic-publication.md): Türkiye saatiyle 08:30, 12:30, 15:00, 18:30 ve 21:00 kontrol pencereleri; günde en fazla iki gönderi ve her gönderi için ilk eşleşen story kartı. Kaynak güncelliği, kalıcı yayın iddiası, belirsiz sonuçta yeniden göndermeme ve farklı içerikler için 45 dakikalık aralık kontrolü korunur. Geçerli içerik yoksa veya bir saatlik pencere kaçırılırsa paylaşım yapılmaz.

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

Instagram için sonraki aşama Meta test hesabını yetkilendirmek ve gerçek gönderi/story testlerini tamamlamaktır. Bu aşama tamamlanmadan Instagram'a yayın yapıldığı iddia edilmez.


Kaynaklar ekranında gerçek son kontrol zamanı, çıkarılan/doğrulanan kayıt sayısı ve hata durumu vardır. Eski kayıt, boş akış ve bağlantı hatası ayrı gösterilir. Sistem ekranı gösterilen çalışma geçmişindeki en uzun aralığı bildirir. Zamanlanmış araştırma Instagram yayımlamaz; gerçek test yayınının başarılı olması düzenli yayının açıldığı anlamına gelmez.
