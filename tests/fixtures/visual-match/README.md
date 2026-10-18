# Sabit görsel regresyonları

Küçük JPG dosyaları yalnız fotoğraf alanıdır; Instagram arayüzü ve hesap
bilgileri dahil edilmemiştir. `traffic-meeting`, `hall-outage` ve
`dry-road-flood`, kullanıcının 17 Ekim 2026'da hata incelemesi için sağladığı
ekran görüntülerinin fotoğraf kırpmalarıdır.

Diğerleri sistemin aynı gün okunan halka açık `automation-state` önbelleğindeki
kendi üretilmiş sahneleridir. `*-accepted` dosyaları güncel sahne anahtarına
bağlı olumlu örneklerdir. `yoga` eski genel salon sahnesidir; `theatre` ve
`tile-art` karede yakın olsa da en az bir geniş kırpmada belirsiz kalan
örneklerdir. Model bu belirsizliklerde fotoğraf onayı vermemelidir.

Eşikler bu az sayıdaki örnek üzerinde doğrulanmıştır; bütün konular için
kusursuz semantik tanıma iddiası yoktur. İlgisiz haber fotoğrafını asıl önleyen
kapalı konu politikası ayrıca test edilir.

v2'nin 506 piksel story kırpmasında `tile_art-accepted` de belirsiz kalır.
Dosya adı eski v1 kabulünü anlatır; bu dosya artık ek bir ret regresyonudur.
Eşik bu örneği geçirmek için gevşetilmez; kart fotoğrafsız hazırlanır.

`news-meeting-source.jpg`, 18 Ekim 2026'da aşağıdaki haber sayfasının kendi ana
fotoğrafı olarak doğrulanıp alınan 768×454, metadata içermeyen yerel test kopyasıdır:
https://seferihisarlife.com/ak-parti-seferihisar-ilce-baskani-serdar-kisaaga-23-mahalle-muhtariyla-bulustu/
Kaynak dosya: https://seferihisarlife.com/wp-content/uploads/2026/10/1-3-1100x650.png
Haber 15 Ekim tarihlidir; test kullanımı yeni haber veya yeni yayın iddiası değildir.
Bu dosyanın gerçek toplantı konusuyla eşleşmesi, kaynak haber kimliğinin ayrıca
doğrulanması gereğini kaldırmaz. Kaynak fotoğrafları baş/yüz kesmeden tam kareyle
yerleştirilir; üretilmiş sahnelerin mevcut kırpma ve ret kuralları değişmez.
