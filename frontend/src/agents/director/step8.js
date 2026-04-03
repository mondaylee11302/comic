import { DIRECTOR_AGENT_TITLE } from './meta.js';
import { DIRECTOR_STEP_META } from './steps_meta.js';

const ASSET_FILTER_OPTIONS = ['全部', '剧本', '结构', '场次', '评审', '归档'];
const EXPORT_FORMAT_OPTIONS = ['PDF', 'Word', 'FDX', 'Excel', 'CSV', 'JSON'];
const EXPORT_ITEM_OPTIONS = [
  '剧本',
  '分场表',
  '结构蓝图',
  'Beat Sheet',
  '评审报告',
  '改稿日志',
  '角色表',
  '模式宪法',
  '创作空间面板',
];

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
  const step7Done = Boolean(directorState.step7?.result);
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">当前已选</h3>
      <span class="tag">${step7Done ? '迭代改稿已完成' : '迭代改稿未完成'}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${renderKV('当前 Logline', logline?.title || '等待在“初始种子”中选定 Logline')}
      ${renderKV('当前 Mode', mode?.title || '等待在“初始种子”中选定创作模式')}
    </div>
  </div>`;
}

function renderExportItemSelector(selectedItems = []) {
  const selected = new Set(Array.isArray(selectedItems) ? selectedItems : []);
  return `
  <div style="display:grid; gap:8px;">
    <span class="section-label" style="margin:0;">导出包内容勾选</span>
    <div style="display:flex; flex-wrap:wrap; gap:8px;">
      ${EXPORT_ITEM_OPTIONS.map((item) => `
        <label class="tag" style="display:inline-flex; align-items:center; gap:6px; cursor:pointer;">
          <input type="checkbox" ${selected.has(item) ? 'checked' : ''} onchange="toggleDirectorExportItem('${item}', this.checked)" />
          <span>${escHtml(item)}</span>
        </label>
      `).join('')}
    </div>
  </div>`;
}

function renderAssetOverview(items = []) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">资产总览</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map((item) => `
        <div class="card" style="box-shadow:none; margin:0;">
          <div class="card-body" style="display:grid; gap:8px;">
            ${renderKV('type', item.type)}
            ${renderKV('count', item.count)}
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderVersionAssets(items = []) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">版本资产列表</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map((row) => `
        <div class="card" style="box-shadow:none; margin:0;">
          <div class="card-header">
            <h4 class="card-title" style="font-size:16px;">${escHtml(row.version)}</h4>
          </div>
          <div class="card-body">
            <ul style="margin:0; padding-left:18px; color: var(--color-text-primary); line-height:1.6;">
              ${(Array.isArray(row.assets) ? row.assets : []).map((a) => `<li>${escHtml(a)}</li>`).join('')}
            </ul>
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderExportBundlePreview(preview = null) {
  if (!preview) return '';
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">导出包预览</h3>
      <span class="tag">${escHtml(preview.export_format || '-')}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${renderKV('selected_version', preview.selected_version)}
      ${renderKV('export_format', preview.export_format)}
      <div>
        <div style="font-size:12px; color: var(--color-text-muted); margin-bottom:6px;">items</div>
        <div style="display:flex; gap:8px; flex-wrap:wrap;">
          ${(Array.isArray(preview.items) ? preview.items : []).map((item) => `<span class="tag">${escHtml(item)}</span>`).join('')}
        </div>
      </div>
      ${renderKV('summary', preview.summary)}
    </div>
  </div>`;
}

function renderDownloadItems(items = []) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">可下载项列表</h3>
      <span class="tag">${items.length}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${items.map((item) => `
        <div class="card" style="box-shadow:none; margin:0;">
          <div class="card-header">
            <h4 class="card-title" style="font-size:16px;">${escHtml(item.label)}</h4>
            <span class="tag">${escHtml(item.status)}</span>
          </div>
          <div class="card-body">
            ${renderKV('kind', item.kind)}
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderArchiveSnapshot(snapshot = null) {
  if (!snapshot) return '';
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">归档快照</h3>
      <span class="tag">${escHtml(snapshot.current_version || '-')}</span>
    </div>
    <div class="card-body" style="display:grid; gap:10px;">
      ${renderKV('mode_constitution', snapshot.mode_constitution)}
      <div>
        <div style="font-size:12px; color: var(--color-text-muted); margin-bottom:6px;">creative_panel_summary</div>
        <ul style="margin:0; padding-left:18px; color: var(--color-text-primary); line-height:1.6;">
          ${(Array.isArray(snapshot.creative_panel_summary) ? snapshot.creative_panel_summary : []).map((line) => `<li>${escHtml(line)}</li>`).join('')}
        </ul>
      </div>
      ${renderKV('current_version', snapshot.current_version)}
    </div>
  </div>`;
}

export function renderDirectorStep8(state = {}, directorState = {}) {
  const STEP_META = DIRECTOR_STEP_META.step8;
  const form = state.form || {};
  const generating = Boolean(state.generating);
  const error = state.error || '';
  const result = state.result || null;
  const projectId = directorState?.project?.project_id || '';
  const exportItems = Array.isArray(form.export_items) ? form.export_items : [];

  return `
  <div style="display:grid; gap:12px;">
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">${DIRECTOR_AGENT_TITLE} · ${STEP_META.title}</h3>
        <span class="tag">${projectId ? `项目 ${escHtml(projectId)}` : '未绑定项目'}</span>
      </div>
      <div class="card-body">
        <div style="display:grid; gap:12px;">
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">版本选择</span>
            <input class="search-input" type="text" value="${escHtml(form.selected_version || '')}" placeholder="例如：Draft v2" oninput="setDirectorStep8Field('selected_version', this.value)" />
          </label>
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">资产筛选</span>
            <select class="search-input" onchange="setDirectorStep8Field('asset_filter', this.value)">
              ${ASSET_FILTER_OPTIONS.map((opt) => `<option value="${opt}" ${form.asset_filter === opt ? 'selected' : ''}>${opt}</option>`).join('')}
            </select>
          </label>
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">导出格式</span>
            <select class="search-input" onchange="setDirectorStep8Field('export_format', this.value)">
              ${EXPORT_FORMAT_OPTIONS.map((opt) => `<option value="${opt}" ${form.export_format === opt ? 'selected' : ''}>${opt}</option>`).join('')}
            </select>
          </label>
          ${renderExportItemSelector(exportItems)}
        </div>
        <div style="display:flex; align-items:center; gap:10px; margin-top:12px; flex-wrap:wrap;">
          <button class="btn btn-primary" onclick="handleDirectorGenerateDeliverables()" ${generating ? 'disabled' : ''}>
            ${generating ? '生成中...' : '生成导出包预览'}
          </button>
          <span style="color: var(--color-text-muted); font-size:12px;">当前为假响应，仅用于资产与导出联调。</span>
        </div>
        ${error ? `<div style="margin-top:10px; color:#b42318; font-size:13px;">${escHtml(error)}</div>` : ''}
      </div>
    </div>

    ${renderSelectedSummary(directorState)}

    ${result ? `
      ${renderAssetOverview(result.asset_overview || [])}
      ${renderVersionAssets(result.version_assets || [])}
      ${renderExportBundlePreview(result.export_bundle_preview || null)}
      ${renderDownloadItems(result.download_items || [])}
      ${renderArchiveSnapshot(result.archive_snapshot || null)}
    ` : ''}
  </div>`;
}
