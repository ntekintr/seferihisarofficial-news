# Kamuya açık kaynak doğrulaması

Kontrol tarihi: **11 Ekim 2026**, Europe/Istanbul. Bu kontrol haber araştırması ve hazırlık içindir; Instagram hesabına yayın yapılmamıştır.

## İncelenen kaynaklar

| Kaynak | Başlangıç adresi | İncelenen format ve sonuç |
| --- | --- | --- |
| Seferihisar Belediyesi | https://seferihisar.bel.tr/haberler | Haber kartları ve detay sayfaları açıldı. Belediye şablonunun JSON-LD verisindeki sondaki virgüller yalnız bu kaynak için onarılır. Yayın tarihi ve haber gövdesi okunur. İncelenen son haberler yedi günlük pencerenin dışında kaldı. |
| Seferihisar Kaymakamlığı | https://www.seferihisar.gov.tr/ | Liste açıldı; genel ayrıştırıcıyla tarih ve içerik koşullarına uygun kayıt çıkmadı. |
| İzmir Büyükşehir Belediyesi | https://www.izmir.bel.tr/tr/Rss/Haberler | RSS açıldı; Atom `updated` tarihi bulunuyor. Son haber penceresinde yerellik filtresini geçen haber çıkmadı. |
| Seferihisar Yeni Haber | https://www.seferihisar.com/ | Haber kartları ve JSON-LD haberleri okundu. İncelenen içerikler eski veya hassas konu filtresine takıldı. |
| Seferihisar Gündem | https://www.seferihisargundem.com/ | Liste ve örnek detay sayfası açıldı; sonraki isteklerde zaman aşımı da görüldü. Geçersiz JSON-LD yerine açık `datePublished` metaverisi ve haber gövdesi kullanılır. 9 Ekim 2026 tarihli Ahi Festivali haberi bu yolla doğrulama koşullarını geçti. |
| Ege Telgraf | https://www.egetelgraf.com/rss | RSS açıldı; son haber penceresinde kapsamla eşleşen kayıt çıkmadı. |
| Haberler.com | https://www.haberler.com/seferihisar/ | Seferihisar, Urla, Güzelbahçe, Özdere ve Yelki listeleri açıldı. Haber detaylarında yayın tarihi ve içerik okundu; eski ve hassas haberler dışarıda tutuldu. |
| Habertürk | https://www.haberturk.com/haberleri/seferihisar | Seferihisar ve çevre ilçe listeleri, JSON-LD haberleri okundu. Şemadaki ana sayfa URL'si yerine ziyaret edilen haber bağlantısı kullanılır. İncelenen içerikler eski veya hassas konu filtresine takıldı; bütün akış kontrolünde bir detay isteği başarısız oldu. |
| DHA | https://www.dha.com.tr/haberleri/seferihisar | Kamuya açık haber listesi ve JSON-LD detayları okundu. İncelenen içerikler hassas konu filtresine takıldı. |

Kaynağın açılması, güncel içerik bulunması ve içerik hazırlığının yapılması ayrı sonuçlardır. Uygun içerik yoksa sıfır haber gösterilmesi beklenen davranıştır. Kayıtlı yerel test örnekleri ayrıştırıcının davranışını doğrular; sonraki canlı erişimi garanti etmez.

## Bütün akış kontrolü

Üretim komutu ayrı bir yerel veritabanı ve ayrı çıktı klasörüyle, API anahtarı ve Instagram yayını olmadan çalıştırıldı. 11 Ekim 2026 16.56–16.58 aralığındaki çalışmada **bir haber toplandı, sıfır etkinlik ve sıfır hazır gönderi oluştu**. Habertürk'te bir detay erişim hatası kaydedildi. Ahi Festivali haberi yedi günlük haber penceresine girdi; mevcut gönderi politikasının 48 saat sınırından eski olduğu için gönderi hazırlığına alınmadı. Açık etkinlik yılı/tarihi çıkarılmadığı için takvim etkinliği sayılmadı.

83 yazılım testi geçti. Panel kodunun sözdizimi, örnek verilerle gönderi/story görsel üretimi, kamuya açık çıktı ve kalıcı durum denetimleri başarılı oldu. Örnek görseller canlı haber başarısı yerine kullanılmadı; canlı durum veritabanı ve ham kaynak metinleri depoya eklenmedi.

## Erişim ve bağlantı kuralları

- Listeler aynı onaylı alan adında olmalıdır. Bir kaynak en fazla altı listeyi ve yapılandırılmış detay sayfası bütçesini kullanır. Çevre ilçe listelerinin haberleri sırayla ziyaret edilir; tek bir yoğun liste tüm bütçeyi tüketmez.
- Seferihisar Belediyesi, İzmir Büyükşehir Belediyesi, Seferihisar Yeni Haber ve DHA'nın kamuya açık sayfaları incelendi; bu alan adlarında bulunmayan `robots.txt` için yalnız 404/410 istisnası etkindir. Diğer erişim hataları ve açık robots kuralları korunur. Her yeni alan adı ayrıca incelenmelidir.
- Gerçek isteklerde bağlantının sonundaki `/` korunur. Tekrar kontrolü için kimlik normalleştirilir; haber bağlantısı kimlik adına değiştirilmez. Böylece slash yönlendirmesi döngüye girmez ve aynı haber farklı takip parametreleriyle çoğalmaz.
- Güzelbahçe, Urla, Yelki ve Özdere için yer adı ile etkinlik veya önemli kamu konusu birlikte aranır. Türkçe büyük harfler ve kelime sınırları kontrol edilir; `buralarda` sözcüğü Urla sayılmaz.
- Yayın tarihi, etkinlik tarihi değildir. Yılı belirtilmeyen veya yalnız afişte bulunan etkinlik tarihi tahmin edilmez. Hassas haberler ve yedi günden eski haberler haber akışının dışında kalır. Mevcut gönderi politikasında 48 saatten eski haber gönderileri sona erer; bu düzenleme bu sınırı değiştirmez.

Yeni sosyal medya/Instagram kaynakları, bilet platformları ve Meta yayın erişimi bu doğrulamanın kapsamında değildir.
