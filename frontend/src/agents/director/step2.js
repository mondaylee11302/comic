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

function renderSelectedSummary(step1 = {}) {
  const result = step1.result || {};
  const loglines = Array.isArray(result.loglines) ? result.loglines : [];
  const modes = Array.isArray(result.modes) ? result.modes : [];
  const logline = Number.isInteger(step1.selected_logline_index) ? loglines[step1.selected_logline_index] : null;
  const mode = Number.isInteger(step1.selected_mode_index) ? modes[step1.selected_mode_index] : null;
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">当前已选</h3>
      <span class="tag">来自初始种子</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${renderKV('当前 Logline', logline?.title || '等待在“初始种子”中选定 Logline')}
      ${renderKV('当前 Mode', mode?.title || '等待在“初始种子”中选定创作模式')}
    </div>
  </div>`;
}

function renderThreeActStructure(items = []) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">三幕结构节拍表</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map(item => `
        <div class="card" style="box-shadow:none; margin:0;">
          <div class="card-header">
            <h4 class="card-title" style="font-size:16px;">${escHtml(item.act)} <span style="font-weight:400; color:var(--color-text-muted)">(${escHtml(item.range)})</span></h4>
          </div>
          <div class="card-body">
            ${renderKV('summary', item.summary)}
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderKeyNodes(items = []) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">关键节点清单</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map(item => `
        <div class="card" style="box-shadow:none; margin:0;">
          <div class="card-header">
            <h4 class="card-title" style="font-size:16px;">${escHtml(item.name)}</h4>
          </div>
          <div class="card-body">
            ${renderKV('content', item.content)}
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderRevealPlan(items = []) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">信息披露表</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map(item => `
        <div class="card" style="box-shadow:none; margin:0;">
          <div class="card-header">
            <h4 class="card-title" style="font-size:16px;">分钟点 ${escHtml(item.minute)}</h4>
          </div>
          <div class="card-body" style="display:grid; gap:10px;">
            ${renderKV('audience_knows', item.audience_knows)}
            ${renderKV('character_knows', item.character_knows)}
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderSetPieces(items = []) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">动作卖点清单（Set Pieces）</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map(item => `
        <div class="card" style="box-shadow:none; margin:0;">
          <div class="card-header">
            <h4 class="card-title" style="font-size:16px;">${escHtml(item.title)}</h4>
          </div>
          <div class="card-body" style="display:grid; gap:10px;">
            ${renderKV('sell_line', item.sell_line)}
            ${renderKV('scene_goal', item.scene_goal)}
            ${renderKV('cost_point', item.cost_point)}
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderHardGatePrecheck(items = []) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">Hard Gate 预检</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map(item => `
        <div class="card" style="box-shadow:none; margin:0;">
          <div class="card-header">
            <h4 class="card-title" style="font-size:16px;">${escHtml(item.type)}</h4>
            <span class="tag">${escHtml(item.status)}</span>
          </div>
          <div class="card-body">
            ${renderKV('note', item.note)}
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

export function renderDirectorStep2(state = {}, directorState = {}) {
  const form = state.form || {};
  const generating = Boolean(state.generating);
  const error = state.error || '';
  const result = state.result || null;
  const projectId = directorState?.project?.project_id || '';

  return `
  <div style="display:grid; gap:12px;">
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">${DIRECTOR_AGENT_TITLE} · 结构蓝图</h3>
        <span class="tag">${projectId ? `项目 ${escHtml(projectId)}` : '未绑定项目'}</span>
      </div>
      <div class="card-body">
        <div style="display:grid; gap:10px;">
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">目标受众</span>
            <input class="search-input" type="text" value="${escHtml(form.audience)}" placeholder="例如：18-30 岁悬疑向观众（可留空）" oninput="setDirectorStep2Field('audience', this.value)" />
          </label>
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">叙事侧重</span>
            <textarea class="prompt-input" rows="3" placeholder="例如：人物关系与信息悬念的平衡（可留空）" oninput="setDirectorStep2Field('narrative_focus', this.value)">${escHtml(form.narrative_focus)}</textarea>
          </label>
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">结局倾向</span>
            <input class="search-input" type="text" value="${escHtml(form.ending_tendency)}" placeholder="例如：开放式但情绪完成（可留空）" oninput="setDirectorStep2Field('ending_tendency', this.value)" />
          </label>
        </div>
        <div style="display:flex; align-items:center; gap:10px; margin-top:12px; flex-wrap:wrap;">
          <button class="btn btn-primary" onclick="handleDirectorGenerateBlueprint()" ${generating ? 'disabled' : ''}>
            ${generating ? '生成中...' : '生成结构蓝图'}
          </button>
          <span style="color: var(--color-text-muted); font-size:12px;">当前为假响应，仅用于结构蓝图联调。</span>
        </div>
        ${error ? `<div style="margin-top:10px; color:#b42318; font-size:13px;">${escHtml(error)}</div>` : ''}
      </div>
    </div>

    ${renderSelectedSummary(directorState.step1 || {})}

    ${result ? `
      ${renderThreeActStructure(result.three_act_structure || [])}
      ${renderKeyNodes(result.key_nodes || [])}
      ${renderRevealPlan(result.reveal_plan || [])}
      ${renderSetPieces(result.set_pieces || [])}
      ${renderHardGatePrecheck(result.hard_gate_precheck || [])}
    ` : ''}
  </div>`;
}
