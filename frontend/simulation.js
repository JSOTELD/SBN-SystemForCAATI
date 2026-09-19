/* Fuente: Guias_30_dias_N1693_DATOS_PRACTICA.xlsx, seis hojas GO.
 * Los agregados se conservan; el reparto individual es sintético y reproducible.
 * No se infieren mediciones individuales reales a partir de totales diarios.
 */
function presentationText(value) {
  return String(value ?? '');
}
async function simulationScreen(view) {
  const studies = await request('/research/simulations');
  if (!studies.length) {view.innerHTML='<h2>Guías y auditoría</h2><p>No hay escenarios importados.</p>';return;}
  const study=studies[0], base='/research/simulations/'+study.id;
  const fmt=n=>Number(n).toLocaleString('es-PE',{maximumFractionDigits:4});
  view.innerHTML=`<h2>Guías y auditoría</h2><section class="panel"><strong>Guías pretest y postest</strong><p>Resultados calculados a partir de las guías importadas.</p></section><p>Fuente: ${escapeHtml(study.filename)}</p><div class="cards">${study.guides.map(g=>`<article class="card"><b>${g.metric}</b><p>Pretest: ${fmt(g.summary.PRETEST.value)} ${escapeHtml(g.unit)}</p><p>Postest: ${fmt(g.summary.POSTTEST.value)} ${escapeHtml(g.unit)}</p><small>Diferencia post − pre: ${fmt(g.summary.POSTTEST.value-g.summary.PRETEST.value)} ${g.unit==='%'?'puntos porcentuales':escapeHtml(g.unit)}</small></article>`).join('')}</div><div class="toolbar"><button id="sim-verify" class="primary">Ejecutar conciliación</button><button id="sim-download">Descargar expediente ZIP</button><a href="/api${base}/report" target="_blank" rel="noopener">Informe imprimible</a></div><div id="sim-result" role="status"></div><section class="panel"><h3>Guías diarias de la fuente</h3><label class="field">Indicador<select id="sim-metric">${study.guides.map(g=>`<option value="${g.metric}">${g.metric} · ${escapeHtml(g.title)}</option>`).join('')}</select></label><div id="sim-guide"></div></section><section class="panel"><h3>Detalle por equipo</h3><p>PRCC expresa cumplimiento conjunto; no identifica qué criterio falló.</p><div class="filters"><label>Día <select id="sim-day"><option value="">Todos</option>${Array.from({length:30},(_,i)=>`<option>${i+1}</option>`).join('')}</select></label><input id="sim-search" placeholder="Código de censo, SBN o sede"><button id="sim-filter">Consultar</button></div><div id="sim-assets"></div><div class="toolbar"><button id="sim-prev">Anterior</button><span id="sim-page"></span><button id="sim-next">Siguiente</button></div></section><p>La procedencia y las acotaciones se incluyen en el expediente técnico descargable.</p><section class="panel"><h3>Historial de consultas</h3><div id="sim-events"></div></section>`;
  async function events(){const rows=await request(base+'/events');view.querySelector('#sim-events').innerHTML=rows.map(r=>`<p>${escapeHtml(r.at)} · ${escapeHtml(({IMPORT_SIMULATION:'Importación de guías',VERIFY_SIMULATION:'Conciliación de datos',EXPORT_SIMULATION:'Exportación del expediente'})[r.action] || 'Consulta')}</p>`).join('');}
  async function guide(){const g=await request(base+'/guides/'+view.querySelector('#sim-metric').value);view.querySelector('#sim-guide').innerHTML=`<p>${escapeHtml(g.formula)}<br>${escapeHtml(presentationText(g.definition))}</p><div class="table-wrap"><table><thead><tr><th>Día</th><th>Pretest: fecha / fuente</th><th>Total</th><th>Numerador</th><th>Resultado ${escapeHtml(g.unit)}</th><th>Postest: fecha / fuente</th><th>Total</th><th>Numerador</th><th>Resultado ${escapeHtml(g.unit)}</th></tr></thead><tbody>${g.rows.map(r=>`<tr><td>${r.day}</td>${['PRETEST','POSTTEST'].map(p=>`<td>${escapeHtml(r[p].date)}<br><small>${escapeHtml(g.sheet+'!'+r[p].sourceRange)} ${escapeHtml(r[p].code||'')} ${escapeHtml(r[p].profile||'')}</small></td><td>${r[p].denominator}</td><td>${fmt(r[p].numerator)}</td><td>${fmt(r[p].value)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;}
  let page=1;
  async function assets(){const q=new URLSearchParams({page,day:view.querySelector('#sim-day').value,search:view.querySelector('#sim-search').value});const data=await request(base+'/assets?'+q);view.querySelector('#sim-assets').innerHTML=`<div class="table-wrap"><table><thead><tr><th>Equipo / sede</th><th>Fase</th><th>Día / fecha</th><th>PRCC</th><th>PACI</th><th>PACR</th><th>PRA</th><th>Tiempo (s)</th></tr></thead><tbody>${data.items.map(a=>['pre','post'].map(p=>`<tr><td>${escapeHtml(a.sample_code)}<br>${escapeHtml(a.snapshot.site)}</td><td>${p==='pre'?'Pretest':'Postest'}</td><td>${a[p].day} · ${escapeHtml(a[p].date)}</td>${['PRCC','PACI','PACR','PRA'].map(m=>`<td>${a[p][m]?'Sí':'No'}</td>`).join('')}<td>${fmt(a[p].durationMs/1000)}</td></tr>`).join('')).join('')}</tbody></table></div>`;view.querySelector('#sim-page').textContent=`Página ${page} · ${data.total} equipos`;view.querySelector('#sim-prev').disabled=page===1;view.querySelector('#sim-next').disabled=page*data.pageSize>=data.total;}
  const safe=fn=>async()=>{try{await fn();}catch(e){view.querySelector('#sim-result').textContent=e.message;}};
  view.querySelector('#sim-metric').onchange=safe(guide);
  view.querySelector('#sim-filter').onclick=view.querySelector('#sim-day').onchange=safe(async()=>{page=1;await assets();});
  view.querySelector('#sim-prev').onclick=safe(async()=>{page--;await assets();});view.querySelector('#sim-next').onclick=safe(async()=>{page++;await assets();});
  view.querySelector('#sim-verify').onclick=safe(async()=>{const r=await request(base+'/verify',{method:'POST',body:'{}'});view.querySelector('#sim-result').textContent=`${r.passed?'CORRECTO':'REVISAR'}: ${r.passedChecks}/${r.totalChecks} controles. Integridad SHA-256: ${Object.values(r.hashes).every(Boolean)?'correcta':'alterada'}. Comprobación aritmética e integridad de los datos.`;await events();});
  view.querySelector('#sim-download').onclick=safe(async()=>{await downloadStudy(base+'/audit.zip','expediente_auditoria_N1693.zip');await events();});
  await Promise.all([guide(),assets(),events()]);
}
screens.simulation=simulationScreen;
const registeredIndicators=screens.indicators;
screens.indicators=async function(view) {
  const studies=await request('/research/simulations');
  view.innerHTML='<h2>Indicadores de tesis</h2><label class="field">Origen de los datos<select id="indicator-source"></select></label><div id="indicator-content"></div>';
  const select=view.querySelector('#indicator-source');
  for(const study of studies){const option=document.createElement('option');option.value=study.id;option.textContent='Guías importadas · '+study.filename;select.append(option);}
  const live=document.createElement('option');live.value='registered';live.textContent='Mediciones individuales registradas';select.append(live);
  const content=view.querySelector('#indicator-content');
  async function render(){
    if(select.value==='registered'){
      await registeredIndicators(content);
      content.querySelector('h2').textContent='Mediciones individuales registradas';
      const note=document.createElement('p');note.textContent='Esta vista utiliza exclusivamente las mediciones ingresadas en las fichas del censo. Las guías importadas se consultan seleccionando el otro origen.';content.prepend(note);return;
    }
    const study=studies.find(s=>s.id===select.value);
    const fmt=n=>Number(n).toLocaleString('es-PE',{minimumFractionDigits:2,maximumFractionDigits:4});
    content.innerHTML=`<section class="panel"><strong>Guías pretest y postest</strong><p>Resultados calculados a partir de las guías importadas.</p></section><div class="table-wrap"><table id="thesis-indicators"><thead><tr><th>Indicador</th><th>Pretest agregado</th><th>Postest</th><th>Diferencia post − pre</th><th>Base pre / post</th></tr></thead><tbody>${study.guides.map(g=>{const pre=g.summary.PRETEST,post=g.summary.POSTTEST;return `<tr><td><strong>${escapeHtml(g.metric)}</strong><br>${escapeHtml(g.title)}</td><td>${fmt(pre.value)} ${escapeHtml(g.unit)}</td><td>${fmt(post.value)} ${escapeHtml(g.unit)}</td><td>${fmt(post.value-pre.value)} ${g.unit==='%'?'puntos porcentuales':escapeHtml(g.unit)}</td><td>${pre.denominator} / ${post.denominator} ${g.metric==='TPGR'?'reportes':'equipos'}</td></tr>`;}).join('')}</tbody></table></div><p>Equipos incluidos: ${study.manifest.population} equipos · 30 días por guía. Los porcentajes y promedios globales se obtienen dividiendo los numeradores acumulados entre sus denominadores acumulados.</p><button id="indicator-guides" class="primary">Ver guías diarias y auditoría</button><details class="panel"><summary>Fórmulas y definiciones</summary>${study.guides.map(g=>`<p><strong>${escapeHtml(g.metric)}</strong>: ${escapeHtml(g.formula)}<br>${escapeHtml(presentationText(g.definition))}</p>`).join('')}</details>`;
    content.querySelector('#indicator-guides').onclick=()=>navigate('simulation');
  }
  select.onchange=async()=>{try{await render();}catch(e){content.textContent=e.message;}};
  await render();
};
const liveStudyScreen=screens.research;
screens.research=async view=>{await liveStudyScreen(view);const box=document.createElement('section');box.className='panel';box.innerHTML='<strong>Guías importadas disponibles</strong><p>Consulte los agregados de las seis guías y el expediente de auditoría en el módulo separado.</p><button>Ver guías y auditoría</button>';box.querySelector('button').onclick=()=>navigate('simulation');view.prepend(box);};
