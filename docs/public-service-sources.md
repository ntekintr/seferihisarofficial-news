# Resmî hizmet kaynakları — 21 Ekim 2026

Yapılandırmaya üç tamamlayıcı okuyucu eklendi: İzmir İl Tarım ve Orman
Müdürlüğü, İzmir Orman Bölge Müdürlüğü ve İzmir İl Sağlık Müdürlüğü.
Toplam yapılandırma **55 okuyucu: 46 web/özel, 9 Instagram**. Bu sayı her
kaynağın her taramada çalıştığı veya bütün ilçe haberlerinin bulunduğu anlamına gelmez.

Tarımın haber arşivi ve ana sayfası tek dört ayrıntı bütçesini paylaşır.
`h3.page-title`, `#th-content-post` ve tam yıllı `.itemDateCreated` alanı okunur;
görünür `gg.aa.yyyy /` tarihi gün başında kabul edilir, saat uydurulmaz.
Canlı ilk örnek Sığacık haberinin 23 Haziran tarihini korudu; 48 saat filtresi
bunu güncel haber saymadı.

Ormanın sayfasındaki herkese açık React başlangıç verisinden yalnız sabit
aynı köken `/izmirobm/haberler/` ve `/duyurular/` bağlantı dizeleri çözülür.
JavaScript çalıştırılmaz; özel API veya oturum kullanılmaz. Tur başına üç
ayrıntı okunur. Görünür `.haber-tarih`/`.duyuru-tarih`, `h1` ve asıl zengin metin
alanı zorunludur. Son ilk üç haberde hedef bölgeye uygun içerik çıkmaması
okuyucunun bütün orman haberlerini kapsadığı şeklinde sunulmaz.

Sağlıkta kamuya açık manşetler ve duyuru listesi, makalede `.page-content-header
h5`, `.update-date` ve `#div_print` incelendi. Boş manşet bağlantısında sitenin
verdiği `title` kullanılır. Yakın ilçelerde açık acil sağlık hizmeti/aile sağlığı
merkezi açılışı önemli yerel hizmet kapsamına girer; sıradan ziyaret/toplantı
genel haber sayılmaz. Görünür eski 5 Aralık 2025 Güzelbahçe duyurusu eski
tarihini korur. Şablonun tarih alanından özgün yayım/güncelleme ayrımı dışında
kesinlik çıkarılmaz; ilk oluşturulma zamanı ayrıca doğrulanmış sayılmaz.

Bu üç ayrıntı şablonunda zorunlu başlık, gövde veya tarih alanı değişirse yan
menü/takvim/genel article verisine sessiz geri dönüş yapılmaz; kısmi ayrıntı
hatası kaynak sağlığına yansır. Haber gövdesi dışındaki ilçe adları yerellik
kanıtı değildir. Etkinliğin açık tarih/saat şartları ve diğer yayın kontrolleri sürer.

İzmir Eczacı Odası doğrudan izinli kontrolde **403** verdi; katalogda erişim
engeli olarak tutuldu, etkin okuyucu eklenmedi. İlçe, gün ve nöbet geçerliliği
doğrulanmadan nöbetçi eczane yayını yapılmaz. Robots/TLS güvenliği aşılmaz.

Mekân/organizatör kapsamı mevcut Bademler ve Teos gibi bağlantılarla sürer;
doğrudan izinli program akışı bulunması bütün mekânların kapsandığı anlamına
gelmez. Yeni keşifler mevcut karantina/kanıt kurallarına tabidir. Eski korumalı
akışlar sırf katalogda bulunduğu için sağlıklı sayılmaz. Canlı sağlık sonuçları
bu belgenin sabit tarihli örneklerinden ayrı raporlanır.
