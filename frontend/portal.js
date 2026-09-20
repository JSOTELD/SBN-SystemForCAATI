/* Roles y flujos móviles. La autorización definitiva se valida en Flask.
 * Cámara: https://github.com/zxing-js/browser (versión local 0.1.5, MIT).
 * La sesión usa cookie HttpOnly y protección CSRF; no se guarda el JWT en JS.
 */
const roleNames = {ADMIN: 'Administrador', INVENTORY: 'Usuario operativo', RESEARCHER: 'Analista', VIEWER: 'Consulta'};
const SBN_PATTERN = /^[A-Z0-9]{12}$/;

function normalizeSbn(value) {
  return String(value ?? '').trim().toUpperCase();
}

function isValidSbn(value) {
  return SBN_PATTERN.test(normalizeSbn(value));
}

function readForm(form) {
  return Object.fromEntries(new FormData(form));
}

function showFormError(view, selector, error) {
  const target = view.querySelector(selector);
  if (target) target.innerHTML = notice(error?.message || 'No fue posible completar la operación.');
}

function displayCheckNotes(check) {
  const notes = check.notes || '';
  if (!notes.includes('[SYNTHETIC]')) return notes;
  const date = check.checked_at ? new Date(check.checked_at).toLocaleDateString('es-PE', {day: '2-digit', month: '2-digit', year: 'numeric'}) : '';
  return  (date ? ' ' + date : '');
}
function homeScreen() { return state.user?.role === 'RESEARCHER' ? 'research' : state.user?.role === 'INVENTORY' ? 'inventory' : state.user?.role === 'VIEWER' ? 'assets' : 'dashboard'; }
function visibleMenu() {
  const permissions = {
    ADMIN: ['dashboard', 'assets', 'register', 'scanner', 'groups', 'inventory', 'maintenance', 'movements', 'users', 'catalogs', 'audit', 'settings'],
    INVENTORY: ['inventory', 'assets', 'scanner', 'settings'],
    RESEARCHER: ['research', 'indicators', 'assets', 'scanner', 'studyAudit', 'settings'],
    VIEWER: ['assets', 'scanner', 'settings']
  };
  return [...menu, ['studyAudit', 'Historial del estudio']].filter(([id]) => (permissions[state.user?.role] || []).includes(id));
}
let cameraControls = null;
let cameraGeneration = 0;
function stopCamera() {
  cameraGeneration++;
  cameraControls?.stop(); cameraControls = null;
  document.querySelectorAll('video').forEach(video => { video.srcObject?.getTracks().forEach(track => track.stop()); video.srcObject = null; });
}
window.addEventListener('pagehide', stopCamera);
document.addEventListener('visibilitychange', () => { if (document.hidden) stopCamera(); });
function cameraPanel() {
  return '<div class="camera-panel"><button type="button" class="secondary" data-camera>Leer etiqueta del activo</button><button type="button" data-stop-camera hidden>Detener cámara</button><video playsinline muted hidden></video><p class="muted" data-camera-status>También puede escribir el código o usar un lector externo.</p></div>';
}
function bindCamera(container, input, onRead = () => {}) {
  if (!container || !input) return;
  const start = container.querySelector('[data-camera]'); const stop = container.querySelector('[data-stop-camera]');
  const video = container.querySelector('video'); const message = container.querySelector('[data-camera-status]');
  if (!start || !stop || !video || !message) return;
  stop.onclick = () => { stopCamera(); video.hidden = true; stop.hidden = true; start.disabled = false; };
  start.onclick = async () => {
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) { message.textContent = 'La cámara necesita HTTPS y un navegador compatible. Puede escribir el código.'; return; }
    stopCamera(); const generation = cameraGeneration; start.disabled = true; stop.hidden = false; video.hidden = false;
    try {
      const reader = new ZXingBrowser.BrowserMultiFormatReader();
      const controls = await reader.decodeFromConstraints({video: {facingMode: {ideal: 'environment'}}, audio: false}, video, (result, error, control) => {
        if (generation !== cameraGeneration) { control?.stop(); return; }
        const code = normalizeSbn(result?.getText());
        if (!code) return;
        if (!isValidSbn(code)) { message.textContent = 'La etiqueta no contiene un código patrimonial de 12 caracteres.'; return; }
        input.value = code; control?.stop(); stopCamera(); video.hidden = true; stop.hidden = true; start.disabled = false;
        message.textContent = 'Código leído: ' + code; input.dispatchEvent(new Event('input')); onRead(code);
      });
      if (generation !== cameraGeneration) controls.stop(); else cameraControls = controls;
    } catch (error) { stopCamera(); video.hidden = true; start.disabled = false; stop.hidden = true; message.textContent = 'No se pudo abrir la cámara. Revise el permiso o ingrese el código manualmente.'; }
  };
}

async function realScanner(view) {
  view.innerHTML = `<h2>Consultar código patrimonial</h2><section class="panel">${cameraPanel()}<form id="lookup"><label class="field">Código<input name="code" maxlength="12" pattern="[A-Za-z0-9]{12}" autocomplete="off" required></label><button class="primary">Consultar</button></form><div id="scan-result"></div></section>`;
  const form = view.querySelector('#lookup');
  const lookup = async () => {
    const code = normalizeSbn(form.elements.code.value);
    form.elements.code.value = code;
    if (!isValidSbn(code)) return;
    try { const asset = await request('/assets/sbn/' + encodeURIComponent(code)); stopCamera(); await assetDetail(view, asset.id); }
    catch(error) { showFormError(view, '#scan-result', error); }
  };
  form.onsubmit = event => {event.preventDefault(); lookup();};
  bindCamera(view, form.elements.code, lookup);
}

async function mobileInventory(view) {
  const sessions = await request('/inventory-sessions');
  view.innerHTML = `<div class="toolbar"><div><h2>${state.user.role === 'ADMIN' ? 'Jornadas de levantamiento' : 'Mis jornadas'}</h2><p>Registro operativo de equipos y hallazgos.</p></div>${state.user.role === 'ADMIN' ? '<button id="new-session" class="primary">Crear jornada</button>' : ''}</div><div class="session-grid">${sessions.map(row => `<button class="panel session-card" data-session="${row.id}"><strong>${escapeHtml(row.name)}</strong><span>${escapeHtml(row.site)}</span><span>${row.checked_count} registros · ${escapeHtml(row.status)}</span></button>`).join('') || '<p>No hay jornadas asignadas. El administrador puede asignarle una.</p>'}</div>`;
  view.querySelectorAll('[data-session]').forEach(button => button.onclick = () => sessionDetail(view, button.dataset.session));
  const create = view.querySelector('#new-session'); if (create) create.onclick = () => newSession(view);
}
async function newSession(view) {
  const [sites, users] = await Promise.all([request('/inventory-sites'), request('/users')]);
  view.innerHTML = `<h2>Nueva jornada</h2><form class="panel" id="session-form"><label class="field">Nombre<input name="name" minlength="3" maxlength="150" required></label><label class="field">Edificio o sede<select name="site">${sites.map(site => `<option>${escapeHtml(site)}</option>`).join('')}</select></label><fieldset><legend>Usuarios operativos asignados</legend>${users.filter(u => u.active && u.role === 'INVENTORY').map(user => `<label class="check-option"><input type="checkbox" name="assigned" value="${user.id}">${escapeHtml(user.fullName)} (${escapeHtml(user.username)})</label>`).join('') || '<p>Primero cree un usuario operativo.</p>'}</fieldset><button class="primary">Crear y abrir</button><button type="button" id="cancel">Volver</button><div id="message"></div></form>`;
  view.querySelector('#cancel').onclick = () => navigate('inventory');
  view.querySelector('form').onsubmit = async event => {
    event.preventDefault(); const f = new FormData(event.target);
    try { const row = await request('/inventory-sessions', {method: 'POST', body: JSON.stringify({name: f.get('name'), site: f.get('site'), assignedUsers: f.getAll('assigned')})}); await sessionDetail(view, row.id); }
    catch(error) {showFormError(view, '#message', error);}
  };
}
async function sessionDetail(view, id) {
  stopCamera(); const session = await request('/inventory-sessions/' + id);
  const draftKey = `itam-draft:${state.user.id}:${id}`;
  let draft = null; try {draft = JSON.parse(sessionStorage.getItem(draftKey));} catch (_) {}
  view.innerHTML = `<div class="toolbar"><div><h2>${escapeHtml(session.name)}</h2><p>${escapeHtml(session.site)}</p><p>${session.checked_count} registrados · ${session.pending} pendientes</p></div><button id="back-session">Volver</button></div>
  ${session.status === 'OPEN' ? `<section class="panel">${cameraPanel()}<form id="check-form"><label class="field">Código patrimonial<input name="sbn" maxlength="12" pattern="[A-Za-z0-9]{12}" autocomplete="off" required></label><button type="button" id="find-code">Revisar ficha</button><div id="code-info"></div><label class="field">Resultado<select name="result" required><option value="">Seleccione</option><option value="MATCH">Encontrado, coincide</option><option value="MISMATCH">Encontrado, con diferencias</option><option value="NOT_FOUND">No localizado</option><option value="NOT_APPLICABLE">No aplica (justificar)</option></select></label><label class="field">Hallazgo / observaciones<textarea name="notes" maxlength="1000" placeholder="Indique estado, ubicación y diferencias encontradas"></textarea></label><label class="field">Motivo de corrección (si ya hay un registro)<input name="correctionReason" maxlength="1000"></label><label class="field">Fotografía opcional (JPEG/PNG, máximo 5 MB)<input name="photo" type="file" accept="image/jpeg,image/png" capture="environment"></label><button class="primary" id="save-check">Guardar hallazgo</button><p class="muted" id="draft-status">${draft ? 'Borrador recuperado de esta pestaña. Revíselo antes de guardar.' : 'El formulario conserva un borrador en esta pestaña si falla la conexión.'}</p><div id="check-message" role="status"></div></form></section>` : '<div class="alert">Jornada cerrada: solo consulta.</div>'}
  ${state.user.role === 'ADMIN' && session.status === 'OPEN' ? '<button id="close-session" class="secondary">Cerrar jornada</button>' : ''}<h3>Hallazgos registrados</h3><div class="session-grid">${session.checks.map(c => `<article class="panel"><strong>${escapeHtml(c.sbn)}</strong><p>${escapeHtml(c.description)}</p><span class="badge">${escapeHtml(c.result)}</span><p>${escapeHtml(displayCheckNotes(c))}</p>${session.status === 'OPEN' ? `<button data-correct="${c.sbn}">Revisar / corregir</button>` : ''}${c.evidence.map(e => `<a href="/api/inventory-evidence/${e}" target="_blank" rel="noopener">Ver fotografía</a>`).join(' ')}</article>`).join('') || '<p>Aún no hay hallazgos registrados.</p>'}</div>`;
  view.querySelector('#back-session').onclick = () => navigate('inventory');
  const close = view.querySelector('#close-session');
  if (close) close.onclick = async () => {if (await uiConfirm(`¿Cerrar la jornada con ${session.pending} pendientes?`)) {try {await request(`/inventory-sessions/${id}/close`, {method: 'POST'}); await sessionDetail(view, id);} catch(e) {uiMessage(e.message);}}};
  const form = view.querySelector('#check-form'); if (!form) return;
  if (draft) ['sbn', 'result', 'notes', 'correctionReason'].forEach(key => {form.elements[key].value = draft[key] || '';});
  const persist = () => {
    const f = new FormData(form); const value = Object.fromEntries(['sbn','result','notes','correctionReason'].map(key => [key, f.get(key)]));
    try {sessionStorage.setItem(draftKey, JSON.stringify(value)); view.querySelector('#draft-status').textContent = 'Borrador local en esta pestaña; todavía no enviado. Las fotografías no se guardan en el borrador.';} catch (_) {}
  };
  form.oninput = persist;
  const lookup = async () => {
    const code = normalizeSbn(form.elements.sbn.value);
    form.elements.sbn.value = code;
    if (!isValidSbn(code)) return;
    try { const a = await request('/assets/sbn/' + encodeURIComponent(code)); view.querySelector('#code-info').innerHTML = `<p><strong>${escapeHtml(a.description)}</strong><br>${escapeHtml(a.brand)} · ${escapeHtml(a.serialNumber)}<br>${escapeHtml(a.site)} · ${escapeHtml(a.room)}<br>Estado: ${escapeHtml(a.status)} / ${escapeHtml(a.condition)}</p>`; }
    catch(error) {showFormError(view, '#code-info', error);}
  };
  bindCamera(view, form.elements.sbn, lookup); view.querySelector('#find-code').onclick = lookup;
  view.querySelectorAll('[data-correct]').forEach(button => button.onclick = () => {
    const row = session.checks.find(c => c.sbn === button.dataset.correct);
    form.elements.sbn.value = row.sbn; form.elements.result.value = row.result; form.elements.notes.value = row.notes || ''; form.elements.correctionReason.value = '';
    persist(); lookup(); form.scrollIntoView({behavior: 'smooth'});
  });
  form.onsubmit = async event => {
    event.preventDefault(); const button = view.querySelector('#save-check'); button.disabled = true; persist();
    const payload = readForm(form); const photo = payload.photo; delete payload.photo;
    payload.sbn = normalizeSbn(payload.sbn);
    const existing = session.checks.find(c => c.sbn === payload.sbn); payload.version = existing?.version || 0;
    try {
      const check = await request(`/inventory-sessions/${id}/checks`, {method: 'POST', body: JSON.stringify(payload)});
      sessionStorage.removeItem(draftKey);
      if (photo?.size) {
        const body = new FormData(); body.append('photo', photo);
        try {await request(`/inventory-checks/${check.id}/evidence`, {method: 'POST', body});}
        catch(error) {uiMessage('El hallazgo se guardó, pero la fotografía no: ' + error.message);}
      }
      await sessionDetail(view, id);
      const msg = view.querySelector('#check-message'); if (msg) msg.innerHTML = notice('Hallazgo guardado correctamente.', 'success');
    } catch(error) {showFormError(view, '#check-message', new Error(`${error.message} El borrador permanece en esta pestaña.`)); button.disabled = false;}
  };
}

async function manageUsers(view) {
  const users = await request('/users');
  view.innerHTML = `<h2>Usuarios operativos</h2><p>Las cuentas de investigación se administran por un procedimiento independiente.</p><details class="panel"><summary>Crear usuario</summary><form id="user-form"><label class="field">Nombre completo<input name="fullName" maxlength="150" required></label><label class="field">Usuario<input name="username" minlength="3" maxlength="50" required></label><label class="field">Correo<input type="email" name="email" maxlength="150" required></label><label class="field">Perfil<select name="role"><option value="INVENTORY">Usuario general</option><option value="ADMIN">Administrador</option><option value="VIEWER">Solo consulta</option></select></label><label class="field">Contraseña temporal<input type="password" name="password" minlength="12" autocomplete="new-password" required></label><p class="muted">12 caracteres; mayúscula, minúscula, número y símbolo. Se solicitará cambiarla al ingresar.</p><button class="primary">Crear cuenta</button><div id="user-message"></div></form></details><div class="session-grid">${users.map(user => `<article class="panel"><h3>${escapeHtml(user.fullName)}</h3><p>${escapeHtml(user.username)} · ${roleNames[user.role] || user.role}</p><p>${user.active ? 'Activo' : 'Desactivado'}</p><button data-reset="${user.id}">Restablecer contraseña</button>${user.id !== state.user.id ? `<button data-active="${user.id}">${user.active ? 'Desactivar' : 'Activar'}</button><button data-role="${user.id}">Cambiar perfil</button>` : ''}</article>`).join('')}</div>`;
  view.querySelector('#user-form').onsubmit = async event => {event.preventDefault(); try {await request('/users', {method:'POST', body:JSON.stringify(Object.fromEntries(new FormData(event.target)))}); await manageUsers(view);} catch(e) {view.querySelector('#user-message').innerHTML = notice(e.message);}};
  view.querySelectorAll('[data-active]').forEach(button => button.onclick = async () => {const user = users.find(u=>u.id === button.dataset.active); try {await request('/users/'+user.id,{method:'PATCH',body:JSON.stringify({active:!user.active})}); await manageUsers(view);} catch(e){uiMessage(e.message);}});
  view.querySelectorAll('[data-role]').forEach(button => button.onclick = async () => {
    const user = users.find(u=>u.id === button.dataset.role); const role = await uiPrompt('Perfil: ADMIN, INVENTORY (usuario general) o VIEWER', user.role);
    if (!role) return; try {await request('/users/'+user.id,{method:'PATCH',body:JSON.stringify({role})}); await manageUsers(view);} catch(e){uiMessage(e.message);}
  });
  view.querySelectorAll('[data-reset]').forEach(button => button.onclick = () => {
    const dialog = document.createElement('dialog'); dialog.innerHTML = `<form><h3>Contraseña temporal</h3><input type="password" name="password" minlength="12" autocomplete="new-password" required><p>La cuenta deberá cambiarla al ingresar.</p><button class="primary">Restablecer</button><button type="button">Cancelar</button><div role="status"></div></form>`;
    view.append(dialog); dialog.showModal(); dialog.querySelector('[type=button]').onclick = () => dialog.remove();
    dialog.querySelector('form').onsubmit = async event => {event.preventDefault(); try {await request(`/users/${button.dataset.reset}/reset-password`,{method:'POST',body:JSON.stringify({temporaryPassword:new FormData(event.target).get('password')})}); dialog.remove();} catch(e){dialog.querySelector('[role=status]').textContent=e.message;}};
  });
}

async function downloadStudy(path, filename) {
  const response = await fetch('/api' + path); if (!response.ok) throw new Error('No se pudo descargar el archivo. Revise su sesión.');
  const url = URL.createObjectURL(await response.blob()); const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function studyScreen(view) {
  const [data, phases] = await Promise.all([request('/research/sample'), request('/research/phases')]);
  view.innerHTML = `<h2>Censo de Libros y El Comercio</h2><p>${data.settings.populationSize} equipos en el marco · ${phases.frozen ? 'Marco congelado al iniciar las mediciones' : 'Marco preparado; se congelará al registrar la primera medición'}</p><div class="cards">${[['Equipos',data.summary.selected],['Pretest',data.summary.pretestCount],['Postest',data.summary.posttestCount],['Pares completos',data.summary.pairedCount]].map(([label,value])=>`<div class="card">${label}<strong>${value}</strong></div>`).join('')}</div><section class="panel"><h3>Control de fases</h3>${phases.phases.map(p=>`<p>${p.phase}: <strong>${p.status}</strong> ${p.status === 'OPEN' ? `<button data-close-phase="${p.phase}">Cerrar fase</button>`:''}</p>`).join('')}<div class="toolbar"><button data-export="/research/paired-data.csv">Exportar pares</button><button data-export="/research/report-trials.csv">Exportar tiempos de reportes</button><button data-export="/research/dictionary.csv">Diccionario de variables</button><button id="report-time">Registrar tiempo de reporte</button></div></section><section class="panel"><h3>Cobertura por edificio y tipo</h3><div id="coverage"></div></section><section class="panel"><h3>Equipos del censo</h3><div class="filters"><input id="study-search" placeholder="Código, SBN, descripción o sede"><select id="study-phase"><option value="">Todos</option><option value="pre">Pendientes pretest</option><option value="post">Pendientes postest</option><option value="paired">Pares completos</option></select></div><div id="study-table"></div><div class="toolbar"><button id="study-prev">Anterior</button><span id="study-page"></span><button id="study-next">Siguiente</button></div></section>`;
  const coverage = new Map(); data.items.forEach(item => {const key=item.site+' · '+typeLabel(item.stratum); const v=coverage.get(key)||[0,0,0]; v[0]++;v[1]+=Number(item.has_pretest);v[2]+=Number(item.has_posttest);coverage.set(key,v);});
  view.querySelector('#coverage').innerHTML = [...coverage].map(([label,v])=>`<p><strong>${escapeHtml(label)}</strong><br>Total ${v[0]} · Pretest ${v[1]} · Postest ${v[2]} · Pendientes ${v[0]-v[1]} / ${v[0]-v[2]}</p>`).join('');
  let page = 1;
  const renderRows = () => {
    const search=view.querySelector('#study-search').value.toLowerCase();const phase=view.querySelector('#study-phase').value;
    const rows=data.items.filter(a=>(`${a.sample_code} ${a.sbn} ${a.description} ${a.site}`).toLowerCase().includes(search)&&(!phase||phase==='pre'&&!a.has_pretest||phase==='post'&&!a.has_posttest||phase==='paired'&&a.has_pretest&&a.has_posttest));
    const pages=Math.max(1,Math.ceil(rows.length/40));page=Math.min(page,pages);
    view.querySelector('#study-table').innerHTML=`<div class="table-wrap"><table><thead><tr><th>Equipo</th><th>Sede</th><th>Pretest</th><th>Postest</th><th>Medir</th></tr></thead><tbody>${rows.slice((page-1)*40,page*40).map(a=>`<tr><td><strong>${escapeHtml(a.sample_code)}</strong><br>${escapeHtml(a.sbn)}<br>${escapeHtml(a.description)}</td><td>${escapeHtml(a.site)}</td><td>${a.has_pretest?'Registrado':'Pendiente'}</td><td>${a.has_posttest?'Registrado':'Pendiente'}</td><td><button data-measure="${a.asset_id}">Abrir guía</button></td></tr>`).join('')}</tbody></table></div>`;
    view.querySelector('#study-page').textContent=`Página ${page}/${pages} · ${rows.length} equipos`;view.querySelector('#study-prev').disabled=page===1;view.querySelector('#study-next').disabled=page===pages;
    view.querySelectorAll('[data-measure]').forEach(button=>button.onclick=()=>measureAsset(view,data.items.find(a=>a.asset_id===button.dataset.measure),phases));
  };
  view.querySelector('#study-search').oninput=view.querySelector('#study-phase').onchange=()=>{page=1;renderRows();};
  view.querySelector('#study-prev').onclick=()=>{page--;renderRows();};view.querySelector('#study-next').onclick=()=>{page++;renderRows();};renderRows();
  view.querySelectorAll('[data-export]').forEach(button=>button.onclick=()=>downloadStudy(button.dataset.export,button.dataset.export.split('/').pop()).catch(e=>uiMessage(e.message)));
  view.querySelectorAll('[data-close-phase]').forEach(button=>button.onclick=async()=>{const reason=await uiPrompt('Motivo del cierre (las mediciones quedarán bloqueadas):');if(!reason)return;const incomplete=await uiConfirm('¿Autoriza cerrar aunque existan equipos pendientes? El motivo quedará registrado.');try{await request(`/research/phases/${button.dataset.closePhase}/close`,{method:'POST',body:JSON.stringify({reason,confirmIncomplete:incomplete})});await studyScreen(view);}catch(e){uiMessage(e.message);}});
  view.querySelector('#report-time').onclick=()=>reportMeasurement(view);
}

const criteria = [['recordComplete','Registro completo','record_complete'],['recordConsistent','Registro consistente','record_consistent'],['correctlyIdentified','Correctamente identificado','correctly_identified'],['correctlyRegistered','Correctamente registrado','correctly_registered'],['recordUpdated','Registro actualizado','record_updated']];
async function measureAsset(view, asset, phases) {
  const [observations,evidence]=await Promise.all([request('/observations?assetId='+asset.asset_id),request('/research/evidence/'+asset.asset_id)]);
  view.innerHTML=`<div class="toolbar"><h2>Guía de observación: ${escapeHtml(asset.sample_code)}</h2><button id="back-study">Volver al censo</button></div><p>${escapeHtml(asset.description)} · ${escapeHtml(asset.site)}</p><details class="panel"><summary>Hallazgos del levantamiento operativo</summary>${evidence.map(e=>`<p>${escapeHtml(e.checked_at)} · ${escapeHtml(e.result)}<br>${escapeHtml(e.notes||'')}</p>`).join('')||'<p>Sin hallazgos operativos registrados.</p>'}</details><form id="measure-form" class="panel"><label class="field">Fase<select name="phase"><option>PRETEST</option><option>POSTTEST</option></select></label><p id="phase-status"></p>${criteria.map(([key,label])=>`<label class="field">${label}<select name="${key}" required><option value="">Seleccione</option><option value="true">Sí</option><option value="false">No</option></select></label>`).join('')}<label class="field">Método de identificación<input name="identificationMethod" maxlength="100" required placeholder="Procedimiento manual / lectura de código"></label><label class="field">Tiempo de identificación (milisegundos)<input type="number" name="identificationDurationMs" min="0" step="1" required></label><p class="muted">Registre el tiempo observado. Un equipo no localizado o sin medición no equivale a cero.</p><label class="field">Observaciones<textarea name="notes" maxlength="1000"></textarea></label><label class="field">Motivo de corrección (si ya existe medición)<input name="correctionReason" maxlength="1000"></label><button class="primary" id="save-measure">Guardar medición</button><div id="measure-message"></div></form>`;
  view.querySelector('#back-study').onclick=()=>navigate('research');const form=view.querySelector('#measure-form');
  let existing=null;
  const update=()=>{existing=observations.find(o=>o.asset_id===asset.asset_id&&o.phase===form.elements.phase.value);const closed=phases.phases.find(p=>p.phase===form.elements.phase.value)?.status==='CLOSED';view.querySelector('#save-measure').disabled=closed;view.querySelector('#phase-status').textContent=closed?'Fase cerrada: solo consulta.':existing?'Medición existente: toda corrección requiere motivo.':'Nueva medición.';criteria.forEach(([key,label,dbkey])=>form.elements[key].value=existing?String(existing[dbkey]):'');form.elements.identificationMethod.value=existing?.identification_method||'';form.elements.identificationDurationMs.value=existing?.identification_duration_ms??'';form.elements.notes.value=existing?.notes||'';form.elements.correctionReason.value='';};
  form.elements.phase.onchange=update;update();
  form.onsubmit=async event=>{event.preventDefault();const payload=readForm(form);criteria.forEach(([key])=>payload[key]=payload[key]==='true');payload.assetId=asset.asset_id;payload.identificationDurationMs=Number(payload.identificationDurationMs);payload.version=existing?.version;const button=view.querySelector('#save-measure');button.disabled=true;try{await request('/observations',{method:'POST',body:JSON.stringify(payload)});await studyScreen(view);}catch(e){showFormError(view, '#measure-message', e);button.disabled=false;}};
}
async function reportMeasurement(view) {
  view.innerHTML=`<h2>Tiempo de generación de reporte</h2><form class="panel"><label class="field">Código del par de mediciones<input name="measurementCode" minlength="3" maxlength="50" required></label><label class="field">Fase<select name="phase"><option>PRETEST</option><option>POSTTEST</option></select></label><label class="field">Tipo de reporte<input name="reportType" minlength="2" maxlength="100" required></label><label class="field">Duración (milisegundos)<input type="number" name="durationMs" min="0" step="1" required></label><button class="primary">Guardar tiempo</button><button type="button" id="cancel-report">Volver</button><div id="report-message"></div></form>`;
  view.querySelector('#cancel-report').onclick=()=>navigate('research');view.querySelector('form').onsubmit=async e=>{e.preventDefault();const p=readForm(e.target);p.durationMs=Number(p.durationMs);try{await request('/report-measurements',{method:'POST',body:JSON.stringify(p)});await studyScreen(view);}catch(error){showFormError(view, '#report-message', error);}};
}
async function studyHistory(view) {
  const rows=await request('/research/audit'); renderTable(view,'Historial del estudio',['Fecha','Acción','Entidad','Motivo'],rows.map(r=>[r.date,r.action,r.entity,r.details?.correctionReason||r.details?.reason||'']));
}

const assetFields = [
  ['sbn','Código patrimonial',12],['description','Descripción',250],['internalCode','Código interno',100],
  ['brand','Marca',100],['model','Modelo',100],['serialNumber','Serie',150],['executingUnit','Unidad ejecutora',30],
  ['site','Sede',150],['building','Edificio',100],['floor','Piso',50],['room','Ambiente',250],
  ['organizationalUnit','Unidad orgánica',150],['responsiblePerson','Responsable',500],['thirdPartyUser','Usuario tercero',500],
  ['processor','Procesador',500],['memory','Memoria',500],['storage','Almacenamiento',500],['operatingSystem','Sistema operativo',500]
];
async function assetEditor(view, asset = null) {
  const types=['TYPE_1','TYPE_2','TYPE_3','ALL_IN_ONE','CPU','MONITOR','KEYBOARD','LAPTOP','PRINTER'];
  view.innerHTML=`<h2>${asset?'Corregir ficha':'Registrar activo'}</h2><form class="panel" id="edit-asset">${cameraPanel()}<div class="grid2">${assetFields.map(([key,label,max])=>`<label class="field">${label}<input name="${key}" maxlength="${max}" value="${escapeHtml(asset?.[key]||'')}" ${['sbn','description','site'].includes(key)?'required':''} ${key==='sbn'?'pattern="[A-Za-z0-9]{12}"':''}></label>`).join('')}<label class="field">Tipo<select name="assetType">${types.map(type=>`<option value="${type}" ${asset?.assetType===type?'selected':''}>${typeLabel(type)}</option>`).join('')}</select></label><label class="field">Estado<select name="status">${['OPERATIVO','MANTENIMIENTO','BAJA','NO_OPERATIVO','INOPERATIVO','SIN_DATO'].map(value=>`<option ${asset?.status===value?'selected':''}>${value}</option>`).join('')}</select></label><label class="field">Condición<select name="condition">${['BUENO','REGULAR','MALO','NUEVO','FALTANTE'].map(value=>`<option ${asset?.condition===value?'selected':''}>${value}</option>`).join('')}</select></label></div><label class="field">Notas y procedencia<textarea name="notes">${escapeHtml(asset?.notes||'')}</textarea></label>${asset?'<label class="field">Motivo de corrección<input name="correctionReason" minlength="5" maxlength="1000" required></label>':''}<button class="primary">Guardar ficha</button><button type="button" id="cancel-asset">Cancelar</button><div id="asset-message"></div></form>`;
  const form=view.querySelector('#edit-asset');bindCamera(view,form.elements.sbn);
  view.querySelector('#cancel-asset').onclick=()=>navigate('assets');
  form.onsubmit=async event=>{event.preventDefault();const payload={...(asset||{}),...readForm(form)};payload.sbn=normalizeSbn(payload.sbn);const button=form.querySelector('.primary');button.disabled=true;try{const saved=await request('/assets'+(asset?'/'+asset.id:''),{method:asset?'PUT':'POST',body:JSON.stringify(payload)});await assetDetail(view,saved.id);}catch(error){showFormError(view, '#asset-message', error);button.disabled=false;}};
}
const originalAssetDetail=assetDetail;
assetDetail=async function(view,id){
  stopCamera();await originalAssetDetail(view,id);
  const groupButton=view.querySelector('#group-now');if(groupButton&&state.user.role!=='ADMIN')groupButton.hidden=true;
  if(state.user.role==='ADMIN'){
    const edit=document.createElement('button');edit.className='primary';edit.textContent='Corregir ficha';view.querySelector('.toolbar').append(edit);
    edit.onclick=async()=>assetEditor(view,await request('/assets/'+id));
  }
};
async function operationalGroups(view){
  const rows=await request('/asset-groups');
  view.innerHTML=`<h2>Agrupaciones de equipos</h2><p>Asocie únicamente componentes cuya pertenencia al mismo puesto haya sido comprobada.</p><div class="grid2"><form class="panel" id="create-group"><h3>Crear puesto</h3><label class="field">Código<input name="code" minlength="3" maxlength="30" required></label><label class="field">Nombre<input name="name" minlength="3" maxlength="150" required></label><label class="field">Sede<input name="site" minlength="2" maxlength="150" required></label><label class="field">Tipo<select name="groupType"><option value="ALL_IN_ONE">All in One</option><option value="TYPE_2">Tipo 2</option><option value="TYPE_3">Tipo 3</option></select></label><button class="primary">Crear grupo</button></form><form class="panel" id="join-group"><h3>Agregar componente</h3>${cameraPanel()}<label class="field">Código patrimonial<input name="sbn" pattern="[A-Za-z0-9]{12}" maxlength="12" required value="${escapeHtml(state.pendingSbn||'')}"></label><label class="field">Grupo<select name="group">${rows.map(g=>`<option value="${g.id}">${escapeHtml(g.code)} · ${escapeHtml(g.name)}</option>`).join('')}</select></label><label class="field">Función<select name="componentRole"><option value="INTEGRATED_UNIT">Unidad integrada (All in One)</option><option value="CPU">CPU</option><option value="MONITOR">Monitor</option><option value="KEYBOARD">Teclado</option></select></label><button class="primary" ${rows.length?'':'disabled'}>Agregar componente</button></form></div><div id="groups-message"></div><div class="session-grid">${rows.map(g=>`<article class="panel"><h3>${escapeHtml(g.code)} · ${escapeHtml(g.name)}</h3><p>${g.complete?'Completo':'Pendiente: '+escapeHtml(g.missingRoles.join(', '))}</p>${g.members.map(m=>`<p>${escapeHtml(m.sbn)} · ${escapeHtml(typeLabel(m.assetType))}</p>`).join('')}</article>`).join('')}</div>`;
  const join=view.querySelector('#join-group');bindCamera(join,join.elements.sbn);
  view.querySelector('#create-group').onsubmit=async e=>{e.preventDefault();try{await request('/asset-groups',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(e.target)))});await operationalGroups(view);}catch(error){view.querySelector('#groups-message').innerHTML=notice(error.message);}};
  join.onsubmit=async e=>{e.preventDefault();const p=Object.fromEntries(new FormData(join));try{await request(`/asset-groups/${p.group}/members`,{method:'POST',body:JSON.stringify(p)});state.pendingSbn=null;stopCamera();await operationalGroups(view);}catch(error){view.querySelector('#groups-message').innerHTML=notice(error.message);}};
}
screens.inventory=mobileInventory;screens.users=manageUsers;screens.research=studyScreen;screens.scanner=realScanner;screens.studyAudit=studyHistory;screens.register=assetEditor;screens.groups=operationalGroups;
localStorage.removeItem('itam_sbn_token');localStorage.removeItem('itam_sbn_user');
(async()=>{try{const response=await fetch('/api/auth/me');if(!response.ok){renderLogin();return;}state.user=await response.json();state.screen=state.user.mustChangePassword?'settings':homeScreen();renderShell();}catch(_){renderLogin();}})();
