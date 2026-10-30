# İşletim denetimi, teslim okuması ve yedek — 21 Ekim 2026

Kullanıcının öncelik sırası: arıza bildirimi, yayın sonrası karşılaştırma,
yedek/geri yükleme; sonra ölçüm, düzenli yerel seriler ve kaynak genişletme.

## Ayrı sağlık denetçisi

`operations-watch.yml` araştırmadan ve üretim kilidinden ayrı saatte bir çalışır.
Ana dal araştırma/yayın/hava/bağlantı işindeki başarısızlık da tetikler.
30 Ekim'den beri her tamamlanan ana dal araştırma turu da tetikler: GitHub saatlik
zamanlamanın çoğunu atlıyor (30 Ekim 12:45'ten sonra iki saati aşkın hiç çalışmadı),
araştırma ise Cloudflare tetiklemesiyle yaklaşık 30 dakikada bir düzenli gelir.
Denetçi yalnız okur; sorun kümesi değişmedikçe issue'ya dokunmaz. Bilinen açık:
Worker'ın "son 55 dakikada koşu var" kontrolü atlanan (`skipped`) koşuları da sayar;
yayın/hava işleri bunları sık ürettiği için araştırma tamamen durursa Worker yedek
çağrısı çıkmayabilir. Düzeltmesi Worker'ın elle yeniden dağıtılmasını gerektirir.
Cloudflare araştırma yedeğine eklenen `checkOperations` Pages erişilemiyorsa,
araştırma 90 dakikadan eskiyse, kaynakların en az yüzde 40'ı başarısız/kısmiyse,
sabah hava penceresi sonrasında teslim yoksa veya çözülmemiş teslim varsa bu
ayrı denetçiyi çağırır; saatte birden fazla çağırmaz. Worker kod değişikliğinin
gerçek dağıtımı ayrıca doğrulanmalıdır. Depoya yazılması dağıtım değildir.

Uyarı yalnız kontrollü kodlardan oluşturulur; kaynak/provider metni ve sır
taşımaz. GitHub Actions botuna ait işaretli tek işletim issue'su kullanılır,
hesap sahibi `ntekintr` atanır. Sorun kümesi değişmedikçe yeni yorum/bildirim yok;
iyileşmede aynı kayıt kapanır, yeni sorunda yeniden açılır. Sağlıklı başlangıç
gereksiz issue oluşturmaz. E-posta/push teslimi kullanıcının GitHub bildirim
ayarlarına bağlıdır. Cloudflare denetimi ayrı hizmette çalışsa da uyarının GitHub
üzerinden gitmesi, GitHub genel kesintisinde bildirim garantisi sağlamaz.

### Sessiz kaynak (30 Ekim 2026)

Bubilet 403'ü, Biletinial'ın boş dönmesi ve Ege Telgraf'ın kesilmesi ancak
denetimde fark edildi; yüzde 40 eşiği tek kaynak kaybını yakalamaz. Araştırma
dışa aktarımı artık `quiet_sources` listesini panele yazar: daha önce kayıt
vermiş, şu an `empty` veya `failed` olan ve en yeni kendi kaydı (`first_seen`)
72 saatten eski kaynaklar. `last_seen` kullanılmaz; başka kaynak aynı kaydı
yeniden bildirince de ilerler. `partial` kaynak okuma yapıyordur, sayılmaz.
Süreli inceleme isteği (`requested_until`) dışarıda kalır. Seyrek kaynak
`quiet_after_hours` ile kendi süresini alır (İzmir Kültür 720 saat). Aşılamayan
bilinen engel `quiet_acknowledged` gerekçesiyle listede kalır ama uyarı vermez
(Bubilet ve Bubilet Bademler bulut 403'ü).

Denetçi onaylanmamış kayıt varsa `source_silent` kodunu ekler ve issue'da yalnız
yapılandırma kimliğini, durumunu ve son yeni kayıt tarihini listeler; kaynak metni
taşınmaz. Liste değişirse issue güncellenir. 30 Ekim verisiyle ilk liste:
`izmir-belediye` (boş, son yeni kayıt 26 Ekim) ve `seferihisar-hem` (okunamıyor,
19 Ekim); Ege Telgraf aynı gün 72 saati doldurur.

## Yayın sonrası GET gözlemi

Mevcut yayın ve hava işinin üretim kilidi içinde, salt GET kullanan
`delivery_audit` son iki günlük bilinen başarılı kayıtları inceler. İlk üç dakika
provider yayılımı için beklenir; aynı kayıt altı saatten önce tekrar okunmaz;
bir turda en fazla 16 GET yapılır. Üçüncü taraf video/hesap taraması eklenmez.

- Instagram gönderisi: kaydedilmiş medya ID, dondurulmuş açıklama ve makul zaman.
- Aktif Instagram story/hava: kendi hesabının story listesinde kaydedilmiş ID.
- Facebook gönderisi: kayıtlı ID, dondurulmuş açıklama ve zaman.
- Facebook story: kendi Page `/stories` listesinde kaydedilmiş `post_id`,
  `published` durumu ve makul oluşturulma zamanı. Yayın yanıtındaki `post_id`
  doğrudan GET yapılabilen bir nesne ID'si kabul edilmez. İlgili liste tur
  başına bir kez okunur; başarısız okuma da önbelleğe alınır. Önceki v1'in
  `read_failed`/`object_readable` sonucu yeni yolla bir kez yenilenir;
  sonraki başarısız okumalara da altı saat bekleme uygulanır.
- 23 saati geçen story ilk kez gözlenecekse `expired_not_checked`; önceden
  görülmüş story süresi doldu diye kayıp yapılmaz.

Medya adresi, caption, ham API yanıtı ve anahtar yeni tabloya yazılmaz. En fazla
500 kontrollü gözlem `delivery_audits` içinde tutulur. Hiçbir eski yayın/teslim/
hava sütunu değiştirilmez, kayıp kayıt tekrar gönderilmez. API nesnesi gözlemi
doğrudan platform ekranı veya piksellerin incelenmesi değildir. Sadece son 24
saatteki gözlem sorunları sağlık uyarısına katılır.

21 Ekim canlı ilk v1 okumasında iki Facebook story `read_failed` verdi.
Yayın iddiaları başarılı kalmıştı; bu sonuç silinmiş paylaşım kanıtı değildi.
Meta'nın resmî SDK'sındaki [Page.get_stories](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/page.py)
ve [Stories alanları](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/stories.py)
esas alınarak v2 okuması sahip listesine taşındı. Yeni canlı GET sonucu ayrıca
doğrulanır; piksel veya platform ekranı kontrolü yapılmış sayılmaz.

## İkinci kopya ve geri yükleme

Günlük `state-backup.yml` tek değişmez automation-state SHA'sından tutarlı
SQLite kopyası alır, kamu veri sınırını ve SQLite integrity_check sonucunu
doğrular. SHA256, boyut ve tablo sayıları arşiv manifestine bağlanır. Arşiv
ayrı geçici dizinde açılarak tekrar doğrulanmadan yüklenmez. Önceki güne ait,
aynı ana dalın başarılı yedek işinin artifact'i varsa o da ayrıca geri yüklenir.
İlk gün eski artifact yokluğu başarı kanıtı gibi gösterilmez.

Yedi günlük artifact, durum dalından ayrı ikinci kopyadır; **aynı GitHub
hizmeti/hesabı üzerinde** kalır. Sağlayıcıdan bağımsız uzak yedek değildir.
48 MiB dosya/indirme sınırı ve iki beklenen arşiv üyesi sınırı vardır. Canlı
veritabanına geri yükleme, kayıt sıfırlama veya yayın denemesi yapılmaz.
