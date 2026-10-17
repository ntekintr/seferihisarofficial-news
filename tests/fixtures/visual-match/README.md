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
