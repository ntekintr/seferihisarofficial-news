# Sistem rehberi ve öğrenilenler

Son gözden geçirme: **26 Ekim 2026**. Bu dosya kod haritası ve kalıcı çalışma
notudur. Anlık sağlık/teslim kanıtı zaman damgalı çıktılardan alınır; burada bir
kez başarılı olması sonraki ay kesintisiz çalışacağı anlamına gelmez.

### 1 Kasım: güncelleme kartları story, kaynak fotoğrafı önce

Kullanıcı kararı: duyurulmuş etkinliğin güncellemesi feed'e girmez, yalnız story
olur (`story_only`, `kind='update'`; su kesintisi güncellemesi kapsam dışı). Yayın
yolu elektrik kesintisiyle aynıdır, günde 2 story hakkını paylaşır. Takipçiye hiç
duyurulmamış etkinliğin yeni revizyonu güncelleme değil normal duyurudur.
Kartta görünen bilgi değişmediyse `unchanged_update` story'yi de tutar: Isparta ve
Seferihisar kayıtlarında duyurulmuş 10 güncellemenin hiçbirinde kart bilgisi
değişmemişti.

Fotoğraf: kaynağın o habere bağlı kendi fotoğrafı konu etiketine uymadı diye
elenmesin diye `OCCASION_SUBJECTS` genişledi ve konusu sınıflanmayan haberlere
`article_photo` eklendi. Manşet yazılı görsel OCR ile, poster ve logo CLIP ile
elenir. Toplantı, tören, etkinlik gibi insanla anlatılan konularda fotoğrafta
insan aranır: toplantı haberindeki sokak ya da boş salon yanlış fotoğraftır, bu
yüzden elenir. Yer ve nesne konuları (`SCENE_SUBJECTS`) insansız da geçer. Sel,
trafik, yol çalışması, hasat ve maç gibi olay konuları hâlâ kendi kanıtını ister.

### 31 Ekim: elektrik kesintisi yalnız story

Kullanıcı kararı: elektrik kesintileri feed'e girmez, yalnız story olur. Bu karar
gelmeden son 30 feed'in 11'i kesintiydi. Kural `publication_policy.story_only`
içindedir; başlığında elektrik geçen `outage` kayıtlarını kapsar, su kesintisi
eskisi gibi feed ve story olarak çıkar. Sahibin elle istediği yayın da feed'e
çıkaramaz.

`publish_outage_story` her otomatik yayın kontrolünde, 08:30–21:00 arasında en
fazla bir story dener. Bugünkü ve yarınki kesintiler alınır, yakın bölge önce
gelir, günde en fazla 2 story çıkar. Haberlerin 3 story hakkını tüketmez ve hava
ile eczane gibi haberi geciktirmez; kendisi haberden sonra 45 dakika bekler.
Facebook'a aynı story yansıtılır. Feed çıkmadığı için üst kayıt `prepared` kalır
ve kesinti bitince süresi dolar. Sıradaki sayısında görünmesi bu yüzdendir.

GDZ aynı kesintiyi yüzlerce kez revize eder, ama kart metni değişmez (bir kayıtta
165 revizyon, tek metin). `duplicate_reason` bunları tek story'de tutar. Saat,
bölge veya iptal gibi gerçek değişiklik kartı değiştirir ve yeni story olur.

### 30 Ekim: Bubilet yerine Biletinial etkinlik kaynakları

Bubilet bulut sunucularına 403 verdiği için Bademler etkinlikleri Biletinial
mekân sayfasından okunur; İzmir tiyatro listesinin dört sayfası ve müzik/etkinlik
listeleri de bağlandı. Biletinial'ın `?cinemaBranchId=` sürümü seans saatini 3
saat kaydırır; Bademler okuyucusu sorgusuz adresi kullanır. Kanıt ve sınırlar:
[kaynak kapsamı](source-coverage.md), 30 Ekim bölümü;
testler `tests/test_biletinial_sources.py`.

Araştırma işinin süre sınırı 14 dakikadan 20 dakikaya çıkarıldı. 30 Ekim'de
"Collect" adımı 506–736 saniye sürdü; 08:53 UTC turu 14. dakikada kesildi ve o
turun durumu kaydedilmedi. Turlar sıraya girdiği için (`cancel-in-progress:
false`) daha uzun sınır yalnız yavaş bir taramanın bitmesine izin verir.

### 26 Ekim: kaynak fotoğrafı, uygun üretim ve görselsiz yayını bekletme

[Yeni görsel sözleşmesi](visual-first-publication.md), yalnız sonraki yayınlara
uygulanır. İzmir Belediyesi RSS kaydı aynı sayfa/başlık/tarihle HTML galerisine
bağlanır. Konu yolları genişletildi; doğrulanmış kapak görseli olmayan yeni
feed bekler. Eski SQL iddiaları ve sosyal teslimler yeniden yazılmaz.
Görselsiz kaynak sayfası iki dosyalık görsel hakkını tüketmez; turda en fazla
altı kaynak kimliği ve iki gerçek görsel dosyası kontrol edilir. Görsel bekleme
sonucu işletim raporunda `awaiting_content_visual` olarak korunur; bilinmeyen
durum sayılıp `check_failed` etiketine çevrilmez. Bütçe ve durum regresyonları
`tests/test_source_photo_queue.py` ile sınanır.
Canlı Isparta turunda aynı uyumsuz görsellerin sonraki turları da meşgul ettiği
görüldü. `source_photo_retry.py` yalnız içerik/revizyon, aşama ve zamanla sınırlı
bekleme tutar; kaynak ve görsel kotası artmadan diğer adaylar ilerler. Şema,
yeniden başlatma, süre dolumu ve yeni revizyon davranışı ayrıca test edilir.

### 24 Ekim akşamı: yeni habere dördüncü çift istisnası

Kullanıcı 20:00–22:59 arasında yayımlanan yeni haber için üçlük sınır dolsa da
dördüncü gönderi ve eşleşen ilk story'ye izin verdi. `publication_policy.py`
normal üç, mutlak dört sınırını; aynı akşamki gerçek kaynak yayım zamanı,
ilk görülme ve ilk revizyon gereğini uygular. Yeni 20:00/22:00 pencereleri yalnız
akşam haberlerini işler; 22:00 penceresi son araştırmanın tamamlanması için en
geç 23:30'da kapanır. Bu pay kaynakta 23:00 sonrası yayımlanmış haberi kapsamaz.
Mevcut aynı pencerenin tamamlanmış üçüncü parent'ı daha sonra gelen dördüncüyü
gizlememelidir; Instagram ve Facebook sıradaki eksik doğru parent'ı seçer.
[Yayın sözleşmesi](automatic-publication.md) hızlı revizyonların neden ek hakka
alınmadığını ve dördüncü story'nin yalnız dördüncü parent'a bağlılığını açıklar.
Eski iddialar değişmez; çalışma anı ve gerçek doğal teslim ayrıca doğrulanır.

### 24 Ekim: yayın sayısı ve aynı kartın ikinci revizyonu

Kullanıcı iki sayfa için üç haber gönderisi ve üç haber story'si istedi; hava ve
eczane story'lerinin buna ek olduğunu ayrıca seçti. Haber tavanı her giriş
noktasında, başarılı/devam eden/belirsiz iddiaları sayarak uygulanır. Kaynakta
metadata değişimi aynı kesinti kartını revizyon 2 olarak yeniden kuyruklayabilir:
yayımlanmış kartın değişmez metin alanları ve story JPEG özeti de karşılaştırılır.
Yeni bir içerik kimliği veya revizyon tek başına yeni haber sayılmaz. Gerçek tarih,
mekân ve iptal değişikliği görünür kartta farklıysa uygundur. Her parent'ın yalnız
ilk story'si, aynı gün ve son bir saat içinde tamamlanır; geçmiş parent yenilenmez.
Canan Tutal ile Hatha Yoga yeni gönderi/story/seçkilerden kullanıcı kararıyla
çıkarılır. [Güncel yayın kuralları](automatic-publication.md). Geçmiş iddialar
değişmez; bu kod notu dağıtım veya doğal yeni teslim kanıtı değildir.

### 22 Ekim: günlük nöbetçi eczane listesi

[Eczane story akışı](daily-pharmacy-story.md) ayrı günlük iddia, yalnız doğru
günün resmî listesi, adres/işletme telefonu, kaynak saat notlarını kaybetmeme,
17:00 hedefi, aynı saatle sınırlı yedekler ve doğrudan JPEG denetimini açıklar.
Kullanıcı artı yerine kırmızı E, Seferihisar'da 3D salyangoz, Isparta'da açık
gri/beyaz ve mevcut logo istedi. Hazır örnek doğal teslim değildir; geçmiş
haber/FB/hava iddiaları değişmez. Yeni izin, token veya ücretli servis yoktur.

### 20 Ekim: otonom üretim kapsamı

Kullanıcı rutin üretim için ayrıca kontrol/teyit beklenmemesini; performanstan
öğrenme ve sürekli yeni kaynak aramasını istedi. `learning.py`,
`source_discovery.py`, `factory.py` ve `automation.yml` içindeki ölçüm işi bu akışı mevcut
üretim kilidiyle tamamlar. [Otonom üretim sözleşmesi](autonomous-factory.md)
asgari örneklem, ham özel ölçümlerin saklanmaması, kontrollü konu tercihi,
aynı güvenilir kökende veya iki referanslı yeni resmî kurumda üç günlük RSS kabulü
ve diğer dış sitelerin karantinasını açıklar.
Yeni tablo eklemek eski yayınları yeniden yazma izni değildir. Yeni canlı sonuç
gözlenene kadar kod yeteneği ile doğrulanmış üretim sonucu ayrı raporlanır.

### 21 Ekim: onaylanan başlık renkleri ve ayrı metin alanları

Kullanıcı krem karttaki lacivert–koyu turkuaz başlığı kalıcı düzen olarak seçti.
`editorial-cream-v1`, yalnız yeni/henüz sahiplenilmemiş haber, etkinlik ve takvim
hazırlıklarına uygulanır. [Kart yerleşimi](editorial-card-layout.md) kodun
gerçek yazı sınırlarıyla başlık, tarih, içerik ve açıklama notunu ayırmasını
açıklar. Eski `caption-note-v1` dahil bütün başlamış/yayımlanmış/belirsiz kartlar
önceki sürüm ve dosyalarını korur. Günlük hava kartı bu değişikliğe dahil değildir.

### 21 Ekim: kullanıcı tarafından eklenen Gerçek İzmir

[Kaynak ve açık haber seçimi](gercek-izmir.md), ASP yayın tarihini, özeti,
makaleye bağlı mandalina hasadı fotoğrafını ve kaynaklar arası sezon açılışı
tekrarını açıklar. Yeni kaynakla yapılandırma 52 okuyucudur (43 web/özel ve 9
Instagram); önceki 51 sayısı 19 Ekim'in tarihli durumudur. Hesap sahibinin belirli
haber isteği `post_id` ile günlük bütçe ve bütün yayın öncesi kontroller korunarak
uygulanır. Otomatik çalışma bu alanı dolduramaz; belirli kaynak önerisi tek
başına eski haberleri toplu yayımlama veya günlük sınır artırma yetkisi değildir.

### 21 Ekim: her paylaşımda ilgili görsel önceliği

[İlgili görsel politikası](relevant-visual-first.md) kaynak görselini önce deneme,
aynı slayt için gereksiz üretim çağrısını önleme, deneme bütçesini sıradaki
editoryal adaylara ayırma ve güvenilir HTML/RSS etkinlik görselinde başlık/
tarih/saat/OCR/konu kontrolünü açıklar. Desteklenmeyen kaynak/konu veya belirsiz
görselde bilgi kartı sürer. “Görsel önceliği” her haberde kesin fotoğraf veya
daha çok erişim garantisi değildir. Donmuş yayınlar ve hava stokları değişmez.

## Akış ve kod haritası

| Adım | Kod / ayar | Görevi ve sınırı |
|---|---|---|
| Kaynak tanımı | `config/sources.json`, `config/source_catalog.json` | Etkin/güvenilir kaynak ile incelenmiş adayları ayırır. |
| Instagram metni | `seferihisar/instagram_sources.py` | Mevcut yetkiyle GET; doğrulanmış kamu manifesti. Araştırmaya Meta anahtarı taşımaz. |
| Instagram fotoğrafı | `seferihisar/instagram_source_photos.py` | Ayrı isteğe bağlı GET, en fazla iki yayına uygun tek-fotoğraf adayı. Video/reel/albüm kullanılmaz. İmzalı CDN adresi yalnız bellekte. |
| Web/özel okuyucu | `seferihisar/collect.py`, `.github/workflows/automation.yml` | Robots, TLS, onaylı sunucu, tarih/konum ve sınırlı tarama. Her boş sonuç arıza değildir. |
| Kaynak doğrulama | `seferihisar/editor.py`, `timeliness.py`, `quality.py` | Ham kaynak metni, haber yaşı, etkinlik/uyarı bitişi ve editoryal uygunluk. Kaynağın okunması otomatik yayın onayı değildir. |
| Kalıcı kimlik | `seferihisar/store.py`, `schedule.py` | Kaynak revizyonları ve yayın kuyruğu. Yeni tarama eski haberi yeniden doğurmaz. |
| Fotoğraf/görsel | `source_photos.py`, `illustrations.py`, `image_safety.py`, `visual_match.py` | Kaynak bağı, temiz JPEG, konu/OCR ve gerçek kart yerleşimi. Model kişi/olay doğruluğunu kanıtlamaz. |
| Kart ve açıklama | `render.py`, `editorial_voice.py`, `text_quality.py`, `media_caption.py` | Sabit kimlik, Türkçe karakterler, okunabilir ve tarafsız metin, kaynak yalnız açıklamada. |
| Araştırma/panel | `pipeline.py`, `site/` | Araştırma, hazırlık ve temiz Pages çıktısı. Hazırlık işi paylaşım yapmaz. |
| Kalıcı durum | `state_git.py`, `security.py`, `automation-state` | SQLite bütünlüğü ve kamuya açık veri sınırı. Artifact tek kalıcı veritabanı sayılmaz. |
| Haber yayını | `instagram.py`, `facebook.py`, `.github/workflows/publish.yml` | İddia Meta yazımından önce kalıcıdır. Eşleşen story ve Facebook teslimleri aynı içeriğe bağlıdır. |
| Son görsel kontrolü | `visual_gate.py` | İçerik/revizyon, canlı Pages manifesti ve gerçek JPEG özetini yazımdan önce denetler. HEAD 200 yeterli değildir. |
| Günlük hava | `weather.py`, `weather_data.py`, `weather_copy.py`, `weather_render.py` | MGM Seferihisar satırı, açık geçerlilik, okunabilir metin ve yerel 3D salyangoz sahnesi; ayrı günlük IG story. |
| Bağlantı testi | `connection_health.py` | Var olan anahtarla hesap/kota/eşleşme GET testi. Yayın yapmaz; anahtarın gelecekteki bitişini göstermez. |
| Zamanlama yedeği | `ops/cron-worker.mjs` | Mevcut araştırma eskiyse/aktif iş yoksa ana dal araştırmasını başlatır; yayın veya yeni yetki oluşturmaz. |

19 Ekim yapılandırmasında **51 okuyucu** vardır: **42 web/özel okuyucu ve 9
Instagram hesabı**. Bu, 51 kaynağın her turda veri okuduğu anlamına gelmez.
Sayıyı sohbet hafızasındaki eski 37/8 gibi değerlerden taşımak yerine yapılandırma
ve son sağlık tablosundan yeniden çıkarın. `ok`: veri ayrıştırıldı; `empty`:
o yanıt penceresinde uygun kayıt yok; `partial`: bazı ayrıntılar okunamadı;
`failed`: kaynak okuma başarısız. `ok` da eksiksiz ilçe kapsamının kanıtı değildir.

## İşletim sözleşmesi

- Haber 48 saati geçince yeni paylaşım yapılmaz. `last_seen` tazeliği kaynak
  kontrolü içindir; ham `published_at` yaşını yenilemez. Kaynak sağlığı ve bir
  saatlik son başarılı görme kontrolü ayrıca gerekir.
- Etkinlik tarihi kaynak haberin yayım tarihi değildir. Bitişi geçen, iptal/
  ertelemenin eski seansı olan veya saati bilinmeyen son günündeki etkinlik
  yeni paylaşıma girmez. Saat/yıl/ücret/organizatör tahmin edilmez; bilet platformu
  otomatik olarak organizatör sayılmaz.
- Hava/kesinti ve süreli uyarılarda doğrulanmış geçerlilik bitişi gerekir.
  Göreli/çelişkili/eksik tarih kendiliğinden tamamlanmaz.
- Haber pencereleri Türkiye saati 08:30, 12:30, 15:00, 18:30 ve 21:00; her biri
  bir saat. Günde en fazla üç haber gönderisi ve üç ilk eşleşen story;
  farklı içerikler için 45 dakika aralığı korunur. Kaçırılan pencere için toplu
  eski yayın veya günlük sınır artışı yoktur.
- Hava story'si bağımsız, günde bir IG story'dir; Facebook hava yayını yoktur.
  07:35 erken tetikleme ve sabah araştırması yedeği, hazır/geçerli/dağıtılmış
  kartla en fazla 25 dakika bekleyip 08:00'da yeniden kontrol eder. Yalnız
  08:00–08:59 içinde yayın; 09:00 sonrası telafi yok. MGM kontrolü en fazla
  90 dakika eski olabilir. Boş sıcaklık başka değerle doldurulmaz.
- Araştırma, yayın ve hava işleri aynı üretim eşzamanlılık grubunu kullanır.
  Bütün SQLite'ı kalıcılaştıran kilidi tablo bazlı birleştirme tasarlamadan
  ayırmak güncellemelerin kaybolmasına yol açabilir. Aynı grupta bekleyen işin
  yer değiştirebilmesi de zamanlamayı etkiler. Yeşil iş yeni teslim değildir.
- `publishing`/`uncertain` sonuç tekrar gönderilmez. Durumu anlamadan iddiayı
  silmek veya sıfırlamak çift yayın oluşturabilir. `published_at`, özellikle
  hava tablosunda Meta çağrısından önceki iddia zamanıdır; tamamlanma saatiyle
  karıştırılmamalıdır.
- `container_id` boş bir `uncertain` haber iddiası Meta'ya hiç yayımlatılmadı:
  `instagram.deliver` kapsayıcı kimliğini Meta döndürür döndürmez kaydeder ve
  `media_publish` ancak ondan sonra çağrılır; hata kapsayıcı oluşturulurken
  çıkmıştır. Bu iddia yerinde kalır (saat dilimini ve günlük bütçeyi tüketir,
  tekrar gönderilmez), ama `operations.unresolved` yerine `not_sent` sayısına
  girer ve panelde `not_published` olarak görünür. 30 Ekim 15:16'daki Urla
  elektrik kesintisi duyurusu böyle kaldı; herkese açık profilde de yoktu.
  Kapsayıcı oluştuktan sonraki hata `unresolved` kalır; yayım olmuş olabilir.

## Görsel ve metin kararları

Onaylı logo, lacivert/turuncu/turkuaz şeritler ve okunabilir Türkçe tipografi
korunur. Kaynak adı/adresi yalnız açıklamada; otomatik AI üretim notu yoktur.
19 Ekim 2026 kullanıcı seçimi: S'nin üst kıvrımına yerleşen 3D salyangozlu
logo ana kimliktir. `brand_version: snail-s-v1` yeni haber/etkinlik/takvim
hazırlığının görsel onayına ve yeni hava tahmininin dosya kimliğine bağlanır.
Panel/favikon aynı onaylı PNG'yi kullanır. İşaretsiz eski iddialar ve bugüne
kadar yayımlanmış hava kartları `logo-legacy.png` ile korunur. Profil fotoğrafı,
reklam dosyası ve üretim dağıtımı ayrı ayrı doğrulanır; tek birinin değişmesi
her yerde tamamlandığı anlamına gelmez.
Yeni akış kartlarının içerik zemini krem, ilk başlık satırı lacivert ve devamı
koyu turkuazdır. Kısa tek satırlı başlıkta renk ayrımı sözcük sınırında yapılır.
Gövde ayrı alan ve renkte, açıklama notu onun hemen altındadır. Fontun negatif
sol taşıması (örneğin kalın y) gerçek yazı sınırına göre hizalanır; metni kenardan
keserek veya taşma denetimini gevşeterek çözülmez.
Hashtagler küçük harfli ve konuyla ilgili olur; keşfet/erişim garantisi verilmez.
19 Ekim kullanıcı kuralıyla “Detaylar açıklamada.” notu haber/etkinlik akışındaki
ilk kartın içerik metninin hemen altındadır; bu not için ayrı kart eklenmez.
Gerçek içerik slaytları kalır. Yeni `card_layout: editorial-cream-v1` bu düzeni
görsel özetine bağlar; eski `caption-note-v1` dahil dondurulmuş kartlar önceki
düzenlerini korur.

Gerçek haberin fotoğrafı yalnız kaynakla ve konuyla doğrulanırsa kullanılır.
İlk kapalı konu kümesi toplantı, trafik, su baskınıdır. Web fotoğrafı kendi
makalesine; Instagram fotoğrafı aynı hesabın aynı medya satırına bağlanır.
İkisi de gerçek olayın görselini uyduran üretime dönüşmez. Konu belirsizse bilgi
kartı. Etkinliklerde nesne/sahne görselleri ayrıca OCR ve yerel CLIP kontrolünden
geçer. Kaynak fotoğrafında tam çerçeve korunur; metadata temizlenince yan
dönecek dosya reddedilir. Model skoru olasılık, kimlik veya mekân kanıtı değildir.

Hava kartı minimal tasarım ve yalnız altta küçük yatay, özgün 3D salyangoz
sahnesi kullanır. Günlük yeni görsel üretimi yoktur. Bugünkü ve geçmişteki hava
kayıtları ayrı saklanır; Pages hava kartı mevcut güne aittir. Geçmiş hava kaydının
SQL'de kalması, eski günlük kartın aynı Pages adresinde tutulduğu anlamına gelmez.

## Önceki hatalardan öğrenilenler

| Gözlenen sorun | Korunan karar | Kontrol yeri |
|---|---|---|
| Toplantı haberinde trafik, selde kuru yol | Kategori fotoğrafı yeterli değil; kaynak bağı + konu kontrolü veya bilgi kartı | `source_photos`, `visual_match`, `visual_gate` |
| Kesintinin etkinlik/salon gibi sunulması | Hizmet duyurusu etkinlik değildir; açık süre ve uygun bilgi kartı | `timeliness`, `visual_subject` |
| Başlığın tekrarı, kaynak hesabının “biz” dili, emoji kutuları | Kaynak sesini tarafsızlaştırma, gerçek font karakteri ve tamamlanmış anlaşılır metin | `editorial_voice`, `quality`, `text_quality` |
| Seans geçmişken yeni paylaşım | Ham haber tarihi ve olay bitişi ayrı; yayın anında ortak kontrol | `timeliness`, `schedule` |
| Fotoğraf değişirken eski URL'nin erişilebilir kalması | İçerik/revizyon/dosya özetiyle sürümlü kart; canlı GET kontrolü | `visual_gate` |
| Yoga matının kırpılması | Gerçek gönderi/story yerleşimlerinde nesneyi koruyan kırpma kontrolü | `render`, `visual_match` |
| MGM yazım hatası veya uzun metnin kesilmesi | Ham tahmin saklı, sürümlü görüntü metni ve satır/font kontrolü | `weather_copy`, `weather_render` |
| Hava işinin erken bitmesi ve sonraki işin kaçması | Geçerli hazır kartla 08:00'a sınırlı bekleme; tek günlük iddia | `weather.run_weather` |
| Eski küçük örnekle yetinip yeni iddiaları kaçırma | Güncel bazın bütün donmuş SQL satırları ve değişiklikten etkilenen canlı JPEG'ler | Tarihli üretim karşılaştırması |
| README'de ilk sürüm sayılarının/kapalı kaynakların kalması | Kurulum varsayılanı, kod yeteneği ve tarihli canlı sonuç ayrılır | README ve bu rehber |
| “Ayrıntılar açıklamada” için gereksiz ikinci görsel | Not ilk kartta metnin altında; gerçek içerik dışındaki ek kart üretilmez. Yeni düzen sürümlü işaretle dondurulur. | `card_layout`, `render`, `visual_gate` |
| Yerel/bulut yeni JPEG özetinin farklı çıkması | Önce font/işletim sistemi farkını kontrol et; yeni Windows render'ını Linux çıktısıyla birebir aynı varsayma. Mevcut canlı dosyanın değişiklik öncesi/sonrası karşılaştırması ayrı kanıttır. | `render.font`, tarihli JPEG incelemesi |

Yeni bulguyu bu tabloya yalnız gözlem, neden ve doğrulanan kontrolle ekleyin.
Başarısız dış erişimi “tamir edildi” diye kaydetmeyin. Bilgi notu projenin
devamlılığını sağlar; modelin ağırlıklarının kalıcı eğitildiği anlamına gelmez.

## Kanıt ve çalışma yöntemi

1. Önce son tarihli raporu, temiz checkout'u, ana dalı ve tutarlı
   `automation-state` kopyasını inceleyin. Özel log/token kopyalamayın.
2. Eski bütün `posts` iddialarını (`published`, `publishing`, `uncertain`),
   `facebook_deliveries` ve `weather_stories` satırlarını bütün sütunlarıyla
   karşılaştırın. Eski altı/dört kaydın değişmemesi tek başına yeterli değildir.
3. Hazırlık: metin/kaynak/geçerlilik, görsel-konu, kaynak/dosya bağı ve canlı
   manifest/JPEG. Dağıtım: doğru ana dalın araştırma → persist → deploy sonucu.
   Teslim: aynı içeriğin parent kaydı, Meta container/media ID ve durum sonuçları.
   Platform ekranında doğrudan bakıldıysa bunu ayrıca belirtin.
4. Somut tekrarlanabilir yazılım hatasını en küçük kapsamda düzeltin; ilgili
   test ve CI, PR bağı, dağıtım ve eski veri kontrolünü tamamlayın. Dış erişim
   engeli için sonuçsuz manuel döngü kurmayın. Salt belge düzeltmesinde yayın
   ayarını veya çalışma kodunu değiştirmeyin.
5. Sonuç dosyası neyin tamamlandığını, hangi kanıtın bulunduğunu ve hangi
   doğrulamanın açık kaldığını kısa ve tarihli anlatsın. Aynı başarısız denemeyi
   farklı şekilde yeniden yapmak yerine önceki bulgudan yararlanın.

### 19 Ekim sabah doğrulaması

Ana çalışma sürümü PR #53, `f6f769f117ec3cfdf4b2a38f515410aebb9f66ea`.
08:42 tutarlı kopyada 25 Instagram iddiası, 23 Facebook teslimi ve dört hava günü
vardı. Bugünün hava kaydı `published`; iddia zamanı 08:00:00, başarılı iş sonuç
satırı 08:00:15.967. Bu, PR #50'nin erken bekleme yoluyla ilk doğal sabah kanıtıdır.
MGM Seferihisar tahmini 22°C en yüksek, düşük değer boş; açık geçerlilik
19 Ekim 06:00–20 Ekim 06:00, son kontrol 07:55. Doğrudan Instagram ekranı gözlemi
değildir. Günlük bağlantı işi IG/FB için `connected`, bitiş tarihi `not_checked`.

Son sağlık 33 `ok`, 17 `empty`, bir `failed`; hata @shgundem hedefindedir.
Güzelbahçe Kaymakamlığının doğrudan okuyucusu hâlâ bağlı değildir ve bu turda
yeniden denenmemiştir. Instagram fotoğraf hattında uygun dosya yoktur; canlı
fotoğraf alanı erişimi veya yeni fotoğraflı doğal teslim bu durumdan çıkarılamaz.
08:42'de son haber yayın kontrolü 08:27 saat penceresi dışındaydı; bugünün haber
sayacının sıfır olması kendi başına arıza değildir. Sonraki doğal yayın sonucu
ayrıca tarihli rapora alınır.

Kanıt çalışma alanında `outputs/continuation-2026-10-19/`, tutarlı kopya
`outputs/production-diagnostics/continuation-2026-10-19-0842.sqlite` altında.
Bu dosyalar depoda yoksa aynı mutlak/bağıl yolu varmış gibi sunmayın; yeni
çalışmanın kendi güvenli okuma kanıtını üretin. Önceki PR'lar: #39–41 zaman
geçerliliği, #45–47 görsel/editoryal kontrol, #48 etkinlik meta bilgisi,
#49 hava metni, #50 zamanlama, #51–52 web fotoğrafı, #53 Instagram fotoğrafı.

## Alt sistem ayrıntıları

[Resmî hizmet kaynakları](public-service-sources.md): 21 Ekim eklemesiyle 55
okuyucu (46 web/özel, 9 Instagram). Tarım, Orman ve İl Sağlık tamamlayıcı
kapsamdır; Eczacı Odası 403 nedeniyle etkinleştirilmedi. Kaynak tarihi ve
şablon alanları kesin okunmadan yeni içerik kabul edilmez.


[Benzer yaş ölçümü ve yerel seriler](cohort-local-series.md), 24–30 saat/7 gün
gruplarını, ham ölçümsüz kaba kayıtları, tamamlanmamış reklam ayrımını ve mevcut
üç haber gönderisi bütçesindeki cuma hafta sonu/salı ücretsiz etkinlik seçkilerini açıklar.

[İşletim denetimi ve yedek](production-resilience.md): ayrı sağlık işi, kontrollü
GitHub uyarıları, GET ile teslim gözlemi ve izole geri yükleme. Bu sürümün canlı
dağıtımı ve yeni API okuma sonuçları tarihli kanıtla ayrıca doğrulanır; eski
yayınlar veya önceki testler yeni özelliğin canlı kanıtı değildir.

[Yayın](automatic-publication.md), [işletim](operations.md),
[Facebook](facebook-publication.md), [etkinlik alanları](event-metadata-control.md),
[görsel kimlik](brand-cards.md), [görsel kapısı](content-visual-control.md),
[web fotoğrafı](source-news-photos.md), [Instagram fotoğrafı](instagram-source-photos.md),
[hava](daily-weather-story.md), [hava metni](weather-copy-control.md).
Eski tarihli kaynak araştırması belgelerini güncel sağlık tablosunun yerine kullanmayın.

22 Ekim 2026 tek kullanıcı isteği: [mandalina yan ürün projesi ve son tarihli yayın](owner-request-mandarin-reuse.md). Genel haber görsel kapıları açılmaz; kesin kaynak/piksel bağı, OCR, günlük bütçe ve tekrar koruması korunur. Hazır görsel gerçek Meta teslimi değildir.

26 Ekim 2026: [görsel kuyruğunu kurtarma ve kalıcı stok](visual-backlog-recovery.md).
İki başarısız üretim, aynı seans sahnesinin gereksiz tekrarı ve Bubilet CDN robots 404 nedeni ayrı ele alınır.
Canlı sonuç için tarihli dağıtım/SQL kanıtı gerekir; eski kurulum notları güncel Meta durumu sayılmaz.

27 Ekim son kontrol: native CI kapsamına test_visual_followup.py eklendi. EXIF 0 desteği tek başına konu onayı değildir; başlıklı örnek fotoğrafın model tarafından reddi korunur. Dokuz etkin stok sahne sürer. Başarısız kekik stok ve yan panel OCR denemesi bu depoya dağıtılmadı; Isparta kaynak incelemesi bağımsız depoda kalır.


### 28 Ekim: eski görsel arşivinin sınırlı onarımı

Önceki temizleme kuralıyla silinen, yayımlanmış kartlara bağlı görsel satırları yalnız bu deponun 26 Ekim durum yedeğinden geri alınır. Sabit yedek ve satır özeti, değişmemiş sahip yayın satırları ve gözlenen mevcut durum birlikte eşleşmelidir. Yeni bir yayın aynı anahtarı kullanıyorsa veya kayıt başka türlü değiştiyse onarım atlanır. Yeni yayın, kota artışı veya eski durum veritabanına dönüş yapılmaz. Mevcut budama koruması bu kayıtları korur. Instagram üzerinde eski içeriğin doğrudan gözlemiyle web arşivinin doğrulanması ayrı kanıtlardır.

Onarım mevcut 80 görsel/12 MiB sınırını yükseltmez. Yer gerekiyorsa yalnız süresi geçmiş veya yerini yeni sürüm almış taslaklara bağlı kullanılmayan önbellek satırları temizlenir. Aktif taslak/yayın görseli temizlenmez; yeterli yer yoksa onarım atlanır, normal durum yüklemesi kesilmez.

29 Ekim: budama bütçesi önce dondurulmuş yayın görsellerine ayrılır; yeni taslaklar yalnız kalan alana sığar. Eski zaman damgalı korunan satırların en sonda sayılıp toplam sınırı aşması iki regresyonla (adet/bayt) yeniden üretildi ve düzeltildi. Silinen taslaklar bütçeyi tüketmez; sınırlar artırılmadı.
