const state = { runId: null, cases: [], selected: null };
const byId = (id) => document.getElementById(id);

async function request(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } });
  if (!response.ok) {
    let detail = `Erreur HTTP ${response.status}`;
    try { detail = (await response.json()).detail || detail; } catch (_) { /* Keep status. */ }
    throw new Error(detail);
  }
  return response.json();
}

function message(text, error = false) {
  const target = byId('message');
  target.textContent = text;
  target.classList.toggle('error', error);
}

function decisionLabel(decision) {
  if (!decision) return 'Sans décision';
  return decision.action === 'documented' ? 'Documentée' : 'À reprendre';
}

function renderQueue() {
  const filter = byId('filter').value;
  const list = byId('case-list');
  list.replaceChildren();
  const visible = state.cases.filter((item) => filter === 'all' ||
    (filter === 'open' ? !item.decision : item.decision?.action === filter));
  byId('queue-count').textContent = `${visible.length} affiché${visible.length > 1 ? 's' : ''}`;
  if (!visible.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-case';
    empty.textContent = 'Aucun dossier dans ce filtre.';
    list.append(empty);
  }
  for (const item of visible) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'case-item';
    button.classList.toggle('selected', item.case_id === state.selected);
    button.setAttribute('role', 'listitem');
    button.setAttribute('aria-current', item.case_id === state.selected ? 'true' : 'false');
    const top = document.createElement('div');
    top.className = 'case-item-top';
    const code = document.createElement('span');
    code.textContent = `${item.code} · ${item.year}`;
    const status = document.createElement('span');
    status.className = `case-item-status ${item.decision?.action || ''}`;
    status.textContent = decisionLabel(item.decision);
    top.append(code, status);
    const bottom = document.createElement('div');
    bottom.className = 'case-item-bottom';
    const where = document.createElement('span');
    where.textContent = `${item.sheet} ${item.cell}`;
    const category = document.createElement('span');
    category.textContent = item.category.replaceAll('_', ' ');
    bottom.append(where, category);
    button.append(top, bottom);
    button.addEventListener('click', () => selectCase(item.case_id));
    list.append(button);
  }
}

function renderSummary(status) {
  const documented = state.cases.filter((item) => item.decision?.action === 'documented').length;
  const followUp = state.cases.filter((item) => item.decision?.action === 'follow_up').length;
  byId('total-count').textContent = String(state.cases.length);
  byId('documented-count').textContent = String(documented);
  byId('follow-up-count').textContent = String(followUp);
  byId('run-status').textContent = `Run ${state.runId} · ${status}`;
}

async function loadQueue(preferredCase = null) {
  const data = await request(`/runs/${state.runId}/review`);
  state.cases = data.cases;
  renderSummary(data.status);
  const firstOpen = data.cases.find((item) => !item.decision);
  const selected = preferredCase || firstOpen?.case_id || data.cases[0]?.case_id;
  if (selected) await selectCase(selected);
  else {
    state.selected = null;
    byId('empty-case').hidden = false;
    byId('case-content').hidden = true;
    renderQueue();
  }
}

function renderHistory(history) {
  const target = byId('history');
  target.replaceChildren();
  if (!history.length) {
    target.textContent = 'Aucune décision enregistrée pour cette cellule.';
    return;
  }
  for (const item of [...history].reverse()) {
    const entry = document.createElement('div');
    entry.className = 'history-item';
    const title = document.createElement('strong');
    title.textContent = `${decisionLabel(item)} · ${item.reviewer}`;
    const time = document.createElement('div');
    time.textContent = new Date(item.at).toLocaleString('fr-TN');
    const note = document.createElement('p');
    note.textContent = item.note;
    entry.append(title, time, note);
    target.append(entry);
  }
}

async function selectCase(caseId) {
  try {
    state.selected = caseId;
    renderQueue();
    let data = await request(`/runs/${state.runId}/review/${caseId}`);
    if (!data.started) data = await request(`/runs/${state.runId}/review/${caseId}/start`, { method: 'POST' });
    const item = data.case;
    byId('empty-case').hidden = true;
    byId('case-content').hidden = false;
    byId('case-location').textContent = `${item.year} · ${item.sheet} · cellule ${item.cell}`;
    byId('case-title').textContent = item.code;
    byId('case-reason').textContent = item.reason;
    byId('case-action').textContent = item.action;
    byId('case-source').textContent = `${item.source}${item.page ? ` · page ${item.page}` : ''}`;
    byId('case-dependencies').textContent = [...item.dependencies, ...item.issue_types].join(', ') || 'Aucune dépendance signalée.';
    const source = byId('source-link');
    source.href = `/runs/${state.runId}/review/${caseId}/source${item.page ? `#page=${item.page}` : ''}`;
    const badge = byId('case-state');
    badge.textContent = decisionLabel(data.decision);
    badge.className = `case-state ${data.decision?.action || ''}`;
    renderHistory(data.history);
    message('');
  } catch (error) { message(error.message, true); }
}

async function saveDecision(event) {
  event.preventDefault();
  if (!state.selected) return;
  const button = byId('save-decision');
  button.disabled = true;
  try {
    await request(`/runs/${state.runId}/review/${state.selected}/decision`, {
      method: 'POST',
      body: JSON.stringify({
        action: byId('decision-action').value,
        reviewer: byId('reviewer').value.trim(),
        note: byId('decision-note').value.trim(),
      }),
    });
    byId('decision-note').value = '';
    const selected = state.selected;
    await loadQueue(selected);
    message('Décision enregistrée. Le classeur n’a pas été modifié.');
  } catch (error) { message(error.message, true); }
  finally { button.disabled = false; }
}

async function loadRuns(preferredRun = null) {
  const data = await request('/runs');
  const runs = data.runs.filter((run) => ['completed', 'needs_review'].includes(run.status));
  const selector = byId('run-select');
  selector.replaceChildren();
  if (!runs.length) {
    const option = document.createElement('option');
    option.textContent = 'Aucune exécution terminée';
    selector.append(option);
    selector.disabled = true;
    message('Lancez d’abord un traitement pour obtenir une file de revue.');
    return;
  }
  selector.disabled = false;
  for (const run of runs) {
    const option = document.createElement('option');
    option.value = run.run_id;
    option.textContent = `${run.company || 'Entreprise'} ${run.years.join(', ')} · ${run.run_id}`;
    selector.append(option);
  }
  selector.value = runs.some((run) => run.run_id === preferredRun) ? preferredRun : runs[0].run_id;
  state.runId = selector.value;
  byId('workbook-link').href = `/runs/${state.runId}/workbook`;
  byId('workbook-link').hidden = false;
  await loadQueue();
}

async function startRun(event) {
  event.preventDefault();
  const years = [...document.querySelectorAll('input[name="year"]:checked')].map((box) => Number(box.value));
  if (!years.length) { message('Choisissez au moins un exercice.', true); return; }
  const button = byId('start-run');
  button.disabled = true;
  try {
    const started = await request('/runs', { method: 'POST', body: JSON.stringify({ years }) });
    byId('job-progress').textContent = 'Extraction en cours…';
    for (let attempt = 0; attempt < 720; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 5000));
      const job = await request(started.poll);
      if (job.status === 'running') continue;
      if (job.status === 'failed') throw new Error(job.message || 'Le traitement a échoué. Consultez le journal local.');
      if (!job.run_id) throw new Error('Traitement terminé sans identifiant de run.');
      await loadRuns(job.run_id);
      byId('job-progress').textContent = `Extraction terminée : ${job.status}.`;
      message('Nouvelle exécution disponible dans la revue.');
      return;
    }
    throw new Error('Délai d’attente dépassé. Vérifiez l’état du traitement dans l’API locale.');
  } catch (error) {
    byId('job-progress').textContent = 'Extraction non terminée.';
    message(error.message, true);
  } finally { button.disabled = false; }
}

async function init() {
  byId('filter').addEventListener('change', renderQueue);
  byId('decision-form').addEventListener('submit', saveDecision);
  byId('run-form').addEventListener('submit', startRun);
  byId('run-select').addEventListener('change', async (event) => {
    state.runId = event.target.value;
    byId('workbook-link').href = `/runs/${state.runId}/workbook`;
    byId('workbook-link').hidden = false;
    try { await loadQueue(); } catch (error) { message(error.message, true); }
  });
  try { await loadRuns(); } catch (error) { message(error.message, true); }
}

document.addEventListener('DOMContentLoaded', init);
