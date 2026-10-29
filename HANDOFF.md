# SeferihisarOfficial — Claude Code devir belgesi

Tarih: 29 Ekim 2026 (Europe/Istanbul). Depo: https://github.com/ntekintr/seferihisarofficial-news
Devam dalı: **`codex/claude-handoff`** (yalnız devir belgesi). Karşı proje: https://github.com/ispartaofficial/ispartaofficial-news, orada açık PR #22 / `codex/restore-frozen-visuals`.

## 29 Ekim 2026 akşam güncellemesi (Claude Code)

Bu bölüm aşağıdaki devir anı notlarından daha günceldir. Seferihisar'da kod, yapılandırma veya durum değiştirilmedi; `main` hâlâ `9296acf`. Akşam salt okunur doğrulaması, 27–28 Ekim kesintisinin gerçek kapsamı, yayın tetiklemesi iptalleri ve önbellek doluluğu [HANDOFF-EVIDENCE.md](HANDOFF-EVIDENCE.md) içindedir.

Karşı projede Isparta PR #22, #23 (12 bağlantılık okuma penceresi, iki kaynaklı yeniden görülme) ve #24 (yayıncının reklam bölümündeki makaleleri bekletme) kullanıcı onayıyla merge edildi. Bu düzeltmeler Seferihisar'a taşınmadı; Seferihisar okuyucuları farklıdır ve ayrı değerlendirme gerekir.

Açık kalanlar: görsel önbelleği saklama stratejisi (karar Aralık'tan önce), yayın tetiklemesi iptalleri (düşük öncelik), 28 Ekim hava ve 27–28 Ekim eczane boşluklarının geçmişte kaldığının kaydı.

## Mevcut durum ve amaç

Seferihisar ve yakın çevre için yerel haber, belediye/kamu, etkinlik ve hizmet duyurularını araştıran, doğrulayan ve Instagram/Facebook'a aynı içerik zincirinden yayımlayan bulut otomasyonu. Ayrı Facebook haber üreticisi yoktur: Facebook gönderi/story teslimi Instagram parent'ına bağlıdır. Onaylı S + 3D salyangoz logo, lacivert/turuncu/turkuaz şerit, krem içerik zemini, lacivert/koyu turkuaz başlık korunur. Hava story'sinde yalnız altta küçük 3D salyangoz sahnesi; günlük yeni resim üretimi yok. Eczane Seferihisar, kırmızı E tabelası.

Son main: `9296acfae3f797294fd1a6ea3b7611fe377db2c7` (PR #80). Devir başlangıcında açık PR yoktu. PR #78/#79/#80 birleşmişti; devir bunları yeniden uygulamaz. Son research/deploy run **40783698198 completed success** olarak 29 Ekim salt okunur doğrulandı. Ancak başarılı dağıtım tek başına bütün tarihsel JPEG'lerin aynı kaldığı veya platform ekranında görüldüğü anlamına gelmez; devam kanıtı aşağıdadır.

## Mimari ve entegrasyonlar

Ana paket `seferihisar/`, giriş `seferihisar.cli`; kaynaklar `config/sources.json`/source_catalog. `pipeline.py` hazırlık/Pages; `instagram.py` ve `facebook.py` teslim; `connection_health.py` GET bağlantı; `delivery_audit.py` GET teslim gözlemi; `learning.py`/learning_cohorts/factory kaynak ve kaba performans tercihleri; source_discovery kontrollü keşif. Ayrıntılı yol haritası `docs/system-handbook.md`.

Son belgelenen yapılandırma 55 okuyucu (46 web/özel, 9 Instagram); güncel gerçek sayı/sağlık config ve son rapordan alınmalı. Belediye/kaymakamlık, yerel gazeteler, İzmir Art/Bademler/Bubilet, resmî ulaşım-kesinti ve tarım/orman/sağlık kaynakları; Gerçek İzmir sonradan eklendi. Instagram okuyucuları ayrı Meta izinlerine bağlıdır. @shgundem ve Güzelbahçe Kaymakamlığı için tekrarlayan manuel denemeleri kullanıcı durdurdu. GDZ/Haberler kısmi erişimini tam sağlıklı sayma; Teos/SEHAYDER veya TLS/robots korumasını aşma.

Meta Facebook Login bağlantısı ve Page/Instagram kimlikleri Isparta Instagram Login'den farklıdır. Tokenları değiştirme; connected sonucu süresiz yetki değildir. Cloudflare Workers AI üretim ve `ops/cron-worker.mjs` mevcut araştırma için yedek tetikleyici; Pages paneli https://ntekintr.github.io/seferihisarofficial-news/ . Worker dağıtımı/secret'ı yalnız kod var diye doğrulanmış sayılmaz.

`automation.yml` UTC saatte 07/22/37/52 araştırma → persist → deploy. `publish.yml` ayrı haber teslimi; `weather-story.yml` 08:00 TR hedef, `pharmacy-story.yml` 17:00 TR; günlük GET `instagram-connection-check.yml` 08:10 TR; saatlik operations-watch; `state-backup.yml` günlük yedek. Üretim concurrency `seferihisar-production`. Bağımsız watch/backup jobs üretim kilidini değiştirme yetkisi vermez. Github cron gecikmesine karşı kapılar vardır, 7/24 garantili servis değildir.

## Son tamamlanan işler ve gerçek açık sınır

PR #72–77: relevant cover gate, kaynak fotoğrafı sırası/beklemesi, dokuz stok sahne, meeting/road subject, EXIF 0/1 ve frozen key koruması; gerçek OCR/model CI. Isparta'ya özel iki Bomba32 fotoğraf istisnasını buraya taşıma.

PR #78: 26 Ekim state `8251e562a6419bc614a29619afbbf7116bc26116` içinden 10 tarihsel illustration satırının dar onarımı (8 kayıp hazır JPEG, bir değişmiş hazır JPEG, bir piksel içermeyen eski failed satır). İlk restore cache sınırına takıldı; 40733725368 başarısız, persist/deploy yapılmadı.

PR #79: sınır içinde restore. 40781873837 restore geçti; son hazırlık doğrulamasında dağıtım engellendi. İzleyen normal prune'ın eski korunan satırları geç saydığı adet/bayt regresyonları yeniden üretildi.

PR #80: frozen-first cache bütçesi. 98 ilgili yerel test geçti; CI 40783333898 test/native başarılı; merge `9296ac...`; research/deploy 40783698198 başarılı. Bu en son sürümdür. Önceki başarısız run'ları hâlâ güncel sorun diye sunma; aynı şekilde bütün dosyaların onarıldığını ayrı kanıtsız iddia etme.

28 Ekimde yeni Antinoos/Teos arkeoloji kaydı source_binding ile bekliyordu; buluntuya ait görsel uydurma. Bugünkü pending kapsamı bu eski bulgudan çıkarılamaz. Eski gerçek teslim SQL iddiaları kullanıcıya gösterilen hazırlanmış örneklerden ayrıdır.

## Öncelikli kalanlar

1. Son main'in normal üretim durumu ve tüm tarihsel görsel/SQL kıyasını tamamla; varsa HANDOFF-EVIDENCE.md tarihli sonucu kullan. 26 Ekim bazında 54 IG/52 FB/10 hava/3 eczane; ayrıca 28 Ekim daha yeni tam donmuş satırları vardır. Bunlar bugünkü toplam değildir.
2. Aynı kapasite düzeltmeleri Isparta PR #22'de henüz canlı değildir; şehir başına ayrı test/dağıtım/SQL kanıtı gerekir.
3. Kaynak veya görsel eşleşmesi nedeniyle haklı bekleyen içerikleri hata diye zorla yayımlama. Yeni özellik ve büyüme çalışmaları ancak kullanıcıyla ayrıca planlanır.
4. Tarihsel haber/görsel arşivi büyüdükçe 80/12MiB sınırının uzun vadeli saklama stratejisi ayrıca tasarlanmalıdır; bu devir sınır artırmaz veya yayın görsellerini silmez. İlgili stok/tekrar koruması testleri kaybedilmemeli.

Reklam bütçesi/video tasarımı ve sosyal profil değişiklikleri bu kod devrinden ayrı geçmiş işlerdir. Bu belgede aktif reklam teslimi/bütçe durumu doğrulanmış değildir; önceki 2000 TL onayını yeni harcama izni sayma.

## Devir talimatı ve güvenlik sınırı

29 Ekim 2026: kullanıcı projeyi Claude Code'a devretti. Bu devir yeni özellik geliştirme veya canlıya birleştirme değildir. Çalışan özellikleri koru, projeyi sıfırdan kurma, gereksiz bağımlılık ekleme. Kullanıcının son talimatı gereği riskli canlı değişikliklerden önce onay al. Eski sohbetin sınırsız yetki ifadelerini yeni riskli işlemlere genel izin sayma.

Başlangıçta `AGENTS.md`, bu belge ve aşağıdaki ilgili alt sistem belgelerini oku. Kod, config ve tarihli kanıt; eski README varsayımlarından daha günceldir. Sırlar, tam özel loglar, ham oturumlar ve tokenlar bu dosyada yoktur. Ortam değişkeni adları değer değildir. Yeni sağlayıcı/ücret/kota/izin/token üretme; robots veya TLS engelini aşma.

## Kullanıcı tarafından kesinleştirilen ürün kuralları

- Aynı motoru kullanan iki ayrı hesap/depo vardır. Şehirler arasında logo, sır, veritabanı veya yayın kimliği kopyalanmaz. Bu bir monorepo ya da otomatik senkronize ortak paket değildir.
- Her hesapta günde en fazla 3 haber gönderisi + bunların ilk eşleşen 3 story'si. Hava ve nöbetçi eczane story'leri bu sayıya EK ve ayrı günlük iddialardır.
- Aynı gün 20:00–22:59'da aslen yayımlanan ve ilk kez o akşam bulunan yeni haber için en fazla 4. gönderi + eşleşen story mümkündür. İlk revizyon, tazelik ve diğer kapılar korunur; 23:30 sonrası telafi/ertesi güne toplu yayın yoktur. Sayı kaliteyi geçmeyen içeriği doldurma hedefi değildir.
- Hava 08:00, eczane 17:00 Türkiye saati hedeflidir; aynı saat içindeki sınırlı yedekler ve günlük tek iddia vardır. GitHub cron gecikebilir, dakikası dakikasına veya bir ay kesintisiz garanti yoktur.
- Gerçek makale/etkinliğe ait fotoğraf veya afiş önceliklidir. Yoksa denetlenmiş ilgili gerçekçi sahne/stok kullanılır. Alakasız şehir, trafik, salon fotoğrafı eklenmez. Model benzerliği gerçek kişi/yer/olay kimliğini kanıtlamaz. Gerçek olaya dair uydurma fotoğraf üretme.
- 26 Ekim görsel öncelikli kuralı eski bilgi kartı yedeği notlarını günceller: yeni haber gönderisinin doğrulanmış kapağı yoksa `awaiting_content_visual` olarak bekler. Her gelecekteki habere görsel bulunacağı garantisi yoktur.
- Logo ve marka şeritleri sabit. Kaynak adı/adresi açıklamada; kart üzerinde kaynak satırı yok. Otomatik AI notu eklenmez. Yaklaşık 5 ilgili küçük harfli hashtag; keşfet garantisi verilmez.
- “Detaylar açıklamada.” ilk kartta içerik altındadır, bunun için ikinci boş slayt yok. Başlık, gövde, tarih, mekân, ücret ayrı alanlardır; tekrar başlık, kaynak hesabının “biz” dili, bozuk emoji kutuları ve kesilmiş metin engellenir.
- Canan Tutal ile Hatha Yoga, yeni Seferihisar gönderi/story/seçkilerinden çıkarılmıştır. Geçmiş yayınlar yeniden yazılmaz.
- Haber yaşı asıl kaynak zamanından en fazla 48 saat; last_seen haberi gençleştirmez. Etkinlik yükleme tarihi etkinlik günü değildir. Geçmiş/iptal/çelişkili tarih, bilinmeyen son-gün saati ve doğrulanmamış uyarı geçerliliği bekler. Ücret/organizatör/yer tahmin edilmez.

## Mimari ve veri akışı

Kaynak tanımları → sınırlı robots/TLS uyumlu okuma → tarih/konum/kaynak doğrulama → SQLite içerik kimliği ve revizyon → editoryal seçim → gerçek kaynak fotoğrafı/uygun sahne → OCR ve konu/kırpma kontrolü → Pillow kart ve açıklama → JPEG özetiyle bağlı `visual_review` → güvenli Pages dağıtımı → yayın anında tekrar doğrulama → kalıcı Meta iddiası → API teslimi ve GET gözlemi.

`store.py` kalıcı kayıtları, `schedule.py` ve `publication_policy.py` seçim/zamanı, `timeliness.py` geçerliliği, `editorial_voice.py`/`text_quality.py` metni, `render.py`/`card_layout.py` yerleşimi, `source_photos.py` kaynak resmini, `illustrations.py`/`editorial_stock.py` üretim ve stoku, `visual_match.py`/`image_safety.py` resim kontrolünü, `visual_gate.py` gerçek dosya/manifest bağını yönetir. `security.py` kamuya çıkabilecek şema/veriyi sınırlar; bu kontrolü gevşetme.

`automation-state` dalındaki `platform.sqlite` kalıcı durumdur; Actions cache/artifact kalıcı veritabanı yerine geçmez. `state_git.py` doğrulanmış geri yükleme/kalıcılaştırmayı yapar. Aynı depo üretim işleri ortak concurrency kilidini kullanır; bütün SQLite yazıldığı için kilidi düşünmeden ayırma. Veri dalını kaynak kod dalına merge etme veya eski SQLite ile canlıyı ezme.

`posts` durumları prepared/blocked_source/expired/superseded ile published/publishing/uncertain ayrılır. Başlamış ve belirsiz iddia bütçeyi tüketir; otomatik tekrar gönderilmez. `facebook_deliveries`, `weather_stories`, `pharmacy_stories` ayrı teslim tablolarıdır. Aynı kimlik veya revizyon dışındaki kart içerik/görsel tekrarı da kontrol edilir.

Hazır kart ≠ yeşil workflow ≠ Meta'nın kalıcı API teslim kaydı ≠ doğrudan Instagram/Facebook ekranında görülmüş içerik. Her raporda hangi kanıtın mevcut olduğunu söyle. Eski bütün donmuş SQL satırlarını TÜM sütunlarla karşılaştır; yalnız ilk birkaç kayıt yeterli değildir. Meta kimlikleri, caption, payload ve medya yollarını koru. Eski URL'nin 200 dönmesi doğru piksellerin kaldığını kanıtlamaz; JPEG hash karşılaştır.

## Teknolojiler ve servisler

Python >=3.11 (bulut 3.12), SQLite, Requests, BeautifulSoup, Pillow, pytest, PyYAML; statik HTML/CSS/JS Pages paneli. OCR Tesseract (tur/eng), konu kontrolü pinned CLIP/Transformers 4.57.1, CPU Torch 2.14.1 ve model cache. Bağımlılıkların kesin sürüm ve kurulum komutlarını `pyproject.toml`/CI'dan al. Bu devir bağımlılık eklemez.

Cloudflare Workers AI Flux `@cf/black-forest-labs/flux-1-schnell` görsel üretimi; günlük/tur sınırı 20/2 korunur. Dokuz hash/tarif bağlı markasız stok sahne depoda paketlenmiştir; bilgisayar veya sohbet açık olmadan kullanılabilir. Geçersiz kekik stok resmi çıkarılmıştır. Her stok gerçek olay fotoğrafı değildir. Kaynak/başlık/tarih/seans bağı, JPEG temizleme, OCR ve görsel konu kapıları korunur. Başarısız iki deneme veya kota dolması “üretilmiş” değildir.

GitHub Actions, Pages, repository/environment Secrets ve Meta Graph API kullanılır. Cloudflare/Meta anahtar DEĞERLERİ bu dosyaya veya açık loga yazılmaz. GitHub commit kimliği, PR numarası ve kamuya açık repo URL'si sır değildir.

## Bilinen hata zinciri ve son düzeltmeler

1. Uyumsuz fotoğraflar (toplantıya trafik, sele kuru yol, kesintiye salon): kategori yerine kaynak kimliği + konu + gerçek kırpma/manifest kontrolü getirildi.
2. Eski etkinlik/uyarı ve tekrar kart: ham zaman, geçerlilik, revizyon, donmuş kart ve günlük iddia korumaları getirildi.
3. Aynı reddedilen resimlerin her turu tüketmesi: kaynak/revizyon/zamanla sınırlı bekleme, dosya hakkının yalnız gerçek dosyalara harcanması ve eksik kapak önceliği getirildi. Genel kota artırılmadı.
4. Afiş OCR/model reddi: genel eşikler düşürülmedi. Yalnız tam kimlik/piksel bağıyla incelenmiş istisna veya uygun genel konu sahnesi var. Başlık/tarih/URL/piksel değişince eski onay kullanılamaz.
5. Tarihsel resim önbelleği budanmıştı. Donmuş anahtar koruması gelecekteki silmeyi önler; zaten kaybolanı tek başına geri getirmez. `historical_visuals.py` pinned Git state snapshot SHA + SQLite SHA256 + tam satır fingerprint + değişmemiş owning post + gözlenen mevcut cache koşuluyla yalnız listelenen satırları geri getirir. Bütün veritabanını geri sarmaz; yeni/başka sahip varsa atlar; ikinci çağrı no-op.
6. Onarım 80 hazır resim/12 MiB sınırını aşabiliyordu. Yer varsa yalnız kullanılmayan/expired/superseded taslak önbelleği temizlenir; aktif taslak/yayın korunur. Yer yetmezse onarım atlanır, normal restore bozulmaz.
7. Normal prune yeni taslakları önce sayıp eski korunan resimleri sona bırakınca toplam sınır tekrar aşılabiliyordu. Son düzeltme önce donmuş resimlerin bütçesini ayırır, taslakları kalan alana alır. Adet ve bayt regresyonları önce kırıldı, düzeltmeden sonra geçti. Limit yükseltilmedi.

## Test ve güvenli devam prosedürü

İzole sanal ortamda repo kökünden `python -m pip install -e ".[test]"`, ardından `python -m pytest -q`. Görsel native testler ayrıca CI'daki Torch/Tesseract/model kurulumunu ve `RUN_VISUAL_NATIVE=true` ister; yerelde skipped olan native testi geçti sayma. Windows/Linux font farkı nedeniyle yeni yerel render hash'i eski Linux hash'iyle zorunlu aynı değildir; canlı önce/sonra pikselleri ayrı kıyaslanır.

İlk görev: mevcut branch/PR diff ve CI'ı incele; yeni kod yazmadan eksik kanıtı belirle. Canlı değişiklik onayı olmadan PR merge etme veya workflow_dispatch ile yayın başlatma. PR testleri sahte sosyal API kullanır; gerçek paylaşım kanıtı değildir. Üretim onayı sonrası normal research → persist → deploy zincirini ve eski donmuş SQL + dosyaları doğrula. Başarılı job yalnız kendi adımının kanıtıdır.

Manuel deneme/tekrar paylaşım, toplu eski içerik, yeni ücretli hizmet, yeni Meta izni, token üretimi ve güvenlik kontrolünü aşma bu devrin kapsamında değildir. Devam eden PR'ı kapatıp yeniden yazma; eski branch'leri gereksiz silme/force-push yapma. Kaynaklar geçici 403/503, TLS, robots veya API izin engeli verebilir; aynı sonuçsuz denemeleri döngüye alma.

## Başlangıçtan devre kadar birleşen PR indeksi

Bu liste GitHub merge kayıtlarından alınmıştır; her satır canlı teslim kanıtı değildir.

| PR | Çalışma | Merge (UTC) |
|---|---|---|
| [#1](https://github.com/ntekintr/seferihisarofficial-news/pull/1) | Seferihisar Official: haber, gelecek etkinlik ve güvenli yayın altyapısı | 2026-10-11T07:34:05Z |
| [#2](https://github.com/ntekintr/seferihisarofficial-news/pull/2) | Haber kaynaklarını ve çevre ilçe etkinlik kapsamını genişlet | 2026-10-11T14:04:16Z |
| [#3](https://github.com/ntekintr/seferihisarofficial-news/pull/3) | Yerel haber taramasında RSS ve kategori listelerini kullan | 2026-10-11T14:19:59Z |
| [#4](https://github.com/ntekintr/seferihisarofficial-news/pull/4) | Generate free per-news illustrations with fixed logo and durable reuse | 2026-10-12T00:56:50Z |
| [#5](https://github.com/ntekintr/seferihisarofficial-news/pull/5) | Fix municipal readers and connect three official regional sources | 2026-10-12T01:46:12Z |
| [#6](https://github.com/ntekintr/seferihisarofficial-news/pull/6) | Verify Instagram credentials from GitHub without publishing | 2026-10-12T01:56:12Z |
| [#7](https://github.com/ntekintr/seferihisarofficial-news/pull/7) | Expand local sources and expose event, reader and scheduling health | 2026-10-12T10:14:23Z |
| [#8](https://github.com/ntekintr/seferihisarofficial-news/pull/8) | Show actionable source errors without exposing provider diagnostics | 2026-10-12T10:27:56Z |
| [#9](https://github.com/ntekintr/seferihisarofficial-news/pull/9) | Fix Cloudflare backup research request handling | 2026-10-12T11:26:36Z |
| [#10](https://github.com/ntekintr/seferihisarofficial-news/pull/10) | Enable bounded automatic Instagram feed and matching story publication | 2026-10-12T18:27:42Z |
| [#11](https://github.com/ntekintr/seferihisarofficial-news/pull/11) | Prepare Facebook feed and story sharing from the existing Instagram content stream | 2026-10-12T19:25:56Z |
| [#12](https://github.com/ntekintr/seferihisarofficial-news/pull/12) | Add verified Seferihisar municipal calendar and community RSS | 2026-10-12T23:59:56Z |
| [#13](https://github.com/ntekintr/seferihisarofficial-news/pull/13) | Reject AI lettering and complete verified event cards | 2026-10-13T07:41:10Z |
| [#14](https://github.com/ntekintr/seferihisarofficial-news/pull/14) | Keep ongoing multi-day events in calendar selections | 2026-10-13T07:50:56Z |
| [#15](https://github.com/ntekintr/seferihisarofficial-news/pull/15) | Keep annual programs out of ongoing weekly selections | 2026-10-13T08:21:59Z |
| [#16](https://github.com/ntekintr/seferihisarofficial-news/pull/16) | Make theatre and event cards clear at first glance | 2026-10-13T11:44:57Z |
| [#17](https://github.com/ntekintr/seferihisarofficial-news/pull/17) | Use photographic subject scenes and lowercase contextual hashtags | 2026-10-13T12:39:14Z |
| [#18](https://github.com/ntekintr/seferihisarofficial-news/pull/18) | Smooth footer edges and remove source titles from photo scene prompts | 2026-10-13T12:56:58Z |
| [#19](https://github.com/ntekintr/seferihisarofficial-news/pull/19) | Capture bounded rejected-image evidence for OCR diagnosis | 2026-10-13T13:34:01Z |
| [#20](https://github.com/ntekintr/seferihisarofficial-news/pull/20) | Accept clean photographic textures and explain detail-source failures | 2026-10-13T17:56:01Z |
| [#21](https://github.com/ntekintr/seferihisarofficial-news/pull/21) | Reuse validated photos and retry temporary source failures once | 2026-10-13T18:25:26Z |
| [#22](https://github.com/ntekintr/seferihisarofficial-news/pull/22) | Use concise neutral course-news copy in prepared cards | 2026-10-13T18:51:26Z |
| [#23](https://github.com/ntekintr/seferihisarofficial-news/pull/23) | Block reviewed lettering and simplify festival and market scenes | 2026-10-14T00:51:49Z |
| [#24](https://github.com/ntekintr/seferihisarofficial-news/pull/24) | Read verified local Instagram sources in an isolated cloud job | 2026-10-14T02:39:09Z |
| [#25](https://github.com/ntekintr/seferihisarofficial-news/pull/25) | Expand local news and event coverage to 37 reviewed web sources | 2026-10-14T03:29:47Z |
| [#26](https://github.com/ntekintr/seferihisarofficial-news/pull/26) | Finish source notice validity and bounded official-source recovery | 2026-10-14T03:53:40Z |
| [#27](https://github.com/ntekintr/seferihisarofficial-news/pull/27) | Report unavailable Instagram target and verify local versus cloud source access | 2026-10-14T12:31:42Z |
| [#28](https://github.com/ntekintr/seferihisarofficial-news/pull/28) | Connect official outage and public notice sources with expiry and location checks | 2026-10-14T13:40:49Z |
| [#29](https://github.com/ntekintr/seferihisarofficial-news/pull/29) | Bound transient governorate connection recovery and record cloud source proof | 2026-10-14T14:01:24Z |
| [#30](https://github.com/ntekintr/seferihisarofficial-news/pull/30) | Keep source attribution in captions, remove it from all graphics | 2026-10-14T15:34:08Z |
| [#31](https://github.com/ntekintr/seferihisarofficial-news/pull/31) | Recover source health and add dated Bademler events | 2026-10-14T16:37:42Z |
| [#32](https://github.com/ntekintr/seferihisarofficial-news/pull/32) | Keep all Bademler programmes visible on repeat crawls | 2026-10-14T16:56:31Z |
| [#33](https://github.com/ntekintr/seferihisarofficial-news/pull/33) | Preserve readable lists when another source endpoint fails | 2026-10-14T20:28:53Z |
| [#34](https://github.com/ntekintr/seferihisarofficial-news/pull/34) | Improve queued content readability and activity-specific imagery | 2026-10-14T21:48:30Z |
| [#35](https://github.com/ntekintr/seferihisarofficial-news/pull/35) | Show publication wait/failure reasons and check Meta connections daily | 2026-10-14T23:22:27Z |
| [#36](https://github.com/ntekintr/seferihisarofficial-news/pull/36) | Keep yoga mats visible, trim duplicated headings, and back up morning connection checks | 2026-10-15T07:18:57Z |
| [#37](https://github.com/ntekintr/seferihisarofficial-news/pull/37) | Keep older due posts in the publication media manifest | 2026-10-15T10:53:59Z |
| [#38](https://github.com/ntekintr/seferihisarofficial-news/pull/38) | Select automatic posts by local relevance and freshness | 2026-10-15T13:11:23Z |
| [#39](https://github.com/ntekintr/seferihisarofficial-news/pull/39) | Block expired events and warnings without verified validity | 2026-10-15T15:08:19Z |
| [#40](https://github.com/ntekintr/seferihisarofficial-news/pull/40) | Hold calendar editions when a deployed slide expires before dispatch | 2026-10-15T15:18:24Z |
| [#41](https://github.com/ntekintr/seferihisarofficial-news/pull/41) | Hold number-only headlines and resolved SEHAYDER appeals | 2026-10-15T19:08:15Z |
| [#42](https://github.com/ntekintr/seferihisarofficial-news/pull/42) | Publish a daily 08:00 Seferihisar weather story with a small snail scene | 2026-10-16T00:13:51Z |
| [#43](https://github.com/ntekintr/seferihisarofficial-news/pull/43) | Sabah hava tahminindeki boş dereceyi işle ve kaynak dilini tarafsızlaştır | 2026-10-16T10:58:58Z |
| [#44](https://github.com/ntekintr/seferihisarofficial-news/pull/44) | Hava story’sindeki salyangoz sahnelerini üç boyutlu görünüme geçir | 2026-10-16T14:31:07Z |
| [#45](https://github.com/ntekintr/seferihisarofficial-news/pull/45) | Reject unrelated news images and verify the reviewed media before publication | 2026-10-17T07:02:02Z |
| [#46](https://github.com/ntekintr/seferihisarofficial-news/pull/46) | Keep event date, venue and price visible in photo stories | 2026-10-17T13:39:17Z |
| [#47](https://github.com/ntekintr/seferihisarofficial-news/pull/47) | Require edited, readable news before visual approval and publication | 2026-10-17T14:33:28Z |
| [#48](https://github.com/ntekintr/seferihisarofficial-news/pull/48) | Separate event organizers from ticket platforms and clean repeated address suffixes | 2026-10-18T10:29:54Z |
| [#49](https://github.com/ntekintr/seferihisarofficial-news/pull/49) | Correct reviewed weather spelling and hold unreadable story text | 2026-10-18T10:58:35Z |
| [#50](https://github.com/ntekintr/seferihisarofficial-news/pull/50) | Keep a ready weather job running until the 08:00 publication target | 2026-10-18T11:28:15Z |
| [#51](https://github.com/ntekintr/seferihisarofficial-news/pull/51) | Use article-bound source photos for supported news with safe information-card fallback | 2026-10-18T14:00:55Z |
| [#52](https://github.com/ntekintr/seferihisarofficial-news/pull/52) | Keep future plans and warnings out of occurrence-photo selection | 2026-10-18T14:07:31Z |
| [#53](https://github.com/ntekintr/seferihisarofficial-news/pull/53) | Verify optional Instagram source photos before news rendering | 2026-10-18T15:43:08Z |
| [#54](https://github.com/ntekintr/seferihisarofficial-news/pull/54) | Document current operation and preserve verified system knowledge | 2026-10-19T05:54:22Z |
| [#55](https://github.com/ntekintr/seferihisarofficial-news/pull/55) | Place caption details note under first-card content | 2026-10-19T06:15:44Z |
| [#56](https://github.com/ntekintr/seferihisarofficial-news/pull/56) | Apply approved snail logo to new content and web panel | 2026-10-19T18:23:05Z |
| [#57](https://github.com/ntekintr/seferihisarofficial-news/pull/57) | Complete cloud content feedback and automatic source discovery | 2026-10-20T00:27:28Z |
| [#58](https://github.com/ntekintr/seferihisarofficial-news/pull/58) | Prevent daily feedback from being dropped by production concurrency | 2026-10-20T00:32:38Z |
| [#59](https://github.com/ntekintr/seferihisarofficial-news/pull/59) | Apply approved navy–teal headlines and separate card text fields | 2026-10-20T21:21:21Z |
| [#60](https://github.com/ntekintr/seferihisarofficial-news/pull/60) | Add Gerçek İzmir and publish an explicitly selected news item safely | 2026-10-21T07:14:58Z |
| [#61](https://github.com/ntekintr/seferihisarofficial-news/pull/61) | Prefer relevant source images with event poster fact checks | 2026-10-21T08:00:14Z |
| [#62](https://github.com/ntekintr/seferihisarofficial-news/pull/62) | Monitor production independently and verify deliveries without replaying them | 2026-10-21T09:50:19Z |
| [#63](https://github.com/ntekintr/seferihisarofficial-news/pull/63) | Compare similarly aged posts and prepare source-bound local guides | 2026-10-21T10:06:33Z |
| [#64](https://github.com/ntekintr/seferihisarofficial-news/pull/64) | Match Facebook story receipts against the owning Page story list | 2026-10-21T12:09:06Z |
| [#65](https://github.com/ntekintr/seferihisarofficial-news/pull/65) | Add date-safe local agriculture, forestry and health coverage | 2026-10-21T12:14:26Z |
| [#66](https://github.com/ntekintr/seferihisarofficial-news/pull/66) | Kullanıcının mandalina yan ürün projesi haberini kontrollü olarak hazırla | 2026-10-22T08:32:43Z |
| [#68](https://github.com/ntekintr/seferihisarofficial-news/pull/68) | Her gün 17:00 için doğrulanmış nöbetçi eczane story listesi ekle | 2026-10-22T17:43:16Z |
| [#69](https://github.com/ntekintr/seferihisarofficial-news/pull/69) | Eczane API bağlantı hatasında tarihli resmî web kaynağını oku | 2026-10-22T18:00:47Z |
| [#70](https://github.com/ntekintr/seferihisarofficial-news/pull/70) | Allow three daily news pairs and block unchanged repeated cards | 2026-10-24T18:56:59Z |
| [#71](https://github.com/ntekintr/seferihisarofficial-news/pull/71) | Publish one additional fresh evening news pair without deferring to tomorrow | 2026-10-25T07:33:16Z |
| [#72](https://github.com/ntekintr/seferihisarofficial-news/pull/72) | Require a relevant cover image before new social posts | 2026-10-25T23:32:12Z |
| [#73](https://github.com/ntekintr/seferihisarofficial-news/pull/73) | Keep source-image searches moving and report visual waits correctly | 2026-10-26T00:03:47Z |
| [#74](https://github.com/ntekintr/seferihisarofficial-news/pull/74) | Let other source images progress after repeated quality rejection | 2026-10-26T04:37:02Z |
| [#75](https://github.com/ntekintr/seferihisarofficial-news/pull/75) | Recover visual backlog with verified posters and reusable reviewed scenes | 2026-10-26T18:05:43Z |
| [#76](https://github.com/ntekintr/seferihisarofficial-news/pull/76) | Complete meeting visuals and protect retained publication image bindings | 2026-10-27T09:35:20Z |
| [#77](https://github.com/ntekintr/seferihisarofficial-news/pull/77) | Run actual photo rejection regression in native CI | 2026-10-27T22:07:27Z |
| [#78](https://github.com/ntekintr/seferihisarofficial-news/pull/78) | Restore archived image rows without changing publication claims | 2026-10-28T17:13:59Z |
| [#79](https://github.com/ntekintr/seferihisarofficial-news/pull/79) | Keep archived visual recovery within existing cache limits | 2026-10-28T22:41:18Z |
| [#80](https://github.com/ntekintr/seferihisarofficial-news/pull/80) | Reserve frozen images before budgeting draft cache | 2026-10-28T22:56:12Z |

## Yerel çalışma ve kanıtların korunması

Önceki çalışma kökü `Documents/Codex/2026-10-11/referenced-chatgpt-conversation-this-is-an/`; checkout'lar `work/visual-first-20261026-seferihisar` ve `work/visual-first-20261026-isparta`. Bu yerel yollar yeni makinede bulunmayabilir. Önce doğru repo/remote/branch ve `git status` kontrolü yap.

Tarihli önceki deliller `outputs/visual-backlog-2026-10-26/` altında şehir-baseline, şehir-closure-1028 ve closure-20261029 klasörlerindedir. Tam SQLite/BLOB/ham logları GitHub'a topluca ekleme. Bu devir yalnız güvenli kod/test/belgeyi aktarır. Baz snapshot'ların kalıcı Git commit kimlikleri historical_visuals manifestindedir; yerel dosya yoksa ilgili committen salt okunur yeniden çıkarılabilir.

`work/verify_backlog_release_20261026.py` ana dal/durum/Pages ve bütün eski SQL alanları ile etkilenen JPEG hash kıyasını yapar. `work/verify_operational_publication_state.py` ve `work/verify_operational_release.py` önceki yardımcılar; repo kökü/şema varsayımları var, kör çalıştırma. Bunlar repo dışı yardımcıdır; bu dosya bunların temiz clone'da mevcut olduğunu vaat etmez. Gerekirse aynı dar salt okunur kıyası repo kodunu kullanarak yeniden yap.

Başlangıç komutları (hesap yetkisini normal güvenli yöntemle sağla, tokenı komut satırına yazma):

```sh
git fetch origin main automation-state
git status --short
git log -5 --oneline
python -m pip install -e ".[test]"
python -m pytest -q
```

Devir branch'i ve ana dal farklıdır. Önce devir branch'ini incele; canlıya geçiş için kullanıcı onayı, yeni head CI ve normal dağıtım kanıtı gerekir. Bu belge eski sohbet içindeki tüm sözlü başarı iddialarını otomatik doğrulanmış saymaz.

## Devir anındaki ek kanıt

[HANDOFF-EVIDENCE.md](HANDOFF-EVIDENCE.md), bu devir sırasında alınmış salt okunur durum/dağıtım sonucudur. Seferihisar arşiv JPEG ve SQL kıyası geçti; Isparta PR #22 henüz canlı değildir.
