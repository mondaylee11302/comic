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

function getSelections(step1 = {}) {
  const result = step1.result || {};
  const loglines = Array.isArray(result.loglines) ? result.loglines : [];
  const modes = Array.isArray(result.modes) ? result.modes : [];
  const logline = Number.isInteger(step1.selected_logline_index) ? loglines[step1.selected_logline_index] : null;
  const mode = Number.isInteger(step1.selected_mode_index) ? modes[step1.selected_mode_index] : null;
  return { logline, mode };
}

function renderSelectedSummary(directorState = {}) {
  const { logline, mode } = getSelections(directorState.step1 || {});
  const step2Done = Boolean(directorState.step2?.result);
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">当前已选</h3>
      <span class="tag">${step2Done ? '结构蓝图已完成' : '结构蓝图未完成'}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${renderKV('当前 Logline', logline?.title || '等待在“初始种子”中选定 Logline')}
      ${renderKV('当前 Mode', mode?.title || '等待在“初始种子”中选定创作模式')}
    </div>
  </div>`;
}

function renderBeatSheet(items = []) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">Beat Sheet</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map(item => `
        <div class="card" style="box-shadow:none; margin:0;">
          <div class="card-header">
            <h4 class="card-title" style="font-size:16px;">${escHtml(item.segment)}</h4>
          </div>
          <div class="card-body" style="display:grid; gap:10px;">
            ${renderKV('goal', item.goal)}
            ${renderKV('conflict', item.conflict)}
            ${renderKV('turn', item.turn)}
            ${renderKV('emotion_curve', item.emotion_curve)}
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderArcMap(items = []) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">角色弧光映射</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map(item => `
        <div class="card" style="box-shadow:none; margin:0;">
          <div class="card-header">
            <h4 class="card-title" style="font-size:16px;">${escHtml(item.segment)}</h4>
          </div>
          <div class="card-body" style="display:grid; gap:10px;">
            ${renderKV('belief_change', item.belief_change)}
            ${renderKV('relationship_change', item.relationship_change)}
            ${renderKV('cost_upgrade', item.cost_upgrade)}
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderForeshadowPlan(items = []) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">伏笔管理表</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map(item => `
        <div class="card" style="box-shadow:none; margin:0;">
          <div class="card-header">
            <h4 class="card-title" style="font-size:16px;">${escHtml(item.segment)}</h4>
            <span class="tag">${item.intentional_open ? '开放' : '闭合'}</span>
          </div>
          <div class="card-body" style="display:grid; gap:10px;">
            ${renderKV('setup', item.setup)}
            ${renderKV('payoff', item.payoff)}
            ${renderKV('intentional_open', item.intentional_open ? 'true' : 'false')}
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderRhythmRisks(items = []) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">节奏风险提示</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map(item => `
        <div class="card" style="box-shadow:none; margin:0;">
          <div class="card-header">
            <h4 class="card-title" style="font-size:16px;">${escHtml(item.type)}</h4>
          </div>
          <div class="card-body">
            ${renderKV('note', item.note)}
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderSoftAlignment(alignment = null) {
  if (!alignment) return '';
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">Soft 对齐提示</h3>
      <span class="tag">${escHtml(alignment.status || '-')}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${renderKV('status', alignment.status)}
      ${renderKV('option_a', alignment.option_a)}
      ${renderKV('option_b', alignment.option_b)}
    </div>
  </div>`;
}

export function renderDirectorStep3(state = {}, directorState = {}) {
  const form = state.form || {};
  const generating = Boolean(state.generating);
  const error = state.error || '';
  const result = state.result || null;
  const projectId = directorState?.project?.project_id || '';

  return `
  <div style="display:grid; gap:12px;">
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">${DIRECTOR_AGENT_TITLE} · 段落节拍</h3>
        <span class="tag">${projectId ? `项目 ${escHtml(projectId)}` : '未绑定项目'}</span>
      </div>
      <div class="card-body">
        <div style="display:grid; gap:10px;">
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">段落粒度</span>
            <input class="search-input" type="text" value="${escHtml(form.segment_granularity)}" placeholder="例如：8 段 / 10 段（可留空）" oninput="setDirectorStep3Field('segment_granularity', this.value)" />
          </label>
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">动作段落比例</span>
            <input class="search-input" type="text" value="${escHtml(form.action_ratio)}" placeholder="例如：60%（可留空）" oninput="setDirectorStep3Field('action_ratio', this.value)" />
          </label>
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">角色戏比例</span>
            <input class="search-input" type="text" value="${escHtml(form.character_ratio)}" placeholder="例如：40%（可留空）" oninput="setDirectorStep3Field('character_ratio', this.value)" />
          </label>
        </div>
        <div style="display:flex; align-items:center; gap:10px; margin-top:12px; flex-wrap:wrap;">
          <button class="btn btn-primary" onclick="handleDirectorGenerateBeats()" ${generating ? 'disabled' : ''}>
            ${generating ? '生成中...' : '生成段落节拍'}
          </button>
          <span style="color: var(--color-text-muted); font-size:12px;">当前为假响应，仅用于段落节拍联调。</span>
        </div>
        ${error ? `<div style="margin-top:10px; color:#b42318; font-size:13px;">${escHtml(error)}</div>` : ''}
      </div>
    </div>

    ${renderSelectedSummary(directorState)}

    ${result ? `
      ${renderBeatSheet(result.beat_sheet || [])}
      ${renderArcMap(result.arc_map || [])}
      ${renderForeshadowPlan(result.foreshadow_plan || [])}
      ${renderRhythmRisks(result.rhythm_risks || [])}
      ${renderSoftAlignment(result.soft_alignment || null)}
    ` : ''}
  </div>`;
}
