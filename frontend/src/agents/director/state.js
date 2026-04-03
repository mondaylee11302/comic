import {
  DIRECTOR_CREATIVE_PANEL_FIELDS,
  DIRECTOR_DEFAULT_REVIEW_DIMENSIONS,
  DIRECTOR_STEP0_FORM_FIELDS,
  DIRECTOR_STEP1_FORM_FIELDS,
  DIRECTOR_STEP2_FORM_FIELDS,
  DIRECTOR_STEP3_FORM_FIELDS,
  DIRECTOR_STEP4_FORM_FIELDS,
  DIRECTOR_STEP5_FORM_FIELDS,
  DIRECTOR_STEP6_FORM_FIELDS,
  DIRECTOR_STEP6_REVIEW_TABS,
  DIRECTOR_STEP7_FORM_FIELDS,
  DIRECTOR_STEP8_FORM_FIELDS,
  DIRECTOR_STEPS,
} from './constants.js';

function createEmptyStringRecord(fields) {
  return Object.fromEntries(fields.map((key) => [key, '']));
}

function createDirectorMockProjectCards() {
  return [
    {
      id: 'script_alpha',
      title: '雾港追光',
      updatedAt: '2026-02-26 20:18',
      status: '最近编辑',
      type: '短片',
      duration: '18min',
      tone: '悬疑 / 冷峻',
      referenceIp: '原创',
    },
    {
      id: 'script_beta',
      title: '零号操场',
      updatedAt: '2026-02-25 23:40',
      status: '草稿',
      type: '番剧单集',
      duration: '24min',
      tone: '青春 / 超现实',
      referenceIp: '原创',
    },
    {
      id: 'script_gamma',
      title: '天桥凌晨四点',
      updatedAt: '2026-02-24 19:07',
      status: '评审后待改',
      type: 'PV',
      duration: '90s',
      tone: '压迫 / 电影感',
      referenceIp: '实验项目',
    },
  ];
}

export function createDirectorInitialState() {
  return {
    uiPage: 'home', // 'home' | 'projects' | 'workspace'
    workspaceProjectMeta: null, // { id, title, updatedAt, isNew }
    projectShelf: {
      items: createDirectorMockProjectCards(),
    },
    step: DIRECTOR_STEPS.STEP0,
    form: createEmptyStringRecord(DIRECTOR_STEP0_FORM_FIELDS),
    creativePanel: createEmptyStringRecord(DIRECTOR_CREATIVE_PANEL_FIELDS),
    creating: false,
    error: '',
    project: null,
    step1: {
      form: createEmptyStringRecord(DIRECTOR_STEP1_FORM_FIELDS),
      generating: false,
      error: '',
      result: null,
      selected_logline_index: null,
      selected_mode_index: null,
    },
    step2: {
      form: createEmptyStringRecord(DIRECTOR_STEP2_FORM_FIELDS),
      generating: false,
      error: '',
      result: null,
    },
    step3: {
      form: createEmptyStringRecord(DIRECTOR_STEP3_FORM_FIELDS),
      generating: false,
      error: '',
      result: null,
    },
    step4: {
      form: createEmptyStringRecord(DIRECTOR_STEP4_FORM_FIELDS),
      generating: false,
      error: '',
      result: null,
    },
    step5: {
      form: createEmptyStringRecord(DIRECTOR_STEP5_FORM_FIELDS),
      generating: false,
      error: '',
      result: null,
    },
    step6: {
      form: {
        ...createEmptyStringRecord(DIRECTOR_STEP6_FORM_FIELDS),
        review_dimensions: [...DIRECTOR_DEFAULT_REVIEW_DIMENSIONS],
      },
      activeTab: DIRECTOR_STEP6_REVIEW_TABS.ISSUES,
      generating: false,
      error: '',
      result: null,
      taskSelections: {},
    },
    step7: {
      form: createEmptyStringRecord(DIRECTOR_STEP7_FORM_FIELDS),
      generating: false,
      error: '',
      result: null,
    },
    step8: {
      form: {
        ...createEmptyStringRecord(DIRECTOR_STEP8_FORM_FIELDS),
        selected_version: 'Draft v2',
        asset_filter: '全部',
        export_format: 'PDF',
        export_items: ['剧本', '分场表', '评审报告'],
      },
      generating: false,
      error: '',
      result: null,
    },
  };
}
