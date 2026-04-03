export const DIRECTOR_STEPS = Object.freeze({
  STEP0: 'step0',
  STEP1: 'step1',
  STEP2: 'step2',
  STEP3: 'step3',
  STEP4: 'step4',
  STEP5: 'step5',
  STEP6: 'step6',
  STEP7: 'step7',
  STEP8: 'step8',
});

export const DIRECTOR_STEP0_FORM_FIELDS = Object.freeze([
  'movie_name',
  'type',
  'duration',
  'tone',
  'reference_ip',
]);

export const DIRECTOR_CREATIVE_PANEL_FIELDS = Object.freeze([
  'theme_question',
  'anti_patterns',
  'must_keep',
  'global_tone_adjust',
]);

export const DIRECTOR_STEP1_FORM_FIELDS = Object.freeze([
  'seed',
  'protagonist',
  'antagonist',
  'core_synopsis',
  'key_setting',
]);

export const DIRECTOR_STEP2_FORM_FIELDS = Object.freeze([
  'audience',
  'narrative_focus',
  'ending_tendency',
]);

export const DIRECTOR_STEP3_FORM_FIELDS = Object.freeze([
  'segment_granularity',
  'action_ratio',
  'character_ratio',
]);

export const DIRECTOR_STEP4_FORM_FIELDS = Object.freeze([
  'target_scene_count',
  'scene_constraints',
  'language_style',
]);

export const DIRECTOR_STEP5_FORM_FIELDS = Object.freeze([
  'writing_tendency',
  'dialogue_density',
  'rating_intensity',
]);

export const DIRECTOR_REVIEW_DIMENSION_OPTIONS = Object.freeze([
  '叙事',
  '人物',
  '导演可视化',
  '战术可信',
  '制片可行',
  'IP规则',
]);

export const DIRECTOR_DEFAULT_REVIEW_DIMENSIONS = Object.freeze([
  '叙事',
  '人物',
  '导演可视化',
]);

export const DIRECTOR_STEP6_FORM_FIELDS = Object.freeze([
  'rewrite_preference',
]);

export const DIRECTOR_STEP6_REVIEW_TABS = Object.freeze({
  ISSUES: 'issues',
  TASKS: 'tasks',
  IMPACT: 'impact',
  REPORT: 'report',
});

export const DIRECTOR_STEP7_FORM_FIELDS = Object.freeze([
  'rewrite_scope',
  'strengthen_metrics',
]);

export const DIRECTOR_STEP8_FORM_FIELDS = Object.freeze([
  'selected_version',
  'asset_filter',
  'export_format',
]);
