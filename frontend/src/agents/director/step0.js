import { DIRECTOR_AGENT_TITLE } from './meta.js';

function escHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function renderResultRow(label, value) {
  return `
    <div style="display:flex; gap:8px; padding:6px 0; border-bottom:1px solid var(--color-border-light);">
      <span style="min-width:88px; color: var(--color-text-muted);">${label}</span>
      <span style="color: var(--color-text-primary); word-break: break-word;">${escHtml(value || '-')}</span>
    </div>`;
}

export function renderDirectorStep0(state = {}) {
  const form = state.form || {};
  const project = state.project || null;
  const creating = Boolean(state.creating);
  const error = state.error || '';

  return `
  <div style="display:grid; gap:12px;">
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">${DIRECTOR_AGENT_TITLE} · 项目初始化</h3>
        <span class="tag">Step0</span>
      </div>
      <div class="card-body">
        <div style="display:grid; gap:10px;">
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">电影名字</span>
            <input class="search-input" type="text" value="${escHtml(form.movie_name)}" oninput="setDirectorField('movie_name', this.value)" placeholder="如：雾港追光" />
          </label>
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">类型</span>
            <input class="search-input" type="text" value="${escHtml(form.type)}" oninput="setDirectorField('type', this.value)" placeholder="如：短片 / 番剧 / PV" />
          </label>
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">时长</span>
            <input class="search-input" type="text" value="${escHtml(form.duration)}" oninput="setDirectorField('duration', this.value)" placeholder="如：90s / 24min" />
          </label>
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">基调</span>
            <input class="search-input" type="text" value="${escHtml(form.tone)}" oninput="setDirectorField('tone', this.value)" placeholder="如：热血 / 悬疑 / 治愈" />
          </label>
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">参考IP</span>
            <input class="search-input" type="text" value="${escHtml(form.reference_ip)}" oninput="setDirectorField('reference_ip', this.value)" placeholder="如：无（可留空）" />
          </label>
        </div>
        <div style="display:flex; align-items:center; gap:10px; margin-top:12px; flex-wrap:wrap;">
          <button class="btn btn-primary" onclick="handleDirectorCreateProject()" ${creating ? 'disabled' : ''}>
            ${creating ? '初始化中...' : '初始化项目'}
          </button>
          <span style="color: var(--color-text-muted); font-size: 12px;">Hard Gate 默认开启（可见，不打扰）。</span>
        </div>
        ${error ? `<div style="margin-top:10px; color:#b42318; font-size:13px;">${escHtml(error)}</div>` : ''}
      </div>
    </div>

    ${project ? `
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">项目已创建</h3>
        <span class="tag">${escHtml(project.status || 'created')}</span>
      </div>
      <div class="card-body">
        ${renderResultRow('项目 ID', project.project_id)}
        ${renderResultRow('电影名字', project.movie_name || form.movie_name)}
        ${renderResultRow('类型', project.type)}
        ${renderResultRow('时长', project.duration)}
        ${renderResultRow('基调', project.tone)}
        ${renderResultRow('参考IP', project.reference_ip)}
        ${renderResultRow('状态', project.status)}
      </div>
    </div>` : ''}
  </div>`;
}
