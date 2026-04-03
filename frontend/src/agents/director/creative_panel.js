const CREATIVE_PANEL_FIELDS = [
  {
    key: 'theme_question',
    title: '主题问题',
    placeholder: '例如：这部作品真正想追问什么问题？',
    examples: [
      '这部作品想回答“人为了守护重要之物愿意付出什么代价”？',
      '主角在秩序与自由之间最终会选择什么？',
      '当记忆不可靠时，人与人的信任如何建立？',
    ],
  },
  {
    key: 'anti_patterns',
    title: '避雷',
    placeholder: '例如：避免套路、避免角色行为失真、避免说教感',
    examples: [
      '避免纯靠台词解释设定，信息尽量通过行动呈现。',
      '避免为了推进剧情强行降智。',
      '避免结尾突然反转但缺乏前文铺垫。',
    ],
  },
  {
    key: 'must_keep',
    title: '必须保留',
    placeholder: '例如：角色关系、世界观设定、名场面、核心情绪',
    examples: [
      '必须保留主角与搭档“嘴硬心软”的互动关系。',
      '必须保留第一集建立的世界观规则与代价机制。',
      '必须保留结尾的克制感，不做过度煽情。',
    ],
  },
  {
    key: 'global_tone_adjust',
    title: '整体更____',
    placeholder: '例如：整体更轻快 / 更悬疑 / 更热血 / 更电影感',
    examples: [
      '整体更悬疑，信息释放更慢一点。',
      '整体更热血，冲突节奏更明确。',
      '整体更电影感，减少直白解释，强化镜头表达。',
    ],
  },
];

function escHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function jsStringLiteral(value) {
  return JSON.stringify(String(value ?? '')).replace(/'/g, '\\u0027');
}

function renderExampleChips(field) {
  return `
    <div style="display:flex; flex-wrap:wrap; gap:8px; margin-top:8px;">
      ${field.examples.map(example => `
        <button
          type="button"
          class="btn-sm"
          onclick='applyDirectorCreativeExample(${jsStringLiteral(field.key)}, ${jsStringLiteral(example)})'
        >${escHtml(example)}</button>
      `).join('')}
    </div>`;
}

export function renderDirectorCreativePanel(creativePanel = {}) {
  return `
  <div class="card">
    <div class="card-header">
      <h3 class="card-title">创作空间面板（Creative Control Panel）</h3>
      <span class="tag">前端本地草稿</span>
    </div>
    <div class="card-body">
      <div style="display:grid; gap:14px;">
        ${CREATIVE_PANEL_FIELDS.map(field => `
          <label style="display:grid; gap:6px;">
            <span class="section-label" style="margin:0;">${field.title}</span>
            <textarea class="prompt-input" rows="3" placeholder="${escHtml(field.placeholder)}" oninput="setDirectorCreativeField('${field.key}', this.value)">${escHtml(creativePanel[field.key] || '')}</textarea>
            ${renderExampleChips(field)}
          </label>
        `).join('')}
      </div>
      <div style="margin-top:10px; color: var(--color-text-muted); font-size:12px;">
        当前仅保存在前端内存状态，不参与“项目初始化”创建项目请求。
      </div>
    </div>
  </div>`;
}
