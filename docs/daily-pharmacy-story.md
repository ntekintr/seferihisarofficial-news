# Günlük nöbetçi eczane story — 22 Ekim 2026

Kullanıcı her iki Instagram hesabı için Türkiye saati 17:00'da günlük nöbetçi
eczane listesi istedi. Seferihisar ilçe kapsamıdır; Isparta yalnız merkez ve
merkez mahalleleridir. Haber/etkinlik akışındaki iki gönderi tavanı ve günlük
hava story kaydı değiştirilmez. Facebook için yeni bir eczane yayını eklenmez.

## Kaynak ve tarih

Seferihisar: İzmir Büyükşehir Belediyesi'nin açık ve anonim tarihli servisi:
https://openapi.izmir.bel.tr/api/ibb/nobetcieczaneler
Resmî API dokümanı:
https://openfiles.izmir.bel.tr/111324/docs/ibbapi-WebServisKullanimDokumani_1.0.pdf

Yalnız SEFERİHİSAR, SEFERİHİSAR-SIĞACIK BÖLGESİ ve adresi Seferihisar tarafında
açıkça Ürkmez/Bengiler/Doğanbey olan ilgili Ürkmez bölgesi satırları alınır.
Gümüldür/Menderes veya adı Seferihisar olan başka ilçedeki eczane alınmaz.
Servisin her seçili satırındaki Tarih alanı bugünün nöbet tarihi olmalıdır.
Resmî belediye sayfasıyla 22 Ekim örneğinde aynı iki kayıt gözlendi; bulunmayan
Ürkmez satırı, başka ilçeden doldurulmaz veya varmış gibi sunulmaz.

Isparta'nın ayrı kurulumu: https://www.ispartaeo.org.tr/nobetci-eczaneler
Yalnız MERKEZ başlıklı eczane blokları ve açık “gün ay yıl Bugün Nöbetçi
Eczaneler” başlığı kabul edilir. Formdaki varsayılan tarih veya sitenin güncel
üst başlığı eski bir nöbet listesini tazelemez. İlçeler merkeze dahil edilmez.

İsim, adres, varsa işletme telefonu ve nöbetle ilgili kaynak notu kayıpsızdır.
Eksik telefon uydurulmaz. Açıkça verilmeyen başlangıç/bitiş saati, “sabaha kadar
açık” veya “24 saat” iddiası eklenmez. Kart nöbet tarihini açık gösterir;
güncel listeyi otomatik paylaşmak, eczanenin o saniye açık olduğunun telefonla
teyidi değildir. Kartta “Gitmeden önce telefonla teyit edin.” bulunur.

Robots/TLS ve onaylı alan adı denetimleri sürer. Belediyenin belgelenen açık
API sunucusunda robots.txt 404 olarak gözlendiğinden yalnız bu sunucu için
mevcut allow_missing_robots seçeneği kullanılır. 403, kimlik doğrulama, sertifika
ve sunucu hatası bu istisna değildir. İzmir Eczacı Odası'nın 403 koruması aşılmaz.
Arama motoru önbelleği, üçüncü tarafın “resmî” iddiası veya eski liste yedek
olarak kullanılmaz. Isparta Oda sayfası normal robots denetimiyle okunabildi.

## Hazırlık, tasarım ve zamanlama

Normal bulut araştırması 16:00–17:59 arasında listeyi yeniler, gerçek yazı
sınırlarıyla 1080×1920 JPEG'leri üretir ve Pages'e dağıtır. Kaynak kontrolü en
fazla 90 dakika eskidir; başarısız yeni kontrol eski önizlemeyi geri çekerek
yayını engeller. En fazla 15 dakikalık aynı başarılı hazırlık tekrar okunmaz.

Seferihisar stok fonu 3D mandalina kabuklu salyangoz, lacivert/turkuaz ve
kırmızı E tabelası kullanır. Isparta açık gri/beyaz, koyu lacivert metin,
orijinal gül logosu ve küçük fuşya vurgular kullanır. Kullanıcı ilk tasarımdaki
artı işaretini ve Isparta'nın pembe/mor atmosferini reddetti; ikisi değiştirildi.
Eczane bilgileri görsel modele yazdırılmaz. Bir kez üretilmiş stok fon ve gerçek
logo depoda kalır; günlük kart kodla hazırlanır ve yeni AI görsel çağrısı yapmaz.
Bilgiler sığmazsa okunur boyutu koruyarak en fazla dört gerçek içerik kartına
bölünür. Adres, telefon veya kaynak notu kesilmez. Kaynak adresi manifesttedir;
kullanıcının mevcut tercihiyle görsel üstünde kaynak veya AI notu yoktur.

16:35 erken iş yalnız güncel/dağıtılmış kart varsa 17:00'a en fazla 25 dakika
bekler. 17:00, 17:17, 17:32, 17:47 ve güvenilir 16–17 saatindeki araştırma
tamamlanması aynı günlük yolu tetikler. Her iş mevcut şehir üretim kilidini
kullanır. 18:00 ve sonrasında telafi/tekrar paylaşımı yoktur. GitHub kuyruğu ve
Meta yanıtları nedeniyle tam dakika garantisi verilmez; hedef 17:00'dır.

## Yayın ve kanıt

pharmacy_stories tablosu her gün için bağımsız tek bir liste iddiası tutar.
İddia uzakta kalıcılaşmadan ilk Meta yazımı yapılmaz. Her kartın container/media
kimliği ayrı sırayla korunur. Kısmi/belirsiz sonuç sıfırlanmaz veya tekrar
gönderilmez. Başlamış/yayımlanmış/belirsiz liste kaynak değişse de değiştirilmez.

Yazımdan önce doğru şehir hesabı, aynı gün, seçilen API yolu, kapalı/açık yayın
kapıları, tam manifest/liste eşleşmesi ve bütün canlı JPEG'lerin gerçek SHA-256,
JPEG türü ve 1080×1920 boyutu doğrulanır. Yalnız HEAD 200 yeterli değildir.
Önceki haber/FB/hava tabloları bu yayın yolunda yazılmaz. Isparta ayrıca bağımsız
runtime JSON yayın, Meta bağlantısı ve eczane özelliği kapılarını zorunlu tutar;
Meta bağlantısı tamamlanana kadar Isparta paylaşımı kapalıdır.

API yayım yanıtı ile GET gözlemi ayrıdır. İlk üç dakikada yayılım beklenir;
aynı saatin sonraki doğal yedek işi doğru hesabın /stories alanında kaydedilen
kimlikleri GET ile kontrol edebilir. Gözlem delivery_audits tablosunda story
olarak tutulur; altı saatlik bekleme gereksiz tekrar okumayı önler. Bu gözlem
platformda kart piksellerinin doğrudan görülmesi veya tekrar yayın izni değildir.

Örnek tasarımlar PAYLAŞILMADI olarak işaretlidir. Manuel deneme paylaşımı veya
bugünün kaçmış 17:00 saatini telafi eden paylaşım yapılmaz. İlk doğal teslim
gerçek zamanında ayrıca doğrulanmadıkça özellik teslim edilmiş diye sunulmaz.

Manuel Run workflow yalnız tek bir kaynak/3D kart önizlemesidir. Bu olay yayın
işini çalıştıramaz; Meta anahtarı, durum veritabanı veya kalıcı durum dalı
kullanmaz. Önizleme bağımsız kilitlidir; üretimin ortak veritabanı kilidi
ayrılmaz. Gerçek bulut kaynak erişimi bu önizlemeyle ayrıca doğrulanabilir.
