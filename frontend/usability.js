/* Capa de presentación: conserva endpoints, autorización y datos existentes. */
function uiMessage(message) {
  let box=document.querySelector('#global-message');
  if(!box){box=document.createElement('div');box.id='global-message';box.className='ux-message';box.setAttribute('role','status');document.body.append(box);}
  box.replaceChildren();const text=document.createElement('span');text.textContent=message;box.append(text);
  const close=document.createElement('button');close.textContent='Cerrar';close.onclick=()=>box.remove();box.append(close);
}
function uiDialog(message, value) {
  return new Promise(resolve=>{
    const previous=document.activeElement, dialog=document.createElement('dialog');dialog.className='ux-dialog';
    dialog.innerHTML='<form method="dialog"><h2>Confirmar acción</h2><label class="field"><span></span></label><div class="toolbar"><button value="cancel" type="button">Cancelar</button><button class="primary" value="ok">Continuar</button></div></form>';
    dialog.querySelector('span').textContent=message;
    let input;if(value!==undefined){input=document.createElement('input');input.value=value;dialog.querySelector('label').append(input);}
    const finish=result=>{dialog.remove();previous?.focus();resolve(result);};
    dialog.querySelector('[value=cancel]').onclick=()=>finish(null);
    dialog.oncancel=e=>{e.preventDefault();finish(null);};
    dialog.querySelector('form').onsubmit=e=>{e.preventDefault();finish(input?input.value:true);};
    document.body.append(dialog);dialog.showModal();(input||dialog.querySelector('[value=cancel]')).focus();
  });
}
const uiConfirm=async message=>Boolean(await uiDialog(message));
const uiPrompt=(message,value='')=>uiDialog(message,value);

const baseVisibleMenu=visibleMenu;
visibleMenu=()=>[['home','Inicio'],...baseVisibleMenu()];
homeScreen=()=> 'home';
screens.home=async view=>{
  const role=state.user.role;
  const options=role==='RESEARCHER'?[['indicators','Indicadores de tesis','Comparar resultados y consultar cálculos'],['research','Mediciones del censo','Registrar y revisar pretest y postest']]:role==='ADMIN'?[['users','Usuarios y permisos','Gestionar cuentas operativas'],['inventory','Jornadas y asignaciones','Organizar el levantamiento'],['dashboard','Avance operativo','Consultar el resumen de activos']]:[['inventory','Mis jornadas','Registrar equipos y hallazgos'],['scanner','Escanear o buscar','Consultar un código patrimonial'],['assets','Buscar equipos','Revisar las fichas disponibles']];
  view.innerHTML=`<section class="ux-welcome"><span>${escapeHtml(roleNames[role]||'Consulta')}</span><h2>Hola, ${escapeHtml(state.user.fullName)}</h2><p>Selecciona una tarea para comenzar.</p></section><div class="session-grid">${options.filter(([key])=>visibleMenu().some(([id])=>key===id)).map(([key,title,help])=>`<button class="panel session-card" data-go="${key}"><strong>${title}</strong><span>${help}</span><span aria-hidden="true">Abrir →</span></button>`).join('')}</div><div id="home-summary"></div>`;
  view.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>navigate(b.dataset.go));
  if(['ADMIN','INVENTORY'].includes(role)){
    const rows=await request('/inventory-sessions');
    view.querySelector('#home-summary').innerHTML=`<h3>${role==='ADMIN'?'Avance de jornadas':'Jornadas asignadas'}</h3><div class="session-grid">${rows.map(r=>`<button class="panel session-card" data-journal="${r.id}"><strong>${escapeHtml(r.name)}</strong><span>${escapeHtml(r.site)}</span><span>${r.checked_count} registros · ${r.status==='OPEN'?'Abierta':'Cerrada'}</span></button>`).join('')||'<p>No hay jornadas disponibles.</p>'}</div>`;
    view.querySelectorAll('[data-journal]').forEach(b=>b.onclick=()=>sessionDetail(view,b.dataset.journal));
  }else if(role==='RESEARCHER'){
    const d=await request('/research/sample');view.querySelector('#home-summary').innerHTML=`<section class="panel"><h3>Mediciones individuales del censo</h3><p>${d.summary.selected} equipos · ${d.summary.pretestCount} pretest · ${d.summary.posttestCount} postest · ${d.summary.pairedCount} pares completos.</p><p>Las guías importadas están disponibles en Indicadores y Guías y auditoría.</p></section>`;
  }
};

let dirtyForm=null;
document.addEventListener('input',e=>{const f=e.target.closest('form');if(f&&f.id!=='login-form'&&f.id!=='lookup'&&!f.closest('dialog'))dirtyForm=f;});
window.addEventListener('beforeunload',e=>{if(dirtyForm?.isConnected){e.preventDefault();e.returnValue='';}});
const baseNavigate=navigate;
navigate=async screen=>{
  if(dirtyForm?.isConnected&&!(await uiConfirm('Hay cambios sin guardar. ¿Desea salir de esta pantalla?')))return;
  dirtyForm=null;await baseNavigate(screen);enhancePage();
  const heading=document.querySelector('#view h2');if(heading){heading.tabIndex=-1;heading.focus({preventScroll:true});}
};

function enhanceForm(form){
  if(form.dataset.ux||form.closest('dialog'))return;form.dataset.ux='1';
  form.querySelectorAll('[required]').forEach(field=>{const label=field.closest('label');if(label&&!label.querySelector('.required-note')){const mark=document.createElement('small');mark.className='required-note';mark.textContent='Obligatorio';label.append(mark);}});
  form.addEventListener('invalid',e=>{const field=e.target;field.setAttribute('aria-invalid','true');let error=field.parentElement.querySelector('.field-error');if(!error){error=document.createElement('small');error.className='field-error';error.id='error-'+Math.random().toString(36).slice(2);field.parentElement.append(error);field.setAttribute('aria-describedby',error.id);}error.textContent=field.validationMessage;},true);
  form.addEventListener('input',e=>{if(e.target.validity?.valid){e.target.removeAttribute('aria-invalid');e.target.parentElement.querySelector('.field-error')?.remove();}});
  if(!['check-form','measure-form','edit-asset'].includes(form.id))return;
  const fields=[...form.children].filter(n=>n.matches('label,.grid2'));
  if(fields.length<2)return;
  const steps=document.createElement('div');steps.className='ux-steps';steps.setAttribute('aria-live','polite');form.prepend(steps);
  const review=document.createElement('div');review.className='panel';review.hidden=true;form.append(review);
  const nav=document.createElement('div');nav.className='toolbar ux-form-actions';nav.innerHTML='<button type="button" data-step-back>Anterior</button><button type="button" class="primary" data-step-next>Continuar</button>';form.append(nav);
  const submit=form.querySelector('button:not([type]),button[type=submit]');let step=0;
  const paint=()=>{steps.textContent=['Paso 1 de 3 · Identificar equipo','Paso 2 de 3 · Completar información','Paso 3 de 3 · Revisar y guardar'][step];fields.forEach((f,i)=>f.hidden=step===2||(step===0?i>0:i===0));review.hidden=step!==2;submit.hidden=step!==2;nav.querySelector('[data-step-back]').disabled=step===0;nav.querySelector('[data-step-next]').hidden=step===2;
    if(step===2){review.replaceChildren();const title=document.createElement('h3');title.textContent='Revisa la información antes de guardar';review.append(title);fields.forEach(f=>f.querySelectorAll('input,select,textarea').forEach(input=>{if(input.type==='password')return;const p=document.createElement('p');const name=input.closest('label')?.firstChild?.textContent||input.name;p.textContent=name+': '+(input.tagName==='SELECT'?input.selectedOptions[0]?.textContent:input.type==='file'?[...input.files].map(f=>f.name).join(', '):input.value||'Sin completar');review.append(p);}));}
  };
  nav.querySelector('[data-step-back]').onclick=()=>{step--;paint();};nav.querySelector('[data-step-next]').onclick=()=>{const invalid=fields.filter(f=>!f.hidden).flatMap(f=>[...f.querySelectorAll('input,select,textarea')]).find(f=>!f.checkValidity());if(invalid){invalid.reportValidity();return;}step++;paint();};
  const save=form.onsubmit;
  form.onsubmit=async e=>{e.preventDefault();if(step<2){nav.querySelector('[data-step-next]').click();return;}if(save){await save(e);if(!form.isConnected){dirtyForm=null;uiMessage('Información guardada correctamente.');}}};paint();
}

function enhancePage(){
  const view=document.querySelector('#view');if(!view)return;
  const title=document.querySelector('#title');const label=visibleMenu().find(([id])=>id===state.screen)?.[1];if(title&&label&&title.textContent!==label)title.textContent=label;
  const top=document.querySelector('.topbar>span');if(top&&top.textContent!=='Gestión de activos')top.textContent='Gestión de activos';
  const nav=document.querySelector('.nav');if(nav&&!nav.dataset.grouped){nav.dataset.grouped='1';for(const [name,ids] of [['Inicio',['home']],['Trabajo diario',['dashboard','assets','register','scanner','groups','inventory']],['Investigación',['research','indicators','simulation','studyAudit']],['Administración',['users','catalogs','audit','settings']]]){const buttons=[...nav.querySelectorAll('[data-screen]')].filter(b=>ids.includes(b.dataset.screen));if(!buttons.length)continue;const group=document.createElement('div');group.className='nav-group';const heading=document.createElement('p');heading.textContent=name;group.append(heading,...buttons);nav.insertBefore(group,nav.querySelector('#logout'));}}
  const toggle=document.querySelector('#toggle-menu');if(toggle&&!toggle.dataset.ux){toggle.dataset.ux='1';toggle.setAttribute('aria-controls','main-sidebar');document.querySelector('.sidebar').id='main-sidebar';toggle.onclick=()=>{const open=document.querySelector('.sidebar').classList.toggle('open');toggle.setAttribute('aria-expanded',String(open));};}
  if(!document.querySelector('.skip-content')){const skip=document.createElement('a');skip.className='skip-content';skip.href='#view';skip.textContent='Saltar al contenido';document.body.prepend(skip);view.tabIndex=-1;}
  view.querySelectorAll('input:not([aria-label]),select:not([aria-label])').forEach(f=>{if(!f.closest('label'))f.setAttribute('aria-label',f.placeholder||({type:'Tipo de activo',status:'Estado',phase:'Fase'})[f.id]||'Filtro');});
  view.querySelectorAll('table').forEach(table=>{const headers=[...table.querySelectorAll('thead th')].map(th=>th.textContent);table.querySelectorAll('tbody tr').forEach(tr=>[...tr.children].forEach((td,i)=>{if(!td.dataset.label)td.dataset.label=headers[i]||'Dato';}));if(table.closest('#asset-table,#study-table'))table.classList.add('mobile-cards');});
  view.querySelectorAll('.filters').forEach(filters=>{if(filters.querySelector('[data-clear]'))return;const clear=document.createElement('button');clear.type='button';clear.dataset.clear='1';clear.textContent='Limpiar filtros';clear.onclick=()=>{filters.querySelectorAll('input,select').forEach(f=>{f.value='';f.dispatchEvent(new Event('input',{bubbles:true}));f.dispatchEvent(new Event('change',{bubbles:true}));});filters.querySelector('#sim-filter')?.click();};filters.append(clear);});
  view.querySelectorAll('form').forEach(enhanceForm);
  view.querySelectorAll('.alert').forEach(e=>{if(!e.hasAttribute('role'))e.setAttribute('role',e.classList.contains('error')?'alert':'status');});
  if(!view.querySelector('.mobile-actions')&&state.user){const actions=document.createElement('nav');actions.className='mobile-actions';actions.setAttribute('aria-label','Acciones rápidas');for(const [id,label] of [['home','Inicio'],['assets','Buscar'],['scanner','Escanear']]){if(visibleMenu().some(([key])=>key===id)){const b=document.createElement('button');b.textContent=label;b.onclick=()=>navigate(id);actions.append(b);}}view.append(actions);}
}
let scheduled=false;
const indicatorPage=screens.indicators;
screens.indicators=async view=>{
  await indicatorPage(view);
  async function charts(){
    view.querySelector('#indicator-charts')?.remove();
    const choice=view.querySelector('#indicator-source');if(!choice||choice.value==='registered')return;
    const studies=await request('/research/simulations');const study=studies.find(s=>s.id===choice.value);if(!study)return;
    const section=document.createElement('section');section.id='indicator-charts';section.innerHTML='<h3>Comparación pretest y postest</h3><div class="session-grid"></div>';
    for(const g of study.guides){const pre=g.summary.PRETEST,post=g.summary.POSTTEST,max=g.unit==='%'?100:Math.max(pre.value,post.value,1);const card=document.createElement('article');card.className='panel';card.innerHTML=`<h3>${escapeHtml(g.metric)} · ${escapeHtml(g.title)}</h3><div class="metric-compare">${[['Pretest',pre],['Postest',post]].map(([name,r])=>`<div><div class="metric-line"><span>${name}</span><meter min="0" max="${max}" value="${r.value}" aria-label="${name}: ${r.value} ${escapeHtml(g.unit)}"></meter></div><p>${Number(r.value).toLocaleString('es-PE',{maximumFractionDigits:4})} ${escapeHtml(g.unit)}</p></div>`).join('')}</div><details><summary>Ver cálculo</summary><p>${escapeHtml(g.formula)}</p><p>Pretest: ${pre.numerator} / ${pre.denominator}${g.unit==='%'?' × 100':''}</p><p>Postest: ${post.numerator} / ${post.denominator}${g.unit==='%'?' × 100':''}</p><p>${escapeHtml(g.definition)}</p></details>`;section.querySelector('.session-grid').append(card);}
    view.querySelector('#indicator-content').append(section);
  }
  const choice=view.querySelector('#indicator-source');const change=choice.onchange;choice.onchange=async()=>{await change();await charts();};await charts();
};
const usabilityObserver=new MutationObserver(()=>{if(scheduled)return;scheduled=true;queueMicrotask(()=>{scheduled=false;if(document.querySelector('#app'))enhancePage();});});
usabilityObserver.observe(document.querySelector('#app'),{childList:true,subtree:true});
window.addEventListener('pagehide',()=>usabilityObserver.disconnect());
document.addEventListener('keydown',e=>{if(e.key==='Escape'){document.querySelector('.sidebar')?.classList.remove('open');document.querySelector('#toggle-menu')?.setAttribute('aria-expanded','false');}});
enhancePage();
