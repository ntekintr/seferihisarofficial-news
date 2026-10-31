# İlgili görsel önceliği — 21 Ekim 2026

Kullanıcı her yeni paylaşımda ilgi çekici ve içerikle ilgili görsel denenmesini
istedi. İlgili resim bulamamak, alakasız bir resim atamak için gerekçe değildir.
Bu tercih eski gönderiyi düzenlemez ve her habere fotoğraf garantisi vermez.

Araştırmada sıradaki editoryal adaylar önce işlenir. Acil düzeltme/hizmet,
yerellik ve zaman sırası mevcut `selection.prioritize` kuralıdır. En fazla iki
kaynak fotoğrafı araştırması ve iki üretim denemesi, eski/uzak kuyruk öğelerinden
önce bu adaylara ayrılır. Yayın seçiminin önem ve zaman kuralları değiştirilmez.

Önce makaleye bağlı kaynak fotoğrafı denenir. Mandalina hasadı artık yalnız
Gerçek İzmir'e özel değildir; açık hasat başlığı, güvenilir yapılandırılmış
kaynak, kendi makalesi ve konu kontrolü yine gerekir. Trafik, su baskını, yol
çalışması ve mandalina hasadı kapalı olay konularıdır. Etkinlik çevresinde anlatılan
haberlerde 31 Ekim'den beri makalenin kendi gerçek fotoğrafı
[ayrı kontrolden](source-news-photos.md) geçebilir; genel kategori veya kişinin adı
tek başına fotoğraf seçtirmez.

## Etkinlik fotoğrafı ve afişi

Mevcut güvenilir HTML/RSS okuyucusunun kendi ayrıntı sayfasında yeniden
ayrıştırılan etkinlik başlığı, başlangıç/bitiş, mekân, durum ve saat bilgisi
kayıtla eşleşmelidir. Resim hem makale gövdesinde hem açık ana görsel seçiminde
bulunmalı; aynı kökende olmalıdır. İlgili haber, logo, arşiv, reklam ve yönlendirme
korumaları devam eder. Henüz desteklenmeyen bilet/CDN/API görüntüleri bu dar
okuyucuya kendiliğinden açılmaz; Instagram afişi için yeni Meta isteği/izni yoktur.

Portre afiş en az 480×640, oranı 0,5–1,4 aralığında olabilir; mevcut yatay
fotoğraf sınırları aynı kalır. Kaynak görselin tamamı oranı korunarak karta
sığdırılır. Afişin küçük yazılarının okunaklı olduğu garanti edilmez; doğrulanmış
başlık, tarih, yer ve ücret kendi kart alanlarında ve açıklamada kalır.

Kaynak etkinlik görseline mevcut yerel Tesseract ile iki tarama uygulanır.
Görülen yıl/tarih/saat çelişkisi ret sebebidir. Portre, okunabilir tarih/saat
veya en az üç sözcük içeren resimde başlığın en az yüzde 60 sözcük örtüşmesi,
açık tam tarih ve bilinen başlangıç saati gerekir. Sayısal ve Türkçe ay isimli
tarihler desteklenir; OCR eksik/kararsızsa afiş kabul edilmez. Bilet/son başvuru
son günü gibi farklı tarihler de bu ilk dar sürümde ret doğurabilir. OCR/model
kontrolleri olgusal doğruluk garantisi veya kişi/mekân tanıma sistemi değildir.

Üç gerçek tam çerçeve oranında mevcut sabit yerel CLIP eşikleri ayrıca korunur.
Konu belirsizliği, iptal ve kesinti afişine genel etkinlik görseli atanmaz.

Etkinlik kaynak kanıtı `source-photo-event-v1` ile başlangıç ve bitişe bağlanır;
haberin yayın zamanı etkinlik tarihi yapılmaz. Sürüm, makale ve temiz JPEG,
önbellek ve canlı dosya bağlantısı korunur. Kaynak görseli atanmış slayt için
ayrıca üretim isteği yapılmaz. Uygun kaynak görseli yoksa etkinliğin mevcut
konu/OCR denetimli sahnesi kullanılır/denenir. Son yedek logolu bilgi kartıdır.
Gerçek haber olayı, kişi, kaza veya afet fotoğrafı uydurulmaz.

`factory.visual_policy` yalnız hazırlanmış ilk kartların gerçek onaylı resim
bağlarından fotoğraf/konu görseli/bilgi kartı sayılarını verir. Takvimin sonraki
slaydında resim bulunması kapakta resim varmış gibi sayılmaz. Ham resim adresleri,
özel metrikler veya erişim anahtarları bu özete girmez. Bu sayı Meta teslimi değildir.

Günlük üç haber ve üç eşleşen story, bağımsız günlük hava/eczane, mevcut ücret/kota ve
belirsiz yayını tekrarlamama sınırları aynı kalır. Geçmiş SQL satırları ve canlı
JPEG byte özetleri dağıtım sonrası tarihli karşılaştırmayla ayrıca doğrulanır.
