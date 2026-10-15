# Saatli Instagram yayını

Yayın akışı, ana daldaki başarılı araştırma ve panel yayını tamamlanınca kontrol edilir. Araştırma akışı Instagram anahtarına erişmez ve paylaşım yapmaz. Ayrı yayın işi yalnız `main` kodunu çalıştırır ve `instagram-production` ortamına erişir.

Türkiye saatine göre kontrol pencereleri: **08:30, 12:30, 15:00, 18:30, 21:00**. Her pencere en fazla bir saat sürer. GitHub gecikmesi nedeniyle bunlar kesin yayın dakikası garantisi değildir; pencere kaçırılırsa eski içerikler topluca yayımlanmaz.

Başlangıç sınırı **günde en fazla iki gönderi/carousel**, her gönderi için **bir eşleşen story kartı**. Story serisinin yalnız ilk kartı otomatik gönderilir; manuel seri yayını ayrı olarak kullanılabilir. Günlük sınır Türkiye gününe göre hesabın kayıtlı başarılı/devam eden/belirsiz gönderi girişimlerini sayar. Bir gönderi ve kendi story'si aynı pencerede paylaşılabilir; farklı içeriklerin 45 dakikalık aralık kontrolü korunur.

Yayın öncesinde kaynak bir saat içinde tekrar görülmüş olmalı; hatalı kaynak, eski haber, doğrulanmamış/hassas içerik ve yayımlanmamış görsel dışarıda kalır. Gönderi ve story için kalıcı yayın iddiası Meta çağrısından önce kaydedilir. Runner yeniden başlarsa tamamlanmış gönderi tekrarlanmaz. Belirsiz gönderi/story kendiliğinden yeniden gönderilmez; insan kontrolü gerekir. Eksik story görseli sonradan doğrulanırsa, aynı pencerede yalnız eksik story tamamlanabilir.

Otomatik gönderi seçimi, zamanı gelmiş ve kaynak kontrolünden geçmiş kayıtları
kuyruğa giriş yaşından önce okuyucuya güncel faydasına göre sıralar:

1. Yaklaşan etkinlik iptali, daha önce duyurulmuş etkinliğin kaynak düzeltmesi;
   önümüzdeki 24 saatteki kesinti ve son 24 saatin ulaşım/hava/kesinti haberleri.
2. Bugün/yarınki etkinlikler ve son 24 saatin haberleri.
3. Sonraki yedi günün etkinlikleri, ardından henüz eskimemiş daha eski haberler.
4. Daha uzak etkinlikler ve son olarak haftalık/aylık takvim seçkileri.

Aynı öncelik grubunda Seferihisar ve mahalleleri önce gelir. Etkinliğin doğrulanmış
mekânı, başlıkta veya açıklamada geçen ilçe adından önce değerlendirilir; hesap
markası ve kaynak adı konum sayılmaz. Eşit yerel önemde bugün başlayan etkinlik,
güncel haber ve yarınki etkinlik sırası kullanılır; aynı türde en yeni haber veya
en yakın etkinlik tarihi öne çıkar. Aynı olgunun duyuru/hatırlatma kopyalarından
uygun hatırlatma seçilir. Farklı seans tarihleri birleştirilmez; benzer başlıklar
tek başına aynı olay sayılmaz. Aynı etkinliğin günlük tekrar engeli korunur;
kaynaktaki gerçek düzeltme ve iptal duyuruları ayrıca değerlendirilebilir.

Bu sıralama yereldir; yeni AI isteği, erişim izni veya hizmet ücreti oluşturmaz.
Yayın saatlerini, iki gönderi sınırını, kaynak tazeliğini, manuel seçim sırasını,
story eşleşmesini ve dondurulmuş yayın kayıtlarını değiştirmez.

Aktivasyon değişkenleri `META_TESTS_COMPLETED=true` ve `INSTAGRAM_PUBLISH_ENABLED=true`; her ikisi de varsayılan olarak kapalı kalır. Anahtarlar mevcut Instagram ortamındadır; başka hizmete kopyalanmaz. Ana dal kısıtı korunur. Tam otonom yayın için ortamın her çalışmada manuel reviewer istememesi gerekir; bu koruma değişikliği ayrıca kullanıcı tarafından onaylanmalıdır. Devreye alma öncesinde mevcut Meta bağlantı testi ve yayın işinin gerçek bulut sonucu kontrol edilir.

Manuel iş `PUBLISH` teyidiyle `automatic`, `feed` veya `story` modunda çalışabilir. `automatic` saat/gün sınırlarına uyar. Manuel tek içerik modu günlük otomatik hedefi aşabilir; otomatik günlük sayaç buna rağmen bu gönderileri de sayar. Aynı içerik akışının ayrı Facebook teslimi [facebook-publication.md](facebook-publication.md) içinde açıklanır. Yayın sonuçları, normal bekleme nedenleri ve günlük bağlantı testi için [operations.md](operations.md) dosyasına bakın.
