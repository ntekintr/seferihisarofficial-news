# Sabit kart kimliği ve görsel politikası

Gönderiler 1080×1350, story kartları 1080×1920 JPEG'dir. Onaylı logo, lacivert,
mandalina turuncusu ve turkuaz şeritler ortaktır. Şeritler yüksek çözünürlükte
çizilip küçültülür; çapraz çizgide belirgin basamak oluşması engellenir.
Türkçe büyük İ ve kullanılan bütün karakterlerin fontta bulunması kontrol edilir.
19 Ekim 2026'da kullanıcı, üst kıvrımında 3D salyangoz bulunan S logosunu ana
kimlik olarak seçti. `assets/logo.png` bu onaylı özgün PNG'dir; haber, etkinlik,
takvim ve hava kartlarında yeniden çizilmeden kullanılır. Web paneli başlığı
ve favicon da aynı dosyanın `logo-snail-s-v1.png` kopyasını kullanır.

Yeni hazırlık `brand_version: snail-s-v1` taşır. Bu alan görsel onayına ve
etkinlik/haber dosya klasörüne bağlanır; eski logolu hazırlığın onayı yeni logoya
kanıt sayılamaz. Hava tahmininde aynı işaret yeni asset kimliği üretir. Başlamış,
yayımlanmış veya belirsiz eski iddialar işaretsiz kalır ve `logo-legacy.png`
ile önceki görsellerini korur; yeni işaretli iddialar yayımlandıktan sonra da
seçilmiş logoyu tutar. Sosyal hesap profil fotoğrafı güncellemesi ayrı platform
işlemidir; kod dağıtımı tek başına bunun yapıldığını kanıtlamaz.
Başlık ve metin okunabilir biçimde yerleşmeli; kritik bilgi veya kelime
kesilerek anlama zarar verilmemelidir. Tam metin açıklamada kalır.

Kaynak adı ve adresi **yalnız açıklamadadır**. Karta otomatik kaynak veya
“Temsili çizim” etiketi eklenmez. Açıklamaya eski otomatik yapay zekâ üretim
notu konmaz. Bu, kaynağın haber konusu olarak AI'dan bahseden gerçek metnini
silme kuralı değildir. Etiketler küçük harfli ve içerikle ilgili olmalıdır.

19 Ekim 2026 kullanıcı kuralı: haber, etkinlik, kesinti, hatırlatma/güncelleme ve
takvim gönderilerinde **“Detaylar açıklamada.” ilk kartın içerik metninin hemen
altında** yer alır. Bu mesaj için ayrı bir görsel/slayt oluşturulmaz. Gerçek
program/etkinlik içeren sonraki kartlar korunur; not yalnız ilk karta eklenir.
Gönderi ve eşleşen story yerleşimlerinde not için alan ayrılır; tarih/mekân/ücret
üzerine yazılmaz. Bağımsız hava story'si kendi tek kartlı tasarımını kullanır.

21 Ekim 2026'da kullanıcı krem zeminli, lacivert–koyu turkuaz başlıklı örneği
yeni haber/etkinlik kartları için seçti. Yeni hazırlık
`card_layout: editorial-cream-v1` işaretiyle görsel onay özetine
bağlanır; eski manifest veya ek kartlı dosya listesi yeni düzenin kanıtı olamaz.
Yeni düzenle yayımlanan kart işaretini korur. Önceden başlamış/yayımlanmış/belirsiz
iddialar kendi önceki dosya sayısını ve görsellerini tutar; geçmiş paylaşım
düzenlenmez veya yeni düzene geçirmek için yeniden yayımlanmaz.
Önceki `caption-note-v1` sürümü kalıcı durumda geçerlidir; onun eski dosyaları
ve içerik özetleri değişmez. [Başlık ve içerik alanları](editorial-card-layout.md)
yeni düzenin taşma, gerçek yazı sınırı ve okunabilirlik denetimlerini açıklar.

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
