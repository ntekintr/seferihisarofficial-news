import test from 'node:test';
import assert from 'node:assert/strict';
import {checkResearch,checkOperations} from './cron-worker.mjs';
const now=Date.parse('2026-10-12T10:00:00Z');
const env={CRON_DISPATCH_ENABLED:'true',GITHUB_ACTIONS_TOKEN:'PRIVATE_FAKE_TEST_VALUE'};
const state=age=>({demo:false,runs:[{finished_at:new Date(now-age*60000).toISOString()}]});
const response=data=>({ok:true,json:async()=>data});

test('disabled and fresh checks never send credential to GitHub',async()=>{
  assert.equal((await checkResearch({},()=>assert.fail('Unexpected fetch'),now)).status,'disabled');
  let calls=0;
  assert.equal((await checkResearch(env,async(url,options)=>{calls++;assert.ok(!options.headers?.Authorization);return response(state(5));},now)).status,'fresh');
  assert.equal(calls,1);
});
test('running job prevents a second dispatch',async()=>{
  let calls=0;
  const fetcher=async()=>response(++calls===1?state(60):{workflow_runs:[{head_branch:'main',status:'queued'}]});
  assert.equal((await checkResearch(env,fetcher,now)).status,'already_running');assert.equal(calls,2);
});
test('stale state dispatches only main research with secret header and no redirect',async()=>{
  const calls=[];
  const fetcher=async(url,options)=>{calls.push({url,options});return calls.length===1?response(state(60)):calls.length===2?response({workflow_runs:[]}):{status:204};};
  assert.equal((await checkResearch(env,fetcher,now)).status,'dispatched');
  assert.ok(calls[2].url.endsWith('/automation.yml/dispatches'));
  assert.deepEqual(JSON.parse(calls[2].options.body),{ref:'main'});
  assert.ok(calls.every(call=>call.options.redirect==='manual'));
  assert.ok(!calls[2].url.includes(env.GITHUB_ACTIONS_TOKEN));
});
test('demo or future state cannot dispatch',async()=>{
  for(const data of [{demo:true,runs:state(60).runs},state(-10)]){
    let calls=0;assert.equal((await checkResearch(env,async()=>{calls++;return response(data);},now)).status,'invalid_state');assert.equal(calls,1);
  }
});
test('provider failures never reveal credential or exception',async()=>{
  const result=await checkResearch(env,async()=>{throw new Error(env.GITHUB_ACTIONS_TOKEN);},now);
  assert.deepEqual(result,{status:'check_failed',stage:'panel_fetch',error_type:'Error',cause:'request_failed'});
});
test('redirects stop without following or dispatching',async()=>{
  let calls=0;
  const result=await checkResearch(env,async(url,options)=>{
    calls++;assert.equal(options.redirect,'manual');
    return calls===1?response(state(60)):{ok:false,status:302,headers:{get:()=> 'https://untrusted.invalid/'}};
  },now);
  assert.equal(result.status,'github_unreachable');assert.equal(calls,2);
});
test('healthy public state does not trigger operations or leak credentials',async()=>{
  const data={...state(5),source_health:[{status:'empty'}],publishing_enabled:false};
  let count=0;
  const result=await checkOperations(env,async(url,options)=>{count++;assert.ok(!options.headers?.Authorization);return response(data);},now);
  assert.deepEqual(result,{status:'healthy'});assert.equal(count,1);
});
test('unreachable public state uses a separate throttled observer, never a publication workflow',async()=>{
  const calls=[];
  const result=await checkOperations(env,async(url,options)=>{
    calls.push({url,options});
    return calls.length===1?{ok:false}:calls.length===2?response({workflow_runs:[]}):{status:204};
  },now);
  assert.equal(result.status,'observer_dispatched');
  assert.ok(calls[2].url.endsWith('/operations-watch.yml/dispatches'));
  assert.deepEqual(JSON.parse(calls[2].options.body),{ref:'main'});
  assert.ok(calls.every(c=>c.options.redirect==='manual'));
});
test('observer is not requeued every fifteen minutes for the same persistent fault',async()=>{
  let calls=0;
  const result=await checkOperations(env,async()=>++calls===1?response(state(120)):response({workflow_runs:[{head_branch:'main',status:'completed',created_at:new Date(now-30*60000).toISOString()}]}),now);
  assert.equal(result.status,'already_observed');assert.equal(calls,2);
});
test('a skipped watch run does not count as having observed the fault',async()=>{
  const skipped={head_branch:'main',status:'completed',conclusion:'skipped',created_at:new Date(now-5*60000).toISOString()};
  let calls=0;
  const result=await checkOperations(env,async()=>++calls===1?response(state(120)):calls===2?response({workflow_runs:[skipped]}):{status:204},now);
  assert.equal(result.status,'observer_dispatched');assert.equal(calls,3);
});
