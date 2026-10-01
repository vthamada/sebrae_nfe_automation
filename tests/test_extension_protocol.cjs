const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const P = require('../extension/protocol.js');

async function plan() {
  const p = {schema_version:1,reference:'TESTE',issuer_document:'11222333000181',
    portal_origin:'https://11222333000181.emissornfe.sebrae.com.br',customer:{document:'52998224725',name:'CLIENTE TESTE'},
    issue_date:'2026-10-01',delivery_date:'2026-10-01',operation:'Venda Dentro do Estado',cfop:'5102',presence:'1 - Operação presencial',
    payment:'PIX',freight_mode:'Sem Ocorrência de Transporte',freight_cents:0,items:[{portal_code:'TESTE',description:'PRODUTO TESTE',unit:'UN',
      quantity_milli:2000,unit_price_cents:1250,discount_cents:0,total_cents:2500}],total_cents:2500,notes:'',mode:'DRAFT_ONLY'};
  p.request_hash = await P.digest(p); return p;
}
test('minimal permissions, no remote code or host grants',()=>{
  const m=JSON.parse(fs.readFileSync('extension/manifest.json','utf8'));
  assert.deepEqual(m.permissions,['activeTab','scripting','storage']);
  assert.equal(m.host_permissions,undefined); assert.equal(m.externally_connectable,undefined);
});
test('exact canonical UTF-8 and monetary parsing',async()=>{
  assert.equal(P.canonical({b:1,a:'ação'}),'{"a":"ação","b":1}');
  assert.equal(P.cents('R$ 1.392 ,60'),139260); assert.equal(P.money(2990),'29,90');
  assert.throws(()=>P.cents('29.90')); assert.throws(()=>P.cents('-0,01'));
  assert.equal((await P.validate(await plan())).mode,'DRAFT_ONLY');
});
test('recomputed hash does not authorize forbidden mode, documents or totals',async()=>{
  for(const changes of [{mode:'EMIT'},{total_cents:2499},{issuer_document:'00000000000000'},{presence:''},{issue_date:'2026-02-30'},{extra:1}]) {
    const p={...await plan(),...changes}; delete p.request_hash; p.request_hash=await P.digest(p);
    await assert.rejects(P.validate(p));
  }
});
test('same-origin issuer boundary',async()=>{
  const p=await plan(); P.portal(`${p.portal_origin}/index-sebrae.html#/invoice/new`,p);
  for(const url of ['http://11222333000181.emissornfe.sebrae.com.br/index-sebrae.html',`${p.portal_origin}.evil.com/index-sebrae.html`,`${p.portal_origin}/other`,`${p.portal_origin}/index-sebrae.html?token=secret`]) assert.throws(()=>P.portal(url,p));
});

function worker() {
  const storage={}, listeners={}, operations=[], updated=new Set();
  let failAt=null, pendingResolve=null;
  const chrome={runtime:{id:'test',getURL:p=>'chrome-extension://test/'+p,onMessage:{addListener:fn=>listeners.message=fn}},
    action:{onClicked:{addListener:fn=>listeners.action=fn}}, tabs:{get:async id=>({id,url:'https://11222333000181.emissornfe.sebrae.com.br/index-sebrae.html#/invoice/new'}),create:async()=>{},
      onUpdated:{addListener:fn=>updated.add(fn),removeListener:fn=>updated.delete(fn)},reload:async id=>{for(const fn of updated) fn(id,{status:'complete'});}},
    storage:{local:{get:async k=>({[k]:storage[k]&&structuredClone(storage[k])}),set:async obj=>Object.assign(storage,structuredClone(obj))}},
    scripting:{executeScript:async arg=>{
      if(arg.files) return [];
      const op=arg.args[0]; operations.push(op);
      if(op===failAt) throw new Error('simulated failure');
      if(pendingResolve && op==='FILL') await new Promise(resolve=>pendingResolve.resolve=resolve);
      return [{result:['SAVE_BASE','RECHECK'].includes(op)?{portal_id:'123',portal_url:'https://11222333000181.emissornfe.sebrae.com.br/index-sebrae.html#/invoice/detail/123'}:{status:'CHECKED',issued:false}}];
    }}};
  vm.runInNewContext(fs.readFileSync('extension/background.js','utf8'),{chrome,SebraeRpaProtocol:P,importScripts:()=>{},URL,Date,Error,setTimeout,clearTimeout});
  const sender={id:'test',url:'chrome-extension://test/panel.html?target=1',tab:{url:'chrome-extension://test/panel.html?target=1'}};
  const request=message=>new Promise(resolve=>{if(!listeners.message(message,sender,resolve)) resolve(null);});
  return {storage,operations,request,setFailure:op=>failAt=op,pause:()=>pendingResolve={},unpause:()=>pendingResolve.resolve()};
}
test('journal prevents repetition, reference collision and manual-stock changes',async()=>{
  const w=worker(), p=await plan();
  assert.equal((await w.request({action:'FILL',plan:p,tabId:1})).result.status,'FILLED');
  assert.equal((await w.request({action:'FILL',plan:p,tabId:1})).ok,false);
  const changed=structuredClone(p);changed.notes='outro';delete changed.request_hash;changed.request_hash=await P.digest(changed);
  assert.equal((await w.request({action:'FILL',plan:changed,tabId:1})).ok,false);
  const r=await w.request({action:'SAVE',plan:p,tabId:1});
  assert.equal(r.result.status,'SAVED_DRAFT'); assert.equal(r.result.issued,false);
  assert.equal(w.operations.filter(op=>op==='SAVE_BASE').length,1);
  assert.equal((await w.request({action:'SAVE',plan:p,tabId:1})).ok,false);
});
test('failed save is uncertain and must not retry; known id survives finalize failure',async()=>{
  for (const failure of ['SAVE_BASE','FINALIZE']) {
    const w=worker(),p=await plan(); await w.request({action:'FILL',plan:p,tabId:1}); w.setFailure(failure);
    assert.equal((await w.request({action:'SAVE',plan:p,tabId:1})).ok,false);
    const r=(await w.request({action:'RECEIPT',plan:p,tabId:1})).result;
    assert.equal(r.status,failure==='SAVE_BASE'?'UNCERTAIN':'SAVED_REVIEW_PENDING');
    if(failure==='FINALIZE') assert.equal(r.portal_id,'123');
    assert.equal((await w.request({action:'SAVE',plan:p,tabId:1})).ok,false);
    assert.equal((await w.request({action:'FILL',plan:p,tabId:1})).ok,false);
  }
});
test('preflight failure creates no write journal',async()=>{
  const w=worker();w.setFailure('CHECK_EMPTY');
  assert.equal((await w.request({action:'FILL',plan:await plan(),tabId:1})).ok,false);
  assert.equal(Object.keys(w.storage).length,0);
});
test('concurrent operations cannot race the journal',async()=>{
  const w=worker(),p=await plan();w.pause();
  const first=w.request({action:'FILL',plan:p,tabId:1});
  // Yield through promise turns to reach the paused DOM operation.
  while(!w.operations.includes('FILL')) await new Promise(resolve=>setImmediate(resolve));
  assert.equal((await w.request({action:'FILL',plan:p,tabId:1})).ok,false);
  w.unpause();assert.equal((await first).ok,true);
});
