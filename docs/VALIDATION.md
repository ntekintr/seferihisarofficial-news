# İlk sürüm doğrulama kaydı

10 Ekim 2026 — Python 3.12.14; yerel Chromium + Playwright; gerçek Instagram yayını kapalı.

## Otomatik doğrulama

`python -m pytest -q`: 55 test geçti. Son güvenlik kontrolündeki ek testler kaynak kesintisi, Pages dışa aktarımı, credential engelleme ve en az yetki modelini doğrular.

Kapsam: 20 gün sonraki etkinliği keşfetme ve kalıcılık, 3 gün/günlük hatırlatma tekrarları, gecikmiş zamanlama, tarih değişikliği, iptal ve seçkilerden çıkarma, kaynaklar arası tekrar, eski etkinlikler, bilinmeyen saat, RSS/Atom ve JSON-LD, açık Türkçe etkinlik tarihi, tarihsiz duyuruda tahmin etmeme, aday kaynakların otomatik onaylanmaması, yerellik, özel ağ adresi/redirect öncesi URL doğrulaması, hassas içeriğin tutulmaması, token içeren bağlantıların dışarıda tutulması, JPEG ölçüleri, takvim, kapalı Meta kontrolleri, mock gönderi/carousel/story, belirsiz yayın sonucunda yeniden göndermeme, yayın öncesi kalıcı checkpoint, ayrı Git dalından yeni runner'a durum geri yükleme ve workflow kontrolleri.

`node --check site/app.js` ve `git diff --check` başarılı.

## PR #1 son güvenlik kontrolü

- Otomatik araştırma workflow'unda Instagram token'ı ve yayın komutu yok; `INSTAGRAM_PUBLISH_ENABLED=false`. Gerçek yayın yalnız manuel workflow, `PUBLISH` girdisi, iki aktivasyon değişkeni ve uygun hesabın token'ıyla açılabilir.
- Üretim kodu/yapılandırma/frontend/workflow dosyalarında credential kalıpları ve literal anahtar taraması geçti. Anahtarlar ortam/Secrets üzerinden alınır; testlerde yalnız sentetik değerler kullanılır.
- Pages tam dosya/alan izin listesiyle yeniden üretilir. `.env`, SQLite, log, eski özel media ve bilinmeyen alanları dışarıda tutma testleri geçti. Yapılandırılmış sentetik anahtar title/body/organizer/URL'de bulunduğunda kalıcı durum veya görsel oluşmuyor.
- SQLite ve Pages artifact'leri yüklemeden önce ayrıca denetlenir. Ayrı state writer commit öncesinde tekrar kontrol eder. Checkout token'ları kalıcı Git yapılandırmasına yazılmaz; Git alt sürecine verilen scoped token testi geçti.
- Araştırma `contents: read`; kalıcılık `contents: write`; dağıtım `contents: read` + `pages: write` + `id-token: write`. CI yalnız okuma izni kullanır. Kontrollü yayın işi yalnız kalıcı rezervasyon için `contents: write` ister. Dış Actions tam commit SHA'sına sabitlenmiştir.
- Tüm kaynaklar hata verdiğinde sıfır içerik ve sıfır AI çağrısı; eski kayıtlardan yeni duyuru/hatırlatma üretilmiyor. Eski hazır içerikler bloke oluyor. Kaynak 404 olduğunda iptal/tarih uydurulmuyor. Kurtarma sonrası yalnız güncel kayıtlardan hazırlık ve story başlatılabiliyor.
- Bir saatten eski kaynak kontrolü ve geçmiş günün kalan gün sayısını kullanan hatırlatmalar yayımlanamaz. Eski etkinlikler panelde uyarılı, ICS'de geçici olarak gösterilir.

Bu kontroller varsayılan Instagram kapalı ilk sürümün birleştirme hazırlığını değerlendirir. Canlı yayın hesabının veya gerçek kaynakların üretim doğrulaması yerine geçmez.

## Tarayıcı doğrulaması

Gerçek Chromium'da 1440 × 1080 masaüstü ve 390 × 844 mobil görünüm test edildi. Genel bakış, haber, etkinlik, içerik stüdyosu, kaynak ve durum sekmeleri; 7/30 gün filtreleri; arama, kategori ve boş sonuç; görsel indirme bağlantıları doğrulandı. JavaScript hatası yok. Mobil yatay sayfa taşması yok. Önizleme açıkça örnek veri olarak etiketli.

Önizleme verileri gerçek etkinlik veya haber değildir. Üretim veritabanından ayrıdır ve yayın komutu demoyu reddeder.

## Henüz canlı doğrulanamayanlar

- Ortam ağ politikasında Seferihisar/İzmir kurumları, bilet siteleri, Gemini ve Meta hostları izinli değil. Dolayısıyla canlı kaynakların yanıtları, robot kuralları ve güncel HTML/API formatları incelenmedi.
- Meta hesabı/token'ı verilmedi; gerçek paylaşım veya Meta hesap/izin testi yapılmadı. API çağrıları mock edildi.
- PR ana dala alınmadan zamanlanmış üretim işi ve Pages dağıtımı devreye girmez. Canlı Pages URL'si dağıtım tamamlandığında doğrulanmalıdır.
- Hassas içerik ilk sürümde tamamen bloke edilir; özel inceleme/onay arayüzü teslim kapsamına dahil değildir.
- API/Web erişimi incelenmeyen bilet, kesinti, sosyal ve medya kaynakları kapalı tutulur; bunların özel adaptörleri canlı erişimden sonra geliştirilmelidir.

Bu sınırlar nedeniyle ilk sürümün doğrulaması **örnek veri ile işleyen yazılım ve GitHub iş akışları** içindir; canlı haber akışı veya çalışan Instagram hesabı teslim edildiği iddia edilmez.
