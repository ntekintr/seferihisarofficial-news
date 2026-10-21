# Gerçek İzmir kaynağı ve açık haber seçimi

21 Ekim 2026 kullanıcı talebiyle Gerçek İzmir, 52. etkin okuyucu olarak eklendi
(43 web/özel + 9 Instagram). Bu sayı erişim başarısı değildir. Ana sayfadaki
aynı kökenli `/haber/…/sayısal-kimlik` bağlantıları yerellik filtresiyle, turda
en fazla altı ayrıntı sayfasıyla okunur. Robots/TLS ve normal sayfa bütçesi korunur.
Mobil kullanıcı bağlantısı yerine masaüstü listesi ve makalenin kendi canonical
adresi kullanılır; mobil ve masaüstü iki bağımsız okuyucu olarak eklenmez.

ASP sayfasında yayın zamanı `t_omni_pubdate` alanındaki açık ay/gün/yıl ve
saatten Europe/Istanbul olarak alınır. Tarih-only `pub_date`, sayfa saati veya
hasat/şenlik planı yayın saati yerine geçmez. Çelişen/eksik alan haber üretmez.
`#haberdetaybaslik h2` kaynak özeti, kendi gövdesi ve fotoğraf alanı yorum ve
ilgili haberlerden ayrıdır. Konu başlıkta tanımlıysa başlık kategorisi önce
kullanılır; özetteki “pazarlanması” mandalina haberini pazar/fuar yapmaz.

Gerçek makalenin 200950 numaralı haberinde açık yayın saati 21 Ekim 09:42;
fotoğraf mandalina ağacında hasattır. Kaynak URL, başlık, tarih, kendi canonical
adresi, gövde içindeki ana fotoğraf, aynı fotoğraf kökeni ve üç gerçek kart
oranındaki yerel model kontrolü birlikte gerekir. `citrus_harvest` yalnız kaynak
fotoğrafı konusudur; bu konu ilk olarak yalnız incelenmiş Gerçek İzmir okuyucusunda
etkindir ve haber olayı gibi üretilmiş fotoğrafa izin vermez. Gelecek
hasat duyurusu bu konuya otomatik girmez. Fotoğraf eksik/reddedilmişse bilgi kartı.

## Hesap sahibinin belirli haberi istemesi

`publish.yml` manuel PUBLISH isteğinde isteğe bağlı `post_id`, yalnız tam
24 haneli parent kimliğini seçer. `cli publish --post-id …` yalnız bu parent ve
ilk eşleşen story'yi işler; başka sıradaki haberle tamamlamaz. Facebook aynı
parent'a süzülür. Açık seçim planlı saatten önce olabilir; günlük iki gönderi,
45 dakika aralık, kaynak tazeliği, 48 saat yaş, tekrar, görsel/Pages dosya kontrolü
ve kalıcı iddia sınırları aynıdır. Otomatik workflow_run bu alanı kullanamaz.
Yayımlanmış haber yeniden gönderilmez; belirsiz iddia yeniden denenmez. En fazla
bir saatlik mevcut yayımlanmış parent'ın eksik ilk story/teslimi güvenle sürer.

Hasadın aynı yerel sezon açılışı 72 saat içinde farklı başlıkla başka kaynakta
gelse de tekrar tutulur. Bu dar kural sonraki destek/alım gelişmesini otomatik
birleştirmez; kaynak kayıtları ve eski yayın SQL alanları değiştirilmez.

Canlı kaynak sağlığı, hazırlanmış kart ve Meta teslimi ayrı ayrı tarihli kanıt
ile raporlanır. Yerel test başarısı canlı paylaşım kanıtı değildir.

21 Ekim sonraki kullanıcı tercihiyle mandalina hasadı fotoğrafı diğer güvenilir
kaynaklara da aynı doğrulamalarla açıldı; ilk Gerçek İzmir teslimi değişmez.
[İlgili görsel politikası](relevant-visual-first.md) yeni kapsamı açıklar.
