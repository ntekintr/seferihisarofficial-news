# İlk sürüm doğrulama kaydı

10 Ekim 2026 — Python 3.12.14; yerel Chromium + Playwright; gerçek Instagram yayını kapalı.

## Otomatik doğrulama

`python -m pytest -q`: 36 test geçti (sonraki test eklemelerinde CI sonuçları esas alınır).

Kapsam: 20 gün sonraki etkinliği keşfetme ve kalıcılık, 3 gün/günlük hatırlatma tekrarları, gecikmiş zamanlama, tarih değişikliği, iptal ve seçkilerden çıkarma, kaynaklar arası tekrar, eski etkinlikler, bilinmeyen saat, RSS/Atom ve JSON-LD, açık Türkçe etkinlik tarihi, tarihsiz duyuruda tahmin etmeme, aday kaynakların otomatik onaylanmaması, yerellik, özel ağ adresi/redirect öncesi URL doğrulaması, hassas içeriğin tutulmaması, token içeren bağlantıların dışarıda tutulması, JPEG ölçüleri, takvim, kapalı Meta kontrolleri, mock gönderi/carousel/story, belirsiz yayın sonucunda yeniden göndermeme, yayın öncesi kalıcı checkpoint, ayrı Git dalından yeni runner'a durum geri yükleme ve workflow kontrolleri.

`node --check site/app.js` ve `git diff --check` başarılı.

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
