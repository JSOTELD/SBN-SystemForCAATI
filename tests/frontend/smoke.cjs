// Prueba DOM + API local. Solo inicia sesión y consulta; no registra activos ni mediciones.
const {JSDOM, VirtualConsole} = require('jsdom');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const base = 'http://localhost:3001';
const root = path.resolve(__dirname, '../..');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function run(username, password, role, screens) {
  const errors = [];
  const console = new VirtualConsole(); console.on('jsdomError', error => errors.push(error));
  const dom = new JSDOM('<div id="app"></div>', {url:base, runScripts:'dangerously', virtualConsole:console});
  const w = dom.window;
  w.Headers = Headers;
  w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
  w.alert = message => {throw new Error(message);};
  w.confirm = () => false;
  w.fetch = async (input, options={}) => {
    const headers = new Headers(options.headers);
    const cookies = dom.cookieJar.getCookieStringSync(base); if(cookies) headers.set('Cookie', cookies);
    const response = await fetch(new URL(input,base), {...options,headers});
    for(const cookie of response.headers.getSetCookie()) dom.cookieJar.setCookieSync(cookie,base);
    return response;
  };
  for(const file of ['app.js','portal.js','usability.js','dashboards.js']) {const script=w.document.createElement('script');script.textContent=fs.readFileSync(path.join(root,'frontend',file),'utf8');w.document.body.append(script);}
  for(let i=0;i<100&&!w.document.querySelector('#login-form');i++) await sleep(20);
  const form=w.document.querySelector('#login-form');assert(form,'Formulario de login');
  form.elements.username.value=username;form.elements.password.value=password;
  await form.onsubmit({preventDefault(){},target:form});
  for(let i=0;i<150&&!w.document.querySelector('#view h2');i++) await sleep(20);
  const menu=[...w.document.querySelectorAll('[data-screen]')].map(b=>b.dataset.screen);
  assert(menu.includes('home'));
  await w.navigate('home');assert(w.document.querySelector('.ux-welcome'));
  assert(w.document.querySelector('.nav-fold'));
  const fold=w.document.querySelector('.nav-fold');fold.open=false;assert.equal(fold.open,false);fold.open=true;
  await w.navigate(role==='RESEARCHER'?'researchOverview':'operationsOverview');
  assert(w.document.querySelector('#view h2').textContent.includes('Resumen'));
  assert(!menu.includes(role==='RESEARCHER'?'operationsOverview':'researchOverview'));
  if(role==='RESEARCHER') assert(!menu.includes('users')&&!menu.includes('inventory'));
  if(role==='ADMIN') assert(!menu.includes('research')&&!menu.includes('indicators'));
  if(role==='INVENTORY') assert(!menu.includes('users')&&!menu.includes('research'));
  for(const screen of screens) {
    await w.navigate(screen);
    assert(w.document.querySelector('#view h2'), `${role}: ${screen} debe renderizar: ${w.document.querySelector('#view')?.textContent}`);
    const alert=w.document.querySelector('#view>.alert.error');assert(!alert,alert?.textContent);
  }
  if(role==='INVENTORY') {
    await w.navigate('inventory');const button=w.document.querySelector('[data-session]');assert(button,'Jornada asignada');
    await w.sessionDetail(w.document.querySelector('#view'),button.dataset.session);
    assert(w.document.querySelector('#check-form'),'Formulario de hallazgo');
    await sleep(10);assert(w.document.querySelector('.ux-steps'),'Formulario por pasos');
    const check=w.document.querySelector('#check-form');
    check.elements.sbn.value='740899500001';check.elements.sbn.dispatchEvent(new w.Event('input',{bubbles:true}));
    check.querySelector('[data-step-next]').click();assert(check.querySelector('.ux-steps').textContent.includes('Paso 2'));
    check.elements.result.value='MATCH';check.querySelector('[data-step-next]').click();
    assert(check.querySelector('.ux-steps').textContent.includes('Paso 3'));
    assert.equal(check.querySelector('#save-check').hidden,false);
    const pending=w.navigate('assets');await sleep(10);assert(w.document.querySelector('.ux-dialog'));
    w.document.querySelector('.ux-dialog [value=cancel]').click();await pending;
    assert(w.document.querySelector('#check-form'),'Cancelar salida conserva formulario');
  }
  if(role==='ADMIN') {
    await w.newSession(w.document.querySelector('#view'));assert(w.document.querySelector('#session-form'),'Crear jornada');
  }
  if(role==='RESEARCHER') {
    await w.navigate('indicators');
    assert.equal(w.document.querySelectorAll('#thesis-indicators tbody tr').length,6);
    assert.equal(w.document.querySelectorAll('#indicator-charts meter').length,12);
    assert(w.document.querySelector('#view').textContent.length >= 0);
    assert(w.document.querySelector('#thesis-indicators').textContent.includes('66.2138'));
    const origin=w.document.querySelector('#indicator-source');origin.value='registered';await origin.onchange();
    assert(w.document.querySelector('#indicator-content').textContent.includes('Sin mediciones'));
    const sample=await (await w.fetch('/api/research/sample')).json();
    const phases=await (await w.fetch('/api/research/phases')).json();
    await w.measureAsset(w.document.querySelector('#view'),sample.items[0],phases);
    assert(w.document.querySelector('#measure-form'),'Guía de medición');
  }
  assert.equal(errors.length,0,errors.map(e=>e.stack).join('\n'));
  w.dispatchEvent(new w.Event('pagehide'));await sleep(30);
  dom.window.close();process.stdout.write(`PASS DOM/API ${role}: ${screens.join(', ')}\n`);
}
(async()=>{
  await run('admin',process.env.TEST_ADMIN_PASSWORD,'ADMIN',['dashboard','assets','register','scanner','groups','inventory','users','catalogs','audit','settings']);
  await run('usuario',process.env.TEST_INVENTORY_PASSWORD,'INVENTORY',['inventory','assets','scanner','settings']);
  await run('investigador',process.env.TEST_RESEARCH_PASSWORD,'RESEARCHER',['research','indicators','assets','scanner','studyAudit','settings']);
})().catch(error=>{console.error(error);process.exit(1);});
