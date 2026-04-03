import { DIRECTOR_AGENT_TITLE } from './meta.js';
import { DIRECTOR_STEP_META } from './steps_meta.js';

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
  const step6Done = Boolean(directorState.step6?.result);
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">当前已选</h3>
      <span class="tag">${step6Done ? '评审质检已完成' : '评审质检未完成'}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${renderKV('当前 Logline', logline?.title || '等待在“初始种子”中选定 Logline')}
      ${renderKV('当前 Mode', mode?.title || '等待在“初始种子”中选定创作模式')}
    </div>
  </div>`;
}

function getAcceptedTaskRows(directorState = {}) {
  const taskSheet = Array.isArray(directorState.step6?.result?.task_sheet) ? directorState.step6.result.task_sheet : [];
  const taskSelections = directorState.step6?.taskSelections || {};
  const acceptedActions = new Set(['accept', 'alternative']);
  return taskSheet
    .map((task) => {
      const currentAction = String(taskSelections[task.task_id] || task.default_action || '');
      return { ...task, currentAction };
    })
    .filter((task) => acceptedActions.has(task.currentAction));
}

function renderAcceptedTaskSummary(directorState = {}) {
  const acceptedRows = getAcceptedTaskRows(directorState);
  return `
  <div>
    <div class="section-label" style="margin:0 0 8px 0;">已接受的修复项摘要</div>
    ${acceptedRows.length ? `
      <div style="display:grid; gap:8px;">
        ${acceptedRows.map((task) => `
          <div class="card" style="box-shadow:none; margin:0;">
            <div class="card-body" style="display:grid; gap:8px;">
              ${renderKV('task_id', task.task_id)}
              ${renderKV('label', task.label)}
              ${renderKV('action', task.currentAction)}
            </div>
          </div>
        `).join('')}
      </div>
    ` : `
      <div style="color: var(--color-text-muted); font-size:12px;">暂无 accept / alternative 的修复项（可先在评审质检中调整任务单）。</div>
    `}
  </div>`;
}

function renderScriptReader(result = null) {
  if (!result) return '';
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">新版本剧本 Draft v2/v3</h3>
      <span class="tag">${escHtml(result.draft_version || 'Draft')}</span>
    </div>
    <div class="card-body" style="display:grid; gap:12px;">
      ${renderKV('draft_version', result.draft_version)}
      ${renderKV('script_title', result.script_title)}
      <div>
        <div style="font-size:12px; color: var(--color-text-muted); margin-bottom:6px;">script_text</div>
        <pre style="margin:0; padding:12px; background:#f7f8fb; border:1px solid var(--color-border-light); border-radius:10px; white-space:pre-wrap; word-break:break-word; line-height:1.6; color: var(--color-text-primary); font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;">${escHtml(result.script_text || '')}</pre>
      </div>
    </div>
  </div>`;
}

function renderChangeLog(items = []) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">变更日志</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map((item) => `
        <div class="card" style="box-shadow:none; margin:0;">
          <div class="card-header">
            <h4 class="card-title" style="font-size:16px;">${escHtml(item.scope)}</h4>
          </div>
          <div class="card-body" style="display:grid; gap:10px;">
            <div>
              <div style="font-size:12px; color: var(--color-text-muted); margin-bottom:6px;">changed_scenes</div>
              <div style="display:flex; gap:8px; flex-wrap:wrap;">
                ${(Array.isArray(item.changed_scenes) ? item.changed_scenes : []).map((scene) => `<span class="tag">${escHtml(scene)}</span>`).join('')}
              </div>
            </div>
            ${renderKV('reason', item.reason)}
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderRegressionCheck(items = []) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">回归检查结果</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map((item) => `
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

function renderCreativeAlignmentCheck(report = null) {
  if (!report) return '';
  const renderList = (label, items) => `
    <div>
      <div style="font-size:12px; color: var(--color-text-muted); margin-bottom:6px;">${escHtml(label)}</div>
      <ul style="margin:0; padding-left:18px; color: var(--color-text-primary); line-height:1.6;">
        ${(Array.isArray(items) ? items : []).map((item) => `<li>${escHtml(item)}</li>`).join('')}
      </ul>
    </div>`;
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">创作空间一致性检查</h3>
      <span class="tag">${escHtml(report.status || '-')}</span>
    </div>
    <div class="card-body" style="display:grid; gap:12px;">
      ${renderKV('status', report.status)}
      ${renderList('matched', report.matched)}
      ${renderList('deviations', report.deviations)}
      ${renderList('fix_paths', report.fix_paths)}
    </div>
  </div>`;
}

export function renderDirectorStep7(state = {}, directorState = {}) {
  const STEP_META = DIRECTOR_STEP_META.step7;
  const form = state.form || {};
  const generating = Boolean(state.generating);
  const error = state.error || '';
  const result = state.result || null;
  const projectId = directorState?.project?.project_id || '';

  return `
  <div style="display:grid; gap:12px;">
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">${DIRECTOR_AGENT_TITLE} · ${STEP_META.title}</h3>
        <span class="tag">${projectId ? `项目 ${escHtml(projectId)}` : '未绑定项目'}</span>
      </div>
      <div class="card-body">
        <div style="display:grid; gap:12px;">
          ${renderAcceptedTaskSummary(directorState)}
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">局部重写范围</span>
            <input class="search-input" type="text" value="${escHtml(form.rewrite_scope || '')}" placeholder="例如：按场 / 按段落 / 按整幕" oninput="setDirectorStep7Field('rewrite_scope', this.value)" />
          </label>
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">需要强化的指标</span>
            <input class="search-input" type="text" value="${escHtml(form.strengthen_metrics || '')}" placeholder="例如：紧张度 / 情感 / 反转密度 / 战术细节" oninput="setDirectorStep7Field('strengthen_metrics', this.value)" />
          </label>
        </div>
        <div style="display:flex; align-items:center; gap:10px; margin-top:12px; flex-wrap:wrap;">
          <button class="btn btn-primary" onclick="handleDirectorGenerateRewrite()" ${generating ? 'disabled' : ''}>
            ${generating ? '生成中...' : '生成新版本'}
          </button>
          <span style="color: var(--color-text-muted); font-size:12px;">当前为假响应，仅用于迭代改稿联调。</span>
        </div>
        ${error ? `<div style="margin-top:10px; color:#b42318; font-size:13px;">${escHtml(error)}</div>` : ''}
      </div>
    </div>

    ${renderSelectedSummary(directorState)}

    ${result ? `
      ${renderScriptReader(result)}
      ${renderChangeLog(result.change_log || [])}
      ${renderRegressionCheck(result.regression_check || [])}
      ${renderCreativeAlignmentCheck(result.creative_alignment_check || null)}
    ` : ''}
  </div>`;
}
