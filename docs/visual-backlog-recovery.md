# Görsel kuyruğu ve kalıcı stok — 26 Ekim 2026

Gözlenen iki neden: Seferihisar'da aynı sabit sahne her etkinlik seansı/revizyonu
için yeniden üretiliyor, iki başarısız denemeden sonra bazı kayıtlar bekliyordu.
Isparta Bubilet afişinde görselin kendisinden önce CDN'nin bulunmayan robots.txt
dosyası 404 veriyordu. Yerel, kurallara uygun tek kontrol gerçek afişi indirdi.

## Hazırlık sırası

Kaynağa bağlı gerçek fotoğraf/afiş önce denenir. Doğrulanmış dosya yoksa aynı
konu **ve aynı sabit sahne tarifine** bağlı yerel stok denenir; sonra güncel
anahtarı hâlâ geçerli başka bir üretilmiş sahne aynı koşullarla kullanılabilir.
İkisi de yoksa mevcut üretim yolu çalışır. Görselsiz taslaklar hazırlık bütçesinde
önceliklidir; haber yayın sıralaması ve günlük paylaşım sınırları ayrıdır.

Stok dosyaları her deponun paketinde taşınır; sohbet, açık bilgisayar veya günlük
üretim kotası gerekmez. Dosya özeti ve tarif özeti kontrol edilir. Yeni yerel
stok kaydının attempts=0 olması API isteği yapılmadığını belirtir; günlük sayaç
artmaz. Eski deneme sayısı düşürülmez. Günlük 20/turda 2 üretim sınırı sürer.
Başlamış/yayımlanmış/belirsiz anahtar yeni görselle değiştirilmez. Publisher
generate=False çağrısıyla yeni stok bağlayamaz.

## Denetim ve açık sınır

Yedi stok sahne gerçek modelin üç kart kırpmasından geçer. Boş takvim, boş bilet
ve kalemden oluşan **tek** yatay kapak, 1080×436/506/586 boyutlarında görsel
olarak incelenip tam JPEG özetiyle sabitlenmiştir: sınıflandırıcı bu boş kırtasiye
nesnelerini kamu hizmeti masasıyla karıştırdığı için bu yalnız event_calendar
konusuna ait kesin dosya kabulüdür. Değişen piksel veya başka konu bu kabulü
kullanamaz. Sekiz dosyanın hepsinde normal OCR zorunludur; eşik genel olarak
düşürülmez. Yeni/bilinmeyen sahneler otomatik onaylanmış sayılmaz.

Stok görsel genel konuyu anlatır; gerçek olayın yeri, kişisi veya fotoğrafı
olduğunun kanıtı değildir. Konusu belirsiz haber rastgele görsel almaz. Böyle
taslaklar bekler; sistem için her gelecekteki içeriğin mutlaka görsel bulacağı
veya dış servislerin kesilmeyeceği garantisi verilmez.

## Afişler ve tazelik

Yalnız gözden geçirilmiş Bubilet kaynağı için cdn.bubilet.com.tr robots 404/410
yanıtı dosya yokluğu sayılır. Mevcut Disallow, 403/429/5xx, TLS, yönlendirme,
boyut ve MIME kontrolleri sürer. Tam seansın kaynak başlığı/tarihi/mekânı
doğrulanır; başka etkinlikten afiş alınmaz. Aynı gösterinin farklı seansları
aynı afişi kullanabilir; her seans için OCR ve basılı tarih/saat çatışması
denetlenir. Türü belirsiz etkinlikte yalnız başlığı eşleşmiş gerçek afiş kabul
edilir, konu tahminiyle bir salon fotoğrafı eklenmez.

Bu düzeltmeye özgü eski image_read beklemesi bir kez yenilenebilir; yeni ağ
hatası poster_delivery_v2 olarak yine bir saat bekler. Denenmeyen ikinci aday
görsel, tur bütçesi dolduğu için altı saat reddedilmiş sayılmaz. Aynı değişmemiş
kaynağa/revizyona bağlı dosya 45 dakika kullanılabilir; yayıncıdaki bir saatlik
üst sınır değişmez. Selçuk yol yenileme başlığı yol bakım konusu olarak ele
alınır; belediye RSS başlığı kategori seçiminde esas alınır.

## Doğrulama

Kota dolu/iki denemesi bitmiş kayıt, yeni koşucu, kimlik bilgisi yokluğu,
başlamış yayın anahtarları, yanlış konu, değişmiş stok, kaynak afişi önceliği,
robots reddi ve süreli tekrar davranışı test edilir. Bulut CI gerçek OCR ve
modeli ayrıca çalıştırır. Hazırlanmış kart, başarılı CI ve gerçek sosyal teslim
ayrı kanıtlardır; dağıtım ve eski SQL alanları tarihli çalışma raporuyla kontrol
edilmeden bu belge tek başına canlı başarı iddiası değildir.


Bulut OCR denemesinde Rebetiko afişinin stilize başlığı güvenilir okunamadı.
Bu afişin denetimi gevşetilmez; açık müzik türü Rebetiko için genel konser
sahnesi kullanılabilir. Atatürk'ün sevdiği şarkılar afişi normal OCR'dan geçti.


## 27 Ekim canlı son kontrolü

İlk dağıtım Seferihisar'da 26 hazır karttan 25'ine görsel bağladı. Kalan
toplantı haberi için dokuzuncu stok sahne eklendi; gerçek kaynak fotoğrafı
önceliği sürer. Isparta'daki yeni müftülük ziyareti, açık resmî muhatap
başlığıyla toplantı konusuna bağlanır. Müze/antik kent ziyareti bu kurala girmez.
Kaynak JPEG'de yön bilgisinin 0 (tanımsız) olması döndürme gerektirmez;
0/1 aynı piksel yönüyle temizlenir. Gerçek döndürme/ayna değerleri 2–8 ve
diğer geçersiz değerler reddedilmeye devam eder.

Festivalden söz eden toplantı haberinin yalnız henüz sahiplenilmemiş kartı,
başlık/açıklama/etiketleriyle yerel haber olarak hazırlanır. Kaynak kaydı,
revizyon, aynı haberin kimliği ve geçmiş SQL iddiaları değişmez.

Seferihisar canlı kıyasında 13 Ekim'den kalmış, hiç piksel içermeyen bir
başarısız önbellek satırının eski temizleme koduyla silindiği görüldü; eski
yayın satırları ve mevcut görsel pikselleri değişmedi. Yeni temizleme,
yayımlanmış/devam eden/belirsiz iddialara bağlı hazır veya başarısız anahtarları
da korur. Boş eski hata kaydı, yayımlanmış bir fotoğraf kaybı sayılmaz.
