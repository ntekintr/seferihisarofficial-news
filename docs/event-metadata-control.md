# Etkinlik düzenleyicisi ve adres kontrolü

Kaynağın `organizer` alanında yalnız bilet platformunun adı bulunması, gerçek
düzenleyiciyi doğrulamaz. Bubilet, Biletix, Biletinial ve Biletino'nun gözden
geçirilmiş tam adları/alan adları düzenleyen olarak kartlara aktarılmaz.
Farklı, açıkça belirtilmiş kurum/kişi adı korunur; mekândan, eğitmenden veya
kaynak isminden yeni bir organizatör çıkarılmaz. Bir ismin platform adını
içermesi tek başına silinmesi için yeterli değildir.

Açıklamada gerçek düzenleyici bilinmiyorsa bu durum belirtilir. Bilet platformu
yalnız tam eşleşen bilinen bilet alan adından belirlenir ve ayrı satırda yazılır;
kaynak adı ve adresi korunur. Kartta doğrulanmamış düzenleyen satırı gösterilmez.

Adres temizliği yalnız sondaki yinelenen yer adlarına uygulanır: örneğin
`Urla İzmir İzmir` → `Urla İzmir`. Sokak, bina/kapı numarası, mekân adı ve farklı
ilçe/il bilgileri silinmez. Metnin içindeki benzer sözcüklerden adres tahmini
yapılmaz. Ham kaynak kaydı ve kaynak revizyonu bu sunum düzeltmesiyle değişmez;
yalnız bekleyen taslaklar normal hazırlamada yenilenir.

Eski hatalı tek etkinlik taslağı veya takvim slaydı yeni dosya özetiyle onaylanamaz.
Dışa aktarım ve gerçek yayın öncesi ortak kontrol `event_metadata_stale` sonucuyla
bekletir. Düzeltilmiş metnin görselleri Pages'e dağıtılmadan eski görsel kanıtı
yeniden kullanılamaz. Instagram gönderi/story ile Facebook teslimleri aynı
kontrolü kullanır. Durum paneli bu beklemeyi anlaşılır biçimde gösterir.

Yayımlanmış, yayınlanmakta olan ve sonucu belirsiz iddiaların metni, medyası ve
kimliği dondurulur; önceki paylaşımlar değiştirilmez veya yeniden yayımlanmaz.
Bu kontrol bilinmeyen organizatörleri internetten otomatik doğrulayan bir servis
değildir ve kaynakta açıkça adı geçen her kurumun rolünü bağımsız ispatlamaz.
