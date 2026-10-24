# Benzer yaştaki gönderiler ve düzenli yerel seçkiler

21 Ekim 2026. Eski lifetime ölçümlerinde iki günlük gönderi ile iki haftalık
gönderi aynı gruptaydı. Yeni `topic-feedback-v2` yalnız 24–30 saat ve 168–174
saat pencerelerinde alınmış gözlemleri karşılaştırır. Günlük ana ölçümün yanında,
henüz ölçülmemiş bir yayın bu pencereye girince normal araştırma ölçüm işini
en fazla saatte bir uyandırabilir. Kaçan pencere geçmişe dönük doldurulmaz.

Ham erişim, kaydetme, paylaşım ve toplam etkileşim sayıları bellekte kalır.
Kalıcı kamu durumunda en fazla 400 gözlemde yalnız mevcut kamu post kimliği,
konu, yaş grubu, tamsayı yaş, bir yüzde puanlık kaba skor sınıfı (0–50),
100 erişim eşiğinin geçilip geçilmediği ve kontrol zamanı tutulur. İlk gözlem
tekrar yazılmaz. Sayılar tekil kullanıcı gibi toplanmaz: kaydetme ve paylaşımın
yeniden ağırlıklandırıldığı bilinçli bir ilgi puanıdır. Gözlem başına gerçek
erişim ya da ham etkileşim sayısı dışa aktarılmaz.

Güncel 28 günde, aynı yaş grubunda en az 10 gönderi, en az iki konu ve her
konuda 100 erişimi geçmiş en az üç gönderi olmadan tercih üretilmez. Gruplar
birbirine eklenmez. Küçük birikimli örneklerden kazanan uydurulmaz. Day1 yeterliyse
o kullanılır; değilse bağımsız Day7 grubuna bakılır. Tercih yine kamu uyarısı,
iptal/düzeltme, konum ve zaman kurallarını geçemez.

**Reklam ayrımı:** Mevcut dört Instagram ölçüsü reklamdan arındırılmış erişimi
kanıtlamaz. Yeni Marketing API izni/anahtarı yoktur. Sonuç açıkça
`paid_and_organic_not_separated` olarak işaretlenir; organik başarı veya reklamın
nedensel etkisi diye sunulmaz. Bu sürüm reklam/organik ayrımını tamamlamış değildir.

## Düzenli yerel seriler

- Cuma 12:30 hedefli hafta sonu seçkisi, cumartesi/pazar başlayacak etkinliklerden.
- Salı 12:30 hedefli ücretsiz etkinlik seçkisi, takip eden yedi gün için ve yalnız
  kaynakta açıkça `free: true` olan etkinliklerden.

En az iki, en çok dört güncel/doğrulanmış etkinlik gerekir. İptal/erteleme,
geçmiş zaman, kaynak kontrolü, mekân, açık ücret ve görsel kapıları sürer.
Kapakta gerçekten seçilen etkinlik adları/tarihleri vardır; boş “ayrıntılar
açıklamada” slaytı eklenmez. Kaynak adı ve tam adresi açıklamanın korunmuş
son alanına ayrılır. Her ayrıntı slaytı yayın öncesinde güncel etkinlikle tekrar
eşleştirilir; ücretsizliği değişen kayıt ücretsiz seçkiye giremez.

Bu seriler 24 Ekim kullanıcı kararıyla günde üç haber gönderisi sınırını paylaşır. Kamu uyarıları ve
düzeltmeler önce gelir; dolu günlük bütçe artırılmaz. Uygun içerik veya boş
slot yoksa o hafta seri yayımlanmayabilir. Yayınlanmamış seçki hedefinden 25 saat
sonra sona erer. Başlamış/yayımlanmış/belirsiz eski kartlar değiştirilmez.
