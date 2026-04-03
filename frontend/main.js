/* ========================================
   子曰工坊V2 — Workbench + Script Studio
   ======================================== */

import { API_BASE, apiFetch, fileUrl } from './src/shared/api/client.js';
import {
  STORYBOARD_AGENT_TITLE,
  STORYBOARD_DEFAULT_TAB,
  STORYBOARD_TABS,
} from './src/agents/storyboard/meta.js';
import {
  DIRECTOR_AGENT_TITLE,
} from './src/agents/director/meta.js';
import { DIRECTOR_STEP6_REVIEW_TABS, DIRECTOR_STEPS } from './src/agents/director/constants.js';
import { createDirectorInitialState } from './src/agents/director/state.js';
import { renderDirectorAgentView } from './src/agents/director/view.js';

// ============ Icons ============
const I = {
  search: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2"><circle cx="8.5" cy="8.5" r="5.5"/><line x1="13" y1="13" x2="17" y2="17"/></svg>`,
  plus: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2"><line x1="10" y1="4" x2="10" y2="16"/><line x1="4" y1="10" x2="16" y2="10"/></svg>`,
  upload: `<svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M24 32V14m0 0l-7 7m7-7l7 7"/><path d="M8 28v10a4 4 0 004 4h24a4 4 0 004-4V28"/></svg>`,
  play: `<svg viewBox="0 0 20 20" fill="currentColor"><polygon points="5,3 17,10 5,17"/></svg>`,
  check: `<svg viewBox="0 0 16 16" fill="currentColor"><path d="M6.5 11.5L3 8l1-1 2.5 2.5L12 4l1 1z"/></svg>`,
  chevron: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 4l6 6-6 6"/></svg>`,
  external: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M15 11v5a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h5"/><path d="M12 3h5v5"/><path d="M8 12L17 3"/></svg>`,
  retry: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 10a7 7 0 0112.9-3.7M17 10a7 7 0 01-12.9 3.7"/><polyline points="3 4 3 8 7 8"/><polyline points="17 16 17 12 13 12"/></svg>`,
  download: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M10 3v10m0 0l-3-3m3 3l3-3"/><path d="M3 14v2a2 2 0 002 2h10a2 2 0 002-2v-2"/></svg>`,
  back: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 4l-6 6 6 6"/></svg>`,
  empty: `<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2"><rect x="8" y="12" width="48" height="40" rx="4"/><path d="M8 24h48"/><circle cx="16" cy="18" r="2" fill="currentColor"/><circle cx="24" cy="18" r="2" fill="currentColor"/></svg>`,
  settings: `<svg viewBox="0 0 80 80" fill="none" stroke="currentColor" stroke-width="3"><circle cx="40" cy="40" r="12"/><path d="M40 8v8M40 64v8M8 40h8M64 40h8M17.5 17.5l5.6 5.6M56.9 56.9l5.6 5.6M17.5 62.5l5.6-5.6M56.9 23.1l5.6-5.6"/></svg>`,
  sparkle: `<svg viewBox="0 0 20 20" fill="currentColor"><path d="M10 1l2.2 6.3L19 9l-6.3 2.2L10 19l-2.2-6.3L1 11l6.3-2.2z"/></svg>`,
  copy: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="6" y="6" width="11" height="11" rx="2"/><path d="M4 14V4a2 2 0 012-2h10"/></svg>`,
  loading: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin-icon"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>`,
};

// ============ State ============
const S = {
  view: 'agent',
  tab: 'storyboard',
  agentModule: 'storyboard', // 'storyboard' | 'director'
  agentTab: STORYBOARD_DEFAULT_TAB, // storyboard sub-tabs
  director: createDirectorInitialState(),
  // workbench
  runs: [],
  statusFilter: 'all',
  searchQ: '',
  uploadQueue: [], // [{ id, name, path, previewUrl }]
  selectedStrategy: 'normal',
  imagePreviewDialog: null, // { name, url }
  // studio
  studioRunId: null,
  studioResult: null, // { panels, texts, cleanImage, run }
  selectedPanel: null, // panel_id
  selectedTexts: new Set(),
  scriptPrompt: '',
  panelScripts: {},   // map of panel_id -> script result (persists across panel switches)
  scriptLoading: false,
  bindingSaving: false,
  studioTextPoolMode: 'all', // 'all' | 'bound'
  hoverStudioPanel: null, // { panelId, x, y }
  studioPanelsScrollTop: 0,
  studioOriginalScrollTop: 0,
  studioTextPoolScrollTop: 0,
  // assets
  assets: [],
  assetSearch: '',
  expandedAssets: new Set(),
  assetDetails: {}, // file -> detail payload
  assetDetailLoading: {}, // file -> boolean
  activeAssetDetail: null, // { file, selectedPanelId }
  assetNoteSaving: {}, // `${file}::${panelId}` -> bool
  settings: {
    apiKeyInput: '',
    hasApiKey: false,
    apiKeyMasked: '',
    defaults: null,
    loading: false,
    saving: false,
    loaded: false,
  },
  // misc
  pollTimer: null,
  loading: {},
};

let uiStateHydrated = false;
let uiStateSaveTimer = null;

// ============ Data ============
function serializeWorkbenchUiState() {
  return {
    view: S.view === 'settings' ? 'settings' : 'agent',
    tab: S.tab === 'settings' ? 'settings' : (S.agentModule === 'director' ? 'director' : 'storyboard'),
    agentModule: S.agentModule === 'director' ? 'director' : 'storyboard',
    agentTab: STORYBOARD_TABS.includes(S.agentTab) ? S.agentTab : STORYBOARD_DEFAULT_TAB,
    statusFilter: S.statusFilter || 'all',
    searchQ: S.searchQ || '',
    assetSearch: S.assetSearch || '',
    selectedStrategy: S.selectedStrategy || 'normal',
    studioRunId: S.studioRunId || null,
    // Uploaded files already exist on disk after /api/upload, so queue entries are safe to persist.
    uploadQueue: Array.isArray(S.uploadQueue)
      ? S.uploadQueue.map(item => ({
        id: item.id,
        name: item.name,
        path: item.path,
        previewUrl: item.previewUrl || null,
      }))
      : [],
  };
}

function applyWorkbenchUiState(state) {
  if (!state || typeof state !== 'object') return;
  const topView = state.view === 'settings' ? 'settings' : 'agent';
  const agentModule = state.agentModule === 'director' ? 'director' : 'storyboard';
  S.view = topView;
  S.agentModule = agentModule;
  S.tab = topView === 'settings' ? 'settings' : agentModule;
  if (STORYBOARD_TABS.includes(state.agentTab)) S.agentTab = state.agentTab;
  if (['all', 'success', 'running', 'error'].includes(state.statusFilter)) S.statusFilter = state.statusFilter;
  if (typeof state.searchQ === 'string') S.searchQ = state.searchQ;
  if (typeof state.assetSearch === 'string') S.assetSearch = state.assetSearch;
  if (['normal', 'advanced'].includes(state.selectedStrategy)) S.selectedStrategy = state.selectedStrategy;
  if (typeof state.studioRunId === 'string' && state.studioRunId) S.studioRunId = state.studioRunId;
  if (Array.isArray(state.uploadQueue)) {
    S.uploadQueue = state.uploadQueue
      .filter(item => item && typeof item === 'object' && typeof item.path === 'string')
      .map(item => ({
        id: item.id || makeUploadQueueId(),
        name: item.name || '未命名文件',
        path: item.path,
        previewUrl: item.previewUrl || null,
      }));
  }
}

async function loadWorkbenchUiState() {
  try {
    const state = await apiFetch('/api/ui/workbench-state');
    applyWorkbenchUiState(state);
  } catch (e) {
    console.warn('loadWorkbenchUiState failed', e);
  } finally {
    uiStateHydrated = true;
  }
}

async function fetchRuntimeSettings() {
  S.settings.loading = true;
  try {
    const payload = await apiFetch('/api/settings/runtime');
    S.settings.hasApiKey = !!payload?.hasApiKey;
    S.settings.apiKeyMasked = payload?.apiKeyMasked || '';
    S.settings.defaults = payload?.defaults || null;
    S.settings.loaded = true;
    return payload;
  } catch (e) {
    console.warn('fetchRuntimeSettings failed', e);
    throw e;
  } finally {
    S.settings.loading = false;
  }
}

async function saveRuntimeSettings() {
  const apiKey = String(S.settings.apiKeyInput || '').trim();
  if (!apiKey) {
    toast('请输入 API Key', 'error');
    return false;
  }
  S.settings.saving = true;
  render();
  try {
    const res = await apiFetch('/api/settings/runtime', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ apiKey }),
    });
    const next = res?.settings || {};
    S.settings.hasApiKey = !!next.hasApiKey;
    S.settings.apiKeyMasked = next.apiKeyMasked || '';
    S.settings.defaults = next.defaults || S.settings.defaults;
    S.settings.apiKeyInput = '';
    toast('API Key 已保存', 'success');
    return true;
  } catch (e) {
    toast(`保存失败: ${e.message}`, 'error');
    return false;
  } finally {
    S.settings.saving = false;
    render();
  }
}

function scheduleSaveWorkbenchUiState() {
  if (!uiStateHydrated) return;
  if (uiStateSaveTimer) clearTimeout(uiStateSaveTimer);
  uiStateSaveTimer = setTimeout(async () => {
    uiStateSaveTimer = null;
    try {
      await apiFetch('/api/ui/workbench-state', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(serializeWorkbenchUiState()),
      });
    } catch (e) {
      console.warn('saveWorkbenchUiState failed', e);
    }
  }, 180);
}

async function fetchRuns() {
  try { S.runs = await apiFetch('/api/runs'); } catch (e) { console.error(e); }
}
async function fetchAssets() {
  try { S.assets = await apiFetch('/api/assets/psd'); } catch (e) { console.error(e); }
}
async function fetchAssetDetail(file) {
  if (!file) return null;
  if (S.assetDetails[file]) return S.assetDetails[file];
  if (S.assetDetailLoading[file]) return null;
  S.assetDetailLoading[file] = true;
  try {
    const detail = await apiFetch(`/api/assets/psd/detail?file=${encodeURIComponent(file)}`);
    S.assetDetails[file] = detail;
    return detail;
  } catch (e) {
    console.error(e);
    toast(`加载资产详情失败: ${e.message}`, 'error');
    return null;
  } finally {
    delete S.assetDetailLoading[file];
  }
}
async function preloadAssetDetails() {
  const targets = (S.assets || []).map(a => a.file).filter(Boolean);
  for (const f of targets) {
    if (!S.assetDetails[f] && !S.assetDetailLoading[f]) {
      await fetchAssetDetail(f);
      if (S.agentTab === 'assets') render();
    }
  }
}
async function fetchStudioResult(runId) {
  S.studioRunId = runId;
  S.studioResult = null;
  S.selectedPanel = null;
  S.selectedTexts.clear();
  S.panelScripts = {};   // clear per-panel scripts when loading new run
  S.bindingSaving = false;
  S.studioTextPoolMode = 'all';
  S.studioOriginalScrollTop = 0;
  S.studioTextPoolScrollTop = 0;
  try {
    S.studioResult = await apiFetch(`/api/runs/${runId}/result`);
    if (S.studioResult.panels?.length) S.selectedPanel = S.studioResult.panels[0].panel_id;
    syncStudioTextPoolModeForCurrentPanel();
    // Auto-select texts belonging to the selected panel
    autoSelectPanelTexts();
  } catch (e) { console.error(e); toast(`加载结果失败: ${e.message}`, 'error'); }
}
function autoSelectPanelTexts() {
  S.selectedTexts.clear();
  if (!S.studioResult || !S.selectedPanel) return;
  const savedBinding = S.studioResult.panelTextScriptBindings?.[S.selectedPanel];
  if (Array.isArray(savedBinding?.selectedTextIds) && savedBinding.selectedTextIds.length) {
    for (const textId of savedBinding.selectedTextIds) S.selectedTexts.add(textId);
  }
}

function getCurrentPanelBinding() {
  if (!S.studioResult || !S.selectedPanel) return null;
  const b = S.studioResult.panelTextScriptBindings?.[S.selectedPanel];
  return b && typeof b === 'object' ? b : null;
}

function syncStudioTextPoolModeForCurrentPanel() {
  S.studioTextPoolMode = getCurrentPanelBinding() ? 'bound' : 'all';
}

function getVisibleStudioTexts(texts) {
  if (S.studioTextPoolMode !== 'bound') return texts || [];
  const binding = getCurrentPanelBinding();
  const ids = new Set(Array.isArray(binding?.selectedTextIds) ? binding.selectedTextIds.map(String) : []);
  if (!ids.size) return texts || [];
  return (texts || []).filter(t => ids.has(String(t.text_id || '')));
}

function startPoll() {
  stopPoll();
  S.pollTimer = setInterval(async () => {
    if (S.runs.some(r => r.status === 'running')) {
      await fetchRuns();
      if (S.view === 'agent') render();
    }
  }, 3000);
}
function stopPoll() { if (S.pollTimer) { clearInterval(S.pollTimer); S.pollTimer = null; } }

// ============ Router ============
function navigate(view, opts) {
  const targetView = view === 'settings' ? 'settings' : 'agent';
  if (view === 'storyboard') S.agentModule = 'storyboard';
  if (view === 'director') {
    S.agentModule = 'director';
    if (S.director) S.director.uiPage = 'home';
  }
  if (targetView === 'agent' && (opts?.agentTab || opts?.runId)) S.agentModule = 'storyboard';
  S.view = targetView;
  S.tab = targetView === 'settings' ? 'settings' : S.agentModule;
  S.imagePreviewDialog = null;
  S.hoverStudioPanel = null;
  S.activeAssetDetail = null;
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === S.tab));

  if (targetView === 'agent') {
    if (S.agentModule === 'director') {
      render();
      return;
    }
    if (opts?.agentTab) S.agentTab = opts.agentTab;
    // If switching to studio sub-tab with a runId
    if (opts?.runId) {
      S.agentTab = 'studio';
      fetchStudioResult(opts.runId).then(() => render());
      return;
    }
    // Ensure we have runs loaded
    if (!S.runs.length) {
      fetchRuns().then(async () => {
        if (S.agentTab === 'assets' && !S.assets.length) {
          await fetchAssets();
        }
        render();
        if (S.agentTab === 'assets') preloadAssetDetails();
        startPoll();
      });
      return;
    }
    if (S.agentTab === 'assets' && !S.assets.length) {
      fetchAssets().then(() => render()); return;
    }
    render(); startPoll(); return;
  }
  render();
}
window.navigate = navigate;

window.setAgentTab = function (tab) {
  S.agentTab = tab;
  S.imagePreviewDialog = null;
  S.hoverStudioPanel = null;
  S.activeAssetDetail = null;
  if (tab === 'assets' && !S.assets.length) {
    fetchAssets().then(() => { render(); preloadAssetDetails(); }); return;
  }
  if (tab === 'assets' && S.assets.length) {
    preloadAssetDetails();
  }
  if (tab === 'studio' && !S.studioResult && S.runs.length) {
    const done = S.runs.find(r => r.status === 'success');
    if (done) { fetchStudioResult(done.id).then(() => render()); return; }
  }
  render();
};

window.setAgentModule = function (module) {
  if (!['storyboard', 'director'].includes(module)) return;
  S.agentModule = module;
  if (module === 'director' && S.director) {
    S.director.uiPage = 'home';
  }
  S.imagePreviewDialog = null;
  S.hoverStudioPanel = null;
  S.activeAssetDetail = null;
  render();
};

function resetDirectorWorkspaceWithShell(projectCard) {
  const prev = S.director || createDirectorInitialState();
  const fresh = createDirectorInitialState();
  fresh.uiPage = 'workspace';
  fresh.projectShelf = prev.projectShelf || fresh.projectShelf;

  if (projectCard && typeof projectCard === 'object') {
    fresh.workspaceProjectMeta = {
      id: projectCard.id || 'local_project',
      title: projectCard.title || '未命名剧本',
      updatedAt: projectCard.updatedAt || '刚刚',
      isNew: false,
    };
    fresh.form.movie_name = projectCard.title || '';
    fresh.form.type = projectCard.type || '';
    fresh.form.duration = projectCard.duration || '';
    fresh.form.tone = projectCard.tone || '';
    fresh.form.reference_ip = projectCard.referenceIp || '';
    fresh.project = {
      project_id: `director_local_${String(projectCard.id || 'demo')}`,
      movie_name: fresh.form.movie_name,
      type: fresh.form.type,
      duration: fresh.form.duration,
      tone: fresh.form.tone,
      reference_ip: fresh.form.reference_ip,
      status: 'created',
    };
  } else {
    fresh.workspaceProjectMeta = {
      id: `draft_new_${Date.now()}`,
      title: '未命名剧本',
      updatedAt: '刚刚',
      isNew: true,
    };
  }

  S.director = fresh;
}

window.setDirectorUiPage = function (page) {
  if (!S.director) return;
  if (!['home', 'projects', 'workspace'].includes(page)) return;
  S.view = 'agent';
  S.tab = 'director';
  S.agentModule = 'director';
  S.director.uiPage = page;
  render();
};

window.openDirectorProjectShelf = function () {
  window.setDirectorUiPage('projects');
};

window.openDirectorNewScriptWorkspace = function () {
  S.view = 'agent';
  S.tab = 'director';
  S.agentModule = 'director';
  resetDirectorWorkspaceWithShell(null);
  render();
};

window.openDirectorProjectWorkspace = function (projectId) {
  if (!S.director?.projectShelf?.items) return;
  const card = S.director.projectShelf.items.find((item) => item && item.id === projectId);
  if (!card) return;
  S.view = 'agent';
  S.tab = 'director';
  S.agentModule = 'director';
  resetDirectorWorkspaceWithShell(card);
  render();
};

window.setDirectorField = function (field, value) {
  if (!S.director?.form || !Object.prototype.hasOwnProperty.call(S.director.form, field)) return;
  S.director.form[field] = value;
};

window.setDirectorStep = function (step) {
  if (!S.director || !Object.values(DIRECTOR_STEPS).includes(step)) return;
  S.director.uiPage = 'workspace';
  S.director.step = step;
  render();
};

window.setDirectorCreativeField = function (field, value) {
  if (!S.director?.creativePanel || !Object.prototype.hasOwnProperty.call(S.director.creativePanel, field)) return;
  S.director.creativePanel[field] = value;
};

window.applyDirectorCreativeExample = function (field, example) {
  if (!S.director?.creativePanel || !Object.prototype.hasOwnProperty.call(S.director.creativePanel, field)) return;
  S.director.creativePanel[field] = String(example ?? '');
  render();
};

window.setDirectorStep1Field = function (field, value) {
  if (!S.director?.step1?.form || !Object.prototype.hasOwnProperty.call(S.director.step1.form, field)) return;
  S.director.step1.form[field] = value;
};

window.setDirectorStep2Field = function (field, value) {
  if (!S.director?.step2?.form || !Object.prototype.hasOwnProperty.call(S.director.step2.form, field)) return;
  S.director.step2.form[field] = value;
};

window.setDirectorStep3Field = function (field, value) {
  if (!S.director?.step3?.form || !Object.prototype.hasOwnProperty.call(S.director.step3.form, field)) return;
  S.director.step3.form[field] = value;
};

window.setDirectorStep4Field = function (field, value) {
  if (!S.director?.step4?.form || !Object.prototype.hasOwnProperty.call(S.director.step4.form, field)) return;
  S.director.step4.form[field] = value;
};

window.setDirectorStep5Field = function (field, value) {
  if (!S.director?.step5?.form || !Object.prototype.hasOwnProperty.call(S.director.step5.form, field)) return;
  S.director.step5.form[field] = value;
};

window.setDirectorStep6Field = function (field, value) {
  if (!S.director?.step6?.form || !Object.prototype.hasOwnProperty.call(S.director.step6.form, field)) return;
  S.director.step6.form[field] = value;
};

window.setDirectorStep6Tab = function (tab) {
  if (!S.director?.step6) return;
  if (!Object.values(DIRECTOR_STEP6_REVIEW_TABS).includes(tab)) return;
  S.director.step6.activeTab = tab;
  render();
};

window.setDirectorStep7Field = function (field, value) {
  if (!S.director?.step7?.form || !Object.prototype.hasOwnProperty.call(S.director.step7.form, field)) return;
  S.director.step7.form[field] = value;
};

window.setDirectorStep8Field = function (field, value) {
  if (!S.director?.step8?.form || !Object.prototype.hasOwnProperty.call(S.director.step8.form, field)) return;
  S.director.step8.form[field] = value;
};

window.toggleDirectorExportItem = function (item, checked) {
  if (!S.director?.step8?.form) return;
  const cur = Array.isArray(S.director.step8.form.export_items) ? S.director.step8.form.export_items : [];
  const next = cur.filter((x) => x !== item);
  if (checked) next.push(item);
  S.director.step8.form.export_items = next;
};

function resetDirectorStep8Result() {
  if (!S.director?.step8) return;
  S.director.step8.error = '';
  S.director.step8.result = null;
}

window.toggleDirectorReviewDimension = function (dimension, checked) {
  if (!S.director?.step6?.form) return;
  const cur = Array.isArray(S.director.step6.form.review_dimensions) ? S.director.step6.form.review_dimensions : [];
  const next = cur.filter((item) => item !== dimension);
  if (checked) next.push(dimension);
  S.director.step6.form.review_dimensions = next;
};

window.setDirectorReviewTaskSelection = function (taskId, action) {
  if (!S.director?.step6) return;
  if (!S.director.step6.taskSelections || typeof S.director.step6.taskSelections !== 'object') {
    S.director.step6.taskSelections = {};
  }
  S.director.step6.taskSelections[String(taskId)] = String(action || '');
  if (S.director.step7) {
    S.director.step7.error = '';
    S.director.step7.result = null;

    resetDirectorStep8Result();
  }
};

window.selectDirectorLogline = function (index) {
  if (!S.director?.step1 || !Array.isArray(S.director.step1.result?.loglines)) return;
  if (!Number.isInteger(index) || index < 0 || index >= S.director.step1.result.loglines.length) return;
  S.director.step1.selected_logline_index = index;
  if (S.director.step2) {
    S.director.step2.result = null;
    S.director.step2.error = '';
  }
  if (S.director.step3) {
    S.director.step3.result = null;
    S.director.step3.error = '';
  }
  if (S.director.step4) {
    S.director.step4.result = null;
    S.director.step4.error = '';
  }
  if (S.director.step5) {
    S.director.step5.result = null;
    S.director.step5.error = '';
  }
  if (S.director.step6) {
    S.director.step6.result = null;
    S.director.step6.error = '';
    S.director.step6.taskSelections = {};
    if (S.director.step7) {
      S.director.step7.error = '';
      S.director.step7.result = null;

      resetDirectorStep8Result();
    }
  }
  render();
};

window.selectDirectorMode = function (index) {
  if (!S.director?.step1 || !Array.isArray(S.director.step1.result?.modes)) return;
  if (!Number.isInteger(index) || index < 0 || index >= S.director.step1.result.modes.length) return;
  S.director.step1.selected_mode_index = index;
  if (S.director.step2) {
    S.director.step2.result = null;
    S.director.step2.error = '';
  }
  if (S.director.step3) {
    S.director.step3.result = null;
    S.director.step3.error = '';
  }
  if (S.director.step4) {
    S.director.step4.result = null;
    S.director.step4.error = '';
  }
  if (S.director.step5) {
    S.director.step5.result = null;
    S.director.step5.error = '';
  }
  if (S.director.step6) {
    S.director.step6.result = null;
    S.director.step6.error = '';
    S.director.step6.taskSelections = {};
    if (S.director.step7) {
      S.director.step7.error = '';
      S.director.step7.result = null;

      resetDirectorStep8Result();
    }
  }
  render();
};

window.handleDirectorCreateProject = async function () {
  if (!S.director || S.director.creating) return;
  S.director.creating = true;
  S.director.error = '';
  render();
  try {
    const payload = {
      movie_name: S.director.form.movie_name || '',
      type: S.director.form.type || '',
      duration: S.director.form.duration || '',
      tone: S.director.form.tone || '',
      reference_ip: S.director.form.reference_ip || '',
    };
    const res = await apiFetch('/api/director/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    S.director.project = res?.project || null;
    if (S.director.project) {
      const projectTitle = String(S.director.project.movie_name || S.director.form.movie_name || '').trim() || '未命名剧本';
      if (!S.director.workspaceProjectMeta || typeof S.director.workspaceProjectMeta !== 'object') {
        S.director.workspaceProjectMeta = {
          id: `draft_new_${Date.now()}`,
          title: projectTitle,
          updatedAt: '刚刚',
          isNew: true,
        };
      } else {
        S.director.workspaceProjectMeta.title = projectTitle;
        S.director.workspaceProjectMeta.updatedAt = '刚刚';
      }
      S.director.step1.error = '';
      S.director.step1.result = null;
      S.director.step1.selected_logline_index = null;
      S.director.step1.selected_mode_index = null;
      S.director.step2.error = '';
      S.director.step2.result = null;
      S.director.step3.error = '';
      S.director.step3.result = null;
      S.director.step4.error = '';
      S.director.step4.result = null;
      S.director.step5.error = '';
      S.director.step5.result = null;
      S.director.step6.error = '';
      S.director.step6.result = null;
      S.director.step6.taskSelections = {};
      if (S.director.step7) {
        S.director.step7.error = '';
        S.director.step7.result = null;

        resetDirectorStep8Result();
      }
    }
  } catch (e) {
    S.director.error = e?.message || '创建项目失败';
  } finally {
    S.director.creating = false;
    render();
  }
};

window.handleDirectorGenerateSeed = async function () {
  if (!S.director?.step1 || S.director.step1.generating) return;
  if (!S.director?.project?.project_id) {
    S.director.step1.error = '请先在“项目初始化”创建项目';
    render();
    return;
  }
  S.director.step1.generating = true;
  S.director.step1.error = '';
  render();
  try {
    const payload = {
      seed: S.director.step1.form.seed || '',
      protagonist: S.director.step1.form.protagonist || '',
      antagonist: S.director.step1.form.antagonist || '',
      core_synopsis: S.director.step1.form.core_synopsis || '',
      key_setting: S.director.step1.form.key_setting || '',
    };
    const res = await apiFetch(`/api/director/projects/${encodeURIComponent(S.director.project.project_id)}/seed`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    S.director.step1.result = res?.seed_result || null;
    S.director.step1.selected_logline_index = null;
    S.director.step1.selected_mode_index = null;
    S.director.step2.error = '';
    S.director.step2.result = null;
    S.director.step3.error = '';
    S.director.step3.result = null;
    S.director.step4.error = '';
    S.director.step4.result = null;
    S.director.step5.error = '';
    S.director.step5.result = null;
    S.director.step6.error = '';
    S.director.step6.result = null;
    S.director.step6.taskSelections = {};
    if (S.director.step7) {
      S.director.step7.error = '';
      S.director.step7.result = null;

      resetDirectorStep8Result();
    }
  } catch (e) {
    S.director.step1.error = e?.message || '生成初始种子失败';
  } finally {
    S.director.step1.generating = false;
    render();
  }
};

window.handleDirectorGenerateBlueprint = async function () {
  if (!S.director?.step2 || S.director.step2.generating) return;
  if (!S.director?.project?.project_id) {
    S.director.step2.error = '请先在“项目初始化”创建项目';
    render();
    return;
  }
  if (!Number.isInteger(S.director.step1?.selected_logline_index) || !Number.isInteger(S.director.step1?.selected_mode_index)) {
    S.director.step2.error = '请先在“初始种子”中选定 Logline 和创作模式';
    render();
    return;
  }

  S.director.step2.generating = true;
  S.director.step2.error = '';
  render();
  try {
    const payload = {
      selected_logline_index: S.director.step1.selected_logline_index,
      selected_mode_index: S.director.step1.selected_mode_index,
      audience: S.director.step2.form.audience || '',
      narrative_focus: S.director.step2.form.narrative_focus || '',
      ending_tendency: S.director.step2.form.ending_tendency || '',
    };
    const res = await apiFetch(`/api/director/projects/${encodeURIComponent(S.director.project.project_id)}/blueprint`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    S.director.step2.result = res?.blueprint_result || null;
    S.director.step3.error = '';
    S.director.step3.result = null;
    S.director.step4.error = '';
    S.director.step4.result = null;
    S.director.step5.error = '';
    S.director.step5.result = null;
    S.director.step6.error = '';
    S.director.step6.result = null;
    S.director.step6.taskSelections = {};
    if (S.director.step7) {
      S.director.step7.error = '';
      S.director.step7.result = null;

      resetDirectorStep8Result();
    }
  } catch (e) {
    S.director.step2.error = e?.message || '生成结构蓝图失败';
  } finally {
    S.director.step2.generating = false;
    render();
  }
};

window.handleDirectorGenerateBeats = async function () {
  if (!S.director?.step3 || S.director.step3.generating) return;
  if (!S.director?.project?.project_id) {
    S.director.step3.error = '请先在“项目初始化”创建项目';
    render();
    return;
  }
  if (!Number.isInteger(S.director.step1?.selected_logline_index) || !Number.isInteger(S.director.step1?.selected_mode_index)) {
    S.director.step3.error = '请先在“初始种子”中选定 Logline 和创作模式';
    render();
    return;
  }
  if (!S.director.step2?.result) {
    S.director.step3.error = '请先生成“结构蓝图”';
    render();
    return;
  }

  S.director.step3.generating = true;
  S.director.step3.error = '';
  render();
  try {
    const payload = {
      selected_logline_index: S.director.step1.selected_logline_index,
      selected_mode_index: S.director.step1.selected_mode_index,
      segment_granularity: S.director.step3.form.segment_granularity || '',
      action_ratio: S.director.step3.form.action_ratio || '',
      character_ratio: S.director.step3.form.character_ratio || '',
    };
    const res = await apiFetch(`/api/director/projects/${encodeURIComponent(S.director.project.project_id)}/beats`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    S.director.step3.result = res?.beats_result || null;
    S.director.step4.error = '';
    S.director.step4.result = null;
    S.director.step5.error = '';
    S.director.step5.result = null;
    S.director.step6.error = '';
    S.director.step6.result = null;
    S.director.step6.taskSelections = {};
    if (S.director.step7) {
      S.director.step7.error = '';
      S.director.step7.result = null;

      resetDirectorStep8Result();
    }
  } catch (e) {
    S.director.step3.error = e?.message || '生成段落节拍失败';
  } finally {
    S.director.step3.generating = false;
    render();
  }
};

window.handleDirectorGenerateScenes = async function () {
  if (!S.director?.step4 || S.director.step4.generating) return;
  if (!S.director?.project?.project_id) {
    S.director.step4.error = '请先在“项目初始化”创建项目';
    render();
    return;
  }
  if (!Number.isInteger(S.director.step1?.selected_logline_index) || !Number.isInteger(S.director.step1?.selected_mode_index)) {
    S.director.step4.error = '请先在“初始种子”中选定 Logline 和创作模式';
    render();
    return;
  }
  if (!S.director.step3?.result) {
    S.director.step4.error = '请先生成“段落节拍”';
    render();
    return;
  }

  S.director.step4.generating = true;
  S.director.step4.error = '';
  render();
  try {
    const payload = {
      selected_logline_index: S.director.step1.selected_logline_index,
      selected_mode_index: S.director.step1.selected_mode_index,
      target_scene_count: S.director.step4.form.target_scene_count || '',
      scene_constraints: S.director.step4.form.scene_constraints || '',
      language_style: S.director.step4.form.language_style || '',
    };
    const res = await apiFetch(`/api/director/projects/${encodeURIComponent(S.director.project.project_id)}/scenes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    S.director.step4.result = res?.scenes_result || null;
    S.director.step5.error = '';
    S.director.step5.result = null;
    S.director.step6.error = '';
    S.director.step6.result = null;
    S.director.step6.taskSelections = {};
    if (S.director.step7) {
      S.director.step7.error = '';
      S.director.step7.result = null;

      resetDirectorStep8Result();
    }
  } catch (e) {
    S.director.step4.error = e?.message || '生成分场表失败';
  } finally {
    S.director.step4.generating = false;
    render();
  }
};

window.handleDirectorGenerateDraft = async function () {
  if (!S.director?.step5 || S.director.step5.generating) return;
  if (!S.director?.project?.project_id) {
    S.director.step5.error = '请先在“项目初始化”创建项目';
    render();
    return;
  }
  if (!Number.isInteger(S.director.step1?.selected_logline_index) || !Number.isInteger(S.director.step1?.selected_mode_index)) {
    S.director.step5.error = '请先在“初始种子”中选定 Logline 和创作模式';
    render();
    return;
  }
  if (!S.director.step4?.result) {
    S.director.step5.error = '请先生成“分场表”';
    render();
    return;
  }

  S.director.step5.generating = true;
  S.director.step5.error = '';
  if (S.director.step6) {
    S.director.step6.error = '';
    S.director.step6.result = null;
    S.director.step6.taskSelections = {};
    if (S.director.step7) {
      S.director.step7.error = '';
      S.director.step7.result = null;

      resetDirectorStep8Result();
    }
  }
  render();
  try {
    const payload = {
      selected_logline_index: S.director.step1.selected_logline_index,
      selected_mode_index: S.director.step1.selected_mode_index,
      writing_tendency: S.director.step5.form.writing_tendency || '',
      dialogue_density: S.director.step5.form.dialogue_density || '',
      rating_intensity: S.director.step5.form.rating_intensity || '',
    };
    const res = await apiFetch(`/api/director/projects/${encodeURIComponent(S.director.project.project_id)}/draft`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    S.director.step5.result = res?.draft_result || null;
  } catch (e) {
    S.director.step5.error = e?.message || '生成一稿失败';
  } finally {
    S.director.step5.generating = false;
    render();
  }
};

window.handleDirectorStartReview = async function () {
  if (!S.director?.step6 || S.director.step6.generating) return;
  if (!S.director?.project?.project_id) {
    S.director.step6.error = '请先在“项目初始化”创建项目';
    render();
    return;
  }
  if (!Number.isInteger(S.director.step1?.selected_logline_index) || !Number.isInteger(S.director.step1?.selected_mode_index)) {
    S.director.step6.error = '请先在“初始种子”中选定 Logline 和创作模式';
    render();
    return;
  }
  if (!S.director.step5?.result) {
    S.director.step6.error = '请先生成“剧本一稿”';
    render();
    return;
  }

  S.director.step6.generating = true;
  S.director.step6.error = '';
  if (S.director.step7) {
    S.director.step7.error = '';
    S.director.step7.result = null;

    resetDirectorStep8Result();
  }
  render();
  try {
    const payload = {
      selected_logline_index: S.director.step1.selected_logline_index,
      selected_mode_index: S.director.step1.selected_mode_index,
      review_dimensions: Array.isArray(S.director.step6.form.review_dimensions)
        ? S.director.step6.form.review_dimensions
        : [],
      rewrite_preference: S.director.step6.form.rewrite_preference || '',
    };
    const res = await apiFetch(`/api/director/projects/${encodeURIComponent(S.director.project.project_id)}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    S.director.step6.result = res?.review_result || null;
    const taskSheet = Array.isArray(S.director.step6.result?.task_sheet) ? S.director.step6.result.task_sheet : [];
    S.director.step6.taskSelections = Object.fromEntries(
      taskSheet
        .filter((task) => task && typeof task.task_id === 'string')
        .map((task) => [task.task_id, String(task.default_action || 'accept')]),
    );
    if (S.director.step7) {
      S.director.step7.error = '';
      S.director.step7.result = null;

      resetDirectorStep8Result();
    }
  } catch (e) {
    S.director.step6.error = e?.message || '评审失败';
  } finally {
    S.director.step6.generating = false;
    render();
  }
};

window.handleDirectorGenerateRewrite = async function () {
  if (!S.director?.step7 || S.director.step7.generating) return;
  if (!S.director?.project?.project_id) {
    S.director.step7.error = '请先在“项目初始化”创建项目';
    render();
    return;
  }
  if (!Number.isInteger(S.director.step1?.selected_logline_index) || !Number.isInteger(S.director.step1?.selected_mode_index)) {
    S.director.step7.error = '请先在“初始种子”中选定 Logline 和创作模式';
    render();
    return;
  }
  if (!S.director.step6?.result) {
    S.director.step7.error = '请先完成“评审质检”并生成评审结果';
    render();
    return;
  }

  const taskSheet = Array.isArray(S.director.step6.result?.task_sheet) ? S.director.step6.result.task_sheet : [];
  const taskSelections = S.director.step6.taskSelections || {};
  const acceptedTasks = taskSheet
    .map((task) => ({
      task_id: task?.task_id,
      action: String(taskSelections[task?.task_id] || task?.default_action || ''),
    }))
    .filter((task) => typeof task.task_id === 'string' && ['accept', 'alternative'].includes(task.action));

  S.director.step7.generating = true;
  S.director.step7.error = '';
  resetDirectorStep8Result();
  render();
  try {
    const payload = {
      selected_logline_index: S.director.step1.selected_logline_index,
      selected_mode_index: S.director.step1.selected_mode_index,
      accepted_tasks: acceptedTasks,
      rewrite_scope: S.director.step7.form.rewrite_scope || '',
      strengthen_metrics: S.director.step7.form.strengthen_metrics || '',
    };
    const res = await apiFetch(`/api/director/projects/${encodeURIComponent(S.director.project.project_id)}/rewrite`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    S.director.step7.result = res?.rewrite_result || null;
  } catch (e) {
    S.director.step7.error = e?.message || '生成新版本失败';
  } finally {
    S.director.step7.generating = false;
    render();
  }
};

window.handleDirectorGenerateDeliverables = async function () {
  if (!S.director?.step8 || S.director.step8.generating) return;
  if (!S.director?.project?.project_id) {
    S.director.step8.error = '请先在“项目初始化”创建项目';
    render();
    return;
  }
  if (!S.director.step7?.result) {
    S.director.step8.error = '请先完成“迭代改稿”并生成新版本';
    render();
    return;
  }

  S.director.step8.generating = true;
  S.director.step8.error = '';
  render();
  try {
    const payload = {
      selected_version: S.director.step8.form.selected_version || '',
      asset_filter: S.director.step8.form.asset_filter || '',
      export_format: S.director.step8.form.export_format || '',
      export_items: Array.isArray(S.director.step8.form.export_items) ? S.director.step8.form.export_items : [],
    };
    const res = await apiFetch(`/api/director/projects/${encodeURIComponent(S.director.project.project_id)}/deliverables`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    S.director.step8.result = res?.deliverables_result || null;
  } catch (e) {
    S.director.step8.error = e?.message || '生成导出包预览失败';
  } finally {
    S.director.step8.generating = false;
    render();
  }
};

// ============ Render ============
function render() {
  const c = document.getElementById('pageContainer');
  let h = '';
  switch (S.view) {
    case 'agent': h = renderAgent(); break;
    case 'settings': h = renderSettings(); break;
    default: h = renderAgent(); break;
  }
  hideStudioHoverPreview();
  c.innerHTML = `<div class="page-view">${h}</div>${renderAssetDetailDialog()}${renderImagePreviewDialog()}`;
  bindEvents();
  scheduleSaveWorkbenchUiState();
}

function getTopUpload() {
  return S.uploadQueue[0] || null;
}

function canPreviewUpload(item) {
  return Boolean(item?.previewUrl);
}

function getStudioHoverPreviewEl() {
  let el = document.getElementById('studioHoverPreview');
  if (!el) {
    el = document.createElement('div');
    el.id = 'studioHoverPreview';
    el.className = 'studio-hover-preview';
    el.style.display = 'none';
    document.body.appendChild(el);
  }
  return el;
}

function hideStudioHoverPreview() {
  const el = document.getElementById('studioHoverPreview');
  if (!el) return;
  el.style.display = 'none';
  el.innerHTML = '';
}

function showStudioHoverPreview(panelId, anchorRect) {
  if (S.agentTab !== 'studio' || !S.studioResult || !panelId || !anchorRect) return;
  const panel = (S.studioResult.panels || []).find(p => p.panel_id === panelId);
  if (!panel?.bbox_path) return;
  const popW = 360;
  const popH = 420;
  const margin = 16;
  const vw = window.innerWidth || 1280;
  const vh = window.innerHeight || 800;
  const left = Math.min(anchorRect.right + 16, vw - popW - margin);
  const top = Math.max(margin, Math.min(anchorRect.top + anchorRect.height / 2 - popH / 2, vh - popH - margin));
  const el = getStudioHoverPreviewEl();
  el.style.left = `${Math.round(left)}px`;
  el.style.top = `${Math.round(top)}px`;
  el.style.display = 'block';
  el.innerHTML = `
    <div class="studio-hover-preview-header">
      <span class="section-label" style="margin-bottom:0">分镜预览</span>
      <span class="tag">${escHtml(panel.panel_id)}</span>
    </div>
    <div class="studio-hover-preview-body">
      <img src="${fileUrl(panel.bbox_path)}" class="studio-hover-preview-img" alt="${escHtml(panel.panel_id)}" />
    </div>`;
}

// ======================================================================
//  AGENT PAGE (unified container with left sidebar)
// ======================================================================
function renderAgent() {
  if (S.agentModule === 'director') {
    return renderDirectorAgentView(S.director);
  }

  const tabs = [
    {
      id: 'split',
      label: '分镜拆分',
      icon: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" width="18" height="18"><path d="M4 6c0 1.1.9 2 2 2s2-.9 2-2-.9-2-2-2-2 .9-2 2zm0 8c0 1.1.9 2 2 2s2-.9 2-2-.9-2-2-2-2 .9-2 2z"/><path d="M8 7l8-4"/><path d="M8 13l8 4"/><path d="M14 10h2"/></svg>`,
    },
    {
      id: 'tasks',
      label: '任务管理',
      icon: `<svg viewBox="0 0 20 20" fill="currentColor" width="18" height="18"><polygon points="5,2 17,10 5,18"/></svg>`,
    },
    {
      id: 'studio',
      label: '脚本撰写',
      icon: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18"><rect x="2" y="3" width="16" height="10" rx="1.5"/><path d="M6 16h8"/><path d="M10 13v3"/></svg>`,
    },
    {
      id: 'assets',
      label: '分镜资产',
      icon: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18"><rect x="3" y="2" width="14" height="16" rx="2"/><line x1="7" y1="6" x2="13" y2="6"/><line x1="7" y1="10" x2="13" y2="10"/><line x1="7" y1="14" x2="10" y2="14"/></svg>`,
    },
  ];

  let content = '';
  if (S.agentTab === 'split') content = renderSplitter();
  else if (S.agentTab === 'tasks') content = renderTaskManager();
  else if (S.agentTab === 'studio') content = renderStudio();
  else if (S.agentTab === 'assets') content = renderAssets();

  return `
  <div class="agent-layout">
    <!-- Left sidebar: vertical sub-tabs -->
    <aside class="agent-sidebar">
      <div class="agent-sidebar-logo">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="22" height="22">
          <rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>
          <rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>
        </svg>
        <span>${STORYBOARD_AGENT_TITLE}</span>
      </div>
      <nav class="agent-nav">
        ${tabs.map(t => `
        <button class="agent-nav-item ${S.agentTab === t.id ? 'active' : ''}" onclick="setAgentTab('${t.id}')">
          <span class="agent-nav-icon">${t.icon}</span>
          <span class="agent-nav-label">${t.label}</span>
        </button>`).join('')}
      </nav>
    </aside>
    <!-- Content area -->
    <div class="agent-content">
      ${content}
    </div>
  </div>`;
}


//  SPLITTER + TASK MANAGER
// ======================================================================
function renderSplitter() {
  const topUpload = getTopUpload();
  const topCanPreview = canPreviewUpload(topUpload);
  return `
  <div class="split-layout">
    <div class="card split-upload-card">
      <div class="card-header">
        <h3 class="card-title">上传 PSD 文件</h3>
        <div class="split-upload-meta">
          <span class="tag">${S.uploadQueue.length ? `${S.uploadQueue.length} 个已上传` : '支持多选 .psd / .psb'}</span>
        </div>
      </div>
      <div class="split-upload-body">
        <div class="upload-zone split-upload-zone" id="uploadZone">
          <div class="upload-zone-icon">${I.upload}</div>
          <div class="upload-zone-text">拖拽 PSD 到此处，或点击选择（可多选）</div>
          <div class="upload-zone-hint">上传后按顺序排队，最顶部文件用于预览与拆分</div>
        </div>

        <div class="split-upload-toolbar">
          <div class="strategy-pills">
            <button class="pill ${S.selectedStrategy === 'normal' ? 'active' : ''}" data-strat="normal">普通模式</button>
            <button class="pill ${S.selectedStrategy === 'advanced' ? 'active' : ''}" data-strat="advanced">高级模式</button>
          </div>
          <div class="split-upload-toolbar-right">
            <div class="split-upload-current">
              ${topUpload
      ? `当前拆分对象：<strong>${escHtml(topUpload.name)}</strong>`
      : '请先上传一个 PSD 文件'}
            </div>
            <button class="btn btn-primary" onclick="handleSplitPanels()" ${topUpload ? '' : 'disabled'}>
              ${I.play} 拆分分镜
            </button>
          </div>
        </div>
      </div>
      <input type="file" id="fileInput" accept=".psd,.psb" multiple style="display:none" />

      <div class="split-upload-files">
        ${S.uploadQueue.length
      ? S.uploadQueue.map((item, idx) => renderUploadQueueItem(item, idx)).join('')
      : `<div class="empty-sm split-upload-empty">${I.empty}<span>暂无已上传文件</span></div>`
    }
      </div>
    </div>

    <div class="split-preview-row">
      <div class="card split-preview-card">
        <div class="card-header">
          <h3 class="card-title">预览</h3>
          ${topUpload ? `<span class="tag">${escHtml(topUpload.name)}</span>` : ''}
        </div>
        <div class="preview-area split-preview-area">
          ${topUpload
      ? (topCanPreview
        ? `<button type="button" class="split-preview-clickzone" onclick="openUploadPreview()" title="点击查看完整画面">
                <img src="${topUpload.previewUrl}" class="split-preview-crop-img" alt="${escHtml(topUpload.name)}" />
                <span class="split-preview-cta">点击预览完整画面</span>
              </button>`
        : `<div class="preview-placeholder">PSD 文件已上传<br><small>${escHtml(topUpload.name)}</small></div>`)
      : '<div class="preview-placeholder">请先上传 PSD 文件</div>'
    }
        </div>
        <div class="card-footer split-preview-footer">
          <span class="split-preview-note">
            ${topUpload ? '此处展示顶部文件的局部画面，点击可查看完整画面' : '上传后将在这里显示顶部文件预览'}
          </span>
          ${topCanPreview ? `<button class="btn-sm" onclick="openUploadPreview()">完整预览</button>` : ''}
        </div>
      </div>
    </div>
  </div>`;
}

function renderUploadQueueItem(item, idx) {
  const top = idx === 0;
  return `
  <div class="upload-queue-item ${top ? 'is-top' : ''}">
    <div class="upload-queue-main">
      <span class="upload-queue-index">${idx + 1}</span>
      <div class="upload-queue-meta">
        <div class="upload-queue-name">${escHtml(item.name)}</div>
        <div class="upload-queue-sub">${top ? '顶部文件（预览 / 拆分对象）' : '等待处理'}</div>
      </div>
    </div>
    <div class="upload-queue-actions">
      ${canPreviewUpload(item) ? `<button class="btn-sm" onclick="openUploadPreview('${item.id}')">预览</button>` : ''}
      <button class="btn-sm" onclick="removeUploadFile('${item.id}')">删除</button>
    </div>
  </div>`;
}

function renderTaskManager() {
  const filtered = getFilteredRuns();
  const counts = {
    all: S.runs.length, success: S.runs.filter(r => r.status === 'success').length,
    running: S.runs.filter(r => r.status === 'running').length, error: S.runs.filter(r => r.status === 'error').length
  };
  return `
  <div class="wb-list-page">
    ${renderTaskListCard(filtered, counts)}
  </div>`;
}

function renderTaskListCard(filtered, counts) {
  return `
  <div class="card task-manager-card">
    <div class="card-header">
      <h3 class="card-title">任务列表</h3>
      <div class="filter-tabs">
        ${['all', 'success', 'running', 'error'].map(f => `
          <button class="filter-tab ${S.statusFilter === f ? 'active' : ''}" data-filter="${f}">
            ${{ all: '全部', success: '完成', running: '运行中', error: '失败' }[f]}
            <span class="count-badge">${counts[f]}</span>
          </button>
        `).join('')}
      </div>
    </div>
    <div class="search-bar-sm">
      ${I.search}
      <input class="search-input" type="text" placeholder="搜索..." value="${S.searchQ}" data-action="searchRuns" />
    </div>
    <div class="task-list task-list-scroll">
      ${filtered.length === 0
      ? `<div class="empty-sm">${I.empty}<span>暂无任务</span></div>`
      : filtered.map(r => renderTaskCard(r)).join('')
    }
    </div>
  </div>`;
}

function renderImagePreviewDialog() {
  if (!S.imagePreviewDialog) return '';
  return `
  <div class="image-preview-dialog" role="dialog" aria-modal="true">
    <div class="image-preview-backdrop" onclick="closeImagePreview()"></div>
    <div class="image-preview-panel">
      <div class="card-header image-preview-header">
        <h3 class="card-title">完整预览</h3>
        <div class="image-preview-header-right">
          ${S.imagePreviewDialog.name ? `<span class="tag">${escHtml(S.imagePreviewDialog.name)}</span>` : ''}
          <button class="btn-sm" onclick="closeImagePreview()">关闭</button>
        </div>
      </div>
      <div class="image-preview-body">
        <div class="preview-canvas">
          <img src="${S.imagePreviewDialog.url}" class="preview-main-img" alt="${escHtml(S.imagePreviewDialog.name || '预览图')}" />
        </div>
      </div>
    </div>
  </div>`;
}

function renderStudioHoverPreview() {
  if (S.agentTab !== 'studio' || !S.studioResult || !S.hoverStudioPanel?.panelId) return '';
  const panel = (S.studioResult.panels || []).find(p => p.panel_id === S.hoverStudioPanel.panelId);
  if (!panel?.bbox_path) return '';
  const popW = 360;
  const popH = 420;
  const margin = 16;
  const vw = window.innerWidth || 1280;
  const vh = window.innerHeight || 800;
  const left = Math.min(S.hoverStudioPanel.x, vw - popW - margin);
  const top = Math.max(margin, Math.min(S.hoverStudioPanel.y - popH / 2, vh - popH - margin));
  return `
  <div class="studio-hover-preview" style="left:${Math.round(left)}px;top:${Math.round(top)}px">
    <div class="studio-hover-preview-header">
      <span class="section-label" style="margin-bottom:0">分镜预览</span>
      <span class="tag">${escHtml(panel.panel_id)}</span>
    </div>
    <div class="studio-hover-preview-body">
      <img src="${fileUrl(panel.bbox_path)}" class="studio-hover-preview-img" alt="${escHtml(panel.panel_id)}" />
    </div>
  </div>`;
}

function renderTaskCard(run) {
  const sMap = {
    success: { l: '完成', c: 'success' },
    running: { l: '运行中', c: 'running' },
    error: { l: '失败', c: 'error' }
  };
  const s = sMap[run.status] || { l: run.status, c: '' };
  return `
  <div class="task-card ${run.status}" data-run-id="${run.id}">
    <div class="task-card-top">
      <span class="task-id">${run.id}</span>
      <span class="status-badge ${s.c}"><span class="dot"></span>${s.l}</span>
    </div>
    <div class="task-card-mid">
      <span class="task-file">${run.file || ''}</span>
      <span class="task-strategy">${run.strategy === 'advanced' ? '高级' : '普通'}</span>
    </div>
    <div class="task-card-bot">
      ${run.panels != null ? `<span><strong>${run.panels}</strong> 分镜</span><span><strong>${run.texts || 0}</strong> 文字</span>` : '<span style="color:var(--color-text-muted)">处理中...</span>'}
      <span class="task-time">${run.time || ''}</span>
    </div>
    <div class="task-card-actions">
      ${run.status === 'success' ? `<button class="btn-sm btn-brand" onclick="event.stopPropagation(); openStudio('${run.id}')">打开工作室 →</button>` : ''}
      ${run.status === 'success' ? `<button class="btn-sm btn-danger" onclick="event.stopPropagation(); handleDeleteRun('${run.id}')">删除</button>` : ''}
      ${run.status === 'error' ? `<button class="btn-sm" onclick="event.stopPropagation(); handleRetry('${run.id}')">重试</button>` : ''}
      ${run.status === 'error' ? `<button class="btn-sm btn-danger" onclick="event.stopPropagation(); handleDeleteRun('${run.id}')">删除</button>` : ''}
      ${run.status === 'running' ? `<button class="btn-sm btn-danger" onclick="event.stopPropagation(); handleStopRun('${run.id}')">停止</button>` : ''}
      ${run.status === 'running' ? `<span class="spin-icon-inline">${I.loading}</span>` : ''}
    </div>
  </div>`;
}

function getFilteredRuns() {
  let r = S.runs;
  if (S.statusFilter !== 'all') r = r.filter(x => x.status === S.statusFilter);
  if (S.searchQ.trim()) { const q = S.searchQ.toLowerCase(); r = r.filter(x => (x.id || '').toLowerCase().includes(q) || (x.file || '').toLowerCase().includes(q)); }
  return r;
}

// ======================================================================
//  SCRIPT STUDIO
// ======================================================================
function renderStudio() {
  if (!S.studioResult) {
    return `
    <div class="studio-empty">
      <div class="empty-state">
        <div class="empty-state-icon">${I.empty}</div>
        <div class="empty-state-text">请先在任务管理完成一个任务，然后点击"打开工作室"</div>
        <button class="btn btn-primary" onclick="setAgentTab('tasks')">前往任务管理</button>
      </div>
    </div>`;
  }
  const { panels = [], texts = [], cleanImage, run } = S.studioResult;
  const visibleTexts = getVisibleStudioTexts(texts);
  const hasCurrentBinding = !!getCurrentPanelBinding();
  const inBoundView = S.studioTextPoolMode === 'bound';

  return `
  <div class="studio-header">
    <div class="studio-header-left">
      <h2 class="studio-title">${run?.id || S.studioRunId}</h2>
      <span class="tag">${run?.file || ''}</span>
      <span class="tag">${panels.length} 分镜 · ${texts.length} 文字</span>
    </div>
  </div>
  <div class="studio-layout">
    <!-- COL 1: Panel List -->
    <div class="studio-panels">
      <div class="section-label">分镜列表</div>
      <div class="panel-thumbs">
        ${panels.map((p, i) => `
          <div class="panel-thumb ${p.panel_id === S.selectedPanel ? 'active' : ''}" data-panel="${p.panel_id}">
            <img src="${fileUrl(p.bbox_path)}" alt="${p.panel_id}" />
            <span class="panel-thumb-label">${i + 1}</span>
          </div>
        `).join('')}
      </div>
    </div>

    <!-- COL 2: Binding + Script Generation (side-by-side) -->
    <div class="studio-main">
      <div class="studio-binding">
        <div class="section-label">文字绑定${S.selectedPanel ? ` — ${S.selectedPanel}` : ''} <span class="count-badge">${S.selectedTexts.size} 已选</span></div>
        <div class="studio-binding-help">${inBoundView
          ? '当前仅显示该分镜已绑定文字；将鼠标移到“文字已绑定”按钮上可取消绑定。'
          : hasCurrentBinding
            ? '当前显示完整文字池；可点击“查看已绑定”切换到该分镜的已绑定文字视图。'
            : '当前显示完整文字池；勾选后可绑定到该分镜。'}</div>
        <div class="text-pool">
          ${visibleTexts.length ? visibleTexts.map(t => renderTextItem(t)).join('') : '<div class="empty-sm" style="padding:12px">暂无文字</div>'}
        </div>
        <div class="studio-binding-actions">
          <button
            class="btn btn-secondary bind-toggle-btn ${hasCurrentBinding && inBoundView ? 'is-bound' : ''}"
            onclick="${hasCurrentBinding ? (inBoundView ? 'handleUnbindTexts()' : 'handleShowBoundTexts()') : 'handleBindTexts()'}"
            ${S.bindingSaving ? 'disabled' : ''}>
            ${S.bindingSaving
              ? `${I.loading} 处理中...`
              : hasCurrentBinding && inBoundView
                ? `<span class="bind-toggle-default">${I.check} 文字已绑定</span><span class="bind-toggle-hover">取消绑定</span>`
                : hasCurrentBinding
                  ? `${I.check} 查看已绑定`
                  : `${I.check} 绑定文字`}
          </button>
        </div>
      </div>

      <div class="studio-script-pane">
        <div class="section-label">生成脚本${S.selectedPanel ? ` — ${S.selectedPanel}` : ''}</div>
        <textarea class="prompt-input" id="promptInput" placeholder="请描述你想要的脚本风格、要求...">${S.scriptPrompt}</textarea>

        <button class="btn btn-primary btn-block" onclick="handleGenScript()" ${S.scriptLoading ? 'disabled' : ''}>
          ${S.scriptLoading ? I.loading + ' 生成中...' : I.sparkle + ' 生成脚本'}
        </button>

        <div class="studio-script-pane-result">
          ${S.scriptLoading ? `
          <div class="script-output-v2">
            <div class="script-output-header"><span class="section-label">生成中...</span></div>
            <div class="script-plain-body"><p>正在调用 AI 模型，请稍候...</p></div>
          </div>` : ''}
          ${!S.scriptLoading && S.panelScripts[S.selectedPanel] ? renderScriptOutput() : ''}
          ${!S.scriptLoading && !S.panelScripts[S.selectedPanel] ? `
          <div class="script-output-v2">
            <div class="script-output-header"><span class="section-label">生成结果</span></div>
            <div class="script-plain-body"><p>选择分镜并绑定文字后，点击“生成脚本”。</p></div>
          </div>` : ''}
        </div>
      </div>
    </div>

    <!-- COL 3: Original Image -->
    <div class="studio-original">
      <div class="section-label">原图预览</div>
      <div class="preview-canvas">
        ${run?.imagePath
      ? `<img src="${fileUrl(run.imagePath)}" class="preview-main-img" />`
      : '<div class="empty-sm">无原图</div>'}
      </div>
    </div>

  </div>
  `;
}

function renderTextItem(t) {
  const checked = S.selectedTexts.has(t.text_id);
  const isPrimary = t.primary_panel_id === S.selectedPanel;
  return `<label class="text-item ${checked ? 'checked' : ''} ${isPrimary ? 'primary' : ''}">
    <input type="checkbox" ${checked ? 'checked' : ''} data-text-id="${t.text_id}" />
    <span class="text-id-badge">${t.text_id}</span>
    <span class="text-content">${escHtml(t.text)}</span>
  </label>`;
}

function renderMarkdown(text) {
  // Simple markdown-to-HTML: bold, bullet lists, line breaks
  if (!text) return '';
  return escHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>\n?)+/g, (m) => `<ul>${m}</ul>`)
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>');
}

function renderScriptOutput() {
  const s = S.panelScripts[S.selectedPanel];
  if (!s) return '';

  const meta = s.meta || {};
  const metaHtml = meta.backend
    ? `<div class="script-meta" > 后端: ${escHtml(meta.backend)}${meta.fallback_reason ? ` · 原因: ${escHtml(meta.fallback_reason)}` : ''}${meta.model_endpoint ? ` · 模型: ${escHtml(meta.model_endpoint)}` : ''}</div> `
    : '';

  // Plain text schema: {script_text, meta}
  const scriptText = s.script_text;
  if (scriptText !== undefined) {
    return `
  <div class="script-output-v2">
    <div class="script-output-header">
      <span class="section-label">生成结果</span>
      <button class="btn-sm" onclick="handleCopyScript()">${I.copy} 复制</button>
    </div>
      ${metaHtml}
<div class="script-plain-body"><p>${renderMarkdown(scriptText)}</p></div>
    </div>`;
  }

  // Fallback: render as raw text if unknown format
  const content = typeof s === 'string' ? s : JSON.stringify(s, null, 2);
  return `
  <div class="script-output-v2">
    <div class="script-output-header">
      <span class="section-label">生成结果</span>
      <button class="btn-sm" onclick="handleCopyScript()">${I.copy} 复制</button>
    </div>
      ${metaHtml}
<pre class="script-content">${escHtml(content)}</pre>
    </div>`;
}

// ======================================================================
//  ASSETS
// ======================================================================
function renderAssets() {
  let assets = S.assets;
  if (S.assetSearch.trim()) { const q = S.assetSearch.toLowerCase(); assets = assets.filter(a => (a.file || '').toLowerCase().includes(q)); }
  return `
  <div class="page-header">
    <div><h1 class="page-title">资产管理</h1><p class="page-subtitle">按 PSD 查看链路产物</p></div>
    <button class="btn btn-primary" onclick="handleExport()">${I.download} 导出 Excel</button>
  </div>
  <div class="search-bar-sm" style="margin-bottom:16px">${I.search}
    <input class="search-input" type="text" placeholder="搜索 PSD..." value="${S.assetSearch}" data-action="searchAssets" />
  </div>
  ${assets.length === 0
    ? `<div class="empty-state"><div class="empty-state-icon">${I.empty}</div><div class="empty-state-text">暂无资产数据</div></div>`
    : `<div class="asset-card-grid">${assets.map(a => renderAssetCard(a)).join('')}</div>`} `;
}

function renderAssetCard(a) {
  const detail = S.assetDetails[a.file];
  const previewPanels = (detail?.panels || []).slice(0, 6);
  const loading = !!S.assetDetailLoading[a.file];
  return `
  <div class="asset-card">
    <div class="asset-card-header">
      <div>
        <div class="asset-card-title">${escHtml(a.file || '')}</div>
        <div class="asset-card-sub">${a.updated || ''}</div>
      </div>
      <span class="tag">${a.panels || 0} 分镜</span>
    </div>
    <div class="asset-card-preview" onclick="openAssetDetail('${escAttr(a.file)}')">
      ${a.imagePath ? `<img src="${fileUrl(a.imagePath)}" alt="${escHtml(a.file || '')}" class="asset-card-preview-img" />` : `<div class="preview-placeholder">无 PSD 预览</div>`}
      <div class="asset-card-preview-overlay">点击查看资产详情</div>
    </div>
    <div class="asset-card-meta">
      <span>覆盖率 ${a.coverage || 0}%</span>
      <span>${(a.runs || []).length} 次运行</span>
    </div>
    <div class="asset-panel-grid">
      ${previewPanels.length
        ? previewPanels.map(p => `
          <button class="asset-panel-mini-card" onclick="openAssetDetail('${escAttr(a.file)}','${escAttr(p.panelId)}')">
            <img src="${fileUrl(p.imagePath)}" alt="${escHtml(p.panelId)}" />
            <span class="asset-panel-mini-label">${escHtml(p.panelId)}</span>
          </button>`).join('')
        : `<button class="asset-panel-mini-card asset-panel-mini-empty" onclick="openAssetDetail('${escAttr(a.file)}')">${loading ? '加载中...' : '查看分镜资产'}</button>`}
    </div>
    <div class="asset-card-actions">
      <button class="btn-sm btn-brand" onclick="openAssetDetail('${escAttr(a.file)}')">查看资产详情</button>
    </div>
  </div>`;
}

function renderAssetDetailDialog() {
  const active = S.activeAssetDetail;
  if (!active?.file) return '';
  const detail = S.assetDetails[active.file];
  if (!detail) {
    return `
    <div class="asset-detail-dialog">
      <div class="image-preview-backdrop" onclick="closeAssetDetail()"></div>
      <div class="asset-detail-panel">
        <div class="card-header">
          <h3 class="card-title">资产详情</h3>
          <button class="btn-sm" onclick="closeAssetDetail()">关闭</button>
        </div>
        <div class="asset-detail-loading">加载中...</div>
      </div>
    </div>`;
  }
  const panels = detail.panels || [];
  const selectedPanel = panels.find(p => p.panelId === active.selectedPanelId) || panels[0] || null;
  const scriptText = selectedPanel?.script?.script_text || selectedPanel?.script?.script_markdown || selectedPanel?.script?.raw || '';
  return `
  <div class="asset-detail-dialog">
    <div class="image-preview-backdrop" onclick="closeAssetDetail()"></div>
    <div class="asset-detail-panel">
      <div class="card-header asset-detail-header">
        <div class="asset-detail-title-wrap">
          <h3 class="card-title">资产详情</h3>
          <span class="tag">${escHtml(detail.file)}</span>
          ${detail.runId ? `<span class="tag">${escHtml(detail.runId)}</span>` : ''}
        </div>
        <button class="btn-sm" onclick="closeAssetDetail()">关闭</button>
      </div>
      <div class="asset-detail-layout">
        <section class="asset-detail-col">
          <div class="section-label">PSD 图片（单文件）</div>
          <div class="asset-detail-box asset-detail-psd-box">
            ${detail.psdImagePath ? `<img src="${fileUrl(detail.psdImagePath)}" class="asset-detail-psd-img" alt="${escHtml(detail.file)}" />` : '<div class="empty-sm">无预览</div>'}
          </div>
        </section>
        <section class="asset-detail-col">
          <div class="section-label">分镜（多文件）</div>
          <div class="asset-detail-box asset-detail-panel-list">
            ${panels.map(p => `
              <button class="asset-detail-panel-card ${selectedPanel?.panelId === p.panelId ? 'active' : ''}" data-asset-file="${escAttr(detail.file)}" data-asset-panel="${escAttr(p.panelId)}">
                <img src="${fileUrl(p.imagePath)}" alt="${escHtml(p.panelId)}" />
                <span class="asset-detail-panel-card-label">${escHtml(p.panelId)}</span>
              </button>`).join('')}
          </div>
        </section>
        <section class="asset-detail-col">
          <div class="section-label">分镜文字（与分镜对应）${selectedPanel ? ` — ${escHtml(selectedPanel.panelId)}` : ''}</div>
          <div class="asset-detail-box asset-detail-text-list">
            ${selectedPanel?.texts?.length
              ? selectedPanel.texts.map(t => `<div class="asset-detail-text-item"><span class="text-id-badge">${escHtml(t.text_id || '')}</span><span>${escHtml(t.text || '')}</span></div>`).join('')
              : '<div class="empty-sm">暂无文字</div>'}
          </div>
        </section>
        <section class="asset-detail-col">
          <div class="section-label">分镜脚本（与分镜对应）</div>
          <div class="asset-detail-box asset-detail-script-box">
            ${scriptText ? `<div class="asset-detail-script-content">${renderMarkdown(String(scriptText))}</div>` : '<div class="empty-sm">暂无脚本</div>'}
          </div>
        </section>
        <section class="asset-detail-col">
          <div class="section-label">备注（可编辑）</div>
          <div class="asset-detail-box asset-detail-note-box">
            ${selectedPanel ? `
              <textarea class="prompt-input asset-note-input" data-asset-note-file="${escAttr(detail.file)}" data-asset-note-panel="${escAttr(selectedPanel.panelId)}" placeholder="填写该分镜备注...">${escHtml(selectedPanel.note || '')}</textarea>
              <button class="btn btn-primary btn-block" onclick="saveAssetPanelNote('${escAttr(detail.file)}','${escAttr(selectedPanel.panelId)}')">保存备注</button>
            ` : '<div class="empty-sm">请选择一个分镜</div>'}
          </div>
        </section>
      </div>
    </div>
  </div>`;
}

// ======================================================================
//  SETTINGS
// ======================================================================
function renderSettings() {
  const defaults = S.settings.defaults || {};
  const placeholder = S.settings.hasApiKey
    ? (S.settings.apiKeyMasked || '已保存，重新输入可覆盖')
    : '请输入你的 API Key';
  return `
  <div class="page-header"><div><h1 class="page-title">设置</h1><p class="page-subtitle">用户只需要填写 API Key，其余参数使用预设值</p></div></div>
    <div class="settings-panel">
      <section class="settings-card">
        <div class="settings-card-head">
          <div>
            <div class="settings-card-title">模型访问</div>
            <div class="settings-card-desc">首次启动只需配置一次。保存后会写入本机用户目录。</div>
          </div>
          <div class="settings-status ${S.settings.hasApiKey ? 'ready' : 'missing'}">${S.settings.hasApiKey ? '已配置' : '未配置'}</div>
        </div>
        <label class="settings-field">
          <span class="settings-label">API Key</span>
          <input
            id="settingsApiKeyInput"
            class="prompt-input settings-input"
            type="password"
            autocomplete="off"
            spellcheck="false"
            value="${escAttr(S.settings.apiKeyInput)}"
            placeholder="${escAttr(placeholder)}"
          />
        </label>
        <div class="settings-actions">
          <button class="btn btn-primary" onclick="saveRuntimeSettings()" ${S.settings.saving ? 'disabled' : ''}>${S.settings.saving ? '保存中...' : '保存 API Key'}</button>
          <button class="btn btn-secondary" onclick="openWorkbenchFromSettings()" ${S.settings.hasApiKey ? '' : 'disabled'}>进入工作台</button>
        </div>
      </section>

      <section class="settings-card settings-card-muted">
        <div class="settings-card-title">已预设参数</div>
        <div class="settings-preset-list">
          <div class="settings-preset-item"><span>脚本模型</span><strong>${escHtml(defaults.scriptModel || 'doubao-seed-1-8-251228')}</strong></div>
          <div class="settings-preset-item"><span>接口地址</span><strong>${escHtml(defaults.baseUrl || 'https://ark.cn-beijing.volces.com/api/v3')}</strong></div>
          <div class="settings-preset-item"><span>默认分镜策略</span><strong>${escHtml(defaults.splitStrategy || 'normal')}</strong></div>
          <div class="settings-preset-item"><span>OCR 开关</span><strong>${defaults.ocrEnabled ? '开启' : '关闭'}</strong></div>
        </div>
        <div class="settings-footnote">如需更换预设，由应用维护者统一修改，不要求最终用户干预。</div>
      </section>
    </div>`;
}

// ======================================================================
//  EVENT BINDING
// ======================================================================
function bindEvents() {
  // Upload zone
  const uz = document.getElementById('uploadZone');
  const fi = document.getElementById('fileInput');
  if (uz && fi) {
    uz.onclick = () => fi.click();
    uz.ondragover = e => { e.preventDefault(); uz.classList.add('drag-over'); };
    uz.ondragleave = () => uz.classList.remove('drag-over');
    uz.ondrop = e => {
      e.preventDefault();
      uz.classList.remove('drag-over');
      if (e.dataTransfer.files.length) handleUploadFiles(Array.from(e.dataTransfer.files));
    };
    fi.onchange = e => {
      if (e.target.files.length) handleUploadFiles(Array.from(e.target.files));
      fi.value = '';
    };
  }

  // Search
  document.querySelectorAll('[data-action="searchRuns"]').forEach(el => {
    el.addEventListener('input', e => { S.searchQ = e.target.value; render(); focusInput('[data-action="searchRuns"]', e.target.selectionStart); });
  });
  document.querySelectorAll('[data-action="searchAssets"]').forEach(el => {
    el.addEventListener('input', e => { S.assetSearch = e.target.value; render(); focusInput('[data-action="searchAssets"]', e.target.selectionStart); });
  });

  const settingsApiKeyInput = document.getElementById('settingsApiKeyInput');
  if (settingsApiKeyInput) {
    settingsApiKeyInput.addEventListener('input', e => {
      S.settings.apiKeyInput = e.target.value;
    });
    settingsApiKeyInput.addEventListener('keydown', async e => {
      if (e.key === 'Enter') {
        e.preventDefault();
        await window.saveRuntimeSettings();
      }
    });
  }

  // Filters
  document.querySelectorAll('.filter-tab[data-filter]').forEach(el => {
    el.onclick = () => { S.statusFilter = el.dataset.filter; render(); };
  });

  // Strategy pills
  document.querySelectorAll('.pill[data-strat]').forEach(el => {
    el.onclick = () => { S.selectedStrategy = el.dataset.strat; render(); };
  });

  // Task cards click -> open studio
  document.querySelectorAll('.task-card[data-run-id]').forEach(el => {
    el.onclick = () => {
      const rid = el.dataset.runId;
      const run = S.runs.find(r => r.id === rid);
      if (run?.status === 'success') openStudio(rid);
    };
  });

  // Panel thumbs
  const studioPanelsEl = document.querySelector('.studio-panels');
  if (studioPanelsEl) {
    // Restore panel list scroll position after a full re-render.
    if (typeof S.studioPanelsScrollTop === 'number' && S.studioPanelsScrollTop > 0) {
      studioPanelsEl.scrollTop = S.studioPanelsScrollTop;
    }
    studioPanelsEl.onscroll = () => {
      S.studioPanelsScrollTop = studioPanelsEl.scrollTop;
      hideStudioHoverPreview();
    };
  }
  const studioOriginalEl = document.querySelector('.studio-original');
  if (studioOriginalEl) {
    if (typeof S.studioOriginalScrollTop === 'number' && S.studioOriginalScrollTop > 0) {
      studioOriginalEl.scrollTop = S.studioOriginalScrollTop;
    }
    studioOriginalEl.onscroll = () => {
      S.studioOriginalScrollTop = studioOriginalEl.scrollTop;
    };
  }
  const studioTextPoolEl = document.querySelector('.studio-binding .text-pool');
  if (studioTextPoolEl) {
    if (typeof S.studioTextPoolScrollTop === 'number' && S.studioTextPoolScrollTop > 0) {
      studioTextPoolEl.scrollTop = S.studioTextPoolScrollTop;
    }
    studioTextPoolEl.onscroll = () => {
      S.studioTextPoolScrollTop = studioTextPoolEl.scrollTop;
    };
  }
  document.querySelectorAll('.panel-thumb[data-panel]').forEach(el => {
    el.onmouseenter = () => {
      showStudioHoverPreview(el.dataset.panel, el.getBoundingClientRect());
    };
    el.onmouseleave = () => {
      hideStudioHoverPreview();
    };
    el.onclick = () => {
      const panelList = el.closest('.studio-panels');
      if (panelList) S.studioPanelsScrollTop = panelList.scrollTop;
      S.selectedPanel = el.dataset.panel;
      syncStudioTextPoolModeForCurrentPanel();
      S.hoverStudioPanel = null;
      hideStudioHoverPreview();
      autoSelectPanelTexts();
      // Don't clear the script — restore previously generated result for this panel
      render();
    };
  });

  // Text checkboxes
  document.querySelectorAll('.text-item input[data-text-id]').forEach(el => {
    el.onchange = () => {
      const id = el.dataset.textId;
      if (el.checked) S.selectedTexts.add(id); else S.selectedTexts.delete(id);
      render();
    };
  });

  // Prompt input
  const pi = document.getElementById('promptInput');
  if (pi) pi.oninput = e => { S.scriptPrompt = e.target.value; };

  // Asset rows expand
  document.querySelectorAll('.asset-detail-panel-card[data-asset-file][data-asset-panel]').forEach(el => {
    el.onclick = () => {
      S.activeAssetDetail = { file: el.dataset.assetFile, selectedPanelId: el.dataset.assetPanel };
      render();
    };
  });
}

function focusInput(sel, pos) {
  requestAnimationFrame(() => {
    const el = document.querySelector(sel);
    if (el) { el.focus(); el.selectionStart = el.selectionEnd = pos; }
  });
}

// ======================================================================
//  ACTION HANDLERS
// ======================================================================
function makeUploadQueueId() {
  return `up_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

async function handleUpload(file, { deferRender = false } = {}) {
  if (!file) return;
  if (!/\.(psd|psb)$/i.test(file.name)) {
    toast(`已跳过非 PSD 文件: ${file.name}`, 'error');
    return;
  }
  toast(`上传中: ${file.name}...`, 'info');
  try {
    const fd = new FormData();
    fd.append('file', file);
    const res = await apiFetch('/api/upload', { method: 'POST', body: fd });
    const sourcePath = res.sourcePath || res.path;
    const previewPath = res.previewPath || res.path;
    const previewUrl = previewPath && !/\.(psd|psb)$/i.test(String(previewPath)) ? fileUrl(previewPath) : null;
    S.uploadQueue.push({
      id: makeUploadQueueId(),
      name: res.filename || file.name,
      path: sourcePath,
      previewUrl,
    });
    toast(`${file.name} 上传成功`, 'success');
    if (!deferRender) render();
  } catch (e) { toast(`上传失败: ${e.message} `, 'error'); }
}

async function handleUploadFiles(files) {
  const list = Array.isArray(files) ? files : Array.from(files || []);
  if (!list.length) return;
  for (const f of list) {
    await handleUpload(f, { deferRender: true });
  }
  render();
}

window.removeUploadFile = function (uploadId) {
  const before = S.uploadQueue.length;
  S.uploadQueue = S.uploadQueue.filter(item => item.id !== uploadId);
  if (S.imagePreviewDialog && before !== S.uploadQueue.length) {
    const stillExists = S.uploadQueue.some(item => item.previewUrl === S.imagePreviewDialog.url);
    if (!stillExists) S.imagePreviewDialog = null;
  }
  render();
};

window.openUploadPreview = function (uploadId) {
  const item = uploadId
    ? S.uploadQueue.find(x => x.id === uploadId)
    : getTopUpload();
  if (!canPreviewUpload(item)) {
    toast('当前文件暂无可用预览图', 'error');
    return;
  }
  S.imagePreviewDialog = { name: item.name, url: item.previewUrl };
  render();
};

window.closeImagePreview = function () {
  if (!S.imagePreviewDialog) return;
  S.imagePreviewDialog = null;
  render();
};

window.handleSplitPanels = async function () {
  const p = getTopUpload();
  if (!p) { toast('请先上传 PSD 文件', 'error'); return; }
  const prefix = p.name.replace(/\.(psd|psb)$/i, '');
  try {
    const params = new URLSearchParams({ image_path: p.path, strategy: S.selectedStrategy, prefix });
    await apiFetch(`/api/runs?${params}`, { method: 'POST' });
    toast(`任务 ${prefix} 已提交！`, 'success');
    S.uploadQueue = S.uploadQueue.slice(1);
    await fetchRuns();
    render();
    startPoll();
  } catch (e) { toast(`提交失败: ${e.message} `, 'error'); }
};

window.openStudio = function (runId) {
  S.agentTab = 'studio';
  navigate('agent', { runId });
};

window.openAssetDetail = async function (filename, panelId = null) {
  if (!filename) return;
  S.activeAssetDetail = { file: filename, selectedPanelId: panelId };
  render();
  const detail = await fetchAssetDetail(filename);
  if (!detail) return;
  if (!S.activeAssetDetail || S.activeAssetDetail.file !== filename) return;
  if (!S.activeAssetDetail.selectedPanelId && detail.panels?.length) {
    S.activeAssetDetail.selectedPanelId = detail.panels[0].panelId;
  }
  render();
};

window.closeAssetDetail = function () {
  S.activeAssetDetail = null;
  render();
};

window.saveAssetPanelNote = async function (file, panelId) {
  const input = document.querySelector(`[data-asset-note-file="${CSS.escape(file)}"][data-asset-note-panel="${CSS.escape(panelId)}"]`);
  if (!input) return;
  const key = `${file}::${panelId}`;
  S.assetNoteSaving[key] = true;
  try {
    await apiFetch('/api/assets/psd/panel-note', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file, panelId, note: input.value }),
    });
    const detail = S.assetDetails[file];
    if (detail?.panels) {
      const panel = detail.panels.find(p => p.panelId === panelId);
      if (panel) panel.note = input.value;
    }
    toast('备注已保存', 'success');
    render();
  } catch (e) {
    toast(`备注保存失败: ${e.message}`, 'error');
  } finally {
    delete S.assetNoteSaving[key];
  }
};

window.handleRetry = async function (runId) {
  const run = S.runs.find(r => r.id === runId);
  if (!run) return;
  try {
    const params = new URLSearchParams({ image_path: run.sourceImagePath || run.imagePath || '', strategy: run.strategy || 'normal', prefix: runId });
    await apiFetch(`/api/runs?${params}`, { method: 'POST' });
    toast(`任务 ${runId} 已重新提交`, 'success');
    await fetchRuns(); render(); startPoll();
  } catch (e) { toast(`重试失败: ${e.message} `, 'error'); }
};

window.handleStopRun = async function (runId) {
  if (!runId) return;
  if (!confirm(`确认停止任务 ${runId} 吗？`)) return;
  try {
    await apiFetch(`/api/runs/${encodeURIComponent(runId)}/stop`, { method: 'POST' });
    toast(`已发送停止请求: ${runId}`, 'success');
    await fetchRuns();
    render();
  } catch (e) {
    toast(`停止失败: ${e.message}`, 'error');
  }
};

window.handleDeleteRun = async function (runId) {
  if (!runId) return;
  if (!confirm(`确认删除任务 ${runId} 吗？这会删除本地任务记录和主要产物文件。`)) return;
  try {
    await apiFetch(`/api/runs/${encodeURIComponent(runId)}`, { method: 'DELETE' });
    if (S.studioRunId === runId) {
      S.studioRunId = null;
      S.studioResult = null;
      S.selectedPanel = null;
      S.selectedTexts.clear();
      if (S.agentTab === 'studio') S.agentTab = 'tasks';
    }
    S.panelScripts = {};
    await fetchRuns();
    if (S.assets.length) await fetchAssets();
    toast(`任务已删除: ${runId}`, 'success');
    render();
  } catch (e) {
    toast(`删除失败: ${e.message}`, 'error');
  }
};

window.handleGenScript = async function () {
  if (!S.studioRunId || !S.selectedPanel) { toast('请先选择一个分镜', 'error'); return; }
  if (S.selectedTexts.size === 0) { toast('请至少选择一条文字', 'error'); return; }
  const panelId = S.selectedPanel; // capture current panel at time of click
  S.scriptLoading = true;
  S.panelScripts[panelId] = null;
  render();
  try {
    const res = await apiFetch('/api/script/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        runId: S.studioRunId,
        panelId: S.selectedPanel,
        selectedTextIds: Array.from(S.selectedTexts),
        prompt: S.scriptPrompt || '请根据分镜画面和选中的文字，生成分镜脚本',
      }),
    });
    S.panelScripts[panelId] = res.script; // save result to this panel's slot
    if (S.studioResult) {
      if (!S.studioResult.panelTextScriptBindings || typeof S.studioResult.panelTextScriptBindings !== 'object') {
        S.studioResult.panelTextScriptBindings = {};
      }
      if (res.binding) S.studioResult.panelTextScriptBindings[panelId] = res.binding;
    }
    S.studioTextPoolMode = 'bound';
    toast('脚本生成完成！', 'success');
  } catch (e) { toast(`生成失败: ${e.message} `, 'error'); }
  S.scriptLoading = false;
  // Only re-render if the user is still on the studio view — don't force-navigate them back
  if (S.view === 'studio') render();
};

window.handleBindTexts = async function () {
  if (!S.studioRunId || !S.selectedPanel) { toast('请先选择一个分镜', 'error'); return; }
  if (S.selectedTexts.size === 0) { toast('请至少选择一条文字', 'error'); return; }
  const panelId = S.selectedPanel;
  S.bindingSaving = true;
  render();
  try {
    const res = await apiFetch('/api/script/bind-texts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        runId: S.studioRunId,
        panelId,
        selectedTextIds: Array.from(S.selectedTexts),
      }),
    });
    if (S.studioResult) {
      if (!S.studioResult.panelTextScriptBindings || typeof S.studioResult.panelTextScriptBindings !== 'object') {
        S.studioResult.panelTextScriptBindings = {};
      }
      if (res.binding) {
        S.studioResult.panelTextScriptBindings[panelId] = {
          ...(S.studioResult.panelTextScriptBindings[panelId] || {}),
          ...res.binding,
        };
      }
    }
    S.studioTextPoolMode = 'bound';
    toast('文字绑定已保存', 'success');
  } catch (e) {
    toast(`文字绑定失败: ${e.message}`, 'error');
  } finally {
    S.bindingSaving = false;
    if (S.view === 'agent' && S.agentTab === 'studio') render();
  }
};

window.handleUnbindTexts = async function () {
  if (!S.studioRunId || !S.selectedPanel) { toast('请先选择一个分镜', 'error'); return; }
  if (!getCurrentPanelBinding()) {
    S.studioTextPoolMode = 'all';
    autoSelectPanelTexts();
    render();
    return;
  }
  const panelId = S.selectedPanel;
  S.bindingSaving = true;
  render();
  try {
    await apiFetch('/api/script/bind-texts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        runId: S.studioRunId,
        panelId,
        selectedTextIds: [],
        clear: true,
      }),
    });
    if (S.studioResult?.panelTextScriptBindings && typeof S.studioResult.panelTextScriptBindings === 'object') {
      delete S.studioResult.panelTextScriptBindings[panelId];
    }
    S.studioTextPoolMode = 'all';
    autoSelectPanelTexts();
    toast('已取消绑定', 'success');
  } catch (e) {
    toast(`取消绑定失败: ${e.message}`, 'error');
  } finally {
    S.bindingSaving = false;
    if (S.view === 'agent' && S.agentTab === 'studio') render();
  }
};

window.handleShowBoundTexts = function () {
  if (!getCurrentPanelBinding()) return;
  S.studioTextPoolMode = 'bound';
  autoSelectPanelTexts();
  render();
};

window.handleCopyScript = function () {
  const scriptObj = S.panelScripts[S.selectedPanel];
  if (!scriptObj) return;
  // Plain text schema
  const text = scriptObj.script_text
    || (typeof scriptObj === 'string' ? scriptObj : JSON.stringify(scriptObj, null, 2));
  navigator.clipboard.writeText(text).then(() => toast('已复制到剪贴板', 'success')).catch(() => toast('复制失败', 'error'));
};

window.toggleScriptSection = function (headerEl) {
  const section = headerEl.closest('.script-section');
  if (section) section.classList.toggle('collapsed');
};

window.copySection = function (sectionKey) {
  if (!S.scriptOutput) return;
  const keyMap = { imageAnalysis: 'image_analysis', textEntries: 'text_entries', bindingTable: 'binding_table', directorScript: 'director_script' };
  const data = S.scriptOutput[keyMap[sectionKey]];
  if (!data) { toast('无数据', 'error'); return; }
  const text = JSON.stringify(data, null, 2);
  navigator.clipboard.writeText(text).then(() => toast('区块已复制', 'success')).catch(() => toast('复制失败', 'error'));
};

window.handleExport = async function () {
  try {
    const res = await apiFetch('/api/exports/excel', { method: 'POST' });
    if (res.path) { const a = document.createElement('a'); a.href = fileUrl(res.path); a.download = res.filename; a.click(); }
    toast('导出完成', 'success');
  } catch (e) { toast(`导出失败: ${e.message} `, 'error'); }
};

window.saveRuntimeSettings = async function () {
  return await saveRuntimeSettings();
};

window.openWorkbenchFromSettings = function () {
  if (!S.settings.hasApiKey) return;
  navigate(S.agentModule === 'director' ? 'director' : 'storyboard');
};

// ============ Helpers ============
function escHtml(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
function escAttr(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/\\/g, '\\\\')
    .replace(/'/g, "\\'");
}

function toast(msg, type = 'info') {
  const c = document.getElementById('toastContainer');
  const t = document.createElement('div');
  t.className = `toast ${type} `;
  const icons = {
    success: `<svg width="18" height="18" viewBox="0 0 20 20" fill="var(--color-success)"><path d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.7-10.3l-4.5 4.5a.7.7 0 01-1 0L6.3 10.3a.7.7 0 011-1l1.4 1.4 4-4a.7.7 0 011 1z"/></svg>`,
    error: `<svg width="18" height="18" viewBox="0 0 20 20" fill="var(--color-error)"><path d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-5H9v-2h2v2zm0-4H9V5h2v4z"/></svg>`,
    info: `<svg width="18" height="18" viewBox="0 0 20 20" fill="var(--color-brand)"><path d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-5H9v-4h2v4zm0-6H9V5h2v2z"/></svg>`,
  };
  t.innerHTML = `${icons[type] || icons.info} <span>${msg}</span>`;
  c.appendChild(t);
  setTimeout(() => { t.style.animation = 'toastOut 250ms ease-in forwards'; setTimeout(() => t.remove(), 250); }, 3500);
}

// ============ Init ============
document.addEventListener('DOMContentLoaded', async () => {
  document.querySelectorAll('.nav-tab').forEach(t => { t.onclick = () => navigate(t.dataset.tab); });
  await loadWorkbenchUiState();
  try {
    await fetchRuntimeSettings();
  } catch (e) {
    toast('加载设置失败，请稍后重试', 'error');
  }
  if (!S.settings.hasApiKey) {
    navigate('settings');
    return;
  }
  if (S.view === 'settings') {
    navigate('settings');
    return;
  }
  if (S.agentModule === 'director') {
    navigate('director');
    return;
  }
  if (S.agentTab === 'studio' && S.studioRunId) {
    navigate('agent', { runId: S.studioRunId });
    return;
  }
  navigate('agent', { agentTab: S.agentTab });
});
