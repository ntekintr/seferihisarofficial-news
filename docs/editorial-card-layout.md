# Lacivert–koyu turkuaz başlık ve ayrı içerik alanları

21 Ekim 2026 kullanıcı seçimi: içerik alanı krem `#f4efe4`, başlığın ilk satırı
lacivert `#06244a`, devamı koyu turkuaz `#08717a`. Tek satırlı birden fazla
sözcüklü başlık sözcük sınırında iki renge ayrılır. Sadece başlık renklendirilir;
başlık veya açıklamadan yeni haber bilgisi türetilmez. Gövde `#18364a`, tarih
lacivert ve açıklamaya yönlendirme koyu turkuazdır. Turuncu kategori ve mevcut
özgün logo korunur. Çapraz turkuaz bant daha incedir ve yüksek çözünürlükte
çizilip küçültülerek pürüzsüz tutulur.

`editorial_render.py`, başlık, tarih, özet/etkinlik bilgileri, açıklama notu ve
alt marka bilgisini ayrı sınırlı alanlara çizer. Font ve satır sayısı yer
ayrıldıktan sonra seçilir. Her satırın gerçek mürekkep sınırı ölçülür; başka
bir satırla kesişme veya kendi alanından taşma `TextRenderError` üretir.
Desteklenmeyen karakter, kesilecek başlık veya sığmayan tarih/mekân/ücret
hazır JPEG oluşturamaz. Normal pipeline yalnız ilgili içeriği bekletir.

Gövde metni tam açıklamada kalır. Uzun haber özeti kartta kısalırsa sonuna
görünür üç nokta konur. Etkinlikte tarih ve mekân/ücret korunur; yer yetmezse
ek organizatör satırı karttan çıkarılabilir, tam açıklamada korunur. Bununla
da sığmayan temel bilgi küçük ve okunaksız yazıya dönüştürülmez. Kaynak adı ve
adresi yalnız açıklamadadır. `Detaylar açıklamada.` ilk kartın içerik metninin
hemen altındadır; sadece bu not için yeni bir slayt eklenmez.

Fotoğrafın üç denetlenmiş kırpma oranı (1080×436, 1080×506, 1080×586) değişmez.
Kaynak fotoğrafında tam çerçeve, yogada aşağı hizalama, OCR/CLIP, kaynak bağı ve
yayın öncesi gerçek JPEG/manifest denetimleri korunur. Sahneyle ilgisi olmayan
yeni fotoğraf veya yeni model çağrısı eklenmez. Günlük hava story'sinin ayrı
tasarımı ve stok 3D salyangoz sahneleri bu sürümle değiştirilmez.

`card_layout.VERSION = editorial-cream-v1`, henüz sahiplenilmemiş hazırlığın
görsel onay anahtarına ve dosya klasörüne bağlanır. Yeni dosyayı eski görsel
onayıyla yayımlamak mümkün değildir. Kalıcı veri sınırı eski `caption-note-v1`
ve yeni sürümü kabul eder; bilinmeyen sürümü reddeder. Başlamış, yayımlanmış
ve belirsiz kartlar işaretli/eski sürümlerini, eski içerik anahtarlarını,
slayt sayılarını ve medya bağlarını korur.

31 Ekim 2026 kullanıcı geri bildirimi: her kart farklı yazı boyutuyla çıkıyordu.
Başlık metnin uzunluğuna göre 76'dan 42'ye sekiz kademede seçiliyordu. Sürüm 2
(`editorial-cream-v2`) her rol için tek boyut kullanır: başlık 52, tarih 34, metin 30,
açıklama notu 26, kategori 28, marka 34/24, kullanıcı adı 23. Yalnız sığmayan başlık
44'e, sığmayan kategori 24'e iner. Bu düşüşün dışında kartlar arasında boyut farkı
olmaz. 261 gerçek kartta başlıkların yüzde 93'ü 52'de kaldı; yazıya sığmadığı için
bekleyen kart sayısı artmadı. Uzun özet kartta eskisi gibi üç noktayla kısalır.

Bulut kartları DejaVu Sans ile çizilir. Windows'ta üretilen elle kart Segoe UI ile
çıktığı için marka yazısı da farklı görünmüştü; aynı yazı tipi artık `assets/fonts`
içindedir ve sistemde DejaVu yoksa kullanılır. Hava ve eczane story'lerinin kendi
tasarımı bu kurala dahil değildir.

Testler her iki formatta gerçek yazı kutularının ayrılığını, uzun başlık/metni,
fotoğraflı etkinliği, elektrik kesintisini, tarih/mekân/ücret görünürlüğünü,
Türkçe karakterleri ve eski/yeni dondurulmuş sürümleri kapsar. Kod yeteneği,
canlı hazırlık/dağıtım ve yeni doğal Meta teslimi ayrı ayrı raporlanır.
