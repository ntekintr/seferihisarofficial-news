# Yayın öncesi görsel–içerik kontrolü

17 Ekim 2026 incelemesinde toplantının trafikle, elektrik kesintisinin boş
salonla ve su baskınının kuru yolla gösterildiği görüldü. Kategoriye uygun
istem üretmek ve OCR ile yazı aramak bu hataları engellemiyordu.

## Karar sırası

1. `visual_subject.subject` yalnız doğrulanmış etkinlik türlerini ve başlıkta
   açık yoga/çini/atölye faaliyetini fotoğraf adayı yapar. Tarihli kesintiler
   etkinlik değildir. Haber kategorileri çok geniştir: yeni haberlerde mevcut
   genel üretilmiş fotoğraflar kullanılmaz. Toplantı/sel gibi gerçek bir olayın
   doğrulanmış fotoğrafını alan bir kaynak-fotoğraf hattı henüz yoktur; bu
   haberler logolu, okunaklı bilgi kartıyla çıkar. Olay fotoğrafı uydurulmaz.
2. Mevcut OCR kontrolünden sonra, **gerçek JPEG pikselleri** yerel CLIP modeliyle
   sabit İngilizce nesne/sahne tanımlarına karşı karşılaştırılır. Kullanıcı
   başlığı modele istem olarak verilmez. Trafik, boş salon, manzara, toplantı,
   su baskını ve düz renk alternatifleri de karşılaştırmaya dahildir.
3. Kare kaynağı kabul etmek yetmez. Gönderinin 1080×436 ve story'nin 1080×506
   gerçek fotoğraf kırpmaları geçmelidir; eski 1080×586 çerçeve kontrolü de
   ihtiyatlı bir ek ret filtresi olarak sürer. Yoga kırpması alttaki
   matları korur. En az 0,24 kosinüs benzerliği ve diğer tüm sınıflardan en az
   0,015 fark gerekir. Bunlar olasılık veya doğruluk yüzdesi değildir.
   Belirsiz, ilgisiz veya çalıştırılamayan kontrol **bilgi kartına döner**.
4. Yeni kartın başlığı, metni, açıklaması, kaynak bağlantıları, revizyonu ve
   görsel bağları tek `visual_review.content` özetine bağlanır. Gerçek görsel
   SHA-256 parmak izleriyle (iki haneli baytlar `:` ile ayrılır) sürümlü bir
   medya klasörü seçilir. Mevcut sır tarayıcısı gevşetilmez. Böylece eski bir
   fotoğraf aynı URL'de dururken yeni metinle onaylanamaz.
   Fotoğrafsız takvimlerde de her kaynak öğesinin kimliği ve revizyonu ayrıca
   bağlanır. Yayın öncesi kaynak revizyonu değişmişse eski kart kullanılamaz.
5. Hem otomatik hem açık CLI yayını; Instagram gönderi/story ve Facebook
   teslimi öncesinde canlı Pages manifestini ve gerçek JPEG SHA-256 değerlerini
   GET ile karşılaştırır. Eksik/eski/erişilemeyen kanıt Meta yazımından ve
   kalıcı yayın iddiasından önce durdurulur. Yalnız HEAD 200 yeterli değildir.

Model yalnız ek bir ret filtresidir; olayın doğruluğunu, mekânı veya kişilerin
kimliğini kanıtlamaz. Sınıf benzerliği yanılabilir. Kanıtlanamayan konuyu
fotoğrafla sunmayan konu politikası bu nedenle modelden önce uygulanır.
OCR ve kaynak/tarih/geçerlilik kontrolleri ayrıca sürer.

## İşletim ve sınırlar

- Model GitHub bulut araştırmasında CPU üzerinde çalışır. Çıkarım için dış
  servis/API anahtarı ve ücretli hizmet eklenmez. Modelin sabit sürümü ilk
  kurulumda indirilir, önbelleğe alınır; ağırlığın SHA-256 değeri doğrulanır.
  Paket/model kurulamazsa araştırma bilgi kartlarıyla devam eder.
- Resmî ağırlık: `openai/clip-vit-base-patch32`, revizyon
  `3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268`. Yerel dosyalar dışında model
  yüklenmez; uzak Python kodu çalıştırılmaz; PyTorch `weights_only=True` kullanır.
  [Model kartı](https://huggingface.co/openai/clip-vit-base-patch32/blob/main/README.md)
  ve [CLIP arayüzü](https://huggingface.co/docs/transformers/model_doc/clip).
- Günlük 20/tur başına iki görsel üretim denemesi ve mevcut yayın sınırları
  korunur. Reddedilen sahne yeniden üretim döngüsüne girmez. Önbellek tekrar
  kullanımında da konu kontrolü uygulanır.
- `visual_review_missing`, `visual_review_stale`, `visual_review_unavailable`
  yayını durdurur ve mevcut operasyon kontrollerinde hata olarak görünür.
  `subject_rejected`, `subject_unavailable`, `text_only` normal araştırmanın
  görsel sayaçlarında neden fotoğraf atanmadığını gösterir.
- Yeni bilgi kartında boş resim alanı ve ikinci kategori başlığı yoktur.
  Kesinti türü doğru etiketlenir. Takvim kapağında açık tarih aralığı, etkinlik
  sayısı ve ilk üç etkinlik bulunur. Logo/renkler/şeritler korunur.
- Canlı incelemede uzun konser başlığının story'de ücret/mekânı ittiği görüldü.
  v2 sürümünde story fotoğrafı 80 piksel kısaltılır, başlık alanı sınırlandırılır;
  mekân ve ücret organizatörden önce ayrılmış alanda gösterilir. Uzun adres
  açık kısaltma işaretiyle özetlenir; tam bilgi açıklamadadır. v1 adresleri
  yeni ölçülerle üzerine yazılmaz; yeni hazırlık v2 medya sürümünü gerektirir.
- Ayrı kaynaklarda aynı haberin yüksek örtüşmeli başlıkları, toplantı
  eşanlamları ve tüm sayılarıyla karşılaştırılır. Son 72 saatte yayımlanmış,
  işlemde veya belirsiz eşleşme varsa ikinci haber bekletilir. Kaynak kayıtları
  birleştirilmez. Farklı sayılar ve açık düzeltme/güncelleme/iptal korunur.
  Bu dar kural her türlü yeniden yazımı yakalayan bir dil modeli değildir.
- Yayımlanmış/işlemde/belirsiz kayıtlar ve eski medya adresleri dondurulur.
  Önceden çıkmış hatalı gönderiler sessizce düzenlenmez veya yeniden yayımlanmaz.
  Hava story'si bu haber kontrolünden bağımsız mevcut hattında kalır.

## Doğrulama

`test_visual_gate.py` ret, eksik model, iki kırpma, eski dosya/manifest, değişen
metin, yanlış format, sınırlı indirme, Meta öncesi durdurma ve kaynaklar arası
tekrar vakalarını sınar. `test_visual_native.py` gerçek sabit CPU modeliyle
ekranlardaki yanlış sahneleri ve incelenmiş olumlu fotoğrafları sınar. Normal
unit testleri gerçek modeli taklit ederek bu testin yerine geçirilmez.
Kontrol dağıtıldı demek, yeni bir doğal yayının platformda görüldüğü anlamına
gelmez; canlı dosya doğrulaması ve Meta teslimi ayrı kanıtlardır.

Başlık, haber özeti ve gerçek font/yazı kontrolü v3 dosya sürümünde eklenmiştir:
[Yayın öncesi metin kontrolü](editorial-publication-control.md). Yukarıdaki
v2 story ölçüleri v3'te de sürer; dondurulmuş v1/v2 dosyaları değişmez.
