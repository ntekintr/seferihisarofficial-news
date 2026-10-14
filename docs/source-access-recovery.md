# Kaynak erişimi ve kısmi okuma — 14 Ekim 2026

Bir kaynağın birden fazla onaylı haber/duyuru listesi varsa tek listenin
erişim veya veri biçimi hatası artık diğer listenin doğrulanmış kayıtlarını
düşürmez. Başarısız listeler `listing_*` koduyla görünür; bu tur `partial`
sayılır. Bütün listeler başarısızsa kaynak `failed` kalır. Altı liste sınırı,
ortak detay bütçesi, yerellik/tarih denetimleri ve robots kuralları korunur.

Menderes Belediyesi ve Seferihisar Kaymakamlığı için mevcut sınırlı tekrar
mekanizması etkinleştirildi: onaylı alan adı başına turda en fazla bir ek
okuma. Sertifika, robots ve erişim reddi hataları bu yolla aşılmaz. Uzun
DNS kesintisinde sonraki normal bulut turu gerekir; kısa tekrar onarım
garantisi değildir.

DNS ve TLS alan adı uyuşmazlığı Requests/urllib3 içindeki gerçek hata
türlerinden ayırt edilir. İstisna metinleri, istek adresleri veya erişim
anahtarları tanı kayıtlarına aktarılmaz. Panel bu nedenleri ve liste
hatalarını ayrı Türkçe açıklamalarla gösterir.

Kaynak ağında tamamlayıcı okuyucunun ancak son bir saat içindeki başarılı
okuması belirtilir. Tamamlayıcı kaynağın başarısı asıl kaynağın hatasını
kapatmaz; web akışı yalnız Instagram'da yayımlanan haberleri kapsamayabilir.

23:24 Türkiye saati canlı GET kontrolünde Menderes Belediyesi, Seferihisar,
Urla ve Menderes kaymakamlıkları, İzmir Valiliği ve GDZ hatasız okundu.
Önceki ortak DNS kesintisi bu kontrolde sürmüyordu. Güzelbahçe Kaymakamlığı
iki güven deposunda da alan adıyla eşleşmeyen sertifika sundu (doğrulama
kodu 62); doğrudan haber okuyucusu bağlı sayılmıyor. Kurumun sertifika
yapılandırmasını düzeltmesi gerekir. Mevcut Meta bağlantısı diğer sekiz
Instagram hedefini okurken @shgundem `instagram_source_unavailable`
döndürüyor; kesin hesap kısıtı veya hesap türü bu koddan çıkarılamaz.
Genel izin yenileme ya da anahtar oluşturma bu değişikliğin parçası değildir.

Yayın politikası ve günlük sınırlar değişmez. Eski yayımlanmış veya sonucu
belirsiz Instagram/Facebook kayıtları yeniden yayımlanmaz.
