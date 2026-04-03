import { DIRECTOR_AGENT_TITLE } from './meta.js';

function escHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function renderKV(label, value) {
  const text = value || '-';
  const isHint = typeof text === 'string' && (
    text.includes('等待在“初始种子”中选定') || text.includes('请在下方选择一个')
  );
  return `
    <div style="display:grid; gap:4px;">
      <div style="font-size:12px; color: var(--color-text-muted);">${escHtml(label)}</div>
      <div class="${isHint ? 'director-kv-hint' : ''}" style="color: var(--color-text-primary); line-height:1.5;">${escHtml(text)}</div>
    </div>`;
}

function renderSelectionSummary(result, selectedLoglineIndex, selectedModeIndex) {
  const loglines = Array.isArray(result?.loglines) ? result.loglines : [];
  const modes = Array.isArray(result?.modes) ? result.modes : [];
  const selectedLogline = Number.isInteger(selectedLoglineIndex) ? loglines[selectedLoglineIndex] : null;
  const selectedMode = Number.isInteger(selectedModeIndex) ? modes[selectedModeIndex] : null;

  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">当前已选</h3>
      <span class="tag">${selectedLogline && selectedMode ? '结构蓝图已解锁' : '请继续选择'}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${renderKV('已选 Logline', selectedLogline?.title || '请在下方选择一个 Logline')}
      ${renderKV('已选 Mode', selectedMode?.title || '请在下方选择一个创作模式')}
      <div style="color: var(--color-text-muted); font-size:12px;">请通过左侧侧栏进入下一阶段。</div>
    </div>
  </div>`;
}

function renderSelectAction(kind, index, selectedIndex) {
  const selected = selectedIndex === index;
  return `
    <div style="display:flex; align-items:center; justify-content:space-between; gap:8px; margin-top:2px;">
      ${selected ? '<span class="tag">已选定</span>' : '<span style="font-size:12px; color: var(--color-text-muted);">未选择</span>'}
      <button class="btn-sm ${selected ? 'btn-brand' : ''}" onclick="${kind === 'logline' ? 'selectDirectorLogline' : 'selectDirectorMode'}(${index})">
        ${selected ? '已选定' : (kind === 'logline' ? '选定此 Logline' : '选定此模式')}
      </button>
    </div>`;
}

function renderLoglineCards(items = [], selectedLoglineIndex = null) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">Logline（3个版本）</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map((item, index) => `
        <div class="card" style="box-shadow:none; margin:0; ${selectedLoglineIndex === index ? 'border:1px solid var(--color-brand);' : ''}">
          <div class="card-header">
            <h4 class="card-title" style="font-size:16px;">${escHtml(item.title)}</h4>
          </div>
          <div class="card-body" style="display:grid; gap:10px;">
            ${renderSelectAction('logline', index, selectedLoglineIndex)}
            ${renderKV('logline', item.logline)}
            ${renderKV('sell_line', item.sell_line)}
            ${renderKV('hook_question', item.hook_question)}
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderThemeCards(items = []) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">主题候选（4个）</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map(item => `
        <div class="card" style="box-shadow:none; margin:0;">
          <div class="card-header">
            <h4 class="card-title" style="font-size:16px;">${escHtml(item.title)}</h4>
          </div>
          <div class="card-body">
            ${renderKV('theme_question', item.theme_question)}
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderWorldRules(items = []) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">世界观规则草案</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map((item, idx) => `
        <div class="card" style="box-shadow:none; margin:0;">
          <div class="card-header">
            <h4 class="card-title" style="font-size:16px;">规则 ${idx + 1}</h4>
          </div>
          <div class="card-body" style="display:grid; gap:10px;">
            ${renderKV('规则', item.rule)}
            ${renderKV('代价', item.cost)}
            ${renderKV('禁区', item.forbidden)}
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderCharacterCards(items = []) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">角色初版</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map(item => `
        <div class="card" style="box-shadow:none; margin:0;">
          <div class="card-header">
            <h4 class="card-title" style="font-size:16px;">${escHtml(item.name)}</h4>
          </div>
          <div class="card-body" style="display:grid; gap:10px;">
            ${renderKV('desire', item.desire)}
            ${renderKV('fear', item.fear)}
            ${renderKV('misbelief', item.misbelief)}
            ${renderKV('cost', item.cost)}
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderModeCards(items = [], selectedModeIndex = null) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">创作模式候选（3个）</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map((item, index) => `
        <div class="card" style="box-shadow:none; margin:0; ${selectedModeIndex === index ? 'border:1px solid var(--color-brand);' : ''}">
          <div class="card-header">
            <h4 class="card-title" style="font-size:16px;">${escHtml(item.title)}</h4>
          </div>
          <div class="card-body" style="display:grid; gap:10px;">
            ${renderSelectAction('mode', index, selectedModeIndex)}
            ${renderKV('manifesto', item.manifesto)}
            ${renderKV('anti_trope', item.anti_trope)}
            ${renderKV('payoff_rhythm', item.payoff_rhythm)}
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderNovelIdeaGate(gate = null) {
  if (!gate) return '';
  const evidence = Array.isArray(gate.evidence) ? gate.evidence : [];
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">Novel Idea Gate 结果</h3>
      <span class="tag">score: ${escHtml(gate.score)}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${renderKV('score', gate.score)}
      <div>
        <div style="font-size:12px; color: var(--color-text-muted); margin-bottom:6px;">evidence</div>
        <ul style="margin:0; padding-left:18px; color: var(--color-text-primary); line-height:1.6;">
          ${evidence.map(item => `<li>${escHtml(item)}</li>`).join('')}
        </ul>
      </div>
      ${renderKV('improve_instruction', gate.improve_instruction)}
    </div>
  </div>`;
}

export function renderDirectorStep1(state = {}, directorState = {}) {
  const form = state.form || {};
  const generating = Boolean(state.generating);
  const error = state.error || '';
  const result = state.result || null;
  const selectedLoglineIndex = Number.isInteger(state.selected_logline_index) ? state.selected_logline_index : null;
  const selectedModeIndex = Number.isInteger(state.selected_mode_index) ? state.selected_mode_index : null;
  const projectId = directorState?.project?.project_id || '';

  return `
  <div style="display:grid; gap:12px;">
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">${DIRECTOR_AGENT_TITLE} · 初始种子</h3>
        <span class="tag">${projectId ? `项目 ${escHtml(projectId)}` : '未绑定项目'}</span>
      </div>
      <div class="card-body">
        <div style="display:grid; gap:10px;">
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">种子</span>
            <textarea class="prompt-input" rows="3" placeholder="一句话种子（可留空）" oninput="setDirectorStep1Field('seed', this.value)">${escHtml(form.seed)}</textarea>
          </label>
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">主角</span>
            <input class="search-input" type="text" value="${escHtml(form.protagonist)}" placeholder="主角（可留空）" oninput="setDirectorStep1Field('protagonist', this.value)" />
          </label>
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">反派/对立面</span>
            <input class="search-input" type="text" value="${escHtml(form.antagonist)}" placeholder="反派/对立面（可留空）" oninput="setDirectorStep1Field('antagonist', this.value)" />
          </label>
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">核心梗概</span>
            <textarea class="prompt-input" rows="3" placeholder="核心梗概（可留空）" oninput="setDirectorStep1Field('core_synopsis', this.value)">${escHtml(form.core_synopsis)}</textarea>
          </label>
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">关键设定</span>
            <textarea class="prompt-input" rows="3" placeholder="关键设定（可留空）" oninput="setDirectorStep1Field('key_setting', this.value)">${escHtml(form.key_setting)}</textarea>
          </label>
        </div>
        <div style="display:flex; align-items:center; gap:10px; margin-top:12px; flex-wrap:wrap;">
          <button class="btn btn-primary" onclick="handleDirectorGenerateSeed()" ${generating ? 'disabled' : ''}>
            ${generating ? '生成中...' : '生成初始种子'}
          </button>
          <span style="color: var(--color-text-muted); font-size:12px;">当前为假响应，仅用于前端结构联调。</span>
        </div>
        ${error ? `<div style="margin-top:10px; color:#b42318; font-size:13px;">${escHtml(error)}</div>` : ''}
      </div>
    </div>

    ${result ? `
      ${renderSelectionSummary(result, selectedLoglineIndex, selectedModeIndex)}
      ${renderLoglineCards(result.loglines || [], selectedLoglineIndex)}
      ${renderThemeCards(result.themes || [])}
      ${renderWorldRules(result.world_rules || [])}
      ${renderCharacterCards(result.characters || [])}
      ${renderModeCards(result.modes || [], selectedModeIndex)}
      ${renderNovelIdeaGate(result.novel_idea_gate || null)}
    ` : ''}
  </div>`;
}
