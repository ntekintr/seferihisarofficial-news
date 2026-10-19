# Sabit kart kimliği ve görsel politikası

Gönderiler 1080×1350, story kartları 1080×1920 JPEG'dir. Onaylı logo, lacivert,
mandalina turuncusu ve turkuaz şeritler ortaktır. Şeritler yüksek çözünürlükte
çizilip küçültülür; çapraz çizgide belirgin basamak oluşması engellenir.
Türkçe büyük İ ve kullanılan bütün karakterlerin fontta bulunması kontrol edilir.
Başlık ve metin okunabilir biçimde yerleşmeli; kritik bilgi veya kelime
kesilerek anlama zarar verilmemelidir. Tam metin açıklamada kalır.

Kaynak adı ve adresi **yalnız açıklamadadır**. Karta otomatik kaynak veya
“Temsili çizim” etiketi eklenmez. Açıklamaya eski otomatik yapay zekâ üretim
notu konmaz. Bu, kaynağın haber konusu olarak AI'dan bahseden gerçek metnini
silme kuralı değildir. Etiketler küçük harfli ve içerikle ilgili olmalıdır.

## Haber, etkinlik ve yedek kart

- Haber için genel kategoriye göre uydurulmuş olay fotoğrafı kullanılmaz.
  Toplantı, trafik ve su baskını haberlerinde [web kaynak fotoğrafı](source-news-photos.md)
  veya [isteğe bağlı Instagram fotoğrafı](instagram-source-photos.md) kendi kaynak,
  başlık, tarih, dosya ve konu kontrolleriyle değerlendirilebilir.
- Haberle bağı doğrulanamayan veya desteklenmeyen görselde sabit kimlikli
  bilgi kartı kullanılır. Kategoriye ait herhangi bir fotoğraf yeterli değildir.
- Etkinlikte konuya uygun, gerçek bir olayın gerçekleştiğini göstermeyen boş
  sahne/nesne görselleri kullanılabilir. OCR ve sabit yerel sahne modeli gerçek
  kart yerleşimleri üzerinde çalışır. Yoga matı, çini tezgâhı veya tiyatro sahnesi
  gibi belirgin nesneler başlıkla uyuşmalıdır. Kontrol yoksa/reddederse bilgi kartı.
- Takvim kapağı ve kaynak/ayrıntı slaytları başka slaydın fotoğrafını otomatik
  devralmaz. Her fotoğraf açık bir slayt bağıyla atanır.

Üretilmiş etkinlik görselleri mevcut Cloudflare bağlantısıyla araştırma işinde
hazırlanabilir; bu belge güncel servis fiyatı veya kota vaadi değildir.
Uygulama sınırı tur başına iki ve UTC gününde yirmi görsel üretim girişimidir.
Günlük sınır Türkiye saati 03:00'te yenilenir. Yerel salyangoz sahnelerinden
hazırlanan hava kartı günlük görsel üretim çağrısı yapmaz.

## Dondurulmuş içerik

Fotoğraf/çizim dosyaları temiz JPEG olarak sınırlı önbelleklerde tutulur. Kaynak
metni, model skoru ve temiz JPEG birbirinin yerine kanıt değildir. Provider yanıtı,
geçici imzalı CDN adresi ve gizli anahtar kamu çıktısına yazılmaz; Meta tesliminden
yalnız güvenli kimlik/durum alanları kalıcı kayda girer. Çizim ve kaynak fotoğrafı
önbelleklerinin her biri 80 görsel / 12 MiB ile sınırlı; tek JPEG en çok 768px ve
512 KiB'dir.

Hazırlanan kart içerik, kaynak revizyonları ve gerçek JPEG özetleriyle sürümlü
bir klasöre bağlanır. Başlamış, yayımlanmış veya belirsiz gönderiler kendi önceki
bağlarını korur. Sonradan değişen kaynak veya yeni tasarım eski gönderinin
görselini değiştiremez. Yayıncı yeni görsel üretmez veya kaynak fotoğrafı indirmez;
yayından önce canlı manifest ve gerçek dosya özeti kontrolü yapar.

Detaylar: [görsel kontrolü](content-visual-control.md),
[yazı güvenliği](illustration-text-safety.md), [günlük hava story'si](daily-weather-story.md).
