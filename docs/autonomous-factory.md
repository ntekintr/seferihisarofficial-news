# Otonom içerik üretim zinciri

20 Ekim 2026 kullanıcı isteği: rutin içerik araştırması, hazırlığı, kontrolü,
yayını, performans ölçümü ve yeni kaynak araması insanın günlük teyidini beklemez.
Bu belge kodun çalışma sözleşmesidir; canlı çalışmanın kanıtı tarihli sonuçlardır.

## Üretim ve otomatik kalite kapıları

Normal bulut araştırması saatte dört kez etkin web/kurum/Instagram okuyucularını
çalıştırır. Kaynak kökeni, konum, tarih ve bitiş kontrolü; tekrar ayıklama;
tarafsız metin, başlık, ücret ve organizatör alanlarının kontrolü uygulanır.
Hassas/kanıtsız iddialar otomatik yayın dışı kalır; kullanıcıdan günlük onay istenmez.
Haber 48 saat sınırını aşamaz; geçmiş etkinlik/uyarı yeni taramayla güncellenmiş
sayılmaz. Hiçbir kontrol kaynağın bütün iddialarının mutlak doğru olduğunu kanıtlamaz.

Kaynakla ve konuyla doğrulanmış haber fotoğrafı veya konuya uygun etkinlik
görseli seçilir/üretilir. Metin, nesne/konu, gerçek kart kırpması, okunabilirlik,
logo ve dosya özeti kapıları çalışır. Uygun görsel üretilememesi kota artırma
veya alakasız fotoğraf kullanma nedeni değildir; kabul edilen bilgi kartı yedeği
kullanılır. Kaynak yalnız açıklamadadır. “Detaylar açıklamada.” ilk karttadır.

Yeni açıklamalar yaklaşık beş küçük harfli, konuyla/coğrafyayla desteklenen
hashtag içerir. Sayıyı doldurmak için bilinmeyen yer, tür, #viral veya #keşfet
eklenmez. Kesinti, konser/etkinlik gibi etiketlenmez. Yeni kural unclaimed
hazırlıkları normal araştırmada yeniler; yayınlanmış iddialar yeniden yazılmaz.

Yayın işi yalnız başarılı ve güvenilir ana dal araştırmasından sonra çalışır.
Yazmadan hemen önce kaynak/geçerlilik, metin sürümü, canlı Pages manifesti ve
JPEG dosyaları tekrar eşleştirilir. Günde iki haber ve ilk eşleşen story,
Facebook teslimleri ve ayrı günlük hava story sınırları korunur. Belirsiz Meta
yanıtı tekrar gönderilmez. Yeşil hazırlık işi gerçek teslim kanıtı değildir.

## Performanstan öğrenme

Ölçüm işi `automation.yml` içinde, günün ilk başarılı araştırma ve durum
kalıcılaştırmasından sonra, aynı üretim kilidi altında çalışır. Günlük tekrar
kilidi vardır; araştırma yalnız zamanının gelip gelmediğini anahtarsız kontrol eder.
Ölçüm işi ayrı bir workflow olarak kuyrukta beklemediğinden yeni araştırmanın
onu başlamadan düşürmesi önlenir. Ölçüm hatası haber işinin başarısını bozmaz.
Mevcut hesabın kimliğini, kendi medya listesini ve otomatik gönderilere ait
insights değerlerini yalnız GET ile okur. Yeni izin veya token oluşturmaz.
Erişim yoksa hata kontrollü kaydedilir; haber üretimi mevcut sıralamayla sürer.

21 Ekim v2 güncellemesinde en fazla 20 kendi gönderisi yalnız 24–30 saat veya
168–174 saatlik yaş pencerelerinde ölçülür. Bu pencerede ölçülmemiş kayıt için
normal araştırma ölçüm işini en fazla saatte bir uyandırabilir; kaçan geçmiş
pencere doldurulmaz. Her grup kendi içinde en az 10 gönderi, en az iki konu ve
her konuda 100 erişimi geçmiş en az üç gönderi gerektirir. Kaydetme/paylaşım
etkileşim toplamına ayrıca ağırlık verir; ayrı tekil insanlar gibi toplanmaz.

Ham ölçümler, erişim anahtarı ve özel hesap detayları herkese açık Git durumuna,
Pages'e, loga veya artifact'e konmaz. Kontrol sonucu ve 0/1 konu tercihlerine ek,
en fazla 400 kayıtlık kaba yaş grubu/skor sınıfı tutulur; ilk gözlem değişmez.
Gerçek erişim/etkileşim sayısı tutulmaz. Reklam etkisi mevcut erişimle ayrılamaz;
özet bunu açıkça belirtir ve organik sonuç iddia etmez. Ayrıntılar
`cohort-local-series.md` içindedir. Üç günden eski tercihler geçersizdir. Bu tercihler yalnız
zaten uygun içerikler arasında, yerellik/aciliyet/zaman sınıfından sonra
kullanılır. Uyarı, iptal ve düzeltmeler önce gelir. Son iki haberin konusuna
yeniden tercih puanı verilmez; başka içeriklerin keşfi korunur. Bu bir sınırlı
sıralama kuralıdır; modelin kendi ağırlıklarını yeniden eğitmesi değildir.

## Yeni kaynak araması

Her normal taramada gerçek kaynak sayfasındaki RSS/Atom ve dış yayıncı/kurum
bağlantıları aday olarak kaydedilir. Kaynak metnindeki talimatlar uygulanmaz.
En fazla 300 aday, günde en fazla üç deneme ve en fazla sekiz ek okuyucu vardır.
Her adaya asıl bağlantıyı veren etkin, güvenilir kaynağın kökeni bağlanır.

Otomatik etkinleştirme **zaten güvenilir yapılandırılmış yayıncının aynı HTTPS
kökenindeki yeni RSS/Atom akışı** veya **iki ayrı güvenilir yayıncıdan bağlantıyla
doğrulanan yeni .gov.tr/.bel.tr kamu kurumu akışı** içindir: robots/TLS/DNS ve ayrıştırma
kontrolü, en az iki farklı güncel/yerel/yayına uygun içerik ve üç ayrı gün başarılı
gözlem gerekir. Aktif kaynak normal sağlık/tarih/görsel kapılarından da geçer.
Yapılandırılmış asıl yayıncı veya gereken iki köken kaldırılırsa türetilmiş
okuyucu kullanılamaz. Resmî alan adı tek başına kabul nedeni değildir.

Bilinmeyen ticari/özel dış siteler sırf link verilmesi, modelin beğenmesi veya tekrar
okunmasıyla güvenilir yayıncı sayılmaz; otomatik yayına alınmaz. Bu, internetteki
tüm yerel sitelerin kendiliğinden kabul edildiği anlamına gelmez. Başarısız aday
bir hafta bekler; robots veya TLS koruması aşılmaz. Durdurulması istenen @shgundem
ve Güzelbahçe Kaymakamlığı için ek manuel döngü kurulmaz.

## İşletim ve sınırlar

Pages `data.json.factory`, üretim aşamalarının sayılarını, öğrenme durumunu ve
kaynak deneme sonuçlarını kontrollü alanlarla açıklar. Paylaşılmış 29 Instagram,
27 Facebook ve geçmiş hava satırlarının tamamı dağıtım öncesi/sonrası karşılaştırılır;
bu sayılar 20 Ekim başlangıç bazıdır, gelecekte sabit kabul edilmez.

Çalışma GitHub/Meta/kaynak hizmetlerinin erişimine ve mevcut kotalara bağlıdır.
Tek seferlik kimlik doğrulama veya servis kesintisini yazılımın tek başına
çözebileceği söylenmez. Yayın sınırını aşma, ücretli hizmet, kota artırımı veya
reklam bütçesine müdahale bu özellikte yoktur. Kural hatalı içeriği paylaşmak
yerine bekletir; kullanıcıdan her haber için teyit almaz.
