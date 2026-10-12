# Resmî çevre kaynakları ve okuyucu düzeltmeleri

12 Ekim 2026'da incelenen gerçek, kamuya açık kaynak biçimleri temel alınmıştır. Instagram yayın kapıları değiştirilmez.

| Kaynak | Okuma yolu | Canlı kontroldeki sonuç |
| --- | --- | --- |
| Seferihisar Kaymakamlığı | /haberler sayfasındaki a.news-card-horizontal; detayda h2.page-title, .icerik ve .dateandtag .card-date | Önceden 0 kayıt; yeni okuyucu 7 tarihli yerel kayıt çıkardı. Eski/incelemelik kayıtlar doğrulamada dışarıda kaldı. |
| Habertürk Özdere | Sitenin arama davranışına göre /arama/ozdere?tr=%C3%96zdere; data-newsid veya block haber kartları, sayısal haber son eki | Arama terimi korunuyor; 28 haber bağlantısı görüldü. Genel arama sonuçları başka konular içerebilir; her detay hâlâ yerellik/tarih denetiminden geçer. Dört bölge ortak detay bütçesiyle kontrolde 4 yerel kayıt, 0 uygun yeni kayıt çıktı. |
| Urla Belediyesi | Haberler.aspx ve kultur-sanat.aspx; HaberDetay bağlantıları ve takvimGrid etkinlik bağlantıları | Üç bölge/konu koşuluna uyan tarihli kayıt çıkarıldı; hepsi eskiydi. Kültür takvimi bu kontrolde boştu. |
| Güzelbahçe Belediyesi | Sitenin ilan ettiği /category/haberler/feed/ RSS adresi ve gerekli detay kontrolleri | Üç yerel kültür/etkinlik haberi çıkarıldı; hepsi eskiydi. |
| Menderes Belediyesi | Kamuya açık wp-json/wp/v2/haberler ve duyurular koleksiyonları, en fazla 12 kayıt/koleksiyon | Haber koleksiyonu boş; duyurularda 12 kayıt okundu, mevcut Özdere/konu filtresine uyan kayıt yok. Varsayılan RSS idari belgeler, haberler_96 ise bir test kaydı içerdiği için kullanılmaz. |

## Tarih ve içerik sınırları

Kaymakamlık yayın alanında gün.ay.yıl okunur. Urla yayın damgası, #printableArea gövdesinin kendi üst elemanının doğrudan metninden alınır; sayfanın yanındaki SON HABERLER tarihleri kullanılmaz. Geçersiz veya belirsiz tarih kaydı üretmez. Kaynağa özel başlık alanı yoksa başka başlık ödünç alınmaz. Urla'nın paragrafsız haber gövdesi yalnız kendi gövde alanında metne dönüştürülür.

Menderes WordPress koleksiyonunda yalnız status=publish, açık date_gmt, başlık, bağlantı ve metin bulunan kayıtlar alınır. GMT damgası Türkiye saatine çevrilir. Taslak, özel kayıt, geçersiz tarih ve genel liste hata nesnesi haber sayılmaz. İçeriğin kaynak alan adına ait oluşu ve yayın/tarih/konu kuralları sonraki doğrulamada da denetlenir.

Etkinlik tarihi yayın tarihinden çıkarılmaz. Yalnız schema.org Event veya yılıyla birlikte açıkça etiketlenmiş etkinlik tarihi takvime alınabilir. Mevcut Urla kültür sayfasında etkinlik görünmemesi, gelecekte afişteki veya açıklanmayan tarihlerin okunabildiğine ilişkin bir doğrulama değildir. Afiş OCR veya yıl tahmini eklenmedi.

Çevre yerleşimlerde dans, atölye, söyleşi, kitap tanıtımı, turnuva ve koşu da etkinlik kapsamına dahildir. Rutin esnaf/personel ziyaretleri ve kapsam dışındaki yerleşimler yine dışarıda kalır.

## Erişim

Yeni adresler aynı resmî alan adında kaldı. Urla'nın bulunmayan robots.txt dosyası, kamuya açık sayfaları incelendikten sonra yalnız 404/410 için dar kaynak istisnasına alındı. Güzelbahçe ve Menderes'in robots dosyaları okundu. Açık yasak veya 403 cevabı aşılmaz.

Aralıklı hata görülen Yeni Haber/Gündem/Habertürk için alan adı başına en fazla bir ek okuma vardır. Ağ zaman aşımı veya 500/502/503/504 yeniden denenebilir; 429 yalnız sayısal, en fazla beş saniyelik Retry-After ile denenir. İkinci hata olağan kaynak hatası olarak bildirilir. Kaynak başarısızlığındaki mevcut yayın/hatırlatma blokları korunur.

## Doğrulama

138 test geçti: yeni şablonlar, doğru tarih alanı, yan haber tarihinin reddi, arama kartı kapsamı, WordPress GMT/publish denetimi, açık etkinlik yılı, kalıcı olay takibi ve sınırlı yeniden deneme dahil. Canlı beş kaynak denemesinde erişim/ayrıştırma hatası çıkmadı; yeni paylaşılabilir içerik bulunmadı. Sonuçlar sitelerin bütün arşivleri için değil mevcut sınırlı tarama içindir.

Resmî kaynaklar: https://www.seferihisar.gov.tr/haberler ; https://www.urla.bel.tr/Haberler.aspx ; https://www.guzelbahce.bel.tr/category/haberler/ ; https://menderes.bel.tr/ . WordPress veri şeması: https://developer.wordpress.org/rest-api/reference/post-types/ .
