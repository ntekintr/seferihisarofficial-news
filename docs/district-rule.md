# İlçe kuralı: elektrik kesintisi ve tiyatro yalnız Seferihisar

22 Kasım 2026 sahip kararı: planlı elektrik kesintilerinden yalnız Seferihisar'a
ait olanlar, tiyatrolardan yalnız Seferihisar'da sahnelenenler paylaşılır. Urla,
Güzelbahçe, Menderes/Özdere ve başka ilçe ya da illerin kesinti ve tiyatroları
paylaşılmaz. Konser, festival, yol ve hava gibi diğer yakın çevre içerikleri eski
`domain.local` kuralıyla devam eder.

Kural `seferihisar/district.py` içindedir ve yalnız standart kütüphaneyi kullanır.

## Elektrik kesintisi

- GDZ kaydında ilçe alanı belirleyicidir: konum `Seferihisar · ...` ile başlamıyorsa
  kayıt `outage_outside_district` ile tutulur. Mahalle adı ilçe kanıtı değildir
  (GDZ'de Güzelbahçe'nin de bir Payamlı mahallesi vardır).
- Serbest metinli kesinti duyurusunda (Instagram, haber) başka ilçe adı geçen
  satırlar çıkarılır, Seferihisar satırları kalır. Başlık ya da tek bir satır
  Seferihisar ile başka ilçeyi birlikte anıyorsa metin güvenle bölünemez:
  `outage_mixed_districts`. Hiç Seferihisar satırı yoksa: `outage_outside_district`.

## Tiyatro

- Tiyatro kategorisi, Biletinial'ın `/tiyatro/` bölümündeki her sahne gösterisi
  (çocuk oyunu, interaktif oyun, gösteri) ve metninde tiyatro/müzikal/çocuk oyunu
  geçen etkinlikler bu kurala girer.
- Karar mekândan (konum alanı) verilir; oyun tanıtımında geçen ilçe adı karar
  vermez. Mekânda başka ilçe/il adı varsa `theatre_outside_district`, Seferihisar
  kanıtı yoksa `theatre_location_unconfirmed` (belirsiz konumda yayın yok).
- Seferihisar kanıtı: Seferihisar, Sığacık, Ürkmez, Doğanbey, Teos, Gödence,
  Ulamış, Bengiler, Kavakdere, Orhanlı, Mersin Alanı, Çolak İbrahim Bey. Başka
  yerlerde de bulunan mahalle adları (Atatürk, Cumhuriyet, Tepecik, Turgut,
  Düzce, Payamlı, Beyler…) tek başına kanıt sayılmaz. "Adnan Menderes Cad." gibi
  cadde/sokak adları ilçe sayılmaz.

## Kuyruk

Her çalışmada `schedule.prepare` hazır ve tutulmuş kartları yeniden değerlendirir.
Kural öncesinde kuyruğa girmiş başka ilçe kartları `blocked_source` olur ve
sebep kodu `withheld` tablosuna yazılır; sonraki çalışmalar onları serbest
bırakmaz. `post_reason` aynı denetimi yayın anında, Facebook aynası
`current_post` içinde tekrarlar. Haftalık/aylık takvim ve hafta sonu seçkileri
bu kayıtları hiç seçmez. Durum dosyasına elle yazılmaz.
