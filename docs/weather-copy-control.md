# Hava durumu metni kontrolü

18 Ekim 2026 MGM Seferihisar satırındaki gerçek ifade “Parçalı ve az bulutlu,
sabah saatlerinde puzlu” idi. Ham `condition`, sıcaklıklar ve tahmin geçerliliği
aynen korunur. Yeni tahminlerde `display_version=weather-copy-v1` belirtilir;
yalnız sunumda gözden geçirilmiş tam sözcük `puzlu` → `puslu` düzeltilir.
`buzlu`, bilinmeyen sözcükler, yağışın şiddeti ve saatleri tahminle değiştirilmez.
Bu genel bir imla veya meteoroloji doğrulama modeli değildir.

Yeni kart ve panel aynı `display_condition` değerini kullanır. Salyangoz sahnesi
bu düzeltilmiş metinden seçilir; pus bilgisi gözden kaçmaz. Metnin gerçek yazı
tipinde görüntülenmesi ve en fazla üç satıra eksiksiz sığması kontrol edilir.
Görünmez kontrol karakterleri, kesilmiş açıklama, desteklenmeyen glif veya taşan
metin yayımlanmaz. Sorunlu hava kartı bekletilir; diğer haberlerin dışa aktarımı
devam eder. Panelde kontrollü ve anlaşılır neden görünür.

Yayın öncesinde sunum sürümü, ham tahmin, paneldeki sunum metni ve yeni medya
adresi birlikte eşleşmelidir. Kontrolsüz eski hazır kart yeni sürüm diye
gönderilemez; normal sabah araştırmasında yeniden okunur. Eski yayımlanmış,
yayınlanmakta olan ve belirsiz kayıtlar dondurulur: eski medya adresi, metni ve
görseli korunur; düzeltme adına yeniden paylaşım yapılmaz.

Sürüm alanı olmayan eski hava kayıtları eski `daily-weather-snail-3d-v2`
kimliğiyle desteklenir. Yeni kartların `daily-weather-snail-3d-v3` kimliği
ayrıdır. Durum doğrulaması iki biçimi de kabul eder; bilinmeyen sürüm reddedilir.
Günlük tek story sınırı, 08:00–08:59 yayın penceresi, MGM kaynağı, sıcaklıklar,
3D salyangoz varlıkları ve erişim anahtarları bu değişiklikte değiştirilmez.
