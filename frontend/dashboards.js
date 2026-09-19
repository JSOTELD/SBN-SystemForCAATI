/* Resúmenes de consulta: los permisos y el alcance los conserva la API. */
const dashboardMenu=visibleMenu;
visibleMenu=()=>{
  const entries=dashboardMenu();
  if(['ADMIN','INVENTORY'].includes(state.user?.role))entries.push(['operationsOverview','Resumen de jornadas']);
  if(state.user?.role==='RESEARCHER')entries.push(['researchOverview','Resumen de tesis']);
  return entries;
};
const formatMetric=n=>Number(n).toLocaleString('es-PE',{maximumFractionDigits:2});
function summaryCards(items){return `<div class="cards">${items.map(([label,value])=>`<article class="card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></article>`).join('')}</div>`;}
screens.operationsOverview=async view=>{
  const rows=await request('/inventory-sessions');
  const open=rows.filter(r=>r.status==='OPEN').length, records=rows.reduce((n,r)=>n+Number(r.checked_count||0),0);
  const sites=new Map();rows.forEach(r=>sites.set(r.site,(sites.get(r.site)||0)+Number(r.checked_count||0)));
  const max=Math.max(1,...sites.values());
  view.innerHTML=`<h2>Resumen de jornadas</h2><p>${state.user.role==='ADMIN'?'Jornadas operativas disponibles':'Solo tus jornadas asignadas'}. Los registros se cuentan por jornada; un equipo puede aparecer en más de una.</p>${summaryCards([['Jornadas',rows.length],['Abiertas',open],['Cerradas',rows.length-open],['Registros',records]])}<section class="panel dashboard-section"><h3>Registros por sede</h3>${[...sites].map(([site,count])=>`<div class="dashboard-bar"><span>${escapeHtml(site)}</span><meter min="0" max="${max}" value="${count}" aria-label="${escapeHtml(site)}: ${count} registros"></meter><strong>${count}</strong></div>`).join('')||'<p>Aún no hay jornadas disponibles.</p>'}</section><details class="panel dashboard-section"><summary>Consultar jornadas (${rows.length})</summary><div class="session-grid">${rows.map(r=>`<button class="session-card panel" data-open-journal="${r.id}"><strong>${escapeHtml(r.name)}</strong><span>${escapeHtml(r.site)}</span><span>${r.status==='OPEN'?'Abierta':'Cerrada'} · ${r.checked_count} registros</span></button>`).join('')}</div></details><button id="overview-inventory" class="primary">Ir a jornadas</button>`;
  view.querySelector('#overview-inventory').onclick=()=>navigate('inventory');
  view.querySelectorAll('[data-open-journal]').forEach(b=>b.onclick=()=>sessionDetail(view,b.dataset.openJournal));
};
screens.researchOverview=async view=>{
  const [sample,studies]=await Promise.all([request('/research/sample'),request('/research/simulations')]);
  const s=sample.summary,study=studies[0];
  view.innerHTML=`<h2>Resumen de tesis</h2><p>Cobertura del censo y resultados de las guías importadas.</p>${summaryCards([['Equipos del censo',s.selected],['Pretest individuales',s.pretestCount],['Postest individuales',s.posttestCount],['Pares individuales',s.pairedCount]])}<p>La cobertura anterior corresponde a fichas individuales. Los resultados siguientes corresponden a las guías importadas.</p><section class="panel dashboard-section"><h3>Resultados pretest y postest</h3>${study?`<div class="session-grid">${study.guides.map(g=>`<article class="panel"><h3>${escapeHtml(g.metric)}</h3><p>${escapeHtml(g.title)}</p><p>Pretest: <strong>${formatMetric(g.summary.PRETEST.value)} ${escapeHtml(g.unit)}</strong></p><p>Postest: <strong>${formatMetric(g.summary.POSTTEST.value)} ${escapeHtml(g.unit)}</strong></p><p>Diferencia: ${formatMetric(g.summary.POSTTEST.value-g.summary.PRETEST.value)} ${g.unit==='%'?'puntos porcentuales':escapeHtml(g.unit)}</p></article>`).join('')}</div>`:'<p>No hay guías importadas.</p>'}</section><details class="panel dashboard-section"><summary>Cobertura por sede</summary><div id="overview-coverage"></div></details><div class="toolbar"><button class="primary" data-target="indicators">Ver indicadores y cálculos</button><button data-target="research">Abrir censo</button><button data-target="simulation">Consultar guías</button></div>`;
  const sites=new Map();sample.items.forEach(a=>{const v=sites.get(a.site)||{n:0,pre:0,post:0};v.n++;v.pre+=Number(a.has_pretest);v.post+=Number(a.has_posttest);sites.set(a.site,v);});
  view.querySelector('#overview-coverage').innerHTML=[...sites].map(([site,v])=>`<p><strong>${escapeHtml(site)}</strong> · ${v.n} equipos · ${v.pre} pretest · ${v.post} postest</p>`).join('');
  view.querySelectorAll('[data-target]').forEach(b=>b.onclick=()=>navigate(b.dataset.target));
};

function collapseSection(section){
  if(!section||section.dataset.collapsible||section.tagName==='DETAILS')return;
  const heading=section.querySelector(':scope > h3');if(!heading)return;
  section.dataset.collapsible='1';const details=document.createElement('details');details.className='section-fold';
  const summary=document.createElement('summary');summary.textContent=heading.textContent;heading.remove();
  details.append(summary);while(section.firstChild)details.append(section.firstChild);section.append(details);
}
const enhanceWithDashboards=enhancePage;
enhancePage=function(){
  enhanceWithDashboards();
  const nav=document.querySelector('.nav');if(!nav)return;
  const loose=[...nav.querySelectorAll(':scope > [data-screen]')].filter(b=>['operationsOverview','researchOverview'].includes(b.dataset.screen));
  if(loose.length){const group=document.createElement('div');group.className='nav-group';const p=document.createElement('p');p.textContent='Resúmenes';group.append(p,...loose);nav.insertBefore(group,nav.querySelector('#logout'));}
  nav.querySelectorAll('div.nav-group').forEach(group=>{
    const title=group.querySelector('p')?.textContent||'Opciones';
    const details=document.createElement('details');details.className='nav-group nav-fold';const summary=document.createElement('summary');summary.textContent=title;details.append(summary);
    const buttons=[...group.querySelectorAll('[data-screen]')];details.append(...buttons);
    const key='itam-menu:'+state.user.id+':'+title;let saved;try{saved=sessionStorage.getItem(key);}catch(_){}
    details.open=saved===null?buttons.some(b=>b.dataset.screen===state.screen):saved==='open';
    details.addEventListener('toggle',()=>{try{sessionStorage.setItem(key,details.open?'open':'closed');}catch(_){}});
    group.replaceWith(details);
  });
  document.querySelectorAll('#view section.panel').forEach(section=>{
    if(section.querySelector('#coverage,#sim-events,#sim-assets'))collapseSection(section);
  });
  const home=document.querySelector('.ux-welcome');if(home&&!home.querySelector('[data-home-summary]')){
    const id=state.user.role==='RESEARCHER'?'researchOverview':['ADMIN','INVENTORY'].includes(state.user.role)?'operationsOverview':null;
    if(id){const b=document.createElement('button');b.dataset.homeSummary='1';b.className='primary';b.textContent='Abrir resumen';b.onclick=()=>navigate(id);home.append(b);}
  }
};
const navigateWithDashboards=navigate;
navigate=async screen=>{await navigateWithDashboards(screen);const active=document.querySelector('.nav button.active');if(active){active.setAttribute('aria-current','page');const group=active.closest('details');if(group)group.open=true;}document.querySelectorAll('.nav button:not(.active)[aria-current]').forEach(b=>b.removeAttribute('aria-current'));};
enhancePage();
