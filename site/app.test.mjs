import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

// Read the pure label declarations without loading the browser UI or its data.
const source=readFileSync(new URL('./app.js',import.meta.url),'utf8');
const context={};
vm.runInNewContext(source.slice(0,source.indexOf('const labels =')),context);
const label=context.errorLabel;

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

test('Instagram source permissions and missing runs are distinguishable',()=>{
 assert.equal(label('instagram_permission_required'),'Meta ek okuma izni gerekli');
 assert.equal(label('instagram_manifest_missing'),'Bu turda Instagram okuma sonucu alınamadı');
 assert.equal(label('instagram_token_expired'),'Meta bağlantısının süresi dolmuş');
 assert.equal(label('instagram_permission_required access_token=PRIVATE_VALUE'),'Erişim veya ayrıştırma kontrolü gerekli');
});

