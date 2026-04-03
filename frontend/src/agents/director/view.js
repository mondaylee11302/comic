import {
  DIRECTOR_AGENT_TITLE,
} from './meta.js';
import { DIRECTOR_STEPS } from './constants.js';
import { getDirectorStepMeta } from './steps_meta.js';
import { renderDirectorStep0 } from './step0.js';
import { renderDirectorStep1 } from './step1.js';
import { renderDirectorStep2 } from './step2.js';
import { renderDirectorStep3 } from './step3.js';
import { renderDirectorStep4 } from './step4.js';
import { renderDirectorStep5 } from './step5.js';
import { renderDirectorStep6 } from './step6.js';
import { renderDirectorStep7 } from './step7.js';
import { renderDirectorStep8 } from './step8.js';

const DIRECTOR_SIDEBAR_ITEMS = [
  { step: DIRECTOR_STEPS.STEP0, icon: '📁', label: '项目初始化' },
  { step: DIRECTOR_STEPS.STEP1, icon: '🌱', label: '初始种子' },
  { step: DIRECTOR_STEPS.STEP2, icon: '🧱', label: '结构蓝图' },
  { step: DIRECTOR_STEPS.STEP3, icon: '🧩', label: '段落节拍' },
  { step: DIRECTOR_STEPS.STEP4, icon: '🎬', label: '分场表' },
  { step: DIRECTOR_STEPS.STEP5, icon: '📝', label: '剧本一稿' },
  { step: DIRECTOR_STEPS.STEP6, icon: '🧪', label: '评审质检' },
  { step: DIRECTOR_STEPS.STEP7, icon: '🔁', label: '迭代改稿' },
  { step: DIRECTOR_STEPS.STEP8, icon: '🧰', label: '编导资产 + 交付导出' },
];

function escAttr(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function escHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function canEnterDirectorStep(state, step) {
  if (!state) return false;
  if (step === DIRECTOR_STEPS.STEP0) return true;
  if (step === DIRECTOR_STEPS.STEP1) return Boolean(state.project?.project_id);
  if (step === DIRECTOR_STEPS.STEP2) {
    return Boolean(
      state.project?.project_id
      && Number.isInteger(state.step1?.selected_logline_index)
      && Number.isInteger(state.step1?.selected_mode_index),
    );
  }
  if (step === DIRECTOR_STEPS.STEP3) {
    return Boolean(
      state.project?.project_id
      && Number.isInteger(state.step1?.selected_logline_index)
      && Number.isInteger(state.step1?.selected_mode_index)
      && state.step2?.result,
    );
  }
  if (step === DIRECTOR_STEPS.STEP4) {
    return Boolean(
      state.project?.project_id
      && Number.isInteger(state.step1?.selected_logline_index)
      && Number.isInteger(state.step1?.selected_mode_index)
      && state.step3?.result,
    );
  }
  if (step === DIRECTOR_STEPS.STEP5) {
    return Boolean(
      state.project?.project_id
      && Number.isInteger(state.step1?.selected_logline_index)
      && Number.isInteger(state.step1?.selected_mode_index)
      && state.step4?.result,
    );
  }
  if (step === DIRECTOR_STEPS.STEP6) {
    return Boolean(
      state.project?.project_id
      && Number.isInteger(state.step1?.selected_logline_index)
      && Number.isInteger(state.step1?.selected_mode_index)
      && state.step5?.result,
    );
  }
  if (step === DIRECTOR_STEPS.STEP7) {
    return Boolean(
      state.project?.project_id
      && Number.isInteger(state.step1?.selected_logline_index)
      && Number.isInteger(state.step1?.selected_mode_index)
      && state.step6?.result,
    );
  }
  if (step === DIRECTOR_STEPS.STEP8) {
    return Boolean(state.project?.project_id && state.step7?.result);
  }
  return false;
}

function renderDirectorStepContent(state) {
  if (state.step === DIRECTOR_STEPS.STEP8) return renderDirectorStep8(state.step8, state);
  if (state.step === DIRECTOR_STEPS.STEP7) return renderDirectorStep7(state.step7, state);
  if (state.step === DIRECTOR_STEPS.STEP6) return renderDirectorStep6(state.step6, state);
  if (state.step === DIRECTOR_STEPS.STEP5) return renderDirectorStep5(state.step5, state);
  if (state.step === DIRECTOR_STEPS.STEP4) return renderDirectorStep4(state.step4, state);
  if (state.step === DIRECTOR_STEPS.STEP3) return renderDirectorStep3(state.step3, state);
  if (state.step === DIRECTOR_STEPS.STEP2) return renderDirectorStep2(state.step2, state);
  if (state.step === DIRECTOR_STEPS.STEP1) return renderDirectorStep1(state.step1, state);
  return renderDirectorStep0(state);
}

function renderDirectorHome(state) {
  const recentItems = Array.isArray(state?.projectShelf?.items) ? state.projectShelf.items.slice(0, 3) : [];
  return `
  <div class="director-home-shell">
    <div class="card director-home-hero">
      <div class="card-body" style="padding:40px 28px; display:grid; gap:18px; justify-items:center; text-align:center;">
        <div style="width:68px; height:68px; border-radius:16px; display:grid; place-items:center; background:rgba(59,130,246,.08); color:var(--color-brand); border:1px solid rgba(59,130,246,.16); font-size:28px;">🎬</div>
        <div>
          <div style="font-size:28px; font-weight:700; color:var(--color-text-primary); line-height:1.2;">${DIRECTOR_AGENT_TITLE}</div>
          <div style="margin-top:8px; color:var(--color-text-muted); line-height:1.6;">
            从项目管理进入剧本工作台，按阶段完成初始种子、结构蓝图、分场表、评审与迭代改稿。
          </div>
        </div>
        <div style="display:flex; gap:10px; flex-wrap:wrap; justify-content:center;">
          <button class="btn btn-primary" onclick="openDirectorProjectShelf()">我的剧本</button>
          <button class="btn btn-secondary" onclick="openDirectorNewScriptWorkspace()">新建剧本</button>
        </div>
      </div>
    </div>

    ${recentItems.length ? `
    <div class="director-home-recent">
      ${recentItems.map((item) => `
        <div class="card director-home-recent-card" role="button" tabindex="0" onclick="openDirectorProjectWorkspace('${escAttr(item.id)}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openDirectorProjectWorkspace('${escAttr(item.id)}');}">
          <div class="card-header">
            <h3 class="card-title">${escHtml(item.title)}</h3>
            <span class="tag tag-slate">${escHtml(item.status || '项目')}</span>
          </div>
          <div class="card-body" style="display:grid; gap:8px;">
            <div class="director-project-card-kv">
              <div class="director-project-card-kv-label">上次修改</div>
              <div class="director-project-card-kv-value">${escHtml(item.updatedAt || '-')}</div>
            </div>
            <div class="director-project-card-tag-row">
              ${item.type ? `<span class="tag tag-blue">${escHtml(item.type)}</span>` : ''}
              ${item.duration ? `<span class="tag tag-slate">${escHtml(item.duration)}</span>` : ''}
              ${item.tone ? `<span class="tag tag-violet">${escHtml(item.tone)}</span>` : ''}
            </div>
          </div>
        </div>
      `).join('')}
    </div>` : ''}
  </div>`;
}

function renderDirectorProjectShelf(state) {
  const items = Array.isArray(state?.projectShelf?.items) ? state.projectShelf.items : [];
  return `
  <div style="display:grid; gap:12px;">
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">${DIRECTOR_AGENT_TITLE} · 我的剧本</h3>
        <div style="display:flex; gap:8px; align-items:center;">
          <span class="tag">${items.length} 个项目</span>
          <button class="btn btn-secondary" onclick="setDirectorUiPage('home')">返回主页</button>
        </div>
      </div>
      <div class="card-body">
        <div style="color: var(--color-text-muted); font-size:12px;">点击卡片进入该剧本工作台；“新建剧本”将进入空白工作台。</div>
      </div>
    </div>

    <div class="director-project-grid">
      <div class="card director-project-card director-project-card-create" role="button" tabindex="0" onclick="openDirectorNewScriptWorkspace()" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openDirectorNewScriptWorkspace();}">
        <div class="card-header">
          <h3 class="card-title">＋ 新建剧本</h3>
          <span class="tag">空白工作台</span>
        </div>
        <div class="card-body" style="display:grid; gap:8px;">
          <div class="director-project-card-sub">进入编导智能体工作台（默认空白状态 / mock 可逐步生成）。</div>
          <div style="display:flex; gap:8px; flex-wrap:wrap;">
            <span class="tag tag-blue">项目初始化</span>
            <span class="tag tag-violet">初始种子</span>
            <span class="tag tag-rose">结构蓝图</span>
          </div>
          <div class="director-project-card-sub">创建后可继续进入段落节拍、分场表、评审质检与导出阶段。</div>
        </div>
      </div>

      ${items.map((item) => `
        <div class="card director-project-card" role="button" tabindex="0" onclick="openDirectorProjectWorkspace('${escAttr(item.id)}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openDirectorProjectWorkspace('${escAttr(item.id)}');}">
          <div class="card-header">
            <h3 class="card-title">${escHtml(item.title)}</h3>
            <span class="tag tag-slate">${escHtml(item.status || '项目')}</span>
          </div>
          <div class="card-body" style="display:grid; gap:8px;">
            <div class="director-project-card-kv">
              <div class="director-project-card-kv-label">上次修改</div>
              <div class="director-project-card-kv-value">${escHtml(item.updatedAt || '-')}</div>
            </div>
            <div class="director-project-card-sub">${escHtml(item.referenceIp || '原创')} · 点击进入工作台继续编辑</div>
            <div class="director-project-card-tag-row">
              ${item.type ? `<span class="tag tag-blue">${escHtml(item.type)}</span>` : ''}
              ${item.duration ? `<span class="tag tag-slate">${escHtml(item.duration)}</span>` : ''}
              ${item.tone ? `<span class="tag tag-violet">${escHtml(item.tone)}</span>` : ''}
            </div>
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
}

function renderDirectorWorkspace(state) {
  const currentProjectTitle = state?.workspaceProjectMeta?.title || '未命名剧本';
  const currentUpdatedAt = state?.workspaceProjectMeta?.updatedAt || '未保存';
  return `
  <div class="agent-layout">
    <aside class="agent-sidebar">
      <div class="agent-sidebar-logo">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="22" height="22">
          <rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>
          <rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>
        </svg>
        <span>${DIRECTOR_AGENT_TITLE}</span>
      </div>
      <nav class="agent-nav">
        ${DIRECTOR_SIDEBAR_ITEMS.map((item) => {
          const active = state.step === item.step;
          const meta = getDirectorStepMeta(item.step);
          const reachableHint = canEnterDirectorStep(state, item.step) ? '' : `（未就绪：${meta?.enterHint || '请先完成前置数据'}）`;
          return `
          <button
            class="agent-nav-item ${active ? 'active' : ''}"
            onclick="setDirectorStep('${item.step}')"
            title="${escAttr((meta?.enterHint || item.label) + reachableHint)}"
          >
            <span class="agent-nav-icon">${item.icon}</span>
            <span class="agent-nav-label">${item.label}</span>
          </button>`;
        }).join('')}
      </nav>
    </aside>
    <div class="agent-content" style="display:grid; gap:12px;">
      <div class="card director-workspace-header-card director-stage-wrap">
        <div class="card-header">
          <h3 class="card-title">${escHtml(currentProjectTitle)}</h3>
          <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
            <span class="tag">上次修改 ${escHtml(currentUpdatedAt)}</span>
            <button class="btn btn-secondary" onclick="openDirectorProjectShelf()">我的剧本</button>
            <button class="btn btn-secondary" onclick="setDirectorUiPage('home')">主页</button>
          </div>
        </div>
      </div>
      <div class="director-stage-wrap">
        ${renderDirectorStepContent(state)}
      </div>
    </div>
  </div>`;
}

export function renderDirectorAgentView(state) {
  if (!state) {
    return `
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">${DIRECTOR_AGENT_TITLE}</h3>
        <span class="tag">未初始化</span>
      </div>
    </div>`;
  }

  const uiPage = state.uiPage || 'workspace';
  if (uiPage === 'home') return renderDirectorHome(state);
  if (uiPage === 'projects') return renderDirectorProjectShelf(state);
  return renderDirectorWorkspace(state);
}
