const API = '/api';
const app = document.querySelector('#app');
const state = {
  token: null,
  user: null,
  screen: 'dashboard',
  scanIndex: -1,
  flowStep: 1,
  pendingRegistrationSbn: null,
  pendingSbn: null,
  pendingGroupId: null,
  pendingScanValue: null,
  completedGroup: null
};

const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
})[char]);
const notice = (text, type = 'error') => `<div class="alert ${type}">${escapeHtml(text)}</div>`;

async function request(path, options = {}) {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) headers.set('content-type', 'application/json');
  const csrf = document.cookie.split('; ').find(value => value.startsWith('csrf_access_token='))?.split('=')[1];
  if (csrf) headers.set('X-CSRF-TOKEN', decodeURIComponent(csrf));
  const response = await fetch(API + path, { ...options, headers });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if ((response.status === 401 || response.status === 422) && !path.endsWith('/auth/login')) {
      localStorage.removeItem('itam_sbn_token');
      localStorage.removeItem('itam_sbn_user');
      state.token = null;
      state.user = null;
      renderLogin();
      throw new Error('La sesión anterior ya no es válida. Inicie sesión nuevamente.');
    }
    throw new Error(data.issues?.map(issue => issue.message).join(' ') || data.message || data.msg || 'No fue posible completar la operación.');
  }
  return data;
}

async function logout() {
  stopCamera();
  try { await request('/auth/logout', {method: 'POST'}); } catch (_) {}
  sessionStorage.clear();
  localStorage.removeItem('itam_sbn_token');
  localStorage.removeItem('itam_sbn_user');
  state.token = null;
  state.user = null;
  renderLogin();
}

function renderLogin() {
  app.innerHTML = `<main class="login"><section class="login-card">
    <div class="brand"><div class="brand-mark">▣</div><h1>Gestor de Activos TI Físicos</h1><p class="muted">Operación, ciclo de vida y trazabilidad de activos</p></div>
    <div id="login-message"></div>
    <form id="login-form">
      <label class="field">Usuario o correo<input name="username" value="admin" required autocomplete="username"></label>
      <label class="field">Contraseña<input name="password" type="password" required autocomplete="current-password"></label>
      <button class="primary wide">Ingresar</button>
    </form></section></main>`;
  document.querySelector('#login-form').onsubmit = async event => {
    event.preventDefault();
    try {
      const result = await request('/auth/login', { method: 'POST', body: JSON.stringify(Object.fromEntries(new FormData(event.target))) });
      state.token = null;
      state.user = result.user;


      state.screen = state.user.mustChangePassword ? 'settings' : homeScreen();
      renderShell();
    } catch (error) {
      document.querySelector('#login-message').innerHTML = notice(error.message);
    }
  };
}

const menu = [
  ['dashboard', '▦  Panel de control'], ['assets', '▣  Activos TI'], ['register', '＋  Registrar activo'],
  ['scanner', 'Consultar etiqueta'], ['groups', '⌘  Agrupaciones'], ['inventory', 'Verificación física'], ['research', 'Cobertura operativa'], ['indicators', 'Indicadores'], ['users', 'Usuarios'], ['catalogs', 'Catálogos'], ['audit', 'Auditoría'], ['settings', '⚙  Configuración']
];

function renderShell() {
  app.innerHTML = `<div class="shell"><aside class="sidebar"><h1>▣ Activos TI</h1>
    <small>${escapeHtml(state.user.fullName)}<br>${escapeHtml(roleNames[state.user.role] || state.user.role)}</small><nav class="nav">
    ${visibleMenu().map(([id, label]) => `<button data-screen="${id}">${label}</button>`).join('')}
    <button id="logout">Cerrar sesión</button></nav></aside><section class="content">
    <header class="topbar"><button class="mobile-menu" id="toggle-menu" aria-label="Abrir menú">☰</button><strong id="title"></strong><span>MySQL · Flask</span></header><main class="main" id="view"></main>
    </section></div>`;
  document.querySelectorAll('[data-screen]').forEach(button => button.onclick = () => navigate(button.dataset.screen));
  document.querySelector('#logout').onclick = logout;
  document.querySelector('#toggle-menu').onclick = () => document.querySelector('.sidebar').classList.toggle('open');
  navigate(state.screen);
}

async function navigate(screen) {
  stopCamera();
  if (!visibleMenu().some(([id]) => id === screen)) screen = homeScreen();
  if (state.user.mustChangePassword) screen = 'settings';
  state.screen = screen;
  document.querySelector('.sidebar')?.classList.remove('open');
  document.querySelectorAll('[data-screen]').forEach(button => button.classList.toggle('active', button.dataset.screen === screen));
  document.querySelector('#title').textContent = menu.find(item => item[0] === screen)?.[1] || 'Sistema';
  const view = document.querySelector('#view');
  view.innerHTML = '<p class="loading">Cargando…</p>';
  try { await screens[screen](view); } catch (error) { view.innerHTML = notice(error.message); }
}

async function dashboard(view) {
  const data = await request('/dashboard');
  const cards = [['Total', data.totals.total], ['Operativos', data.totals.operational], ['Completos', data.totals.complete_consistent], ['SBN verificados', data.totals.barcode_verified]];
  view.innerHTML = `<div class="page-heading"><div><span class="eyebrow">GESTIÓN DE ACTIVOS TI</span><h2>Resumen operativo</h2><p>Control del ciclo de vida, estado y ubicación de activos tecnológicos físicos.</p></div><div class="page-actions">${state.user.role === 'ADMIN' ? '<button class="secondary" id="export-movements">Exportar movimientos CSV</button>' : ''}</div></div><div class="cards">${cards.map(([label, value], index) => `<div class="card stat-${index + 1}"><span>${label}</span><strong>${value}</strong></div>`).join('')}</div>
    <div class="group-alert-summary"><div><strong>${data.grouping?.ungroupedComponents || 0}</strong><span>componentes sin agrupación</span></div><div><strong>${data.grouping?.incompleteGroups || 0}</strong><span>grupos incompletos</span></div><button class="primary" id="review-groups">Revisar agrupaciones</button></div>
    <section class="panel operational-alerts"><div class="section-title"><div><h3>Alertas operativas</h3><p class="muted">Prioriza los registros que requieren revisión.</p></div><span class="alert-total">${data.alertTotal || 0}</span></div><div class="alert-grid">${(data.alerts || []).map(alert => `<article class="alert-card ${escapeHtml(alert.severity || 'info')}"><div><strong>${escapeHtml(alert.label)}</strong><span>${alert.note ? escapeHtml(alert.note) : (alert.count ? 'Requiere revisión' : 'Sin pendientes')}</span></div><b>${alert.count}</b></article>`).join('')}</div></section>
    <div class="grid2"><section class="panel"><h3>Por tipo</h3>${data.byType.map(row => `<div class="row"><span>${escapeHtml(row.type)}</span><strong>${row.total}</strong></div>`).join('')}</section>
    <section class="panel"><h3>Por sede</h3>${data.bySite.map(row => `<div class="row"><span>${escapeHtml(row.site)}</span><strong>${row.total}</strong></div>`).join('')}</section></div>
    <section class="panel" style="margin-top:18px"><h3>Actualizados recientemente</h3>${data.recent.map(asset => `<button class="row list-button" data-asset="${asset.id}"><span><strong>${asset.sbn}</strong><br>${escapeHtml(asset.description)}</span><span>${escapeHtml(asset.site)}</span></button>`).join('')}</section>`;
  view.querySelectorAll('[data-asset]').forEach(button => button.onclick = () => assetDetail(view, button.dataset.asset));
  view.querySelector('#review-groups').onclick = () => navigate('groups');
  const exportButton = view.querySelector('#export-movements');
  if (exportButton) exportButton.onclick = async () => {
    exportButton.disabled = true;
    exportButton.textContent = 'Preparando?';
    try {
      const response = await fetch(API + '/movements.csv', { credentials: 'same-origin' });
      if (!response.ok) throw new Error('No fue posible generar el reporte.');
      const blob = await response.blob();
      const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = 'movimientos.csv'; link.click();
      setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    } catch (error) { view.insertAdjacentHTML('afterbegin', notice(error.message)); }
    finally { exportButton.disabled = false; exportButton.textContent = 'Exportar movimientos CSV'; }
  };
}

async function assets(view) {
  view.innerHTML = `<div class="toolbar"><div><h2>Activos físicos</h2><span id="count" class="muted"></span></div><button class="primary" id="new">Registrar activo</button></div>
    <div class="filters"><input id="search" placeholder="SBN, serie, descripción o responsable"><select id="type"><option value="">Todos los activos</option><option value="TYPE_1">Tipo 1 - All in One</option><option value="TYPE_2">Tipo 2 - CPU</option><option value="TYPE_3">Tipo 3 - Workstation</option><option value="ALL_IN_ONE">All in One integrado</option><option value="MONITOR">Monitor / pantalla</option><option value="KEYBOARD">Teclado</option><option value="CPU">CPU</option><option value="LAPTOP">Laptop</option><option value="PRINTER">Impresora</option></select><select id="status"><option value="">Todos los estados</option><option>OPERATIVO</option><option>MANTENIMIENTO</option><option>BAJA</option><option>NO_OPERATIVO</option><option>INOPERATIVO</option><option>SIN_DATO</option></select></div><div id="asset-table"></div><div class="toolbar"><button id="previous">Anterior</button><span id="page-label"></span><button id="next">Siguiente</button></div>`;
  view.querySelector('#new').hidden = state.user.role !== 'ADMIN';
  view.querySelector('#new').onclick = () => navigate('register');
  let timer; let page = 1; let lastPage = 1; let loadVersion = 0;
  const load = async () => {
    const version = ++loadVersion;
    const query = new URLSearchParams({ search: view.querySelector('#search').value, type: view.querySelector('#type').value, status: view.querySelector('#status').value, pageSize: '100', page: String(page) });
    const [data, groups] = await Promise.all([request('/assets?' + query), state.user.role === 'ADMIN' ? request('/asset-groups') : Promise.resolve([])]);
    if (version !== loadVersion || state.screen !== 'assets') return;
    lastPage = Math.max(1, Math.ceil(data.total / data.pageSize));
    view.querySelector('#page-label').textContent = `Página ${page} de ${lastPage}`;
    view.querySelector('#previous').disabled = page <= 1;
    view.querySelector('#next').disabled = page >= lastPage;
    view.querySelector('#count').textContent = `${data.total} registros`;
    const visible = new Map(data.items.map(asset => [asset.id, asset]));
    const groupedIds = new Set(groups.flatMap(group => group.members.map(member => member.assetId)));
    const renderMember = member => {
      const asset = visible.get(member.assetId);
      if (!asset) return '';
      return `<tr data-id="${asset.id}"><td><button class="sbn-chip">${asset.sbn}</button></td><td><strong>${escapeHtml(asset.description)}</strong><small>${escapeHtml(asset.brand || '')} ${escapeHtml(asset.model || '')}</small></td><td>${member.componentRole === 'INTEGRATED_UNIT' ? 'Pantalla + procesador' : typeLabel(member.componentRole)}</td><td>${escapeHtml(asset.site)}</td><td><span class="badge">${asset.status}</span></td></tr>`;
    };
    const groupBlocks = groups.map(group => {
      const memberRows = group.members.map(renderMember).filter(Boolean).join('');
      if (!memberRows) return '';
      return `<section class="asset-group-block"><header><div class="group-symbol">${group.groupType === 'ALL_IN_ONE' ? 'AIO' : group.groupType === 'TYPE_2' ? 'T2' : 'WS'}</div><div><span class="eyebrow">${group.groupType === 'ALL_IN_ONE' ? 'ALL IN ONE' : group.groupType === 'TYPE_2' ? 'PC TIPO 2' : 'PC TIPO 3 · WORKSTATION'}</span><h3>${escapeHtml(group.name)}</h3><code>${group.code}</code></div><div class="group-meta"><span>${group.members.length} componentes</span><strong class="${group.complete ? 'complete-text' : 'warning-text'}">${group.complete ? '✓ Grupo completo' : `⚠ Faltan ${group.missingRoles.length}`}</strong></div></header><div class="table-wrap embedded"><table><thead><tr><th>SBN</th><th>Activo</th><th>Función</th><th>Sede</th><th>Estado</th></tr></thead><tbody>${memberRows || '<tr><td colspan="5" class="muted">Ningún componente coincide con el filtro.</td></tr>'}</tbody></table></div></section>`;
    }).join('');
    const independent = data.items.filter(asset => !groupedIds.has(asset.id));
    const independentRows = independent.map(asset => `<tr data-id="${asset.id}" class="${asset.groupingAlert ? 'warning-row' : ''}"><td><button class="sbn-chip">${asset.sbn}</button></td><td><strong>${escapeHtml(asset.description)}</strong><small>${escapeHtml(asset.brand || '')} ${escapeHtml(asset.model || '')}</small></td><td>${typeLabel(asset.assetType)}</td><td>${asset.groupingAlert ? '<span class="badge group-warning">⚠ Pendiente de agrupación</span>' : '<span class="muted">Activo independiente</span>'}</td><td><span class="badge">${asset.status}</span></td></tr>`).join('');
    view.querySelector('#asset-table').innerHTML = `<div class="assets-by-group">${groupBlocks}</div><section class="asset-group-block independent-block"><header><div class="group-symbol neutral">•••</div><div><span class="eyebrow">SIN GRUPO DE EQUIPO</span><h3>Activos independientes y pendientes</h3><p>${independent.length} registros</p></div></header><div class="table-wrap embedded"><table><thead><tr><th>SBN</th><th>Activo</th><th>Tipo</th><th>Clasificación</th><th>Estado</th></tr></thead><tbody>${independentRows || '<tr><td colspan="5" class="muted">No hay activos en esta sección.</td></tr>'}</tbody></table></div></section>`;
    view.querySelectorAll('[data-id]').forEach(row => row.onclick = () => assetDetail(view, row.dataset.id));
  };
  view.querySelectorAll('.filters input,.filters select').forEach(control => control.oninput = () => { clearTimeout(timer); page = 1; timer = setTimeout(() => load().catch(error => { view.querySelector("#asset-table").innerHTML = notice(error.message); }), 250); });
  view.querySelector("#previous").onclick = () => { if (page > 1) { page--; load().catch(error => uiMessage(error.message)); } };
  view.querySelector("#next").onclick = () => { if (page < lastPage) { page++; load().catch(error => uiMessage(error.message)); } };
  await load();
}

async function assetDetail(view, id) {
  const asset = await request('/assets/' + id);
  const technical = [['Descripción', asset.description], ['Tipo', asset.assetType], ['Marca', asset.brand], ['Modelo', asset.model], ['Serie', asset.serialNumber], ['Estado', asset.status], ['Condición', asset.condition], ['Código interno', asset.internalCode], ['Unidad ejecutora', asset.executingUnit], ['Procedencia y observaciones', asset.notes]];
  const location = [['Sede', asset.site], ['Edificio', asset.building], ['Piso', asset.floor], ['Ambiente', asset.room], ['Responsable', asset.responsiblePerson], ['Unidad', asset.organizationalUnit]];
  const rows = values => values.map(([label, value]) => `<div class="row"><span>${label}</span><strong>${escapeHtml(value || '—')}</strong></div>`).join('');
  const grouping = asset.assetGroup || asset.grouping?.group;
  view.innerHTML = `<div class="toolbar"><div><span class="eyebrow">FICHA DEL ACTIVO</span><h2>${asset.sbn}</h2></div><button class="secondary" id="back">Volver</button></div>${asset.groupingAlert ? `<div class="alert warning"><strong>⚠ Componente sin agrupación.</strong> Este activo está inventariado, pero todavía no pertenece a un equipo completo. <button class="secondary" id="group-now">Agrupar ahora</button></div>` : grouping ? `<div class="alert success">✓ Pertenece a <strong>${escapeHtml(grouping.code)}</strong> · ${escapeHtml(grouping.name)}</div>` : ''}<div class="grid2"><section class="panel">${rows(technical)}</section><section class="panel">${rows(location)}</section></div>`;
  view.querySelector('#back').onclick = () => navigate('assets');
  const groupButton = view.querySelector('#group-now'); if (groupButton) groupButton.onclick = () => { state.pendingSbn = asset.sbn; navigate('groups'); };
}

function typeLabel(type) {
  return ({ ALL_IN_ONE: 'All in One integrado', MONITOR: 'Monitor / pantalla', KEYBOARD: 'Teclado', CPU: 'CPU',
    TYPE_1: 'Tipo 1', TYPE_2: 'Tipo 2', TYPE_3: 'Workstation', LAPTOP: 'Laptop', PRINTER: 'Impresora' })[type] || type;
}

function flowProgress(activeStep) {
  const steps = [['1', 'Consultar'], ['2', 'Registrar'], ['3', 'Agrupar'], ['4', 'Finalizar']];
  return `<section class="flow-progress"><div class="flow-title"><span class="flow-mode">FLUJO</span><strong>Proceso de lectura y registro del código patrimonial</strong></div><div class="flow-steps">${steps.map(([number, label], index) => `<div class="flow-step ${index + 1 < activeStep ? 'done' : ''} ${index + 1 === activeStep ? 'active' : ''}"><span>${index + 1 < activeStep ? '✓' : number}</span><small>${label}</small></div>`).join('')}</div></section>`;
}

function newScanSbn() {
  return `777${String(Date.now()).slice(-9)}`;
}

function scannerBox(inputId, context, title = 'Leer código SBN') {
  return `<section class="scanner-box reader-only"><div class="scanner-copy"><span class="scanner-icon">▥</span><div><span class="reader-mode light">LECTURA</span><strong>${title}</strong><p>Preparando la validación del código patrimonial.</p></div></div><button type="button" class="scan-button" data-reader-for="${inputId}" data-context="${context}">▶ Iniciar lectura</button><div class="reader-area hidden" id="reader-${inputId}"><div class="barcode-view"><div class="barcode-bars"></div><strong></strong><small>Procesando etiqueta patrimonial…</small></div><div class="scan-line"></div></div><p class="scan-status" id="status-${inputId}"></p></section>`;
}

function bindScanner(view, inputId, onDetected, valueProvider) {
  const scanButton = view.querySelector(`[data-reader-for="${inputId}"]`);
  const area = view.querySelector(`#reader-${inputId}`);
  const status = view.querySelector(`#status-${inputId}`);
  scanButton.onclick = async () => {
    const scanValues = ['888100000001', '888200000003', '888900000001', '888300000002'];
    state.scanIndex = (state.scanIndex + 1) % scanValues.length;
    const value = valueProvider ? valueProvider() : scanValues[state.scanIndex];
    area.querySelector('strong').textContent = value;
    area.classList.remove('hidden');
    scanButton.disabled = true;
    status.textContent = 'Leyendo la etiqueta SBN...';
    status.className = 'scan-status';
    await new Promise(resolve => setTimeout(resolve, 1400));
    const input = view.querySelector(`#${inputId}`);
    input.value = value;
    input.dispatchEvent(new Event('change', { bubbles: true }));
    area.classList.add('hidden');
    scanButton.disabled = false;
    status.textContent = `SBN ${value} detectado y completado.`;
    status.className = 'scan-status success-text';
    if (onDetected) await onDetected(value);
  };
}

async function register(view) {
  state.completedGroup = null;
  const initialSbn = state.pendingRegistrationSbn || '';
  state.pendingRegistrationSbn = null;
  state.flowStep = Math.max(state.flowStep, 2);
  view.innerHTML = `${flowProgress(2)}<div class="page-heading"><span class="eyebrow">PASO 2 · NUEVO REGISTRO</span><h2>Registrar activo o componente</h2><p>El SBN se valida y los datos patrimoniales se completan en el formulario.</p></div><div id="form-message"></div><form class="panel asset-form" id="asset-form">${scannerBox('register-sbn', 'register', 'Leer una etiqueta SBN nueva')}<div class="form-helper"><div><strong>Datos del activo</strong><p>Puede completarlos manualmente o cargar un ejemplo de referencia.</p></div><button type="button" class="secondary" id="fill-reference">Completar datos de ejemplo</button></div><div class="form-grid">
    <label class="field">Código SBN<input id="register-sbn" name="sbn" value="${escapeHtml(initialSbn)}" pattern="[A-Za-z0-9]{12}" maxlength="12" placeholder="000000000000" required></label><label class="field">Clase de activo<select name="assetType"><option value="MONITOR">Monitor / pantalla</option><option value="KEYBOARD">Teclado</option><option value="CPU">CPU de escritorio / workstation</option><option value="ALL_IN_ONE">All in One con procesador integrado</option><option value="LAPTOP">Laptop</option><option value="PRINTER">Impresora</option></select></label>
    <label class="field full">Descripción<input name="description" minlength="3" required></label><label class="field">Marca<input name="brand"></label><label class="field">Modelo<input name="model"></label><label class="field">Serie<input name="serialNumber"></label><label class="field">Unidad ejecutora<input name="executingUnit"></label><label class="field">Sede<input name="site" required></label><label class="field">Responsable<input name="responsiblePerson"></label>
    <label class="field">Estado<select name="status"><option>OPERATIVO</option><option>MANTENIMIENTO</option><option>BAJA</option><option>NO_OPERATIVO</option><option>INOPERATIVO</option><option>SIN_DATO</option></select></label><label class="field">Condición<select name="condition"><option>BUENO</option><option>REGULAR</option><option>MALO</option><option>NUEVO</option><option>FALTANTE</option></select></label></div><button class="primary">Guardar y continuar a agrupación →</button></form>`;
  view.querySelector('#fill-reference').onclick = () => {
    const form = view.querySelector('#asset-form');
    form.elements.assetType.value = 'MONITOR';
    form.elements.description.value = 'Monitor empresarial';
    form.elements.brand.value = 'Dell';
    form.elements.model.value = 'P2425H';
    form.elements.serialNumber.value = `REF-${String(Date.now()).slice(-6)}`;
    form.elements.executingUnit.value = 'Unidad de Tecnologías de Información';
    form.elements.site.value = 'Sede Central';
    form.elements.responsiblePerson.value = 'Usuario del área';
  };
  view.querySelector('#asset-form').onsubmit = async event => {
    event.preventDefault(); const payload = Object.fromEntries(new FormData(event.target));
    Object.assign(payload, { installedSoftware: [], recordComplete: false, recordConsistent: false, correctlyRegistered: false, recordUpdated: false, barcodeVerified: false });
    try {
      const created = await request('/assets', { method: 'POST', body: JSON.stringify(payload) });
      state.pendingSbn = created.sbn;
      state.flowStep = 3;
      navigate('groups');
    }
    catch (error) { view.querySelector('#form-message').innerHTML = notice(error.message); }
  };
  bindScanner(view, 'register-sbn', null, () => initialSbn || newScanSbn());
}

async function scanner(view) {
  state.completedGroup = null;
  state.pendingGroupId = null;
  state.flowStep = 1;
  view.innerHTML = `${flowProgress(1)}<div class="page-heading"><span class="eyebrow">PASO 1 · CONSULTA</span><h2>Consultar activo por SBN</h2><p>Seleccione el tipo de consulta o introduzca el código patrimonial para continuar.</p></div><section class="scan-scenarios"><button class="scenario-card existing" id="existing-asset"><span>✓</span><div><strong>Activo inventariado</strong><small>Busca un SBN ya dado de alta y verifica su agrupación.</small></div></button><button class="scenario-card new" id="new-asset"><span>＋</span><div><strong>Etiqueta nueva</strong><small>Si no existe, se habilita el alta del registro.</small></div></button></section><section class="panel scan-panel">${scannerBox('query-sbn', 'query')}<form id="scan"><label class="field">Código SBN<input id="query-sbn" name="sbn" pattern="[A-Za-z0-9]{12}" maxlength="12" placeholder="Ingrese el código patrimonial" required></label><button class="primary wide">Consultar en inventario</button></form><div id="result"></div></section>`;
  const findAsset = async value => { const result = view.querySelector('#result'); result.innerHTML = '<p class="loading">Consultando inventario…</p>'; try { const asset = await request('/assets/sbn/' + value); result.innerHTML = `<article class="scan-result"><div class="result-head"><span class="result-check">✓</span><div><span class="eyebrow">ACTIVO INVENTARIADO</span><h3>${escapeHtml(asset.description)}</h3><strong class="sbn-large">${asset.sbn}</strong></div></div>${asset.groupingAlert ? '<div class="alert warning"><strong>⚠ Alerta de agrupación:</strong> este componente está registrado, pero no pertenece a ningún equipo.</div>' : asset.assetGroup ? `<div class="alert success">✓ Agrupado en <strong>${escapeHtml(asset.assetGroup.code)}</strong> · ${escapeHtml(asset.assetGroup.name)}</div>` : ''}<div class="result-grid"><span>Tipo<strong>${typeLabel(asset.assetType)}</strong></span><span>Marca / modelo<strong>${escapeHtml(asset.brand || '—')} ${escapeHtml(asset.model || '')}</strong></span><span>Sede<strong>${escapeHtml(asset.site)}</strong></span><span>Responsable<strong>${escapeHtml(asset.responsiblePerson || 'Sin asignar')}</strong></span></div><div class="actions"><button class="primary" id="open">Ver ficha completa</button>${asset.groupingAlert ? '<button class="secondary" id="group-result">Continuar y agrupar →</button>' : ''}</div></article>`; result.querySelector('#open').onclick = () => assetDetail(view, asset.id); const groupButton = result.querySelector('#group-result'); if (groupButton) groupButton.onclick = () => { state.pendingSbn = asset.sbn; state.flowStep = 3; navigate('groups'); }; } catch (error) { state.pendingRegistrationSbn = value; result.innerHTML = `<div class="not-found"><span>×</span><h3>SBN no inventariado</h3><p>${escapeHtml(error.message)}</p><div class="alert info">La etiqueta no existe en el inventario y debe darse de alta antes de agruparla.</div><button class="primary" id="register-result">Registrar este SBN →</button></div>`; result.querySelector('#register-result').onclick = () => { state.flowStep = 2; navigate('register'); }; } };
  view.querySelector('#scan').onsubmit = event => { event.preventDefault(); findAsset(new FormData(event.target).get('sbn')); };
  <button type="button" class="secondary" id="fill-reference">Completar datos de referencia</button></div><div class="form-grid">
    view.querySelector('#query-sbn').value = value;
    state.pendingScanValue = value;
    button.disabled = true;
    button.classList.add('running');
    const readerButton = view.querySelector('[data-reader-for="query-sbn"]');
    readerButton.click();
    button.disabled = false;
    button.classList.remove('running');
  };
  view.querySelector('#existing-asset').onclick = event => runScenario('888900000001', event.currentTarget);
  view.querySelector('#new-asset').onclick = event => runScenario(newScanSbn(), event.currentTarget);
  const reader = view.querySelector('[data-reader-for="query-sbn"]');
  const originalProvider = () => state.pendingScanValue || ['888100000001', '888200000003', '888900000001', '888300000002'][state.scanIndex];
  bindScanner(view, 'query-sbn', async value => { state.pendingScanValue = null; await findAsset(value); }, originalProvider);
}

async function indicators(view) {
  const [pre, post] = await Promise.all([request('/indicators?phase=PRETEST'), request('/indicators?phase=POSTTEST')]);
  const display = item => (item.denominator ?? item.measurements) > 0 ? `${item.value} ${item.unit}` : 'Sin mediciones';
  view.innerHTML = `<h2>Indicadores de tesis</h2><div class="table-wrap"><table><thead><tr><th>Indicador</th><th>Pretest</th><th>Postest</th></tr></thead><tbody>${['PRCC', 'TPGR', 'PACI', 'TPI', 'PACR', 'PRA'].map(key => `<tr><td><strong>${key}</strong></td><td>${display(pre[key])}</td><td>${display(post[key])}</td></tr>`).join('')}</tbody></table></div><p class="muted">Pares completos: ${post.sampleSize}. Cobertura del estudio: ${post.selectedSize}/${post.targetSize}.</p>`;
}

async function research(view) {
  const data = await request('/research/sample');
  view.innerHTML = `<div class="toolbar"><div><h2>Datos de investigación</h2><p class="muted">Censo de equipos de cómputo · Sede Central, edificios Libros y El Comercio · Población: ${data.settings.populationSize} · Objetivo: ${data.settings.targetSize}</p></div></div><div class="cards"><div class="card">Seleccionados<strong>${data.summary.selected}</strong></div><div class="card">Pretest<strong>${data.summary.pretestCount}</strong></div><div class="card">Postest<strong>${data.summary.posttestCount}</strong></div><div class="card">Pares<strong>${data.summary.pairedCount}</strong></div></div><section class="panel" style="margin-top:18px"><h3>Distribución</h3>${data.byStratum.map(row => `<div class="row"><span>${row.stratum}</span><strong>${row.total}</strong></div>`).join('') || '<p>Sin muestra generada.</p>'}</section><section class="panel"><h3>Equipos incluidos en el censo</h3><p>Se incluyen todos los equipos de cómputo registrados en los edificios Libros y El Comercio, sin impresoras ni periféricos. El censo no implica que las mediciones ya se hayan realizado.</p><div class="table-wrap"><table><thead><tr><th>Código</th><th>SBN / código patrimonial</th><th>Tipo</th><th>Sede</th></tr></thead><tbody>${data.items.map(item => `<tr><td>${escapeHtml(item.sample_code)}</td><td><button data-sample-asset="${item.asset_id}">${escapeHtml(item.sbn)}</button></td><td>${escapeHtml(typeLabel(item.stratum))}</td><td>${escapeHtml(item.site)}</td></tr>`).join('')}</tbody></table></div></section>`;
  view.querySelectorAll('[data-sample-asset]').forEach(button => button.onclick = () => assetDetail(view, button.dataset.sampleAsset));
}

async function groups(view) {
  const [groups, assetsData] = await Promise.all([request('/asset-groups'), request('/assets?pageSize=500&ungrouped=1')]);
  const ungrouped = assetsData.items.filter(asset => asset.groupingAlert);
  const pending = state.pendingSbn || ungrouped[0]?.sbn || '';
  const completed = state.completedGroup;
  const activeStep = completed ? 4 : 3;
  state.flowStep = activeStep;
  view.innerHTML = `${flowProgress(activeStep)}${completed ? `<section class="flow-complete"><span>✓</span><div><strong>Operación completada</strong><p>El SBN fue consultado, registrado y agregado al grupo <b>${escapeHtml(completed.code)}</b>.</p></div><button class="secondary" id="restart-flow">Reiniciar flujo</button></section>` : ''}<div class="page-heading"><span class="eyebrow">PASO ${activeStep} · CONFIGURACIÓN DE PUESTOS</span><h2>Agrupaciones de activos</h2><p>Revise el componente y asígnelo al equipo correspondiente.</p></div>
    <div class="group-layout"><section><div class="section-title"><h3>Equipos agrupados</h3><span>${groups.length} grupos</span></div><div class="group-cards">${groups.map(group => `<article class="group-card ${group.complete ? 'complete' : 'incomplete'}"><header><div><span class="group-type">${group.groupType === 'ALL_IN_ONE' ? 'ALL IN ONE' : group.groupType === 'TYPE_2' ? 'PC TIPO 2' : 'WORKSTATION TIPO 3'}</span><h3>${escapeHtml(group.name)}</h3><code>${group.code}</code></div><span class="completion">${group.complete ? '✓ Completo' : '⚠ Incompleto'}</span></header><div class="component-list">${group.members.map(member => `<div><span>${member.componentRole === 'INTEGRATED_UNIT' ? 'Pantalla + procesador' : typeLabel(member.componentRole)}</span><strong>${member.sbn}</strong><small>${escapeHtml(member.description)}</small></div>`).join('')}${group.missingRoles.map(role => `<div class="missing"><span>${role === 'INTEGRATED_UNIT' ? 'Pantalla + procesador' : typeLabel(role)}</span><strong>Componente faltante</strong></div>`).join('')}</div></article>`).join('')}</div></section>
    <aside><section class="panel sticky-panel"><h3>Agrupar componente</h3><p class="muted">Identifique el componente y asócielo al grupo correcto.</p><div id="group-message"></div>${scannerBox('group-sbn', 'group', 'Leer código del componente')}<form id="member-form"><label class="field">SBN detectado<input id="group-sbn" name="sbn" value="" placeholder="Ingrese el SBN o lea la etiqueta" required></label><label class="field">Grupo de destino<select name="groupId" id="target-group">${groups.map(group => `<option value="${group.id}" data-type="${group.groupType}" ${String(group.id) === String(state.pendingGroupId) ? 'selected' : ''}>${group.code} · ${escapeHtml(group.name)}</option>`).join('')}</select></label><label class="field">Función del componente<select name="componentRole" id="component-role"></select></label><button class="primary wide" ${!groups.length ? 'disabled' : ''}>Guardar agrupación y finalizar</button></form><hr><h3>Crear grupo nuevo</h3><p class="muted">Cree un puesto vacío y luego agregue el componente identificado.</p><form id="new-group"><label class="field">Código<input name="code" value="GR-${String(Date.now()).slice(-5)}" required></label><label class="field">Tipo<select name="groupType"><option value="TYPE_2">PC Tipo 2</option><option value="TYPE_3">Workstation Tipo 3</option><option value="ALL_IN_ONE">All in One</option></select></label><label class="field">Nombre<input name="name" value="Puesto de trabajo" required></label><label class="field">Sede<input name="site" value="Sede Central" required></label><button class="secondary wide">Crear grupo vacío</button></form></section></aside></div>
    <section class="panel orphan-panel"><h3>⚠ Componentes pendientes de agrupación</h3><p class="muted">Se muestran hasta 500 pendientes. Puede indicar cualquier SBN inventariado.</p>${ungrouped.length ? `<div class="orphan-grid">${ungrouped.map(asset => `<button data-orphan="${asset.sbn}"><strong>${asset.sbn}</strong><span>${typeLabel(asset.assetType)}</span><small>${escapeHtml(asset.description)}</small></button>`).join('')}</div>` : '<div class="alert success">No hay componentes pendientes en esta consulta.</div>'}</section>`;
  const roleSelect = view.querySelector('#component-role'); const groupSelect = view.querySelector('#target-group');
  const refreshRoles = () => { const type = groupSelect.selectedOptions[0]?.dataset.type; const roles = type === 'ALL_IN_ONE' ? [['INTEGRATED_UNIT', 'Pantalla con procesador integrado'], ['KEYBOARD', 'Teclado']] : [['MONITOR', 'Monitor / pantalla'], ['KEYBOARD', 'Teclado'], ['CPU', 'CPU']]; roleSelect.innerHTML = roles.map(([value, label]) => `<option value="${value}">${label}</option>`).join(''); const scanned = ungrouped.find(asset => asset.sbn === view.querySelector('#group-sbn').value); const expectedRole = ['ALL_IN_ONE', 'TYPE_1'].includes(scanned?.assetType) ? 'INTEGRATED_UNIT' : ['TYPE_2', 'TYPE_3'].includes(scanned?.assetType) ? 'CPU' : scanned?.assetType; if ([...roleSelect.options].some(option => option.value === expectedRole)) roleSelect.value = expectedRole; };
  refreshRoles(); groupSelect.onchange = refreshRoles;
  bindScanner(view, 'group-sbn', refreshRoles, () => pending);
  view.querySelectorAll('[data-orphan]').forEach(button => button.onclick = () => { state.pendingSbn = button.dataset.orphan; navigate('groups'); });
  view.querySelector('#member-form').onsubmit = async event => { event.preventDefault(); const values = Object.fromEntries(new FormData(event.target)); try { const result = await request(`/asset-groups/${values.groupId}/members`, { method: 'POST', body: JSON.stringify({ sbn: values.sbn, componentRole: values.componentRole }) }); state.completedGroup = result; state.pendingSbn = null; state.pendingGroupId = null; state.flowStep = 4; navigate('groups'); } catch (error) { view.querySelector('#group-message').innerHTML = notice(error.message); } };
  view.querySelector('#new-group').onsubmit = async event => { event.preventDefault(); try { const result = await request('/asset-groups', { method: 'POST', body: JSON.stringify(Object.fromEntries(new FormData(event.target))) }); state.pendingSbn = pending; state.pendingGroupId = result.id; navigate('groups'); } catch (error) { view.querySelector('#group-message').innerHTML = notice(error.message); } };
  const restart = view.querySelector('#restart-flow'); if (restart) restart.onclick = () => { state.completedGroup = null; state.pendingSbn = null; state.pendingGroupId = null; state.flowStep = 1; navigate('scanner'); };
}

async function inventory(view) {
  const rows = await request('/inventory-sessions');
  view.innerHTML = `<div class="toolbar"><h2>Inventario físico</h2>${state.user.role !== 'VIEWER' ? '<button class="primary" id="create">Nueva jornada</button>' : ''}</div><div class="table-wrap"><table><thead><tr><th>Nombre</th><th>Fase</th><th>Estado</th><th>Verificados</th></tr></thead><tbody>${rows.map(row => `<tr><td>${escapeHtml(row.name)}</td><td>${row.phase}</td><td>${row.status}</td><td>${row.checked_count}</td></tr>`).join('')}</tbody></table></div>`;
  const button = view.querySelector('#create'); if (button) button.onclick = async () => { const name = await uiPrompt('Nombre de la jornada'); if (name) { await request('/inventory-sessions', { method: 'POST', body: JSON.stringify({ name, phase: 'POSTTEST' }) }); navigate('inventory'); } };
}

async function users(view) { const rows = await request('/users'); renderTable(view, 'Usuarios', ['Usuario', 'Nombre', 'Correo', 'Rol'], rows.map(row => [row.username, row.fullName, row.email, row.role])); }
async function catalogs(view) { const rows = await request('/catalogs'); renderTable(view, 'Catálogos', ['Categoría', 'Código', 'Etiqueta'], rows.map(row => [row.category, row.code, row.label])); }
async function audit(view) { const rows = await request('/audit-logs'); renderTable(view, 'Auditoría', ['Fecha', 'Acción', 'Entidad', 'IP'], rows.map(row => [row.created_at, row.action, row.entity_type, row.ip_address || '—'])); }
function renderTable(view, title, headers, rows) { view.innerHTML = `<h2>${title}</h2><div class="table-wrap"><table><thead><tr>${headers.map(value => `<th>${value}</th>`).join('')}</tr></thead><tbody>${rows.map(row => `<tr>${row.map(value => `<td>${escapeHtml(value)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`; }

async function settings(view) {
  view.innerHTML = `<h2>Configuración y seguridad</h2><div id="settings-message"></div><form class="panel" id="password"><label class="field">Contraseña actual<input type="password" name="currentPassword" required></label><label class="field">Nueva contraseña<input type="password" name="newPassword" minlength="12" required></label><button class="primary">Cambiar contraseña</button></form>`;
  view.querySelector('#password').onsubmit = async event => { event.preventDefault(); try { await request('/auth/change-password', { method: 'POST', body: JSON.stringify(Object.fromEntries(new FormData(event.target))) }); view.querySelector('#settings-message').innerHTML = notice('Contraseña actualizada. Inicie sesión nuevamente.', 'success'); setTimeout(logout, 1200); } catch (error) { view.querySelector('#settings-message').innerHTML = notice(error.message); } };
}

const screens = { dashboard, assets, register, scanner, groups, inventory, research, indicators, users, catalogs, audit, settings };
// Inicio de sesión recuperado mediante cookie HttpOnly en portal.js.
