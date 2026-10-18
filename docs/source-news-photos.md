# Habere bağlı gerçek kaynak fotoğrafları

Araştırma, etkin ve güvenilir olarak zaten tanımlanmış `html`/`rss` web haber
kaynaklarında açık fotoğraf adayını değerlendirir. İlk kapalı konu kümesi
toplantı/muhtar buluşması, trafik ve su baskınıdır. Konu yalnız kaynak başlığında
açıkça varsa seçilir; genel kategori veya görsel benzerliği olayın kanıtı sayılmaz.
Diğer haberlerde mevcut logolu bilgi kartı kullanılır. Etkinliklerin denetlenen
görsel akışı ve bağımsız günlük hava story'si kendi kurallarını korur.

Kaynak metni değişmez. Ayrı fotoğraf kanıtı, haber kimliği/sürümü, aynı kaynağın
haber adresi, fotoğraf adresi, kaynak başlığı/yayım tarihi, kontrol zamanı, konu ve
temiz JPEG parmak izini içerir. Fotoğraf bulunmuş olması haberin güncellik veya
editoryal denetimini geçmesini sağlamaz.

Sayfanın URL'si, yapılandırılmış/görünür başlığı ve açık yayım tarihi ilgili
kayıtla eşleşmelidir. Fotoğraf aynı makalenin içinde olmalıdır; OpenGraph resmi
bu kümeden seçilir. WordPress'in aynı dosyaya ait boyut eki taşıyan ana fotoğrafı
da tanınır. İlgili haber bağlantıları, site logosu, avatar, reklam, arşiv/temsili
olarak etiketlenmiş ve belirsiz çoklu adaylar kullanılmaz. Sadece metadata'daki
bir resim adresi yeterli değildir. Fotoğraf haberle aynı onaylı sunucudadır;
haricî CDN veya imzalı sosyal medya bağlantısı otomatik olarak onaylanmaz.
Ayrı haber kayıtlarında daha önce görülen aynı fotoğraf adresi/JPEG de otomatik
olarak yeni olayın fotoğrafı sayılmaz; bilgi kartına dönülür.

Mevcut robots, TLS, onaylı sunucu ve genel DNS denetimleri korunur. Bir turda
en fazla iki haber için ek fotoğraf araştırması yapılır. Fotoğraf isteğinde
yönlendirme veya yeniden deneme yoktur. HTML/fotoğraf yanıtları 2 MB ile sınırlı;
JPEG/PNG/WebP, tek kare, en fazla 4 milyon piksel ve en az 640×300 boyut gerekir.
Portre/afiş biçimleri bu ilk sürüme dahil değildir. Metadata temizlenerek en fazla
768 piksel JPEG oluşturulur. Yerel sabit CLIP modeli üç gerçek yayın yerleşiminde
konu eşleşmesini kontrol eder; model yoksa, kararsızsa veya eşleşmezse bilgi kartı
kullanılır. Eşikler eski hatalı örnekleri geçirmek için gevşetilmez. Model skoru
belirli kişiyi, mekânı veya olayın gerçekliğini kanıtlamaz; makale bağlantısı ve
görsel ret denetimi birlikte kullanılır.

Gerçek kaynak fotoğrafının tamamı lacivert zemine oranı korunarak yerleştirilir;
geniş karta uydurmak için yüzler veya önemli nesneler kesilmez. Logo, şeritler ve
metin düzeni korunur. Kaynak adı/adresi açıklamadadır; görsele yeni kaynak/AI notu
eklenmez. Yeni fotoğraf alımı görsel üretim isteği veya yeni Meta izni gerektirmez.
Mevcut Instagram kaynak manifesti sadece metin içerir; Instagram haberlerinde
görüntü kazınmaz veya oturum açma engeli aşılmaz, uygun doğrulanmış fotoğraf yoksa
bilgi kartı kullanılır. Bu değişiklik Instagram kaynaklarının tüm medyasını alma
özelliği olarak sunulmaz.

Fotoğraf kanıtı en fazla 15 dakika yeniden kullanılır; yeni kontrol ayrı anahtar
alır. Yayımlanmış/başlamış/belirsiz gönderinin kanıtı ve JPEG'i değişmez. Kalıcı
cache en fazla 80 fotoğraf/12 MB; yalnız hiçbir gönderiye bağlı olmayan kayıtlar
temizlenir. Donmuş kayıtlar limiti doldurursa eski fotoğraflar silinmez, yeni
fotoğraf yerine bilgi kartı kullanılır. Fotoğrafın anahtarı içerik/görsel sürümü
ve dağıtılmış JPEG parmak izlerine bağlanır. Yayıncı yeni kaynak isteği yapmaz;
Meta çağrısından önce kayıt/sürüm, fotoğraf kanıtı, bir saatlik tazelik, canlı
manifest ve gerçek JPEG byte eşleşmesi yeniden denetlenir. Normal hazırlık bu
bağlantıyı kaybetmez. Haber, ilk eşleşen story ve Facebook aynı kanıtı kullanır.
