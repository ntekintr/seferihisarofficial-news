import test from 'node:test';
import assert from 'node:assert/strict';
import {checkResearch} from './cron-worker.mjs';
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
  assert.equal(calls[2].options.redirect,'error');
  assert.ok(!calls[2].url.includes(env.GITHUB_ACTIONS_TOKEN));
});
test('demo or future state cannot dispatch',async()=>{
  for(const data of [{demo:true,runs:state(60).runs},state(-10)]){
    let calls=0;assert.equal((await checkResearch(env,async()=>{calls++;return response(data);},now)).status,'invalid_state');assert.equal(calls,1);
  }
});
test('provider failures never reveal credential or exception',async()=>{
  const result=await checkResearch(env,async()=>{throw new Error(env.GITHUB_ACTIONS_TOKEN);},now);
  assert.deepEqual(result,{status:'check_failed'});
});
