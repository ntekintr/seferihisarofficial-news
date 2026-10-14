# Bulut yayın durumu ve bağlantı takibi

Araştırma işinin veya yayın işinin yeşil tamamlanması yeni içerik yayımlandığını
göstermez. Yayın komutu son 100 kontrolün saatini, modunu ve yalnız onaylı sonuç
kodlarını ayrı `publication_checks` tablosuna kaydeder. Mevcut yayın iddiaları,
görsel bağlantıları ve Facebook teslimleri bu gözlem için değiştirilmez.
Durum sonraki normal araştırma / Pages turunda panelin **Sistem** bölümüne yansır;
paneldeki özetin tarihi ayrıca gösterilir. Kontrol doğrudan Meta'daki içeriğin
ekranda görüldüğüne dair bir kanıt değildir.

Panelde son kontrol nedeni, hazır ve saati gelmiş içerik sayısı, kaynak doğrulaması
bekleyenler, açık/sonraki saat penceresi, günlük Instagram/Facebook girişimleri,
sonucu belirsiz kayıtlar ve UTC gününe bağlı görsel bütçesi gösterilir. Girişim
sayılarına başarılı, devam eden ve belirsiz kayıtlar dahildir. Görsel denemeleri
Türkiye saati 03:00'te yeni UTC gününe geçer; günde 20 / turda 2 sınırı korunur.
Bu zaman bütçeyi yeniler, bütün bekleyen görsellerin aynı anda üretileceği
anlamına gelmez. Uygun fotoğraf bulunmazsa logolu metin kartı kullanılabilir.

`outside_window`, `daily_limit`, `empty` ve paylaşım aralığı bekleme sonuçları
normal bekleme sayılır. Eksik/dağıtılmamış medya, yanlış hesap, belirsiz yayın
ve çözümlenmesi gereken iddia komutu başarısız bitirir. Yayın workflow'undaki
`always()` adımı bu sonucu ve mevcut iddiaları yine kalıcı duruma yazar. Otomatik
yeniden gönderme eklenmez; yayın pencereleri ve günlük iki gönderi sınırı değişmez.

Mevcut bağlantı testi Türkiye saati **08:10** için günlük GitHub zamanlaması
aldı. Modül/workflow değişikliği ana dala geldiğinde de bir kez çalışır. Var olan
Instagram anahtarıyla hesap kimliği ve yayın kotası, Facebook etkinse var olan
Sayfa anahtarıyla Sayfa/Instagram eşleşmesi yalnız GET ile kontrol edilir.
İzin verilmez, anahtar oluşturulmaz/uzatılmaz, hiçbir paylaşım yapılmaz.
Özet GitHub iş ekranında ve yedi günlük `meta-connection-health` artifact'inde
kalır. Bağlantı hatası işi başarısız kılar. GitHub'ın kullanıcıya e-posta/push
bildirimi göndermesi hesap bildirim tercihlerine bağlıdır; harici bildirim kanalı
eklenmedi. GitHub zamanlaması kesin dakika veya kesintisiz kontrol garantisi vermez.

Bu kontrol anahtarın **şimdi** okunabildiğini doğrular. Gelecekteki sona erme tarihi
mevcut kimlik/kota yanıtlarından çıkarılamaz; raporda `expiry: not_checked` olarak
açık kalır. Yayın yetkisinin tümünü ve gerçek gönderi/story teslimini ayrıca
doğrulamak gerekir. Başarılı okuma tek başına yeni yayın kanıtı sayılmaz.

## Kalan kapsam sınırları

- `@shgundem`: API okuması hedef hesap için kullanılamıyor; diğer sekiz hedefin
  başarısı bu hesabı çalışıyor yapmaz. Kullanıcının isteğiyle ek manuel tekrar yok.
- Güzelbahçe Kaymakamlığı: bilinen TLS alan adı uyuşmazlığı; doğrudan okuyucu bağlı
  sayılmaz ve güvenlik doğrulaması kapatılmaz. Ek manuel tekrar yapılmaz.
- Seferihisar Yeni Haber: 15 Ekim 01:53 turunda `source_robots_denied`; tarama
  kısıtı aşılmaz. Diğer yerel basın kaynakları kısmi tamamlayıcıdır.
- Yılı olmayan Bademler duyurusu tarih tahminiyle yayına alınmaz; tarihli ve
  mekânı doğrulanmış Bubilet seansları ayrı kaynaktır.
- Kaynağın okunması o tur uygun yeni içerik bulunması veya ilçenin bütün
  haberlerinin kapsanması anlamına gelmez. Instagram yalnız bağlı profesyonel
  hesapların API üzerinden erişilebilen içeriğini kapsar.
