# İşletim denetimi, teslim okuması ve yedek — 21 Ekim 2026

Kullanıcının öncelik sırası: arıza bildirimi, yayın sonrası karşılaştırma,
yedek/geri yükleme; sonra ölçüm, düzenli yerel seriler ve kaynak genişletme.

## Ayrı sağlık denetçisi

`operations-watch.yml` araştırmadan ve üretim kilidinden ayrı saatte bir çalışır.
Ana dal araştırma/yayın/hava/bağlantı işindeki başarısızlık da tetikler.
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

## Yayın sonrası GET gözlemi

Mevcut yayın ve hava işinin üretim kilidi içinde, salt GET kullanan
`delivery_audit` son iki günlük bilinen başarılı kayıtları inceler. İlk üç dakika
provider yayılımı için beklenir; aynı kayıt altı saatten önce tekrar okunmaz;
bir turda en fazla 16 GET yapılır. Üçüncü taraf video/hesap taraması eklenmez.

- Instagram gönderisi: kaydedilmiş medya ID, dondurulmuş açıklama ve makul zaman.
- Aktif Instagram story/hava: kendi hesabının story listesinde kaydedilmiş ID.
- Facebook gönderisi: kayıtlı ID, dondurulmuş açıklama ve zaman.
- Facebook story: Page anahtarıyla kayıtlı nesnenin okunabilirliği; sahibi,
  açıklaması veya gerçek görseli ayrıca doğrulanmış sayılmaz.
- 23 saati geçen story ilk kez gözlenecekse `expired_not_checked`; önceden
  görülmüş story süresi doldu diye kayıp yapılmaz.

Medya adresi, caption, ham API yanıtı ve anahtar yeni tabloya yazılmaz. En fazla
500 kontrollü gözlem `delivery_audits` içinde tutulur. Hiçbir eski yayın/teslim/
hava sütunu değiştirilmez, kayıp kayıt tekrar gönderilmez. API nesnesi gözlemi
doğrudan platform ekranı veya piksellerin incelenmesi değildir. Sadece son 24
saatteki gözlem sorunları sağlık uyarısına katılır.

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
