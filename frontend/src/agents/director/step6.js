import { DIRECTOR_AGENT_TITLE } from './meta.js';
import { DIRECTOR_REVIEW_DIMENSION_OPTIONS, DIRECTOR_STEP6_REVIEW_TABS } from './constants.js';

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
  const step5Done = Boolean(directorState.step5?.result);
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">当前已选</h3>
      <span class="tag">${step5Done ? '剧本一稿已完成' : '剧本一稿未完成'}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${renderKV('当前 Logline', logline?.title || '等待在“初始种子”中选定 Logline')}
      ${renderKV('当前 Mode', mode?.title || '等待在“初始种子”中选定创作模式')}
    </div>
  </div>`;
}

function renderDimensionsSelector(selected = []) {
  const selectedSet = new Set(Array.isArray(selected) ? selected : []);
  return `
    <div style="display:grid; gap:8px;">
      <span class="section-label" style="margin:0;">评审维度选择</span>
      <div style="display:flex; flex-wrap:wrap; gap:8px;">
        ${DIRECTOR_REVIEW_DIMENSION_OPTIONS.map((dim) => `
          <label class="tag" style="display:inline-flex; align-items:center; gap:6px; cursor:pointer;">
            <input type="checkbox" ${selectedSet.has(dim) ? 'checked' : ''} onchange="toggleDirectorReviewDimension('${dim}', this.checked)" />
            <span>${escHtml(dim)}</span>
          </label>
        `).join('')}
      </div>
    </div>`;
}

function renderIssues(items = []) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">问题清单</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map((item) => `
        <div class="card" style="box-shadow:none; margin:0;">
          <div class="card-header">
            <h4 class="card-title" style="font-size:16px;">${escHtml(item.title)}</h4>
            <span class="tag">${escHtml(item.severity)}</span>
          </div>
          <div class="card-body" style="display:grid; gap:10px;">
            ${renderKV('id', item.id)}
            ${renderKV('evidence', item.evidence)}
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderFixOptions(items = []) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">修复方案</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map((item) => `
        <div class="card" style="box-shadow:none; margin:0;">
          <div class="card-header">
            <h4 class="card-title" style="font-size:16px;">${escHtml(item.issue_id)}</h4>
          </div>
          <div class="card-body">
            <ul style="margin:0; padding-left:18px; color: var(--color-text-primary); line-height:1.6;">
              ${(Array.isArray(item.options) ? item.options : []).map((opt) => `<li>${escHtml(opt)}</li>`).join('')}
            </ul>
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderTaskSheet(items = [], taskSelections = {}) {
  const validActions = ['accept', 'ignore', 'alternative'];
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">一键修复任务单</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map((task) => {
        const current = validActions.includes(taskSelections?.[task.task_id]) ? taskSelections[task.task_id] : (task.default_action || 'accept');
        return `
        <div class="card" style="box-shadow:none; margin:0;">
          <div class="card-header">
            <h4 class="card-title" style="font-size:16px;">${escHtml(task.label)}</h4>
            <span class="tag">${escHtml(task.task_id)}</span>
          </div>
          <div class="card-body" style="display:grid; gap:10px;">
            ${renderKV('issue_id', task.issue_id)}
            ${renderKV('default_action', task.default_action)}
            <label style="display:grid; gap:6px;">
              <span class="section-label" style="margin:0;">当前选择（本地）</span>
              <select class="search-input" style="max-width:220px;" onchange="setDirectorReviewTaskSelection('${task.task_id}', this.value)">
                ${validActions.map((action) => `<option value="${action}" ${current === action ? 'selected' : ''}>${action}</option>`).join('')}
              </select>
            </label>
          </div>
        </div>`;
      }).join('')}
    </div>
  </div>`;
}

function renderChangeImpact(items = []) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">版本变更预估</h3>
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
              <div style="font-size:12px; color: var(--color-text-muted); margin-bottom:6px;">affected_scenes</div>
              <div style="display:flex; gap:8px; flex-wrap:wrap;">
                ${(Array.isArray(item.affected_scenes) ? item.affected_scenes : []).map((scene) => `<span class="tag">${escHtml(scene)}</span>`).join('')}
              </div>
            </div>
            ${renderKV('note', item.note)}
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderHardSoftList(title, items = []) {
  return `
    <div class="card" style="box-shadow:none; margin:0;">
      <div class="card-header">
        <h4 class="card-title" style="font-size:16px;">${escHtml(title)}</h4>
        <span class="tag">${items.length}</span>
      </div>
      <div class="card-body" style="display:grid; gap:10px;">
        ${items.map((item) => `
          <div class="card" style="box-shadow:none; margin:0; border-style:dashed;">
            <div class="card-header">
              <h5 class="card-title" style="font-size:14px;">${escHtml(item.type)}</h5>
              <span class="tag">${escHtml(item.status)}</span>
            </div>
            <div class="card-body">
              ${renderKV('evidence', item.evidence)}
            </div>
          </div>
        `).join('')}
      </div>
    </div>`;
}

function renderHardSoftReport(report = null) {
  if (!report) return '';
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">Hard / Soft 分层报告</h3>
      <span class="tag">报告</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${renderHardSoftList('hard', Array.isArray(report.hard) ? report.hard : [])}
      ${renderHardSoftList('soft', Array.isArray(report.soft) ? report.soft : [])}
    </div>
  </div>`;
}

function renderReviewSubTabs(activeTab) {
  const tabs = [
    { key: DIRECTOR_STEP6_REVIEW_TABS.ISSUES, label: '问题清单' },
    { key: DIRECTOR_STEP6_REVIEW_TABS.TASKS, label: '任务单' },
    { key: DIRECTOR_STEP6_REVIEW_TABS.IMPACT, label: '影响预估' },
    { key: DIRECTOR_STEP6_REVIEW_TABS.REPORT, label: 'Hard&Soft报告' },
  ];
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">评审结果视图</h3>
      <span class="tag">子标签</span>
    </div>
    <div class="card-body">
      <div style="display:flex; gap:8px; flex-wrap:wrap;">
        ${tabs.map((tab) => `
          <button class="pill ${activeTab === tab.key ? 'active' : ''}" onclick="setDirectorStep6Tab('${tab.key}')">${tab.label}</button>
        `).join('')}
      </div>
    </div>
  </div>`;
}

export function renderDirectorStep6(state = {}, directorState = {}) {
  const form = state.form || {};
  const activeTab = state.activeTab || DIRECTOR_STEP6_REVIEW_TABS.ISSUES;
  const generating = Boolean(state.generating);
  const error = state.error || '';
  const result = state.result || null;
  const taskSelections = state.taskSelections || {};
  const projectId = directorState?.project?.project_id || '';

  return `
  <div style="display:grid; gap:12px;">
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">${DIRECTOR_AGENT_TITLE} · 评审质检</h3>
        <span class="tag">${projectId ? `项目 ${escHtml(projectId)}` : '未绑定项目'}</span>
      </div>
      <div class="card-body">
        <div style="display:grid; gap:12px;">
          ${renderDimensionsSelector(form.review_dimensions || [])}
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">修改偏好</span>
            <input class="search-input" type="text" value="${escHtml(form.rewrite_preference || '')}" placeholder="例如：保守修补 / 中度重构 / 激进重写" oninput="setDirectorStep6Field('rewrite_preference', this.value)" />
          </label>
        </div>
        <div style="display:flex; align-items:center; gap:10px; margin-top:12px; flex-wrap:wrap;">
          <button class="btn btn-primary" onclick="handleDirectorStartReview()" ${generating ? 'disabled' : ''}>
            ${generating ? '评审中...' : '开始评审'}
          </button>
          <span style="color: var(--color-text-muted); font-size:12px;">当前为假响应，仅用于评审质检联调。</span>
        </div>
        ${error ? `<div style="margin-top:10px; color:#b42318; font-size:13px;">${escHtml(error)}</div>` : ''}
      </div>
    </div>

    ${renderSelectedSummary(directorState)}

    ${result ? `
      ${renderReviewSubTabs(activeTab)}
      ${activeTab === DIRECTOR_STEP6_REVIEW_TABS.ISSUES ? `
        ${renderIssues(result.issues || [])}
        ${renderFixOptions(result.fix_options || [])}
      ` : ''}
      ${activeTab === DIRECTOR_STEP6_REVIEW_TABS.TASKS ? renderTaskSheet(result.task_sheet || [], taskSelections) : ''}
      ${activeTab === DIRECTOR_STEP6_REVIEW_TABS.IMPACT ? renderChangeImpact(result.change_impact || []) : ''}
      ${activeTab === DIRECTOR_STEP6_REVIEW_TABS.REPORT ? renderHardSoftReport(result.hard_soft_report || null) : ''}
    ` : ''}
  </div>`;
}
