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
  const step4Done = Boolean(directorState.step4?.result);
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">当前已选</h3>
      <span class="tag">${step4Done ? '分场表已完成' : '分场表未完成'}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${renderKV('当前 Logline', logline?.title || '等待在“初始种子”中选定 Logline')}
      ${renderKV('当前 Mode', mode?.title || '等待在“初始种子”中选定创作模式')}
    </div>
  </div>`;
}

function renderScriptReader(result = null) {
  if (!result) return '';
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">剧本 Draft v1 阅读器</h3>
      <span class="tag">${escHtml(result.script_title || 'Draft v1')}</span>
    </div>
    <div class="card-body" style="display:grid; gap:12px;">
      ${renderKV('script_title', result.script_title)}
      <div>
        <div style="font-size:12px; color: var(--color-text-muted); margin-bottom:6px;">script_text</div>
        <pre style="margin:0; padding:12px; background:#f7f8fb; border:1px solid var(--color-border-light); border-radius:10px; white-space:pre-wrap; word-break:break-word; line-height:1.6; color: var(--color-text-primary); font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;">${escHtml(result.script_text || '')}</pre>
      </div>
    </div>
  </div>`;
}

function renderActionAppendix(items = []) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">动作段落附录</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map(item => `
        <div class="card" style="box-shadow:none; margin:0;">
          <div class="card-header">
            <h4 class="card-title" style="font-size:16px;">${escHtml(item.title)}</h4>
          </div>
          <div class="card-body" style="display:grid; gap:10px;">
            ${renderKV('spatial_relation', item.spatial_relation)}
            ${renderKV('rhythm_layer', item.rhythm_layer)}
            ${renderKV('climax_point', item.climax_point)}
            ${renderKV('cost_point', item.cost_point)}
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderDialogueStats(items = []) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">台词与角色占比统计</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map(item => `
        <div class="card" style="box-shadow:none; margin:0;">
          <div class="card-body" style="display:grid; gap:8px;">
            ${renderKV('character', item.character)}
            ${renderKV('line_ratio', item.line_ratio)}
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderSoftAlignmentSummary(summary = null) {
  if (!summary) return '';
  const best = Array.isArray(summary.best_matching_sections) ? summary.best_matching_sections : [];
  const dev = Array.isArray(summary.deviation_notes) ? summary.deviation_notes : [];
  const fixes = Array.isArray(summary.optional_fixes) ? summary.optional_fixes : [];
  const renderList = (title, items) => `
    <div>
      <div style="font-size:12px; color: var(--color-text-muted); margin-bottom:6px;">${escHtml(title)}</div>
      <ul style="margin:0; padding-left:18px; color: var(--color-text-primary); line-height:1.6;">
        ${items.map(i => `<li>${escHtml(i)}</li>`).join('')}
      </ul>
    </div>`;
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">Soft 审美对齐摘要</h3>
      <span class="tag">摘要</span>
    </div>
    <div class="card-body" style="display:grid; gap:12px;">
      ${renderList('best_matching_sections', best)}
      ${renderList('deviation_notes', dev)}
      ${renderList('optional_fixes', fixes)}
    </div>
  </div>`;
}

export function renderDirectorStep5(state = {}, directorState = {}) {
  const form = state.form || {};
  const generating = Boolean(state.generating);
  const error = state.error || '';
  const result = state.result || null;
  const projectId = directorState?.project?.project_id || '';

  return `
  <div style="display:grid; gap:12px;">
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">${DIRECTOR_AGENT_TITLE} · 剧本一稿</h3>
        <span class="tag">${projectId ? `项目 ${escHtml(projectId)}` : '未绑定项目'}</span>
      </div>
      <div class="card-body">
        <div style="display:grid; gap:10px;">
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">写作取向</span>
            <input class="search-input" type="text" value="${escHtml(form.writing_tendency)}" placeholder="例如：更电影感 / 更工业化（可留空）" oninput="setDirectorStep5Field('writing_tendency', this.value)" />
          </label>
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">对白密度</span>
            <input class="search-input" type="text" value="${escHtml(form.dialogue_density)}" placeholder="例如：低 / 中 / 高（可留空）" oninput="setDirectorStep5Field('dialogue_density', this.value)" />
          </label>
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">分级强度</span>
            <input class="search-input" type="text" value="${escHtml(form.rating_intensity)}" placeholder="例如：PG-13 感 / 中等强度（可留空）" oninput="setDirectorStep5Field('rating_intensity', this.value)" />
          </label>
        </div>
        <div style="display:flex; align-items:center; gap:10px; margin-top:12px; flex-wrap:wrap;">
          <button class="btn btn-primary" onclick="handleDirectorGenerateDraft()" ${generating ? 'disabled' : ''}>
            ${generating ? '生成中...' : '生成一稿'}
          </button>
          <span style="color: var(--color-text-muted); font-size:12px;">当前为假响应，仅用于剧本一稿联调。</span>
        </div>
        ${error ? `<div style="margin-top:10px; color:#b42318; font-size:13px;">${escHtml(error)}</div>` : ''}
      </div>
    </div>

    ${renderSelectedSummary(directorState)}

    ${result ? `
      ${renderScriptReader(result)}
      ${renderActionAppendix(result.action_appendix || [])}
      ${renderDialogueStats(result.dialogue_stats || [])}
      ${renderSoftAlignmentSummary(result.soft_alignment_summary || null)}
    ` : ''}
  </div>`;
}
