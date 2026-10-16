import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

// Read the pure label declarations without loading the browser UI or its data.
const source=readFileSync(new URL('./app.js',import.meta.url),'utf8');
const context={};
vm.runInNewContext(source.slice(0,source.indexOf('const labels =')),context);
const label=context.errorLabel;

test('daytime weather never renders null or makes up a missing temperature',()=>{
 assert.equal(context.weatherTemperatures({low:null,high:20}),'En yüksek 20°');
 assert.equal(context.weatherTemperatures({low:12,high:null}),'En düşük 12°');
 assert.equal(context.weatherTemperatures({low:0,high:20}),'En düşük 0° / En yüksek 20°');
 assert.equal(context.weatherTemperatures({low:null,high:null}),'');
});

test('weather retains distinct safe source and data failure explanations',()=>{
 assert.match(context.weatherReason('forecast_temperature_missing'),/sıcaklık yok/);
 assert.match(context.weatherReason('forecast_district_missing'),/Seferihisar/);
 assert.match(context.weatherReason('source_tls_failed'),/güvenli bağlantı/);
 for(const value of ['__proto__','toString','PRIVATE_PROVIDER_ERROR',null,{}])assert.equal(context.weatherReason(value),null);
});

test('publication waits, missing media and uncertainty have separate safe labels',()=>{
 assert.equal(context.publicationLabel('outside_window'),'Yayın saati bekleniyor');
 assert.match(context.publicationLabel('uncertain'),/tekrar gönderilmez/);
 assert.match(context.publicationLabel('media_not_deployed'),/Görsel bağlantısı/);
 assert.equal(context.publicationLabel('__proto__'),'Henüz doğrulanmadı');
 assert.equal(context.publicationLabel('PRIVATE_BODY'),'Henüz doğrulanmadı');
});

test('detail and calendar failures have Turkish labels',()=>{
 const codes=['timeout','tls_failed','connection_failed','robots_denied','response_too_large','redirect_limit','check_failed'];
 for(const code of codes){
  const text=label('detail_'+code);
  assert.equal(label('calendar_detail_'+code),text);
  assert.match(text,/sayfas|Kaynak/);
  assert.doesNotMatch(text,/detail_|calendar_/);
 }
 assert.equal(label('detail_timeout'),'Ayrıntı sayfasının yanıt süresi aşıldı');
});

test('only bounded HTTP status codes enter displayed text',()=>{
 assert.equal(label('source_http_503'),'Kaynak HTTP 503 yanıtı verdi');
 assert.equal(label('detail_http_403'),'Ayrıntı sayfası HTTP 403 yanıtı verdi');
 assert.equal(label('calendar_detail_http_429'),'Ayrıntı sayfası HTTP 429 yanıtı verdi');
 for(const code of ['source_http_650','detail_http_099','source_http_403 access_token=PRIVATE_VALUE','calendar_detail_http_PRIVATE_VALUE']){
  assert.equal(label(code),'Erişim veya ayrıştırma kontrolü gerekli');
 }
});

test('unknown values and prototype names use the safe generic fallback',()=>{
 for(const code of [undefined,null,{},'__proto__','toString','detail_toString','calendar_detail_unrecognized','api_key=PRIVATE_VALUE']){
  assert.equal(label(code),'Erişim veya ayrıştırma kontrolü gerekli');
 }
});

test('existing whole-source error labels remain available',()=>{
 assert.equal(label('source_timeout'),'Yanıt süresi aşıldı');
 assert.equal(label('source_robots_denied'),'Kaynak taramaya izin vermiyor');
});

test('DNS, hostname mismatch and partial-list errors have explicit safe labels',()=>{
 assert.match(label('source_dns_failed'),/DNS/);
 assert.match(label('source_tls_name_mismatch'),/alan adıyla eşleşmiyor/);
 assert.match(label('detail_dns_failed'),/DNS/);
 assert.equal(label('listing_http_503'),'Liste sayfası HTTP 503 yanıtı verdi');
 assert.equal(label('listing_parse_failed'),'Liste sayfasındaki veri biçimi okunamadı');
 assert.match(label('listing_tls_name_mismatch'),/^Liste sayfası/);
 assert.equal(label('listing_http_503 access_token=PRIVATE_VALUE'),'Erişim veya ayrıştırma kontrolü gerekli');
});

test('Instagram source permissions and missing runs are distinguishable',()=>{
 assert.equal(label('instagram_permission_required'),'Meta ek okuma izni gerekli');
 assert.equal(label('instagram_manifest_missing'),'Bu turda Instagram okuma sonucu alınamadı');
 assert.equal(label('instagram_token_expired'),'Meta bağlantısının süresi dolmuş');
 assert.equal(label('instagram_permission_required access_token=PRIVATE_VALUE'),'Erişim veya ayrıştırma kontrolü gerekli');
});

test('service intervals appear with local news only before their verified end',()=>{
 const outage={kind:'event',category:'outage',end:'2026-10-15T17:30:00+03:00'};
 const show={kind:'event',category:'theatre',end:'2026-10-15T20:30:00+03:00'};
 const news={kind:'news',category:'news'};
 assert.equal(context.isService(outage),true);
 assert.equal(context.isService(show),false);
 const data={news:[news],events:[outage,show]};
 assert.equal(context.displayNews(data,Date.parse('2026-10-14T16:00:00+03:00')).length,2);
 assert.equal(context.displayNews(data,Date.parse('2026-10-15T17:31:00+03:00')).length,1);
});

