export const DIRECTOR_STEP_META = Object.freeze({
  step0: Object.freeze({
    title: '项目初始化',
    shortLabel: 'Project',
    enterHint: '初始化项目基础信息',
  }),
  step1: Object.freeze({
    title: '初始种子',
    shortLabel: 'Seed',
    enterHint: '需先创建项目',
  }),
  step2: Object.freeze({
    title: '结构蓝图',
    shortLabel: 'Blueprint',
    enterHint: '需先在初始种子中选定 Logline 与 Mode',
  }),
  step3: Object.freeze({
    title: '段落节拍',
    shortLabel: 'Beats',
    enterHint: '需先完成结构蓝图',
  }),
  step4: Object.freeze({
    title: '分场表',
    shortLabel: 'Scenes',
    enterHint: '需先完成段落节拍',
  }),
  step5: Object.freeze({
    title: '剧本一稿',
    shortLabel: 'Draft',
    enterHint: '需先完成分场表',
  }),
  step6: Object.freeze({
    title: '评审质检',
    shortLabel: 'Review',
    enterHint: '需先完成剧本一稿',
  }),
  step7: Object.freeze({
    title: '迭代改稿',
    shortLabel: 'Rewrite',
    enterHint: '需先完成评审质检',
  }),
  step8: Object.freeze({
    title: '编导资产 + 交付导出',
    shortLabel: 'Assets',
    enterHint: '需先完成迭代改稿',
  }),
});

export function getDirectorStepMeta(stepKey) {
  return DIRECTOR_STEP_META[stepKey] || null;
}
