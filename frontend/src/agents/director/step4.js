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
  const step3Done = Boolean(directorState.step3?.result);
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">当前已选</h3>
      <span class="tag">${step3Done ? '段落节拍已完成' : '段落节拍未完成'}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${renderKV('当前 Logline', logline?.title || '等待在“初始种子”中选定 Logline')}
      ${renderKV('当前 Mode', mode?.title || '等待在“初始种子”中选定创作模式')}
    </div>
  </div>`;
}

function renderSceneList(items = []) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">分场表（主表）</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map(item => `
        <div class="card" style="box-shadow:none; margin:0;">
          <div class="card-header">
            <h4 class="card-title" style="font-size:16px;">${escHtml(item.scene_title)}</h4>
          </div>
          <div class="card-body" style="display:grid; gap:10px;">
            ${renderKV('goal', item.goal)}
            ${renderKV('conflict', item.conflict)}
            ${renderKV('turn', item.turn)}
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderSceneFunctions(items = []) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">场景功能标注</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map(item => `
        <div class="card" style="box-shadow:none; margin:0;">
          <div class="card-header">
            <h4 class="card-title" style="font-size:16px;">${escHtml(item.scene_title)}</h4>
          </div>
          <div class="card-body">
            <div style="display:flex; gap:8px; flex-wrap:wrap;">
              ${(Array.isArray(item.tags) ? item.tags : []).map(tag => `<span class="tag">${escHtml(tag)}</span>`).join('')}
            </div>
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderSceneEventCoupling(items = []) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">场景-事件耦合说明</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map(item => `
        <div class="card" style="box-shadow:none; margin:0;">
          <div class="card-header">
            <h4 class="card-title" style="font-size:16px;">${escHtml(item.scene_title)}</h4>
          </div>
          <div class="card-body">
            ${renderKV('why_here', item.why_here)}
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderSceneStats(stats = null) {
  if (!stats) return '';
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">初版场景清单统计</h3>
      <span class="tag">统计</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${renderKV('interior_count', stats.interior_count)}
      ${renderKV('exterior_count', stats.exterior_count)}
      ${renderKV('day_count', stats.day_count)}
      ${renderKV('night_count', stats.night_count)}
      ${renderKV('core_location_ratio', stats.core_location_ratio)}
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

export function renderDirectorStep4(state = {}, directorState = {}) {
  const form = state.form || {};
  const generating = Boolean(state.generating);
  const error = state.error || '';
  const result = state.result || null;
  const projectId = directorState?.project?.project_id || '';

  return `
  <div style="display:grid; gap:12px;">
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">${DIRECTOR_AGENT_TITLE} · 分场表</h3>
        <span class="tag">${projectId ? `项目 ${escHtml(projectId)}` : '未绑定项目'}</span>
      </div>
      <div class="card-body">
        <div style="display:grid; gap:10px;">
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">场次数量目标</span>
            <input class="search-input" type="text" value="${escHtml(form.target_scene_count)}" placeholder="例如：12-16 场（可留空）" oninput="setDirectorStep4Field('target_scene_count', this.value)" />
          </label>
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">场景限制</span>
            <textarea class="prompt-input" rows="3" placeholder="例如：尽量控制核心场景数量、夜戏比例（可留空）" oninput="setDirectorStep4Field('scene_constraints', this.value)">${escHtml(form.scene_constraints)}</textarea>
          </label>
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">语言风格</span>
            <input class="search-input" type="text" value="${escHtml(form.language_style)}" placeholder="例如：简洁影视化 / 更文学化（可留空）" oninput="setDirectorStep4Field('language_style', this.value)" />
          </label>
        </div>
        <div style="display:flex; align-items:center; gap:10px; margin-top:12px; flex-wrap:wrap;">
          <button class="btn btn-primary" onclick="handleDirectorGenerateScenes()" ${generating ? 'disabled' : ''}>
            ${generating ? '生成中...' : '生成分场表'}
          </button>
          <span style="color: var(--color-text-muted); font-size:12px;">当前为假响应，仅用于分场表联调。</span>
        </div>
        ${error ? `<div style="margin-top:10px; color:#b42318; font-size:13px;">${escHtml(error)}</div>` : ''}
      </div>
    </div>

    ${renderSelectedSummary(directorState)}

    ${result ? `
      ${renderSceneList(result.scene_list || [])}
      ${renderSceneFunctions(result.scene_functions || [])}
      ${renderSceneEventCoupling(result.scene_event_coupling || [])}
      ${renderSceneStats(result.scene_stats || null)}
      ${renderHardGatePrecheck(result.hard_gate_precheck || [])}
    ` : ''}
  </div>`;
}
