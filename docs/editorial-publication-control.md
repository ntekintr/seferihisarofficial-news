# Yayın öncesi başlık, metin ve yazı kontrolü

17 Ekim'deki SEHAYDER kaydı, görsel eşleşmesi kontrolünün tek başına yeterli
olmadığını gösterdi: “Böyle çocuklar hep olsun” başlığı, uzun kurum metni ve
fontun gösteremediği emojiler bilgi kartı olarak yayımlanmıştı.

## Karar sırası

- Ham kaynak kaydı ve revizyonu değiştirilmez. İlk kaynak doğrulaması ile
  haberin yayına uygunluğu ayrı kontrollerdir.
- Bilgi vermeyen övgü/uyarı başlıkları, 160 karakteri aşan veya açık kesilme
  işareti taşıyan haber başlıkları bekletilir. Tanınmayan birinci şahıs/kampanya
  dili tahminle habere çevrilmez. Yeni bir olgu veya başlık uydurulmaz.
- Kaynak gövdesindeki bağımsız, incelenmiş takip/teşekkür kapanışları ve en
  sondaki kurum+ilçe imzası temizlenir. İmza olayın yerini kanıtlamaz. Sosyal
  kaynakta başlık/gövde veya açık yer alanında bölgesel bilgi kalmıyorsa kayıt
  bekletilir. Kaynak paylaşım tarihi olayın gerçekleşme tarihi yapılmaz.
- Temiz metin en az beş kelimeyle ek bilgi taşımalıdır. Kaynağın metni yalnız
  başlığın tekrarıysa veya tanınmayan kurum dili otomatik alıntıya dönüşüyorsa
  bilgi kartı olarak onaylanmaz. Haber özeti 300 karakter içinde en fazla iki
  uygun cümle sonuna kadar alınır; kısaltma açıkça üç noktayla gösterilir.
- Haber başlığı, açıklaması ve kart özeti güncel kaynaktan türetilen taslakla
  hem hazırlıkta hem gerçek Instagram/Facebook tesliminden önce karşılaştırılır.
  Yanlış metnin JPEG özetini kaydetmek tek başına editoryal onay sayılmaz.
- Yeni v3 kartlarda dekoratif emoji ve görünmez kontrol kodları basılmaz.
  Türkçe harfler, rakamlar, tarih/saat ve para bilgisi korunur. Seçilen gerçek
  fontun eksik karakter işaretiyle aynı çizilen bir karakter varsa kart
  bekletilir; bilinmeyen bir harf tahminle değiştirilmez. Başlık ve etkinlik
  tarihi alana sığmıyorsa sessizce kesilerek yayımlanmaz.
- Bir kartın yazı sorunu diğer kaynakların araştırmasını durdurmaz. İlgili
  taslak `blocked_source` olur; yayın görseli listesi boş kalır. Panelde
  başlık/yer/metin ve çizim sorunları yalnız kontrollü neden/sayılarla görünür.

## Kapsam ve korunan kayıtlar

Bu ihtiyatlı, kurallı bir yayın filtresidir; her Türkçe metni anlayan bir
gazeteci veya kaynak olgularını bağımsız doğrulayan model değildir. Tanınmayan
bir durumu daha iyi görünmesi için tahminle yeniden yazmak yerine bekletir.
Görsel konusu, OCR, kaynak/tarih/geçerlilik ve günlük sınırlar ayrıca sürer.

`content-visual-v3` yeni dosya sürümüdür. v1/v2 adresleri yeni yazı düzeniyle
üzerine yazılmaz. Yayımlanmış, işlemde ve belirsiz iddialar; kaynak satırları,
medya kimlikleri ve önceki görseller korunur. Önceden yayımlanan sorunlu kart
sessizce düzenlenmez, silinmez veya tekrar yayımlanmaz. Hava story hattı değişmez.

`tests/fixtures/news-children-source.json` gerçek kaynak kaydının test kopyasıdır.
Bu kayıt yeni yayın için bekletilir. Yalnız başlığını değiştirmek, kurum
imzasını olay yeri yapamaz. Testte eklenen açık yer cümlesi sentetik bir
karşı örnektir; gerçek kaydın doğrulanmış yeni bilgisi sayılmaz.
