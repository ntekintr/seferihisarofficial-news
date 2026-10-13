# Temsili çizimlerde yazı kontrolü

Üretim isteminde yazı, tarih ve logo istenmemesine rağmen görsel modeli bir
festival afişine yanlış bir yıl yazabilir. Araştırma turu, yalnızca modelin
ürettiği sade JPEG üzerinde yerel Tesseract OCR kontrolü yapar. Hesabın doğru
başlığı, kaynak tarihi, logosu ve şeritleri bu kontrolden sonra eklenir.

Yeni çizimler, hazır önbellek kayıtları ve yayımlanmış gönderilerin sabit çizim
bağlantıları aynı kontrolden geçer. Korunan hazır önbellek kayıtları her
araştırma turunda bir kez taranır; kaynak değişip yeni çizim anahtarı oluşsa
bile eski yanlış çizim denetimden kaçmaz. Yazı veya olası bir yıl algılanırsa kayıt
`failed` durumuna alınır, çizim baytları silinir ve aynı kayıt yeniden üretilmez.
Normal durum kaydı bu karantinayı sonraki bulut turlarına taşır. Gönderi ve
story kartı, doğrulanmış metni ve sabit kurumsal tasarımı kullanan görselsiz
kartla yeniden hazırlanır; bu işlem sosyal medyada tekrar paylaşım yapmaz.

OCR kullanılamazsa, Türkçe/İngilizce dil verileri eksikse veya kontrol başarısız
olursa çizim kartta kullanılmaz. Önceden hazır olan baytlar bu geçici arıza
nedeniyle silinmez. Araştırma ve tasarım denemesi iş akışları Ubuntu'nun resmî
`tesseract-ocr` ve `tesseract-ocr-tur` paketlerini kurar. Durum yazıcısı yalnızca
standart kitaplığı kullanır ve OCR çalıştırmaz.

Bu ek koruma tüm görsel hatalarını veya okunamayan yapay yazıları bulmayı
garanti etmez. Kaynak doğrulaması, temsili çizim etiketi ve güvenli metin kartı
geri dönüşü geçerliliğini korur. Cloudflare modeli, anahtarları, günlük 20 ve
tur başına 2 üretim denemesi sınırları değişmez; OCR başka bir servise istek
göndermez veya ek API kotası tüketmez.

Tesseract komut ve TSV biçimi:
https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html
