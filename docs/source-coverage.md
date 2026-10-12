# Kaynak kapsamı ve gerçek çalışma durumu

13 Ekim 2026 güncellemesi. Kaynak sayısı, kuruma değil ayrı okuyucu bağlantısına göre sayılır.

31 bağlantı tanımlı; 26 okuyucu etkin. Seferihisar'ın yerel haberleri ile Güzelbahçe, Urla, Yelki ve Özdere'nin etkinlikleri ve önemli kamu/hizmet duyuruları kapsamda. Belediye/kaymakamlık adı tek başına bölge dışı etkinliği yerel saydırmaz.

| Alan | Bağlı kaynaklar | Sınır / eksik |
|---|---|---|
| Yerel basın | Seferihisar Yeni Haber, Seferihisar Gündem, SeferihisarLife, Urla Ada Haber | Eski kayıtlar yeni haber gibi hazırlanmaz. Son testte Ada Haber kayıtları eskiydi. |
| Bölgesel / ulusal basın | Ege Telgraf, Haberler.com, Habertürk, DHA | İlçe ve konu filtresi var. Arama listesindeki her içerik otomatik alınmaz. |
| Belediye | Seferihisar haber + duyuru, İzmir Büyükşehir RSS, Urla haber/kültür, Güzelbahçe RSS, Menderes WordPress haber/duyuru | Menderes gerçek haber koleksiyonu boş; test koleksiyonu kullanılmıyor. |
| Kaymakamlık | Seferihisar, Urla, Menderes | Güzelbahçe canlı okuması ağ hatası verdi; bağlanmadı. |
| Eğitim / kurs | Seferihisar İlçe Millî Eğitim RSS, Atatürk Halk Eğitimi haber/duyuru | Kurumun kendi yazısı ve tarihi esas; başka kartın tarihi kullanılmaz. Etkinlik yılı/saat tahmini yok. |
| Oda / organizatör | Seferihisar Esnaf ve Sanatkârlar Odası RSS, TeosFest RSS, KültürEkoloji Derneği RSS | Akış okunabilir; son kayıtların eski olması bağlantı hatası değildir. KültürEkoloji'nin son testteki iki kaydı eski. |
| Tarihli etkinlik | İzmir Art bölgesel seans takvimi, Seferihisar Belediyesi etkinlik takvimi | İzmir Art'ta gerçek adres ve tam UTC tarihi. Belediye takviminde tam yıl/gün aralığı ve eşleşen canlı detay sayfası; açıklanmayan saat, mekân, ücret ve organizatör tahmin edilmez. |
| Günlük kamu hizmeti | ESHOT tarihli haber/duyuru, İZSU yeni adresteki tarihli kurum haberleri | Tarihsiz hat değişiklikleri, anlık su/elektrik kesintileri henüz otomatik değil. |

İncelenen diğer kaynaklar: İzmir Kültür Sanat, Bademler Sanat Köyü, Urla Ot Bayramı, Barbaros Oyuk Festivali, Urla'da Yaşam, Seferihisar Necat Hepkon Devlet Hastanesi, Rotary 2440, Teos Kültür Sanat Derneği, SEHAYDER, GDZ, AFAD, MGM, Biletix, Biletinial, Biletino ve Bubilet. Durumları ve adresleri `config/source_catalog.json` ile paneldeki Kaynaklar bölümündedir. Okunabilir bir web sitesi tek başına çalışan etkinlik okuyucusu sayılmaz.

KültürEkoloji, Seferi Sahne, Çağdaş Yaşamı Destekleme Derneği'nin Seferihisar şubesi, yerel kent konseyi, muhtarlıklar, meslek kuruluşları, spor kulüpleri ve özel salonlar kaynak ağı açısından önemlidir. Bazıları belediye/festival duyurularında bulunabilir; her biri için bağımsız güncel yayın adresi/izinli veri akışı henüz doğrulanmadı. Yerel Instagram hesapları doğrudan otomatik taranmıyor. Uygun API/izin veya organizatörün açık takvimi gerekir.

## Düzeltmeler ve doğrulama

- Açık HTTP, HTML ve XML karakter kodlamaları dikkate alınıyor; HTTP'nin varsayılan Latin-1 çözümü Türkçe UTF-8 metni bozmuyor.
- İZSU www adresi yönlendirmesi yerine incelenmiş gerçek alan adı kullanılıyor. Arşiv listesi yeni uygulamada boş iskelet döndürdüğü için gerçek haber bağlantıları bulunan ana sayfa kullanılıyor.
- ESHOT için incelenmiş robots 404/410 istisnası, açık başlık/metin/tarih okuyucusu var. 403 veya robots engeli aşılmıyor; tarihsiz duyuruya yayın tarihi uydurulmuyor.
- DHA ve İzmir Büyükşehir geçici bağlantı/DNS hatasında bir turda en fazla bir ek deneme yapıyor. Kalıcı ret veya bozuk veri otomatik onaylanmıyor.
- İzmir Art ilçe etiketi yanlış kalan gezici gösterilerde gerçek mekân adresiyle filtreleniyor. Farklı ilçedeki seans, Urla seansı gibi alınmıyor. Eksik/çelişkili tarih, saat, seans veya iptal alanında kayıt dışarıda tutuluyor.
- Her kaynak için son kontrol, çıkarılan/doğrulanan kayıt ve hata sayısı ayrı saklanıp gösteriliyor. Ham hata, anahtar ve hassas haber gövdesi sağlık kaydına eklenmiyor.

209 Python testi geçti; ek zamanlayıcının altı testi önceki sürümde doğrulandı. Belediye takvimi canlı yerel kontrolünde 15–17 Ekim Ürkmez ve 31 Ekim–1 Kasım Orhanlı festival kayıtları, eşleşen detaylarıyla bulundu. KültürEkoloji RSS okundu; eski iki kayıt yeni haber olarak reddedildi. İzmir Art'tan 14 Ekim Urla tiyatro seansı önceki denetimde bulunmuştu. Yeni sürümün bulut kontrolü birleşmeden sonra ayrıca yapılmalıdır; yerel başarı bulut başarısı diye sunulmaz.

## Şu an nasıl çalışıyor?

1. GitHub Actions, `automation.yml` zamanlamasıyla bilgisayardan bağımsız bulutta başlar.
2. Önceki veriler `automation-state` dalından alınır. İncelenmiş kaynaklar sınırlı hız/sayfa bütçesiyle okunur.
3. Yer, tarih, kaynak, tekrar ve hassas içerik kontrolü yapılır. Açıklanmayan olgu tahmin edilmez.
4. Şablonlu kaynak atıflı Türkçe açıklama hazırlanır. İsteğe bağlı Gemini sadece önem sıralaması yapar; serbest haber yeniden yazımı mevcut değildir.
5. Cloudflare Free üzerinde uygun yeni içerik için en fazla iki temsili çizim denenir. Sabit orijinal logo/şeritler gönderi ve story üzerine eklenir; çizimler tekrar kullanılır. Üretim başarısızsa markalı metin kartı hazırlanır.
6. Veri kalıcı olarak yazılır, GitHub Pages paneli ve görseller yenilenir.
7. Başarılı ana dal araştırması ve görsel dağıtımı sonrası ayrı bulut yayını tetiklenir. Saatli Instagram gönderi/story yayını etkin ve gerçek haberle doğrulandı. Aynı yeni içeriği Facebook'a aktaran hedef de etkin; ilk gerçek Facebook gönderi/story kontrolü bekliyor. İki hedef aynı araştırma ve görselleri kullanır.

Yayın aralıkları Türkiye saatiyle 08:30, 12:30, 15:00, 18:30, 21:00'dan sonraki birer saat; normal etkinlik ilk duyuru hedefi 15:00. Günlük sınır iki gönderi ve eşleşen ilk story'lerdir. Yeterli güncel içerik ve tamamlanan araştırma gereklidir; tam dakika garantisi yok. Hazır haber 48 saati aşınca eskir; bir kaynağın son görülmesi bir saatten eskiyse yayın durur. Hatırlatma ve takvim seçkileri içerik uygunsa hazırlanır.

## 7/24 kontrolünün sonucu

GitHub geçmişinde zamanlanmış #8 çalışma 04:48'de, #9 çalışma 11:05'te başlamış: 377 dakika aralık. Ayar `7,22,37,52 * * * *` olsa da tam 15 dakikada bir çalıştığı doğrulanmadı. GitHub resmi dokümanı zamanlanmış çalışmanın gecikebileceğini ve yoğunlukta düşebileceğini belirtir. Panel gecikme uyarısı verir; yeni sistem ekranı geçmişteki en uzun aralığı da gösterir.

İkinci, küçük Cloudflare Cron kontrolü `ops/cron-worker.mjs` devrede ve gerçek zamanlanmış olaylarla doğrulandı. Her 15 dakikada paneli kontrol eder. Son başarılı tur 20 dakikadan eskiyse, hâlen çalışan/yeni başlamış araştırma yoksa yalnız ana daldaki araştırma iş akışını yeniden başlatmayı dener. Yayın bayraklarını değiştirmez, Meta/AI anahtarı istemez ve GitHub kuyruk gecikmesini mutlak olarak ortadan kaldırmaz.

Kullanıcı onayıyla yalnız bu depo için **Actions read/write** ve zorunlu Metadata read anahtarı Worker secret'ına kaydedildi ve zamanlama etkinleştirildi. Anahtar 10 Ocak 2027'den önce yenilenmelidir. Mevcut yalnız Workers AI yetkili anahtar genişletilmedi.

## 13 Ekim ek kaynak denetimi

Belediyenin ana sayfasındaki FullCalendar açık `/Kurumsal/TakvimService.aspx` servisini kullanıyor. Takvim bitişi dışlayıcı olduğu için 15–18 Ekim kaydı 15–17 Ekim günlerini kapsar; 31 Ekim–2 Kasım kaydı 31 Ekim–1 Kasım günlerini kapsar. Takvimde haberler de bulunduğundan yalnız konu ve bölge filtresinden geçen etkinlikler, önümüzdeki 90 gün ve aynı başlıklı erişilebilir detay sayfası doğrulamasıyla alınır. Detay hatası kaynak sağlığına yansır. Eski kayıtlar veya listeden kaybolan duyurular otomatik güncel sayılmaz, iptal varsayılmaz.

Bademler'in örnek 25 Aralık duyurusunda yıl yok; Teos Kültür Sanat'ın düzenli etkinlik sayfası eski yıllıkları gösteriyor; SEHAYDER güncel duyurularını Facebook'a yönlendiriyor. Rotary'nin örnek Güzelbahçe konserinde görünür 20:30 ile JSON-LD UTC etiketi çelişiyor. Bu adresler otomatik etkinlik yayınına açılmadı. Kulüp adı gerçek mekân yerine kullanılmaz; kişisel irtibat/banka bilgileri takvim kartına alınmaz.

Kaynak: [FullCalendar dışlayıcı bitiş](https://fullcalendar.io/docs/event-object), [Belediye takvimi](https://seferihisar.bel.tr/), [KültürEkoloji](https://www.kulturekoloji.org/).

Kaynaklar: [GitHub zamanlama](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule), [Cloudflare Cron](https://developers.cloudflare.com/workers/configuration/cron-triggers/), [İzmir Art](https://www.izmir.art/tr/etkinlikler).
