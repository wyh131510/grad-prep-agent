/* ==========================================================================
 * app.js —— 毕设 Agent 前端主逻辑（SPA，无路由库，6 个视图）
 * 视图：概览 / 任务与检索 / 文献库 / 开题报告 / 评审与答辩 / 设置
 * 长任务统一模式：POST 返回 {"job_id"} → EventSource('/api/jobs/{id}/events')
 *   event: log    → 更新进度条(progress 0~1) + 日志行(message)
 *   event: result → 关闭流、toast 成功、刷新相关数据
 *   event: error  → 关闭流、toast 错误
 * 依赖：api.js（window.API）、md.js（window.MD）、ui.js（window.UI）
 * ========================================================================== */
'use strict';
(function () {

  const $ = function (sel) { return document.querySelector(sel); };
  const esc = UI.esc;
  const jsq = UI.jsq;

  /* ================= 常量 ================= */

  const VIEW_META = {
    overview: { title: '概览', sub: '项目介绍 · 全流程示意 · 统计' },
    tasks: { title: '任务与检索', sub: '创建调研任务 · 启动检索 · 筛选文献' },
    library: { title: '文献库', sub: '已收藏文献 · 生成调研综述' },
    proposal: { title: '开题报告', sub: '上传模板 · 分块生成 · 导出' },
    review: { title: '评审与答辩', sub: '多智能体评审 · 答辩问题清单' },
    settings: { title: '设置', sub: '服务商 · 角色映射 · 检索参数' }
  };

  /** 检索来源（创建/编辑任务表单的可选项；cnki/wanfang 因反爬/0 命中已移除，direct_url 走独立输入框） */
  const SEARCH_SOURCES = [
    { id: 'semantic_scholar', label: 'Semantic Scholar' },
    { id: 'arxiv', label: 'arXiv' },
    { id: 'crossref', label: 'Crossref' },
    { id: 'pubmed', label: 'PubMed' },
    { id: 'openalex', label: 'OpenAlex' }
  ];

  /** 文献来源徽章表（含旧数据兼容显示：cnki/wanfang/direct_url/import） */
  const SOURCES = [
    { id: 'semantic_scholar', label: 'Semantic Scholar', cls: 'badge-blue' },
    { id: 'arxiv', label: 'arXiv', cls: 'badge-red' },
    { id: 'crossref', label: 'Crossref', cls: 'badge-green' },
    { id: 'pubmed', label: 'PubMed', cls: 'badge-cyan' },
    { id: 'openalex', label: 'OpenAlex', cls: 'badge-purple' },
    { id: 'cnki', label: '知网 CNKI', cls: 'badge-purple' },
    { id: 'wanfang', label: '万方', cls: 'badge-amber' },
    { id: 'direct_url', label: '直链抓取', cls: 'badge-gray' },
    { id: 'import', label: '导入', cls: 'badge-gray' }
  ];

  const TASK_STATUS = {
    created: ['未检索', 'badge-gray'],
    searching: ['检索中', 'badge-blue pulse'],
    searched: ['已检索', 'badge-green'],
    failed: ['检索失败', 'badge-red']
  };

  /** 角色 → 服务商映射的 10 个角色 */
  const ROLES = [
    ['planner', '选题规划（拆解检索）'],
    ['summary', '文献总结'],
    ['translate', '翻译'],
    ['proposal', '开题初稿生成'],
    ['academic', '学术规范评审'],
    ['logic', '逻辑评审'],
    ['feasibility', '可行性评审'],
    ['format', '格式评审'],
    ['coordinator', '一致性汇总'],
    ['defense', '答辩问题清单']
  ];

  /** 默认分块 key → 中文标题（契约默认分块） */
  const SECTION_TITLES = {
    background: '课题背景与研究意义',
    literature_review: '国内外研究现状',
    objectives: '研究内容与目标',
    methodology: '研究方案与技术路线',
    feasibility: '可行性分析',
    schedule: '进度安排',
    references: '参考文献'
  };
  function sectionTitle(key) { return SECTION_TITLES[key] || key || ''; }

  /** 概览页：4 张能力卡 */
  const CAPABILITIES = [
    ['🔍', '自动检索与排序', '选题拆解 + 多源并行抓取 + 三重混合检索，自动给出最相关文献'],
    ['📚', '文献阅读与理解', '关键片段/真实图表提取、结构化总结、高质量翻译、主题综述'],
    ['✍️', '开题报告生成', '按学校模板分块生成初稿，可预览/编辑/重新生成，一键导出 Word'],
    ['👥', '评审与答辩', '4 角色评审 + 一致性汇总，辅助修改有改动对比，答辩问题清单']
  ];

  /** 概览页：9 步详解（做什么 / 输出结果 / 有什么作用） */
  const OVERVIEW_STEPS = [
    { n: '①', title: '选题拆解', what: '大模型把一句话选题拆成 4~6 个子问题，并为每个子问题生成中英文检索词', out: '子问题列表 + 20 条左右中英文检索词', why: '把「一句话选题」变成专业的检索策略' },
    { n: '②', title: '多源并行检索', what: '5 个来源（Semantic Scholar / arXiv / CrossRef / PubMed / OpenAlex）并行抓取', out: '各源命中的文献：标题、摘要、作者、年份、出处、DOI、链接、被引数', why: '一次搜到数十篇候选文献' },
    { n: '③', title: '统一解析与清洗', what: '把不同来源的数据标准化、去脏、去重', out: '统一格式的文献记录', why: '后续筛选/总结/生成都在干净数据上进行' },
    { n: '④', title: '三重混合检索', what: 'BM25 关键词 → 本地向量语义 → reranker 精排，RRF 融合', out: '每篇文献的相关度分 + 最终排序（分数列可视化）', why: '最相关的文献排最前，不用自己翻几十页' },
    { n: '⑤', title: '筛选收藏与全文解析', what: '勾选收藏（可一键批量），自动下载开放获取 PDF 并解析', out: '本地 PDF + 关键片段（带页码）+ 真实图表与图注 + 表格；失败时明确原因', why: '建立你自己的文献库；片段/图表直接可引用' },
    { n: '⑥', title: '结构化总结与翻译', what: '对收藏文献做单篇总结、术语一致翻译；多篇生成主题聚类综述', out: '单篇总结（方法/贡献/局限/与你的选题关联）+ 中译（含术语表）+ 综述全文', why: '每篇文献都能「落地」到你的毕设' },
    { n: '⑦', title: '开题报告分块生成', what: '结合模板 + 收藏文献，分块生成', out: '7 个分块初稿（标题/字数/状态），可预览/编辑/重新生成/导出 md + docx', why: '拿到可继续打磨的初稿，而不是从空白页开始' },
    { n: '⑧', title: '多智能体评审', what: '学术规范/逻辑/可行性/格式 4 个角色并行评审 + 主席一致性汇总', out: '4 份评分+问题+建议；最终修改建议（按优先级）+ 一键辅助修改（红绿对比）', why: '发现你自己没看出来的问题，按建议修改' },
    { n: '⑨', title: '答辩问题清单', what: '基于初稿预测评委提问', out: '4 类问题（背景/方法/可行性/进度）+ 考察意图 + 回答要点', why: '开题答辩前有准备' }
  ];

  /** 概览页：优点（绿色系） */
  const PROS = [
    ['🚀', '一条流水线直达开题初稿', '检索→解析→阅读→写作→评审全流程自动化，省掉最痛苦的重复劳动'],
    ['🎯', '每篇文献都有「与选题的关联」', '单篇总结直接告诉你它怎么用于你的毕设'],
    ['✅', '真实可信', '关键片段/图表/表格都来自原文解析，不由 AI 生成；引用与参考文献一一对应'],
    ['💾', '本地存档', '元数据 SQLite + 源文件本地目录，可离线查看，数据不出本机'],
    ['🔓', '模型自由', '任意 OpenAI 兼容 API（DeepSeek/Kimi/千问/智谱…），10 个角色可分用不同模型'],
    ['✏️', '全程可改', '分块预览/编辑/局部重生成/导出 Word；评审建议一键套用并显示改动对比']
  ];

  /** 概览页：缺点与限制（琥珀色系，诚实说明） */
  const LIMITS = [
    ['只做「文献调研 → 开题报告初稿」', '不包含中期检查、毕业论文正文写作、查重降重'],
    ['中文付费源受限', '知网/万方有反爬，无法直接抓取（可用 OpenAlex 的中文收录替代，或手动导入知网导出的 EndNote 文件）；付费墙文献拿不到免费全文，只能基于摘要总结，原文需到学校图书馆/知网获取'],
    ['部分开放获取出版商有反爬拦截', '（如 MDPI）PDF 需浏览器手动下载'],
    ['需要联网 + 自备大模型 API Key', '有少量调用费用；未配置时检索/生成会降级或不可用'],
    ['可选依赖未安装时自动降级', 'BGE 向量检索与 OCR 为可选依赖，未安装时降级为 BM25 + LLM 精排'],
    ['文献库暂不做跨任务去重', '个别网站图表依赖页面结构，可能提取不到']
  ];

  /* ================= 全局状态 ================= */

  const state = {
    view: 'overview',
    backendOnline: null,          // null=检测中 true/false
    settings: null,
    presets: [],
    stats: null,
    tasks: [],
    currentTaskId: null,
    currentTask: null,
    plan: null,                   // 当前任务 TopicPlan
    papers: { total: 0, items: [] },
    paperFilters: { q: '', year_from: '', year_to: '', source: '', collected: false, sort: 'score', order: 'desc', limit: 20, offset: 0 },
    selectedPaperIds: new Set(),  // 任务视图表格勾选（批量操作）
    drawerPaper: null,            // 抽屉中展示的文献
    // 文献库（走全局接口 GET /api/papers）
    libTaskId: '',                // '' = 全部任务（任务筛选作用于当前页）
    libQ: '',                     // 关键词（服务端筛选）
    libLimit: 20,
    libOffset: 0,
    libTotal: 0,                  // 全局接口返回的总数
    libPapers: [],                // 当前页已收藏文献（Paper 含 task_id）
    libFiltered: [],              // 当前页经任务筛选后的显示列表
    libTitles: {},                // 文献标题缓存（综述聚类 id→标题 映射）
    libSelected: new Set(),
    librarySurvey: {},            // taskId -> {content, clusters}
    // 开题报告
    propTaskId: '',
    propSections: [],
    propTemplate: null,
    editorKey: '',
    editorMode: 'edit',
    // 评审与答辩
    revTaskId: '',
    reviewData: null,
    defenseData: null,
    reviewRunning: false,         // 评审任务进行中标志
    reviewRunningTaskId: ''       // 正在评审的任务（切换任务时避免误标）
  };

  let papersSeq = 0;   // 文献列表请求序号（防止竞态）
  let planSeq = 0;     // 计划请求序号
  let libSeq = 0;      // 文献库请求序号（防止竞态）

  /* ================= 通用工具 ================= */

  function hasLLM() {
    const s = state.settings;
    if (!s || !Array.isArray(s.providers)) return false;
    return s.providers.some(function (p) { return p && p.enabled && p.api_key; });
  }

  function sourceBadge(src) {
    const s = SOURCES.find(function (x) { return x.id === src; });
    if (s) return UI.badge(s.label, s.cls);
    return UI.badge(src || '未知来源', 'badge-gray');
  }

  function statusBadge(st) {
    const s = TASK_STATUS[st] || [st || '未知', 'badge-gray'];
    return UI.badge(s[0], s[1]);
  }

  /**
   * 文献表格「操作」列：按 paper.download_status 分支渲染下载状态。
   * downloading → 「⏳ 下载中」徽章（琥珀色，不显示打开/无文件）
   * failed（或已收藏但无文件）→ 「⚠️ 下载失败」徽章（红色，title=download_note）
   * done 且 file_path 非空 → 「打开」按钮；none → 「无文件」
   */
  function downloadOpHtml(p) {
    const st = p.download_status || 'none';
    if (st === 'downloading') {
      return '<span title="正在下载 PDF，请稍候">' + UI.badge('⏳ 下载中', 'badge-amber') + '</span>';
    }
    if (st === 'failed') {
      return '<span title="' + esc(p.download_note || '源文件下载失败') + '">' + UI.badge('⚠️ 下载失败', 'badge-red') + '</span>';
    }
    if (p.file_path) {
      return '<button class="btn btn-ghost btn-sm" onclick="App.previewFileByPath(' + jsq(p.file_path) + ')" title="打开本地文件">📂 打开</button>';
    }
    if (p.collected && st !== 'done') {
      // 已收藏但无文件：视为下载失败（兼容旧数据无 download_status 的情况）
      return '<span title="' + esc(p.download_note || '源文件下载失败') + '">' + UI.badge('⚠️ 下载失败', 'badge-red') + '</span>';
    }
    return '<span class="muted small">无文件</span>';
  }

  /** 详情抽屉的下载状态行：done=已下载 / failed=下载失败+原因 / downloading=下载中 */
  function drawerDownloadStatusHtml(p) {
    const st = p.download_status || 'none';
    if (st === 'downloading') {
      return '<div class="dl-status">' + UI.badge('⏳ 下载中', 'badge-amber')
        + '<span class="muted small">正在下载 PDF，请稍候</span></div>';
    }
    if (st === 'failed' || (p.collected && !p.file_path && st !== 'done')) {
      return '<div class="dl-status">' + UI.badge('⚠️ 下载失败', 'badge-red')
        + '<span class="muted small">' + esc(p.download_note || '源文件下载失败') + '</span></div>';
    }
    if (p.file_path) {
      return '<div class="dl-status">' + UI.badge('已下载', 'badge-green')
        + '<span class="muted small">' + esc(p.file_path) + '</span></div>';
    }
    return '';
  }

  /** /api/files/preview 图片地址（逐段编码路径，避免编码 '/'） */
  function fileSrc(path) {
    return '/api/files/preview?path=' + String(path || '').split('/').map(encodeURIComponent).join('/');
  }

  /** 长任务返回体统一提取 job_id（契约返回 {"job_id": ...}） */
  function extractJobId(r) {
    if (!r) return null;
    if (typeof r.job_id === 'string' && r.job_id) return r.job_id;
    if (typeof r.id === 'string' && (r.status === 'running' || r.status === 'done' || r.status === 'error')) return r.id;
    return null;
  }

  /** 弹出「列表详情」模态框（如检索失败来源、下载失败文献） */
  function showListModal(title, items, desc) {
    const list = (items || []).map(function (i) { return '<li>' + esc(String(i)) + '</li>'; }).join('');
    UI.openModal(title,
      (desc ? '<p class="muted" style="margin-bottom:10px">' + esc(desc) + '</p>' : '')
      + '<ul class="plain-list">' + (list || '<li class="muted">（空）</li>') + '</ul>');
  }

  /* ================= 长任务统一执行（SSE） ================= */

  /**
   * 订阅并等待一个后台 Job 完成。
   * @param {string} jobId
   * @param {string} label 进度面板标题
   * @param {Function} onResult 收到 event: result 时回调（入参为结果对象）
   * @returns {Promise<object|null>} 任务结果；失败/中断返回 null
   */
  function runJob(jobId, label, onResult) {
    UI.jobPanel.open(label);
    return new Promise(function (resolve) {
      let es = null;
      let finished = false;
      const finish = function (payload) {
        if (finished) return;
        finished = true;
        if (es) { try { es.close(); } catch (e) { /* 忽略 */ } }
        resolve(payload);
      };
      try {
        es = new EventSource('/api/jobs/' + jobId + '/events');
      } catch (e) {
        UI.jobPanel.fail('无法连接后端服务');
        resolve(null);
        return;
      }
      es.addEventListener('log', function (e) {
        try {
          const d = JSON.parse(e.data);
          UI.jobPanel.log(d.progress, d.message);
        } catch (err) { /* 忽略坏数据 */ }
      });
      es.addEventListener('result', function (e) {
        let d = null;
        try { d = JSON.parse(e.data); } catch (err) { d = null; }
        UI.jobPanel.done();
        if (onResult) { try { onResult(d); } catch (err) { /* 回调异常不中断主流程 */ } }
        finish(d);
      });
      es.addEventListener('error', function (e) {
        // 服务端发送的 event: error（带 data），或连接异常（无 data）
        if (e.data) {
          let msg = '任务执行失败';
          try {
            const d = JSON.parse(e.data);
            msg = d.message || msg;
          } catch (err) { /* 忽略 */ }
          UI.jobPanel.fail(msg);
          UI.toast(msg, 'error');
        } else {
          UI.jobPanel.fail('无法连接后端服务或连接中断');
          UI.toast('任务进度流中断，请稍后在页面中刷新查看状态', 'error');
        }
        finish(null);
      });
    });
  }

  /* ================= 后端连接状态 ================= */

  function setBackendState(online) {
    state.backendOnline = online;
    const banner = $('#backendBanner');
    const dot = $('#connDot');
    const txt = $('#connText');
    if (online) {
      banner.hidden = true;
      dot.className = 'conn-dot on';
      txt.textContent = '后端已连接';
    } else {
      banner.hidden = false;
      dot.className = 'conn-dot off';
      txt.textContent = '后端未连接';
    }
  }

  async function checkBackend() {
    try {
      const h = await API.health();
      // GET /api/health 已实现：{"status":"ok","version":...,"optional":{...}}
      setBackendState(!!(h && h.status === 'ok'));
    } catch (e) {
      // 网络层失败（后端未启动 / file:// 打开）或健康检查异常：显示「后端未连接」提示条
      setBackendState(false);
    }
  }

  async function retryBackend() {
    const btn = $('#bannerRetry');
    if (btn) btn.disabled = true;
    await checkBackend();
    if (state.backendOnline) {
      UI.toast('后端已连接', 'success');
      goto(state.view);
    } else {
      UI.toast('后端仍无法连接，请确认服务已启动', 'error');
    }
    if (btn) btn.disabled = false;
  }

  /* ================= 视图切换 ================= */

  function goto(view) {
    if (!VIEW_META[view]) view = 'overview';
    state.view = view;
    document.querySelectorAll('.nav-item').forEach(function (b) {
      b.classList.toggle('active', b.getAttribute('data-view') === view);
    });
    document.querySelectorAll('.view').forEach(function (v) {
      v.classList.toggle('active', v.id === 'view-' + view);
    });
    $('#viewTitle').textContent = VIEW_META[view].title;
    $('#viewSub').textContent = VIEW_META[view].sub;

    const enter = {
      overview: enterOverview,
      tasks: enterTasks,
      library: enterLibrary,
      proposal: enterProposal,
      review: enterReview,
      settings: enterSettings
    }[view];
    if (enter) enter();
    window.scrollTo({ top: 0 });
  }

  /* ============================================================
   * 视图 1：概览
   * ============================================================ */

  function enterOverview() { renderOverview(); loadStats(); }

  function statCardHtml(icon, label, value) {
    return '<div class="stat-card">'
      + '<div class="stat-icon">' + icon + '</div>'
      + '<div class="stat-value">' + (value === null || value === undefined ? '—' : esc(String(value))) + '</div>'
      + '<div class="stat-label">' + esc(label) + '</div>'
      + '</div>';
  }

  async function loadStats() {
    try {
      state.stats = (await API.stats()) || null;
    } catch (e) {
      state.stats = null;
      if (!API.isNetworkError(e)) UI.toast('加载统计失败：' + e.message, 'error');
    }
    if (state.view === 'overview') renderOverview();
  }

  function renderOverview() {
    const el = $('#view-overview');
    if (!el) return;
    // GET /api/stats 已确认返回 {tasks, papers, collected, proposals, reviews}
    const s = state.stats || {};
    const statsHtml =
      statCardHtml('📋', '调研任务', s.tasks)
      + statCardHtml('📄', '文献总数', s.papers)
      + statCardHtml('⭐', '已收藏文献', s.collected)
      + statCardHtml('📑', '开题报告', s.proposals)
      + statCardHtml('👥', '已评审任务', s.reviews);

    el.innerHTML =
      /* ---- 1. Hero ---- */
      '<div class="hero"><div class="hero-inner">'
      + '<div class="hero-badge">📌 毕业设计 · 文献调研 × 开题报告 Agent</div>'
      + '<h1>文献调研 × 开题报告<br>一站式 <span class="grad">Agent</span></h1>'
      + '<p class="hero-quote">“我搜到的文献，到底怎么用于我的毕业设计？”</p>'
      + '<p class="hero-sub">从一句话选题，到可直接修改与评审的开题报告初稿：检索 → 阅读 → 写作 → 评审 全流程自动化。</p>'
      + '<div class="hero-chips">'
      + '<span>🔍 多源抓取</span><span>🧠 三重混合检索</span><span>📄 结构化综述</span>'
      + '<span>✍️ 开题初稿生成</span><span>👥 多智能体评审</span><span>🎤 答辩问题清单</span>'
      + '</div>'
      + '<p class="hero-meta">9 个步骤：拆解 → 检索 → 解析 → 排序 → 收藏 → 总结 → 生成 → 评审 → 答辩</p>'
      + '<button class="hero-cta" onclick="App.goto(\'tasks\')">🚀 快速开始：创建调研任务 →</button>'
      + '</div></div>'

      /* ---- 2. 统计卡片 ---- */
      + '<div class="section-head"><div class="section-tag">Stats</div>'
      + '<h2 class="section-title">当前进度统计</h2>'
      + '<p class="section-desc">' + (state.backendOnline === false ? '后端未连接，统计不可用。' : '数据来自后端接口 GET /api/stats。') + '</p></div>'
      + '<div class="stat-grid">' + statsHtml + '</div>'

      /* ---- 3. 它能为你做什么：4 张能力卡 ---- */
      + '<div class="section-head"><div class="section-tag">Capabilities</div>'
      + '<h2 class="section-title">它能为你做什么</h2>'
      + '<p class="section-desc">四个能力模块，覆盖从文献到开题初稿的完整链路。</p></div>'
      + '<div class="ov-cap-grid">'
      + CAPABILITIES.map(function (c, i) {
        return '<div class="ov-cap">'
          + '<span class="ov-cap-ico">' + c[0] + '</span>'
          + '<h3>' + esc(c[1]) + '</h3>'
          + '<p>' + esc(c[2]) + '</p>'
          + '</div>';
      }).join('')
      + '</div>'

      /* ---- 4. 步骤详解：9 步 ---- */
      + '<div class="section-head"><div class="section-tag">Pipeline</div>'
      + '<h2 class="section-title">步骤详解：每一步做什么、输出什么</h2>'
      + '<p class="section-desc">从一句话选题到可答辩的开题初稿，共 9 个步骤，每步的产物都直接服务于下一步。</p></div>'
      + '<div class="ov-steps">'
      + OVERVIEW_STEPS.map(function (st) {
        return '<div class="card ov-step">'
          + '<div class="ov-step-head">'
          + '<span class="ov-step-num">' + st.n + '</span>'
          + '<b class="ov-step-title">' + esc(st.title) + '</b>'
          + '<span class="ov-step-why">💡 ' + esc(st.why) + '</span>'
          + '</div>'
          + '<div class="ov-step-grid">'
          + '<div class="ov-step-what"><label>做什么</label><div>' + esc(st.what) + '</div></div>'
          + '<div class="ov-step-out"><label>输出结果</label><div>' + esc(st.out) + '</div></div>'
          + '</div>'
          + '</div>';
      }).join('')
      + '</div>'

      /* ---- 5. 优点（绿色系） ---- */
      + '<div class="section-head"><div class="section-tag">Pros</div>'
      + '<h2 class="section-title">优点</h2>'
      + '<p class="section-desc">为什么它能真正帮到你的毕业设计。</p></div>'
      + '<div class="ov-pros">'
      + PROS.map(function (p) {
        return '<div class="ov-pro">'
          + '<span class="ov-pro-ico">' + p[0] + '</span>'
          + '<div><b>' + esc(p[1]) + '</b><p>' + esc(p[2]) + '</p></div>'
          + '</div>';
      }).join('')
      + '</div>'

      /* ---- 6. 缺点与限制（琥珀色系） ---- */
      + '<div class="section-head"><div class="section-tag">Limits</div>'
      + '<h2 class="section-title">缺点与限制</h2>'
      + '<p class="section-desc">诚实说明：目前它做不到什么。</p></div>'
      + '<div class="ov-limits">'
      + LIMITS.map(function (l) {
        return '<div class="ov-limit">'
          + '<div class="ov-limit-head">⚠️ <b>' + esc(l[0]) + '</b></div>'
          + '<p>' + esc(l[1]) + '</p>'
          + '</div>';
      }).join('')
      + '</div>';
  }

  /* ============================================================
   * 视图 2：任务与检索
   * ============================================================ */

  async function loadTasks() {
    try {
      state.tasks = (await API.tasks()) || [];
    } catch (e) {
      state.tasks = state.tasks || [];
      if (!API.isNetworkError(e)) UI.toast('加载任务列表失败：' + e.message, 'error');
    }
    if (state.currentTaskId && !state.tasks.some(function (t) { return t.id === state.currentTaskId; })) {
      state.currentTaskId = null;
      state.currentTask = null;
    }
  }

  async function enterTasks() {
    await loadTasks();
    renderTasksView();
    if (state.currentTaskId) {
      const id = state.currentTaskId;
      try { state.currentTask = await API.task(id); } catch (e) { /* 详情失败保持列表数据 */ }
      renderTasksView();
      await Promise.all([loadPlan(id), loadPapers()]);
    }
  }

  function renderTasksView() {
    if (state.currentTaskId) renderTaskDetail();
    else renderTaskList();
  }

  /* ---------- 创建任务表单 + 任务卡片列表 ---------- */

  /**
   * 任务表单字段（创建/编辑共用）。
   * @param {string} prefix id 前缀（f=创建表单，e=编辑表单，避免 id 冲突）
   * @param {object} t 任务对象；传 null 表示创建（来源默认勾选 semantic_scholar + arxiv）
   */
  function taskFieldsHtml(prefix, t) {
    const sourceChecks = SEARCH_SOURCES.map(function (s) {
      const checked = (t && t.sources)
        ? (t.sources.indexOf(s.id) !== -1)
        : (s.id === 'semantic_scholar' || s.id === 'arxiv');
      return '<label class="check-pill"><input type="checkbox" value="' + s.id + '"' + (checked ? ' checked' : '') + ' /> ' + esc(s.label) + '</label>';
    }).join('');
    return ''
      + '<label class="span2">选题 <span class="req">*</span>'
      + '<input class="input" id="' + prefix + '-topic" placeholder="例如：基于深度学习的路面裂缝检测方法研究" value="' + esc(t ? (t.topic || '') : '') + '" /></label>'
      + '<label>专业<input class="input" id="' + prefix + '-major" placeholder="例如：计算机科学与技术" value="' + esc(t ? (t.major || '') : '') + '" /></label>'
      + '<div class="year-row"><span>年份范围</span><div class="year-inputs">'
      + '<input class="input input-year" id="' + prefix + '-year-from" type="number" min="1950" max="2035" placeholder="起始（如 2019）" value="' + (t && t.year_from ? esc(String(t.year_from)) : '') + '" />'
      + '<span class="year-sep">~</span>'
      + '<input class="input input-year" id="' + prefix + '-year-to" type="number" min="1950" max="2035" placeholder="结束（如 2025）" value="' + (t && t.year_to ? esc(String(t.year_to)) : '') + '" />'
      + '</div></div>'
      + '<div class="field-block span2"><span>检索来源（可多选；不选则使用全部可用来源）</span>'
      + '<div class="source-checks" id="' + prefix + '-sources">' + sourceChecks + '</div></div>'
      + '<label class="span2">补充要求<textarea class="input" id="' + prefix + '-req" rows="2" placeholder="例如：重点关注轻量化模型、近三年中文文献优先（可选）">' + esc(t ? (t.requirements || '') : '') + '</textarea></label>'
      + '<label class="span2">自定义文献 URL（每行一个，选填）<textarea class="input" id="' + prefix + '-urls" rows="3" placeholder="https://…（每行一个，将直接抓取这些页面）">' + esc(t && t.urls ? t.urls.join('\n') : '') + '</textarea></label>';
  }

  function taskFormHtml() {
    return '<div class="card section-card">'
      + '<div class="card-title">➕ 创建调研任务</div>'
      + '<div class="form-grid2">' + taskFieldsHtml('f', null) + '</div>'
      + '<div class="form-row" style="justify-content:flex-end;margin-top:14px">'
      + '<button class="btn btn-primary" id="btn-create-task" onclick="App.createTask()">创建任务</button>'
      + '</div>'
      + '</div>';
  }

  function taskCardHtml(t) {
    return '<div class="task-card card">'
      + '<div class="task-card-head"><div class="task-card-topic">' + esc(t.topic) + '</div>' + statusBadge(t.status) + '</div>'
      + '<div class="task-card-meta">'
      + (t.major ? '<span class="chip">🎓 ' + esc(t.major) + '</span>' : '')
      + (t.year_from ? '<span class="chip">📅 ' + esc(String(t.year_from)) + (t.year_to ? ' ~ ' + esc(String(t.year_to)) : '') + '</span>' : '')
      + '<span class="chip">📄 文献 ' + (t.paper_count || 0) + '</span>'
      + '<span class="chip">⭐ 收藏 ' + (t.collected_count || 0) + '</span>'
      + '</div>'
      + '<div class="task-card-foot">'
      + '<span class="muted small">创建于 ' + UI.fmtDate(t.created_at) + '</span>'
      + '<div class="btn-row">'
      + '<button class="btn btn-primary btn-sm" onclick="App.openTask(' + jsq(t.id) + ')">打开详情</button>'
      + '<button class="btn btn-danger-ghost btn-sm" onclick="App.deleteTask(' + jsq(t.id) + ')">删除</button>'
      + '</div>'
      + '</div>'
      + '</div>';
  }

  function renderTaskList() {
    const el = $('#view-tasks');
    if (!el) return;
    let listHtml;
    if (!state.tasks.length) {
      listHtml = '<div class="card">' + UI.emptyState('🗂️', '暂无调研任务',
        '填写上方表单创建第一个调研任务，即可开始文献检索。') + '</div>';
    } else {
      listHtml = '<div class="task-grid">' + state.tasks.map(taskCardHtml).join('') + '</div>';
    }
    el.innerHTML = taskFormHtml()
      + '<div class="section-head"><div class="section-tag">Tasks</div>'
      + '<h2 class="section-title">任务列表</h2></div>'
      + listHtml;
  }

  /** 读取表单中的「自定义 URL」textarea → 数组（每行一个，去空白行） */
  function readUrlsField(prefix) {
    const el = document.getElementById(prefix + '-urls');
    if (!el) return [];
    return el.value.split('\n').map(function (l) { return l.trim(); }).filter(Boolean);
  }

  async function createTask() {
    const topic = $('#f-topic').value.trim();
    if (!topic) { UI.toast('请填写选题（必填）', 'error'); $('#f-topic').focus(); return; }
    const yearFrom = parseInt($('#f-year-from').value, 10) || null;
    const yearTo = parseInt($('#f-year-to').value, 10) || null;
    if (yearFrom && yearTo && yearFrom > yearTo) { UI.toast('起始年份不能大于结束年份', 'error'); return; }
    const sources = Array.prototype.map.call(document.querySelectorAll('#f-sources input:checked'),
      function (i) { return i.value; });
    const body = {
      topic: topic,
      major: $('#f-major').value.trim(),
      year_from: yearFrom,
      year_to: yearTo,
      sources: sources,
      requirements: $('#f-req').value.trim(),
      urls: readUrlsField('f')
    };
    const btn = $('#btn-create-task');
    btn.disabled = true;
    try {
      const t = await API.createTask(body);
      UI.toast('任务创建成功', 'success');
      // 重置表单
      $('#f-topic').value = ''; $('#f-major').value = '';
      $('#f-year-from').value = ''; $('#f-year-to').value = ''; $('#f-req').value = ''; $('#f-urls').value = '';
      document.querySelectorAll('#f-sources input').forEach(function (i) {
        i.checked = (i.value === 'semantic_scholar' || i.value === 'arxiv');
      });
      await loadTasks();
      await openTask(t.id);
    } catch (e) {
      UI.toast('创建失败：' + e.message, 'error');
    } finally {
      btn.disabled = false;
    }
  }

  async function deleteTask(id) {
    const t = state.tasks.find(function (x) { return x.id === id; });
    if (!UI.confirm('确定删除任务「' + (t ? t.topic : id) + '」？将级联删除其全部文献数据，此操作不可恢复。')) return;
    try {
      await API.deleteTask(id);
      UI.toast('任务已删除', 'success');
      if (state.currentTaskId === id) { state.currentTaskId = null; state.currentTask = null; }
      await loadTasks();
      renderTasksView();
      loadStats();
    } catch (e) {
      UI.toast('删除失败：' + e.message, 'error');
    }
  }

  async function openTask(id) {
    state.currentTaskId = id;
    resetPaperFiltersState();
    try {
      state.currentTask = await API.task(id);
    } catch (e) {
      state.currentTask = state.tasks.find(function (t) { return t.id === id; }) || null;
      if (!API.isNetworkError(e)) UI.toast('加载任务详情失败：' + e.message, 'error');
    }
    renderTasksView();
    await Promise.all([loadPlan(id), loadPapers()]);
  }

  function closeTask() {
    state.currentTaskId = null;
    state.currentTask = null;
    renderTasksView();
  }

  /* ---------- 任务详情面板 ---------- */

  function renderTaskDetail() {
    const t = state.currentTask;
    const el = $('#view-tasks');
    if (!el || !t) return;
    el.innerHTML =
      '<div class="detail-head card">'
      + '<button class="btn btn-ghost btn-sm" onclick="App.closeTask()">← 返回任务列表</button>'
      + '<h2>' + esc(t.topic) + '</h2>'
      + '<div class="detail-meta">'
      + statusBadge(t.status)
      + (t.major ? '<span class="chip">🎓 ' + esc(t.major) + '</span>' : '')
      + (t.year_from ? '<span class="chip">📅 ' + esc(String(t.year_from)) + (t.year_to ? ' ~ ' + esc(String(t.year_to)) : '') + '</span>' : '')
      + (t.sources && t.sources.length ? t.sources.map(function (s) {
        const src = SOURCES.find(function (x) { return x.id === s; });
        return '<span class="chip">' + esc(src ? src.label : s) + '</span>';
      }).join('') : '<span class="chip">全部可用来源</span>')
      + '<span class="chip">📄 文献 ' + (t.paper_count || 0) + '</span>'
      + '<span class="chip">⭐ 收藏 ' + (t.collected_count || 0) + '</span>'
      + '</div>'
      + '</div>'
      + renderTaskEditPanel(t)
      + renderSearchPanel(t)
      + '<div id="planPanel"><div class="card section-card"><div class="loading">正在加载检索计划…</div></div></div>'
      + '<div id="papersPanel"></div>';
    renderPapersPanel();
  }

  /** 任务详情：「编辑检索条件」可折叠区（复用创建表单字段，预填当前值） */
  function renderTaskEditPanel(t) {
    return '<div class="card section-card">'
      + '<div class="card-title">✏️ 任务参数'
      + '<button class="btn btn-ghost btn-sm" style="margin-left:auto" onclick="App.toggleTaskEdit()">编辑检索条件</button>'
      + '</div>'
      + '<div id="taskEditBox" class="hidden">'
      + '<div class="form-grid2">' + taskFieldsHtml('e', t) + '</div>'
      + '<div class="form-row" style="justify-content:flex-end;margin-top:14px">'
      + '<button class="btn btn-ghost" id="btn-save-task-edit" onclick="App.saveTaskEdit(false)">💾 保存</button>'
      + '<button class="btn btn-primary" id="btn-save-task-research" onclick="App.saveTaskEdit(true)">💾 保存并重新检索</button>'
      + '</div>'
      + '<p class="muted small" style="margin-top:8px">「保存并重新检索」会先保存条件，再启动一轮新检索（沿用下方「启动检索」区的反馈输入内容）。</p>'
      + '</div>'
      + '</div>';
  }

  /** 展开/收起任务编辑区 */
  function toggleTaskEdit() {
    const box = $('#taskEditBox');
    if (box) box.classList.toggle('hidden');
  }

  /**
   * 保存任务编辑：PUT /api/tasks/{id}（只传当前字段）。
   * @param {boolean} reSearch true=保存后立刻启动新检索（走 runJob SSE）
   */
  async function saveTaskEdit(reSearch) {
    const t = state.currentTask;
    if (!t) return;
    const topic = $('#e-topic').value.trim();
    if (!topic) { UI.toast('请填写选题（必填）', 'error'); $('#e-topic').focus(); return; }
    const yearFrom = parseInt($('#e-year-from').value, 10) || null;
    const yearTo = parseInt($('#e-year-to').value, 10) || null;
    if (yearFrom && yearTo && yearFrom > yearTo) { UI.toast('起始年份不能大于结束年份', 'error'); return; }
    const sources = Array.prototype.map.call(document.querySelectorAll('#e-sources input:checked'),
      function (i) { return i.value; });
    const body = {
      topic: topic,
      major: $('#e-major').value.trim(),
      year_from: yearFrom,
      year_to: yearTo,
      sources: sources,
      requirements: $('#e-req').value.trim(),
      urls: readUrlsField('e')
    };
    // 保存前捕获检索反馈（重渲染会清空输入框）
    const feedback = $('#searchFeedback') ? $('#searchFeedback').value.trim() : '';
    const btnSave = $('#btn-save-task-edit');
    const btnResearch = $('#btn-save-task-research');
    if (btnSave) btnSave.disabled = true;
    if (btnResearch) btnResearch.disabled = true;
    try {
      await API.updateTask(t.id, body);
      UI.toast('任务检索条件已保存', 'success');
      // 刷新任务详情与列表（编辑区收起、字段预填新值）
      try { state.currentTask = await API.task(t.id); } catch (e) { /* 忽略 */ }
      try { state.tasks = (await API.tasks()) || state.tasks; } catch (e) { /* 忽略 */ }
      renderTasksView();
      await Promise.all([loadPlan(t.id), loadPapers()]);
      if (reSearch) await startSearch(feedback);
    } catch (e) {
      UI.toast('保存失败：' + e.message, 'error');
    } finally {
      const b1 = $('#btn-save-task-edit');
      const b2 = $('#btn-save-task-research');
      if (b1) b1.disabled = false;
      if (b2) b2.disabled = false;
    }
  }

  function renderSearchPanel(t) {
    const running = t.status === 'searching';
    let inner;
    if (!hasLLM()) {
      inner = UI.llmGuide('检索需要调用大模型进行选题拆解与相关度排序，请先配置服务商。');
    } else {
      inner = '<div class="form-row">'
        + '<input class="input" style="flex:1;min-width:240px" id="searchFeedback" placeholder="补充检索反馈（可选）：例如「重点关注轻量化模型、近三年综述」" />'
        + '<button class="btn btn-primary" id="btn-search" onclick="App.startSearch()"' + (running ? ' disabled' : '') + '>'
        + (running ? '检索进行中…' : '🔍 启动检索') + '</button>'
        + '</div>';
    }
    return '<div class="card section-card">'
      + '<div class="card-title">🔍 启动检索</div>'
      + '<p class="muted small" style="margin-bottom:12px">Agent 将把选题拆解为若干子问题，多源并行抓取文献，统一解析后进行混合检索排序。</p>'
      + inner
      + (t.requirements ? '<div class="req-note">📝 检索要求：' + esc(t.requirements) + '</div>' : '')
      + '</div>';
  }

  /**
   * 启动检索 Job。
   * @param {string} feedbackOverride 可选：外部传入的检索反馈（如「保存并重新检索」流程保留的输入）
   */
  async function startSearch(feedbackOverride) {
    const t = state.currentTask;
    if (!t) return;
    if (!hasLLM()) { UI.toast('请先到设置页配置大模型 API', 'error'); goto('settings'); return; }
    const feedback = (feedbackOverride !== undefined && feedbackOverride !== null)
      ? feedbackOverride
      : ($('#searchFeedback') ? $('#searchFeedback').value.trim() : '');
    try {
      const r = await API.startSearch(t.id, feedback);
      const jobId = extractJobId(r);
      if (!jobId) { UI.toast('检索任务已启动（未返回 job_id，请稍后刷新查看）', 'info'); await refreshTaskAfterJob(t.id); return; }
      state.currentTask.status = 'searching';
      renderTasksView();
      await Promise.all([loadPlan(t.id), loadPapers()]);
      const jobResult = await runJob(jobId, '文献检索：' + t.topic.slice(0, 30), async function (result) {
        if (!result) return;
        UI.toast('检索完成：共获取 ' + (result.papers || 0) + ' 篇文献', 'success');
        if (result.sources_failed && result.sources_failed.length) {
          showListModal('部分来源检索失败', result.sources_failed.map(String), '以下来源未能成功检索，其余来源正常：');
        }
        await refreshTaskAfterJob(t.id);
      });
      if (!jobResult) await refreshTaskAfterJob(t.id); // 任务失败也要同步状态（如 status=failed）
    } catch (e) {
      UI.toast('启动检索失败：' + e.message, 'error');
    }
  }

  /** 检索/收藏等任务完成后刷新任务详情与统计数据 */
  async function refreshTaskAfterJob(taskId) {
    try { state.currentTask = await API.task(taskId); } catch (e) { /* 忽略 */ }
    try { state.tasks = (await API.tasks()) || state.tasks; } catch (e) { /* 忽略 */ }
    loadStats();
    if (state.view === 'tasks' && state.currentTaskId === taskId) {
      renderTasksView();
      await Promise.all([loadPlan(taskId), loadPapers()]);
    }
  }

  /* ---------- 选题拆解计划 ---------- */

  async function loadPlan(taskId) {
    const seq = ++planSeq;
    try {
      state.plan = await API.plan(taskId);
    } catch (e) {
      state.plan = null; // 未生成时 404，静默
    }
    if (seq !== planSeq) return;
    if (state.view === 'tasks' && state.currentTaskId === taskId) renderPlanPanel();
  }

  function renderPlanPanel() {
    const holder = $('#planPanel');
    if (!holder) return;
    const plan = state.plan;
    if (!plan || !plan.sub_questions || !plan.sub_questions.length) {
      holder.innerHTML = '<div class="card section-card"><div class="card-title">🧭 选题拆解计划</div>'
        + UI.emptyState('🧭', '尚未生成检索计划', '启动检索后，Agent 会把选题拆解为若干子问题，并生成中英文查询词。') + '</div>';
      return;
    }
    holder.innerHTML = '<div class="card section-card">'
      + '<div class="card-title">🧭 选题拆解计划（' + plan.sub_questions.length + ' 个子问题）</div>'
      + '<div class="sq-grid">'
      + plan.sub_questions.map(function (sq, i) {
        return '<div class="sq-card">'
          + '<div class="sq-head"><span class="sq-num">' + (i + 1) + '</span><b>' + esc(sq.question) + '</b></div>'
          + (sq.rationale ? '<div class="sq-why">💡 ' + esc(sq.rationale) + '</div>' : '')
          + '<div class="sq-queries">' + (sq.queries || []).map(function (q) {
            return '<span class="query-chip"><span class="lang-tag ' + (q.lang === 'zh' ? 'zh' : 'en') + '">'
              + (q.lang === 'zh' ? '中' : '英') + '</span>' + esc(q.text) + '</span>';
          }).join('') + '</div>'
          + '</div>';
      }).join('')
      + '</div></div>';
  }

  /* ---------- 文献表格 ---------- */

  function resetPaperFiltersState() {
    state.paperFilters = { q: '', year_from: '', year_to: '', source: '', collected: false, sort: 'score', order: 'desc', limit: 20, offset: 0 };
    state.selectedPaperIds.clear();
  }

  function renderPapersPanel() {
    const holder = $('#papersPanel');
    if (!holder) return;
    const f = state.paperFilters;
    const sourceOptions = SOURCES.filter(function (s) { return s.id !== 'import'; })
      .map(function (s) {
        return '<option value="' + s.id + '"' + (f.source === s.id ? ' selected' : '') + '>' + esc(s.label) + '</option>';
      }).join('');
    holder.innerHTML = '<div class="card section-card">'
      + '<div class="card-title">📄 文献列表 <span class="muted small" id="paperTotal">共 ' + state.papers.total + ' 篇</span></div>'
      + '<div class="filters">'
      + '<input class="input" id="pq" placeholder="关键词（标题/摘要）" value="' + esc(f.q) + '" />'
      + '<input class="input input-year" id="pyf" type="number" placeholder="起始年份" value="' + (f.year_from || '') + '" />'
      + '<input class="input input-year" id="pyt" type="number" placeholder="结束年份" value="' + (f.year_to || '') + '" />'
      + '<select class="input" id="psrc" onchange="App.applyPaperFilters()"><option value="">全部来源</option>' + sourceOptions + '</select>'
      + '<label class="check-pill"><input type="checkbox" id="pcol"' + (f.collected ? ' checked' : '') + ' onchange="App.applyPaperFilters()" /> 只看已收藏</label>'
      + '<select class="input" id="psort" onchange="App.applyPaperFilters()">'
      + '<option value="score"' + (f.sort === 'score' ? ' selected' : '') + '>按相关度</option>'
      + '<option value="year"' + (f.sort === 'year' ? ' selected' : '') + '>按年份</option>'
      + '<option value="citations"' + (f.sort === 'citations' ? ' selected' : '') + '>按被引</option>'
      + '<option value="title"' + (f.sort === 'title' ? ' selected' : '') + '>按标题</option>'
      + '</select>'
      + '<button class="btn btn-ghost btn-sm" id="porder" onclick="App.toggleOrder()">' + (f.order === 'desc' ? '↓ 降序' : '↑ 升序') + '</button>'
      + '<button class="btn btn-primary btn-sm" onclick="App.applyPaperFilters()">筛选</button>'
      + '<button class="btn btn-ghost btn-sm" onclick="App.resetPaperFilters()">重置</button>'
      + '</div>'
      + '<div class="table-wrap" id="paperTableWrap"><div class="loading">加载文献中…</div></div>'
      + '<div class="table-foot">'
      + '<div class="batch-bar">'
      + '<label class="check-pill"><input type="checkbox" id="selAll" onchange="App.toggleSelectAll(this.checked)" /> 全选本页</label>'
      + '<span class="muted small">已选 <b id="selCount">' + state.selectedPaperIds.size + '</b> 篇</span>'
      + '<button class="btn btn-primary btn-sm" id="btnBatchCollect" onclick="App.batchCollect()"'
      + (state.selectedPaperIds.size ? '' : ' disabled') + '>⭐ 批量收藏选中（含下载）</button>'
      + '</div>'
      + '<div class="pagination" id="paginationHolder">' + paginationHtml() + '</div>'
      + '</div>'
      + '</div>';
    bindPaperFilterKeys();
  }

  function bindPaperFilterKeys() {
    ['pq', 'pyf', 'pyt'].forEach(function (id) {
      const el = document.getElementById(id);
      if (el) el.addEventListener('keydown', function (e) { if (e.key === 'Enter') App.applyPaperFilters(); });
    });
  }

  function paginationHtml() {
    const f = state.paperFilters;
    const total = state.papers.total || 0;
    const pages = Math.max(1, Math.ceil(total / f.limit));
    const cur = Math.floor(f.offset / f.limit) + 1;
    return '<select class="input input-sm" onchange="App.changePageSize(this.value)">'
      + [10, 20, 50].map(function (n) {
        return '<option value="' + n + '"' + (f.limit === n ? ' selected' : '') + '>每页 ' + n + ' 条</option>';
      }).join('')
      + '</select>'
      + '<button class="btn btn-ghost btn-sm"' + (f.offset <= 0 ? ' disabled' : '') + ' onclick="App.gotoPage(' + (cur - 1) + ')">‹ 上一页</button>'
      + '<span class="muted small">第 ' + cur + ' / ' + pages + ' 页</span>'
      + '<button class="btn btn-ghost btn-sm"' + (f.offset + f.limit >= total ? ' disabled' : '') + ' onclick="App.gotoPage(' + (cur + 1) + ')">下一页 ›</button>';
  }

  async function loadPapers() {
    const tid = state.currentTaskId;
    if (!tid) return;
    const seq = ++papersSeq;
    const f = state.paperFilters;
    const query = {
      q: f.q,
      year_from: f.year_from || undefined,
      year_to: f.year_to || undefined,
      source: f.source || undefined,
      collected: f.collected ? true : undefined,
      sort: f.sort,
      order: f.order,
      limit: f.limit,
      offset: f.offset
    };
    try {
      const r = await API.papers(tid, query);
      if (seq !== papersSeq) return; // 已被更新的请求取代
      state.papers = { total: (r && r.total) || 0, items: (r && r.items) || [] };
    } catch (e) {
      if (seq !== papersSeq) return;
      state.papers = { total: 0, items: [] };
      if (!API.isNetworkError(e)) UI.toast('加载文献失败：' + e.message, 'error');
    }
    renderPaperTableOnly();
  }

  function paperRowHtml(p) {
    const selected = state.selectedPaperIds.has(p.id);
    return '<tr class="' + (p.collected ? 'row-collected' : '') + '">'
      + '<td class="td-check"><input type="checkbox" title="选择（用于批量操作）"' + (selected ? ' checked' : '')
      + ' onchange="App.togglePaperSelect(' + jsq(p.id) + ', this.checked)" /></td>'
      + '<td class="td-check"><input type="checkbox" title="' + (p.collected ? '取消收藏' : '收藏并下载源文件') + '"'
      + (p.collected ? ' checked' : '') + ' onchange="App.toggleCollect(' + jsq(p.id) + ', this.checked)" /></td>'
      + '<td class="td-title">'
      + '<button class="paper-link" onclick="App.openPaperDrawer(' + jsq(p.id) + ')">' + esc(p.title) + '</button>'
      + (p.title_zh ? '<div class="title-zh">' + esc(p.title_zh) + '</div>' : '')
      + (p.authors && p.authors.length ? '<div class="paper-authors">' + esc(p.authors.slice(0, 3).join(', ')) + (p.authors.length > 3 ? ' 等' : '') + '</div>' : '')
      + '</td>'
      + '<td><div class="score-cell"><div class="score-bar"><div class="score-fill" style="width:' + Math.round((p.score || 0) * 100) + '%"></div></div>'
      + '<span class="score-num">' + (p.score == null ? '—' : Number(p.score).toFixed(2)) + '</span></div></td>'
      + '<td>' + (p.year || '—') + '</td>'
      + '<td class="td-venue">' + esc(p.venue || '—') + '</td>'
      + '<td>' + sourceBadge(p.source) + '</td>'
      + '<td>' + (p.citations == null ? '—' : p.citations) + '</td>'
      + '<td>' + downloadOpHtml(p) + '</td>'
      + '</tr>';
  }

  function paperTableHtml() {
    return '<table class="paper-table"><thead><tr>'
      + '<th class="td-check">选择</th><th class="td-check">收藏</th><th>标题</th><th>相关度</th><th>年份</th><th>出处</th><th>来源</th><th>被引</th><th>操作</th>'
      + '</tr></thead><tbody>'
      + state.papers.items.map(paperRowHtml).join('')
      + '</tbody></table>';
  }

  function renderPaperTableOnly() {
    const wrap = $('#paperTableWrap');
    if (!wrap) return;
    if (state.papers.items.length) {
      wrap.innerHTML = paperTableHtml();
    } else {
      const isFiltered = state.paperFilters.q || state.paperFilters.source || state.paperFilters.collected
        || state.paperFilters.year_from || state.paperFilters.year_to;
      wrap.innerHTML = UI.emptyState('📄', isFiltered ? '没有符合条件的文献' : '暂无文献',
        isFiltered ? '试试放宽筛选条件，或点击「重置」。' : '启动检索后，这里会展示检索到的文献列表。');
    }
    const totalEl = $('#paperTotal');
    if (totalEl) totalEl.textContent = '共 ' + state.papers.total + ' 篇';
    const ph = $('#paginationHolder');
    if (ph) ph.innerHTML = paginationHtml();
    const sc = $('#selCount');
    if (sc) sc.textContent = state.selectedPaperIds.size;
    const btn = $('#btnBatchCollect');
    if (btn) btn.disabled = !state.selectedPaperIds.size;
    // 清理已不存在的勾选
    const ids = new Set(state.papers.items.map(function (p) { return p.id; }));
    state.selectedPaperIds.forEach(function (id) { if (!ids.has(id)) state.selectedPaperIds.delete(id); });
  }

  function applyPaperFilters() {
    const f = state.paperFilters;
    f.q = $('#pq') ? $('#pq').value.trim() : '';
    f.year_from = ($('#pyf') && $('#pyf').value) ? parseInt($('#pyf').value, 10) : '';
    f.year_to = ($('#pyt') && $('#pyt').value) ? parseInt($('#pyt').value, 10) : '';
    f.source = $('#psrc') ? $('#psrc').value : '';
    f.collected = $('#pcol') ? $('#pcol').checked : false;
    f.sort = $('#psort') ? $('#psort').value : 'score';
    f.offset = 0;
    state.selectedPaperIds.clear();
    loadPapers();
  }

  function resetPaperFilters() {
    resetPaperFiltersState();
    renderPapersPanel();
    loadPapers();
  }

  function toggleOrder() {
    const f = state.paperFilters;
    f.order = f.order === 'desc' ? 'asc' : 'desc';
    const b = $('#porder');
    if (b) b.textContent = f.order === 'desc' ? '↓ 降序' : '↑ 升序';
    loadPapers();
  }

  function gotoPage(p) {
    const f = state.paperFilters;
    f.offset = Math.max(0, (p - 1) * f.limit);
    loadPapers();
  }

  function changePageSize(n) {
    const f = state.paperFilters;
    f.limit = parseInt(n, 10) || 20;
    f.offset = 0;
    loadPapers();
  }

  function toggleSelectAll(checked) {
    if (checked) state.papers.items.forEach(function (p) { state.selectedPaperIds.add(p.id); });
    else state.papers.items.forEach(function (p) { state.selectedPaperIds.delete(p.id); });
    renderPaperTableOnly();
  }

  function togglePaperSelect(id, checked) {
    if (checked) state.selectedPaperIds.add(id);
    else state.selectedPaperIds.delete(id);
    renderPaperTableOnly();
  }

  /** 单篇收藏/取消收藏（收藏为长任务：返回 Job，走 SSE） */
  async function toggleCollect(paperId, checked) {
    const paper = state.papers.items.find(function (p) { return p.id === paperId; });
    if (!paper) return;
    if (checked) {
      try {
        const r = await API.collect(paperId, true);
        const jobId = extractJobId(r);
        if (jobId) {
          // 乐观更新：任务运行期间标记「下载中」，任务完成后刷新真实状态
          paper.collected = true;
          paper.download_status = 'downloading';
          paper.download_note = '';
          if (state.drawerPaper && state.drawerPaper.id === paperId) {
            state.drawerPaper.collected = true;
            state.drawerPaper.download_status = 'downloading';
            state.drawerPaper.download_note = '';
            renderPaperDrawer(state.drawerPaper);
          }
          renderPaperTableOnly();
          const jobResult = await runJob(jobId, '收藏文献：' + paper.title.slice(0, 30), async function (result) {
            const failed = (result && result.failed) || [];
            if (failed.length) {
              UI.toast('已收藏，但源文件下载失败 ' + failed.length + ' 篇', 'info');
              showListModal('源文件下载失败', failed.map(function (f) {
                return (f.title || '') + (f.reason ? '（' + f.reason + '）' : '');
              }), '以下文献已收藏，但未能下载源文件（可能无开放获取 PDF）：');
            } else {
              UI.toast('已收藏「' + paper.title.slice(0, 30) + '」', 'success');
            }
            // 收藏完成后刷新详情：后端已自动下载 PDF 并解析关键片段/图表
            await refreshDrawerPaper(paperId);
            await refreshTaskAfterJob(state.currentTaskId);
          });
          if (!jobResult) await loadPapers(); // 失败恢复勾选状态
        } else {
          UI.toast('已收藏', 'success');
          await refreshDrawerPaper(paperId);
          await refreshTaskAfterJob(state.currentTaskId);
        }
      } catch (e) {
        UI.toast('收藏失败：' + e.message, 'error');
        await loadPapers();
      }
    } else {
      if (!UI.confirm('取消收藏将同时删除本地文件与图片，确定？')) {
        renderPaperTableOnly(); // 取消操作：恢复勾选状态
        return;
      }
      try {
        await API.uncollect(paperId);
        UI.toast('已取消收藏，本地文件与图片已删除', 'info');
        await refreshDrawerPaper(paperId);
        await refreshTaskAfterJob(state.currentTaskId);
      } catch (e) {
        UI.toast('取消收藏失败：' + e.message, 'error');
        renderPaperTableOnly();
      }
    }
  }

  /** 批量收藏选中（POST /api/tasks/{id}/papers/collect，download:true） */
  async function batchCollect() {
    const ids = Array.from(state.selectedPaperIds);
    if (!ids.length) { UI.toast('请先勾选要收藏的文献', 'error'); return; }
    const t = state.currentTask;
    if (!t) return;
    try {
      const r = await API.batchCollect(t.id, ids, true);
      const jobId = extractJobId(r);
      if (!jobId) { UI.toast('批量收藏请求已提交', 'success'); await refreshTaskAfterJob(t.id); return; }
      // 乐观更新：任务运行期间标记「下载中」，任务完成后刷新真实状态
      state.papers.items.forEach(function (it) {
        if (ids.indexOf(it.id) !== -1) {
          it.collected = true;
          it.download_status = 'downloading';
          it.download_note = '';
        }
      });
      if (state.drawerPaper && ids.indexOf(state.drawerPaper.id) !== -1) {
        state.drawerPaper.collected = true;
        state.drawerPaper.download_status = 'downloading';
        state.drawerPaper.download_note = '';
        renderPaperDrawer(state.drawerPaper);
      }
      renderPaperTableOnly();
      const jobResult = await runJob(jobId, '批量收藏（' + ids.length + ' 篇）', async function (result) {
        if (!result) return;
        const failed = result.failed || [];
        UI.toast('批量收藏完成：成功 ' + (result.collected || 0) + ' 篇，下载源文件 ' + (result.downloaded || 0) + ' 篇'
          + (failed.length ? '，失败 ' + failed.length + ' 篇' : ''), failed.length ? 'info' : 'success');
        if (failed.length) {
          showListModal('部分文献下载失败', failed.map(function (f) {
            return (f.title || '') + (f.reason ? '（' + f.reason + '）' : '');
          }), '以下文献未能下载源文件（可能无开放获取 PDF）：');
        }
        state.selectedPaperIds.clear();
        // 若抽屉正展示其中某篇，刷新其详情（含新解析出的片段/图表与下载状态）
        if (state.drawerPaper && ids.indexOf(state.drawerPaper.id) !== -1) {
          await refreshDrawerPaper(state.drawerPaper.id);
        }
        await refreshTaskAfterJob(t.id);
      });
      if (!jobResult) await refreshTaskAfterJob(t.id); // 失败恢复真实状态
    } catch (e) {
      UI.toast('批量收藏失败：' + e.message, 'error');
    }
  }

  /* ---------- 文献详情抽屉 ---------- */

  async function openPaperDrawer(paperId) {
    UI.openDrawer('文献详情', '<div class="loading">加载中…</div>');
    try {
      const p = await API.paper(paperId);
      state.drawerPaper = p;
      renderPaperDrawer(p);
    } catch (e) {
      UI.toast('加载文献详情失败：' + e.message, 'error');
      UI.closeDrawer();
    }
  }

  /** 关键片段：为空时返回空串（整个区块不显示），非空时渲染列表 */
  function snippetsHtml(p) {
    const list = p.snippets || [];
    if (!list.length) return '';
    return list.map(function (s) {
      return '<div class="snippet-item"><div class="snip-text">' + esc(s.text) + '</div>'
        + '<div class="snip-meta">'
        + (s.section ? UI.badge('📑 ' + s.section, 'badge-plain') : '')
        + (s.page != null ? UI.badge('第 ' + s.page + ' 页', 'badge-plain') : '')
        + '</div></div>';
    }).join('');
  }

  /** 图表：为空时返回空串（整个区块不显示），非空时渲染全部真实图表图片 */
  function figuresHtml(p) {
    const list = p.figures || [];
    if (!list.length) return '';
    return '<div class="fig-grid">' + list.map(function (f, i) {
      return '<div class="fig-card">'
        + (f.image
          ? '<img src="' + esc(fileSrc(f.image)) + '" alt="' + esc(f.caption || ('图表 ' + (i + 1))) + '" loading="lazy" onerror="App.imgFail(this)" />'
          : '<div class="img-fail">无图片文件</div>')
        + (f.caption ? '<div class="fig-cap">' + esc(f.caption) + '</div>' : '')
        + (f.description ? '<div class="fig-desc">' + esc(f.description) + '</div>' : '')
        + (f.page != null ? '<div class="fig-desc">📄 第 ' + esc(String(f.page)) + ' 页</div>' : '')
        + '</div>';
    }).join('') + '</div>';
  }

  function summaryCardHtml(s) {
    if (!s) return '<p class="muted">尚未生成总结。</p>';
    return '<div class="summary-card">'
      + '<div class="sum-field"><label>研究问题</label><div>' + esc(s.research_question || '—') + '</div></div>'
      + '<div class="sum-field"><label>方法</label><div>' + esc(s.method || '—') + '</div></div>'
      + '<div class="sum-field"><label>主要贡献</label><ul>' + (s.contributions || []).map(function (c) { return '<li>' + esc(c) + '</li>'; }).join('') + '</ul></div>'
      + '<div class="sum-field"><label>数据集</label><div>' + esc(s.dataset || '—') + '</div></div>'
      + '<div class="sum-field"><label>评价指标</label><div>' + esc(s.metrics || '—') + '</div></div>'
      + '<div class="sum-field"><label>局限性</label><div>' + esc(s.limitations || '—') + '</div></div>'
      + '<div class="sum-field sum-key"><label>🎯 与我的选题的关联（重点）</label><div>' + esc(s.relevance_to_topic || '—') + '</div></div>'
      + '<div class="sum-field"><label>要点</label><ul>' + (s.key_points || []).map(function (c) { return '<li>' + esc(c) + '</li>'; }).join('') + '</ul></div>'
      + '</div>';
  }

  function translationCardHtml(p, t) {
    if (!t) return '<p class="muted">尚未翻译。</p>';
    let gloss = '';
    if (t.glossary && Object.keys(t.glossary).length) {
      gloss = '<div class="sum-field"><label>术语表</label><table class="gloss-table"><thead><tr><th>原文术语</th><th>译文</th></tr></thead><tbody>'
        + Object.keys(t.glossary).map(function (k) { return '<tr><td>' + esc(k) + '</td><td>' + esc(t.glossary[k]) + '</td></tr>'; }).join('')
        + '</tbody></table></div>';
    }
    // 关键片段译文：与原文关键片段一一对应（snippets_zh 存在且非空时显示）
    let snipsZh = '';
    if (t.snippets_zh && t.snippets_zh.length) {
      const origin = (p && p.snippets) || [];
      snipsZh = '<div class="sum-field"><label>关键片段译文</label>'
        + t.snippets_zh.map(function (txt, i) {
          const o = origin[i];
          return '<div class="snippet-item"><div class="snip-text">' + esc(txt) + '</div>'
            + ((o && (o.section || o.page != null))
              ? '<div class="snip-meta">'
              + (o.section ? UI.badge('📑 ' + o.section, 'badge-plain') : '')
              + (o.page != null ? UI.badge('第 ' + o.page + ' 页', 'badge-plain') : '')
              + '</div>'
              : '')
            + '</div>';
        }).join('')
        + '</div>';
    }
    return '<div class="trans-card">'
      + '<div class="sum-field"><label>中文标题</label><div>' + esc(t.title_zh || '—') + '</div></div>'
      + '<div class="sum-field"><label>中文摘要</label><div class="pre-wrap pre-scroll">' + esc(t.abstract_zh || '—') + '</div></div>'
      + snipsZh
      + gloss
      + (t.quality_note ? '<div class="q-note">📌 质量说明：' + esc(t.quality_note) + '</div>' : '')
      + '</div>';
  }

  function renderPaperDrawer(p) {
    const d = $('#drawerBody');
    if (!d) return;
    const scorePct = Math.round((p.score || 0) * 100);
    d.innerHTML =
      (p.title_zh ? '<div class="drawer-title-zh">' + esc(p.title_zh) + '</div>' : '')
      + '<h2 class="drawer-paper-title">' + esc(p.title) + '</h2>'
      + '<div class="drawer-meta">'
      + (p.authors && p.authors.length ? UI.badge('👤 ' + p.authors.join(', '), 'badge-plain') : '')
      + (p.year ? UI.badge('📅 ' + p.year, 'badge-plain') : '')
      + (p.venue ? UI.badge('🏛 ' + p.venue, 'badge-plain') : '')
      + sourceBadge(p.source)
      + (p.citations != null ? UI.badge('📈 被引 ' + p.citations, 'badge-plain') : '')
      + (p.is_open_access ? UI.badge('开放获取', 'badge-green') : '')
      + (p.collected ? UI.badge('已收藏', 'badge-amber') : '')
      + '</div>'
      + '<div class="drawer-score">相关度 <b>' + (p.score == null ? '—' : Number(p.score).toFixed(2)) + '</b>'
      + '<div class="score-bar"><div class="score-fill" style="width:' + scorePct + '%"></div></div></div>'
      + '<div class="drawer-actions">'
      + '<button class="btn btn-sm ' + (p.collected ? 'btn-ghost' : 'btn-primary') + '" onclick="App.toggleCollectFromDrawer()">'
      + (p.collected ? '取消收藏' : '⭐ 收藏并下载') + '</button>'
      + (p.url ? '<a class="btn btn-ghost btn-sm" href="' + esc(p.url) + '" target="_blank" rel="noopener noreferrer">打开原文 ↗</a>' : '')
      + (p.pdf_url ? '<a class="btn btn-ghost btn-sm" href="' + esc(p.pdf_url) + '" target="_blank" rel="noopener noreferrer">PDF ↗</a>' : '')
      + (p.file_path ? '<button class="btn btn-ghost btn-sm" onclick="App.previewFileByPath(' + jsq(p.file_path) + ')">📂 打开本地文件</button>' : '')
      + '</div>'
      + drawerDownloadStatusHtml(p)
      + (p.keywords && p.keywords.length
        ? '<div class="drawer-section"><h4>🔑 关键词</h4><div class="chip-row">' + p.keywords.map(function (k) { return '<span class="chip">' + esc(k) + '</span>'; }).join('') + '</div></div>'
        : '')
      + '<div class="drawer-section"><h4>📝 摘要</h4>'
      + (p.abstract ? '<p class="pre-wrap">' + esc(p.abstract) + '</p>' : '<p class="muted">无摘要</p>')
      + (p.abstract_zh ? '<h4 style="margin-top:12px">🀄 中文摘要</h4><div class="pre-wrap pre-scroll">' + esc(p.abstract_zh) + '</div>' : '')
      + '</div>'
      // 关键片段 / 图表：为空时整个区块不显示
      + (snippetsHtml(p) ? '<div class="drawer-section"><h4>🔎 关键片段（来自全文解析）</h4>' + snippetsHtml(p) + '</div>' : '')
      + (figuresHtml(p) ? '<div class="drawer-section"><h4>🖼 图表（真实来自该文献解析）</h4>' + figuresHtml(p) + '</div>' : '')
      // 解析全文：位于图表区下方、单篇总结上方
      + '<div class="drawer-section"><h4>📥 全文解析</h4>'
      + '<p class="muted small" style="margin-bottom:8px">自动下载 PDF / 从来源页提取全文，解析关键片段与真实图表。</p>'
      + '<button class="btn btn-sm btn-primary" id="btnParseFulltext" onclick="App.parseFulltext()">📥 解析全文 / 提取图表</button>'
      + '</div>'
      + '<div class="drawer-section" id="drawerSummary"><h4>🧠 单篇总结</h4>' + summaryCardHtml(p.summary)
      + '<div style="margin-top:10px"><button class="btn btn-sm ' + (p.summary ? 'btn-ghost' : 'btn-primary') + '" onclick="App.summarizePaper()">'
      + (p.summary ? '重新生成总结' : '生成总结') + '</button></div></div>'
      + '<div class="drawer-section" id="drawerTranslation"><h4>🌐 翻译（标题 + 摘要 + 片段）</h4>' + translationCardHtml(p, p.translation)
      + '<div style="margin-top:10px"><button class="btn btn-sm ' + (p.translation ? 'btn-ghost' : 'btn-primary') + '" onclick="App.translatePaper()">'
      + (p.translation ? '重新翻译' : '翻译') + '</button></div></div>';
  }

  function imgFail(img) {
    img.outerHTML = '<div class="img-fail">⚠️ 图片加载失败</div>';
  }

  /** 重新拉取某篇文献详情；若详情抽屉正展示该文献则刷新抽屉 */
  async function refreshDrawerPaper(paperId) {
    try {
      const p = await API.paper(paperId);
      if (state.drawerPaper && state.drawerPaper.id === paperId) {
        state.drawerPaper = p;
        renderPaperDrawer(p);
      }
      return p;
    } catch (e) {
      return null;
    }
  }

  /** 解析全文 / 提取图表（POST /api/papers/{id}/parse_fulltext，长任务走 SSE） */
  async function parseFulltext() {
    const p = state.drawerPaper;
    if (!p) return;
    const btn = $('#btnParseFulltext');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ 解析中…'; }
    try {
      const r = await API.parseFulltext(p.id);
      const jobId = extractJobId(r);
      if (!jobId) {
        UI.toast('解析任务已提交（未返回 job_id，请稍后刷新查看）', 'info');
        await refreshDrawerPaper(p.id);
        return;
      }
      const jobResult = await runJob(jobId, '解析全文：' + p.title.slice(0, 30), async function (result) {
        if (!result) return;
        // 后端已写入 snippets / figures / 下载状态，刷新文献详情与当前列表即可看到
        await refreshDrawerPaper(p.id);
        if (state.view === 'tasks' && state.currentTaskId) await loadPapers();
        if (state.view === 'library') await loadLibraryPapers();
        if (result.status === 'no_content') {
          UI.toast('该文献无开放获取全文，无法提取段落与图表', 'info');
        } else {
          const notes = result.notes || [];
          notes.forEach(function (n) { UI.toast(n, 'success'); });
          if (!notes.length) UI.toast('全文解析完成', 'success');
        }
      });
      if (!jobResult) await refreshDrawerPaper(p.id); // 失败恢复界面
    } catch (e) {
      UI.toast('解析全文失败：' + e.message, 'error');
      await refreshDrawerPaper(p.id);
    }
  }

  /** 抽屉内收藏/取消收藏（收藏为长任务） */
  async function toggleCollectFromDrawer() {
    const p = state.drawerPaper;
    if (!p) return;
    if (!p.collected) {
      try {
        const r = await API.collect(p.id, true);
        const jobId = extractJobId(r);
        if (jobId) {
          // 乐观更新：任务运行期间标记「下载中」，任务完成后刷新真实状态
          p.collected = true;
          p.download_status = 'downloading';
          p.download_note = '';
          renderPaperDrawer(p);
          const jobResult = await runJob(jobId, '收藏文献：' + p.title.slice(0, 30), async function (result) {
            const failed = (result && result.failed) || [];
            UI.toast('已收藏「' + p.title.slice(0, 30) + '」' + (failed.length ? '，但源文件下载失败' : ''), failed.length ? 'info' : 'success');
            // 收藏完成后刷新详情：后端已自动下载 PDF 并解析关键片段/图表
            await refreshAfterDrawerCollect();
          });
          if (!jobResult) await refreshAfterDrawerCollect(); // 失败恢复界面
        } else {
          UI.toast('已收藏', 'success');
          await refreshAfterDrawerCollect();
        }
      } catch (e) {
        UI.toast('收藏失败：' + e.message, 'error');
      }
    } else {
      if (!UI.confirm('取消收藏将同时删除本地文件与图片，确定？')) return;
      try {
        await API.uncollect(p.id);
        UI.toast('已取消收藏，本地文件与图片已删除', 'info');
        await refreshAfterDrawerCollect();
      } catch (e) {
        UI.toast('取消收藏失败：' + e.message, 'error');
      }
    }
  }

  async function refreshAfterDrawerCollect() {
    const pid = state.drawerPaper ? state.drawerPaper.id : null;
    if (pid) await refreshDrawerPaper(pid); // 刷新当前文献详情（含新解析出的片段/图表）
    if (state.view === 'tasks' && state.currentTaskId) await refreshTaskAfterJob(state.currentTaskId);
    if (state.view === 'library') await loadLibraryPapers();
  }

  async function summarizePaper() {
    const p = state.drawerPaper;
    if (!p) return;
    if (!hasLLM()) { UI.toast('请先到设置页配置大模型 API', 'error'); return; }
    const box = $('#drawerSummary');
    if (box) box.innerHTML = '<h4>🧠 单篇总结</h4><div class="loading">正在生成结构化总结…</div>';
    try {
      const r = await API.summarize(p.id);
      const jobId = extractJobId(r);
      if (!jobId) { UI.toast('总结任务已提交（未返回 job_id，请稍后刷新查看）', 'info'); await refreshAfterDrawerCollect(); return; }
      const jobResult = await runJob(jobId, '单篇总结：' + p.title.slice(0, 30), async function (result) {
        if (!result) return;
        UI.toast('总结生成完成', 'success');
        state.drawerPaper.summary = result;
        renderPaperDrawer(state.drawerPaper);
        if (state.view === 'library') await loadLibraryPapers();
      });
      if (!jobResult && state.drawerPaper) renderPaperDrawer(state.drawerPaper); // 失败恢复界面
    } catch (e) {
      UI.toast('总结失败：' + e.message, 'error');
      if (state.drawerPaper) renderPaperDrawer(state.drawerPaper);
    }
  }

  async function translatePaper() {
    const p = state.drawerPaper;
    if (!p) return;
    if (!hasLLM()) { UI.toast('请先到设置页配置大模型 API', 'error'); return; }
    const box = $('#drawerTranslation');
    if (box) box.innerHTML = '<h4>🌐 翻译（标题 + 摘要）</h4><div class="loading">正在翻译…</div>';
    try {
      const r = await API.translate(p.id);
      const jobId = extractJobId(r);
      if (!jobId) { UI.toast('翻译任务已提交（未返回 job_id，请稍后刷新查看）', 'info'); await refreshAfterDrawerCollect(); return; }
      const jobResult = await runJob(jobId, '翻译文献：' + p.title.slice(0, 30), async function (result) {
        if (!result) return;
        UI.toast('翻译完成', 'success');
        state.drawerPaper.translation = result;
        state.drawerPaper.title_zh = result.title_zh || state.drawerPaper.title_zh;
        state.drawerPaper.abstract_zh = result.abstract_zh || state.drawerPaper.abstract_zh;
        renderPaperDrawer(state.drawerPaper);
        if (state.view === 'library') await loadLibraryPapers();
      });
      if (!jobResult && state.drawerPaper) renderPaperDrawer(state.drawerPaper); // 失败恢复界面
    } catch (e) {
      UI.toast('翻译失败：' + e.message, 'error');
      if (state.drawerPaper) renderPaperDrawer(state.drawerPaper);
    }
  }

  /** 本地文件预览（PDF 用 iframe） */
  function previewFileByPath(path) {
    if (!path) { UI.toast('该文献没有本地文件', 'info'); return; }
    UI.openModal('本地文件预览',
      '<iframe src="' + esc(fileSrc(path)) + '" style="width:100%;height:70vh;border:0;border-radius:10px;background:#f8fafc" title="文件预览"></iframe>'
      + '<p class="muted small" style="margin-top:8px">' + esc(path) + '</p>', true);
  }

  /* ============================================================
   * 视图 3：文献库
   * ============================================================ */

  async function enterLibrary() {
    if (!state.tasks.length) await loadTasks();
    renderLibrary();
    await Promise.all([loadLibraryPapers(), loadSurveyForCurrent()]);
  }

  function renderLibrary() {
    const el = $('#view-library');
    if (!el) return;
    const taskOptions = state.tasks.map(function (t) {
      return '<option value="' + esc(t.id) + '"' + (state.libTaskId === t.id ? ' selected' : '') + '>' + esc(t.topic) + '</option>';
    }).join('');
    el.innerHTML = '<div class="card toolbar-card">'
      + '<div class="form-row" style="flex:1">'
      + '<label class="field-label">任务筛选</label>'
      + '<select class="input" id="libTaskSel" style="max-width:300px" onchange="App.libTaskChange(this.value)">'
      + '<option value=""' + (state.libTaskId === '' ? ' selected' : '') + '>全部任务</option>' + taskOptions + '</select>'
      + '<input class="input" id="libQ" style="max-width:260px" placeholder="关键词筛选（标题/摘要）" value="' + esc(state.libQ) + '" />'
      + '<button class="btn btn-ghost btn-sm" onclick="App.applyLibFilter()">筛选</button>'
      + '<span class="grow"></span>'
      + '<span class="muted small">已收藏文献 <b id="libCount">0</b> 篇<span id="libFilterNote"></span></span>'
      + '</div></div>'
      + '<div class="card section-card">'
      + '<div class="table-wrap" id="libTableWrap"><div class="loading">加载中…</div></div>'
      + '<div class="table-foot">'
      + '<div class="batch-bar">'
      + '<label class="check-pill"><input type="checkbox" id="libSelAll" onchange="App.toggleLibSelectAll(this.checked)" /> 全选本页</label>'
      + '<span class="muted small">已选 <b id="libSelCount">0</b> 篇</span>'
      + '<button class="btn btn-primary btn-sm" id="btnSurvey" onclick="App.startSurvey()" disabled>📝 生成调研综述</button>'
      + '</div>'
      + '<div class="pagination" id="libPaginationHolder">' + libPaginationHtml() + '</div>'
      + '</div></div>'
      + '<div id="surveyPanel"></div>';
    bindLibraryKeys();
    if (!state.tasks.length) {
      const wrap = $('#libTableWrap');
      wrap.innerHTML = UI.emptyState('📚', '暂无任务', '先到「任务与检索」页创建调研任务并收藏文献。',
        '<button class="btn btn-primary btn-sm" onclick="App.goto(\'tasks\')">去创建任务 →</button>');
    }
  }

  function bindLibraryKeys() {
    const el = $('#libQ');
    if (el) el.addEventListener('keydown', function (e) { if (e.key === 'Enter') App.applyLibFilter(); });
  }

  /** 任务筛选切换：仅客户端过滤当前页（全局接口无 task 参数），并刷新该任务的综述面板 */
  async function libTaskChange(v) {
    state.libTaskId = v || '';
    state.libSelected.clear();
    applyLibTaskFilter();
    await loadSurveyForCurrent();
  }

  /** 拉取已收藏文献：直接调用全局接口 GET /api/papers?collected=true（服务端关键词筛选 + 分页） */
  async function loadLibraryPapers() {
    const seq = ++libSeq;
    const query = {
      q: state.libQ,
      collected: true,
      sort: 'score',
      order: 'desc',
      limit: state.libLimit,
      offset: state.libOffset
    };
    try {
      const r = await API.allPapers(query);
      if (seq !== libSeq) return; // 已被更新的请求取代
      state.libPapers = (r && r.items) || [];
      state.libTotal = (r && r.total) || 0;
      state.libPapers.forEach(function (p) { if (p.id) state.libTitles[p.id] = p.title; });
    } catch (e) {
      if (seq !== libSeq) return;
      state.libPapers = [];
      state.libTotal = 0;
      if (!API.isNetworkError(e)) UI.toast('加载文献库失败：' + e.message, 'error');
    }
    applyLibTaskFilter();
  }

  /** 应用关键词（服务端）：重置到第 1 页重新拉取 */
  function applyLibFilter() {
    state.libQ = $('#libQ') ? $('#libQ').value.trim() : '';
    state.libOffset = 0;
    state.libSelected.clear();
    loadLibraryPapers();
  }

  /** 任务筛选（客户端）：作用于全局接口返回的当前页 */
  function applyLibTaskFilter() {
    const tid = state.libTaskId;
    state.libFiltered = tid
      ? state.libPapers.filter(function (p) { return p.task_id === tid; })
      : state.libPapers.slice();
    const ids = new Set(state.libFiltered.map(function (p) { return p.id; }));
    state.libSelected.forEach(function (id) { if (!ids.has(id)) state.libSelected.delete(id); });
    renderLibraryTable();
  }

  function libPaginationHtml() {
    const pages = Math.max(1, Math.ceil(state.libTotal / state.libLimit));
    const cur = Math.floor(state.libOffset / state.libLimit) + 1;
    return '<select class="input input-sm" onchange="App.changeLibPageSize(this.value)">'
      + [10, 20, 50].map(function (n) {
        return '<option value="' + n + '"' + (state.libLimit === n ? ' selected' : '') + '>每页 ' + n + ' 条</option>';
      }).join('')
      + '</select>'
      + '<button class="btn btn-ghost btn-sm"' + (state.libOffset <= 0 ? ' disabled' : '') + ' onclick="App.gotoLibPage(' + (cur - 1) + ')">‹ 上一页</button>'
      + '<span class="muted small">第 ' + cur + ' / ' + pages + ' 页</span>'
      + '<button class="btn btn-ghost btn-sm"' + (state.libOffset + state.libLimit >= state.libTotal ? ' disabled' : '') + ' onclick="App.gotoLibPage(' + (cur + 1) + ')">下一页 ›</button>';
  }

  function gotoLibPage(p) {
    state.libOffset = Math.max(0, (p - 1) * state.libLimit);
    state.libSelected.clear();
    loadLibraryPapers();
  }

  function changeLibPageSize(n) {
    state.libLimit = parseInt(n, 10) || 20;
    state.libOffset = 0;
    state.libSelected.clear();
    loadLibraryPapers();
  }

  function libRowHtml(p) {
    const sel = state.libSelected.has(p.id);
    const t = state.tasks.find(function (x) { return x.id === p.task_id; });
    return '<tr>'
      + '<td class="td-check"><input type="checkbox" title="选择"' + (sel ? ' checked' : '')
      + ' onchange="App.toggleLibSelect(' + jsq(p.id) + ', this.checked)" /></td>'
      + '<td class="td-title">'
      + '<button class="paper-link" onclick="App.openPaperDrawer(' + jsq(p.id) + ')">' + esc(p.title) + '</button>'
      + (p.title_zh ? '<div class="title-zh">' + esc(p.title_zh) + '</div>' : '')
      + '</td>'
      + '<td class="td-task">' + esc(t ? t.topic : p.task_id) + '</td>'
      + '<td>' + (p.year || '—') + '</td>'
      + '<td class="td-venue">' + esc(p.venue || '—') + '</td>'
      + '<td>' + sourceBadge(p.source) + '</td>'
      + '<td>' + (p.citations == null ? '—' : p.citations) + '</td>'
      + '<td><div class="chip-row">'
      + (p.summary ? '<span class="chip chip-green">已总结</span>' : '')
      + (p.translation ? '<span class="chip chip-blue">已翻译</span>' : '')
      + '</div></td>'
      + '<td>' + downloadOpHtml(p) + '</td>'
      + '</tr>';
  }

  function renderLibraryTable() {
    const wrap = $('#libTableWrap');
    if (!wrap) return;
    const items = state.libFiltered;
    const cnt = $('#libCount');
    if (cnt) cnt.textContent = state.libTotal;
    const note = $('#libFilterNote');
    if (note) {
      note.textContent = state.libTaskId
        ? '（任务筛选作用于当前页：本页匹配 ' + state.libFiltered.length + ' 篇）'
        : '';
    }
    const sc = $('#libSelCount');
    if (sc) sc.textContent = state.libSelected.size;
    const btn = $('#btnSurvey');
    if (btn) btn.disabled = !state.libSelected.size;
    const ph = $('#libPaginationHolder');
    if (ph) ph.innerHTML = libPaginationHtml();
    if (!items.length) {
      let empty;
      if (state.libTotal === 0) {
        empty = UI.emptyState('📚', '暂无已收藏文献',
          '在「任务与检索」页勾选收藏文献后，它们会出现在这里，可用于生成调研综述。',
          '<button class="btn btn-primary btn-sm" onclick="App.goto(\'tasks\')">去检索收藏 →</button>');
      } else if (state.libTaskId) {
        empty = UI.emptyState('📚', '当前页没有该任务的文献',
          '任务筛选作用于当前页，可尝试翻页，或切换为「全部任务」。');
      } else {
        empty = UI.emptyState('📚', '没有匹配的文献', '试试更换关键词。');
      }
      wrap.innerHTML = empty;
      return;
    }
    wrap.innerHTML = '<table class="paper-table"><thead><tr>'
      + '<th class="td-check">选择</th><th>标题</th><th>所属任务</th><th>年份</th><th>出处</th><th>来源</th><th>被引</th><th>状态</th><th>操作</th>'
      + '</tr></thead><tbody>' + items.map(libRowHtml).join('') + '</tbody></table>';
  }

  function toggleLibSelect(id, checked) {
    if (checked) state.libSelected.add(id);
    else state.libSelected.delete(id);
    renderLibraryTable();
  }

  function toggleLibSelectAll(checked) {
    if (checked) state.libFiltered.forEach(function (p) { state.libSelected.add(p.id); });
    else state.libFiltered.forEach(function (p) { state.libSelected.delete(p.id); });
    renderLibraryTable();
  }

  /** 生成调研综述：按任务分组，逐任务提交 Job */
  async function startSurvey() {
    const ids = Array.from(state.libSelected);
    if (!ids.length) { UI.toast('请先勾选要纳入综述的文献', 'error'); return; }
    if (!hasLLM()) { UI.toast('请先到设置页配置大模型 API', 'error'); goto('settings'); return; }
    const byTask = {};
    ids.forEach(function (pid) {
      const p = state.libPapers.find(function (x) { return x.id === pid; });
      if (!p) return;
      (byTask[p.task_id] = byTask[p.task_id] || []).push(pid);
    });
    const groups = Object.keys(byTask);
    for (let i = 0; i < groups.length; i++) {
      const taskId = groups[i];
      const pids = byTask[taskId];
      try {
        const r = await API.survey(taskId, pids);
        const jobId = extractJobId(r);
        let result = null;
        if (jobId) {
          result = await runJob(jobId, '生成调研综述（' + pids.length + ' 篇）');
        } else {
          UI.toast('综述任务已提交（未返回 job_id）', 'info');
        }
        if (result) {
          state.librarySurvey[taskId] = result;
          UI.toast('综述生成完成：' + ((result.clusters && result.clusters.length) ? result.clusters.length + ' 个主题聚类' : '已生成'), 'success');
        }
      } catch (e) {
        UI.toast('综述生成失败：' + e.message, 'error');
        return;
      }
    }
    state.libSelected.clear();
    renderLibraryTable();
    renderSurveyPanel();
  }

  async function loadSurveyForCurrent() {
    const tid = state.libTaskId;
    if (!tid) { renderSurveyPanel(); return; }
    if (state.librarySurvey[tid] === undefined) {
      try {
        state.librarySurvey[tid] = await API.getSurvey(tid);
      } catch (e) {
        state.librarySurvey[tid] = null; // 无则 404，静默
      }
    }
    renderSurveyPanel();
  }

  function renderSurveyPanel() {
    const holder = $('#surveyPanel');
    if (!holder) return;
    const tid = state.libTaskId;
    if (!tid) {
      holder.innerHTML = '<div class="card section-card">' + UI.emptyState('📝', '调研综述',
        '选择上方某个具体任务，即可查看/生成该任务的调研综述（主题聚类 + 综述全文）。') + '</div>';
      return;
    }
    const data = state.librarySurvey[tid];
    if (!data || !data.content) {
      holder.innerHTML = '<div class="card section-card"><div class="card-title">📝 调研综述</div>'
        + UI.emptyState('📝', '该任务尚未生成调研综述', '勾选该任务的已收藏文献，点击「生成调研综述」。',
          hasLLM() ? '<button class="btn btn-primary btn-sm" onclick="App.goto(\'tasks\')">去任务页查看文献</button>' : '')
        + '</div>';
      return;
    }
    // 主题聚类卡片：papers 为文献 id，用标题缓存映射回标题
    const titleMap = state.libTitles;
    const clusters = data.clusters || [];
    holder.innerHTML = '<div class="card section-card">'
      + '<div class="card-title">📝 调研综述（主题聚类）</div>'
      + (clusters.length ? '<div class="sq-grid" style="margin-bottom:16px">' + clusters.map(function (c) {
        return '<div class="sq-card">'
          + '<div class="sq-head"><b>🏷 ' + esc(c.theme || '未命名主题') + '</b></div>'
          + '<div class="sq-why">' + esc(c.summary || '') + '</div>'
          + '<ul class="plain-list" style="margin-top:8px">' + (c.papers || []).map(function (pid) {
            return '<li class="small">' + esc(titleMap[pid] || pid) + '</li>';
          }).join('') + '</ul>'
          + '</div>';
      }).join('') + '</div>' : '')
      + '<div class="card-title" style="margin-top:4px">综述全文</div>'
      + '<div class="md-body" style="border-top:1px dashed var(--line);padding-top:14px">' + MD.render(data.content) + '</div>'
      + (data.created_at ? '<p class="muted small" style="margin-top:12px">生成于 ' + UI.fmtDate(data.created_at) + '</p>' : '')
      + '</div>';
  }

  /* ============================================================
   * 视图 4：开题报告
   * ============================================================ */

  async function enterProposal() {
    if (!state.tasks.length) await loadTasks();
    if (state.tasks.length && !state.tasks.some(function (t) { return t.id === state.propTaskId; })) {
      state.propTaskId = state.tasks[0].id;
    }
    renderProposal();
    await loadProposalData();
  }

  function renderProposal() {
    const el = $('#view-proposal');
    if (!el) return;
    if (!state.tasks.length) {
      el.innerHTML = '<div class="card">' + UI.emptyState('✍️', '暂无任务', '先创建调研任务，再为其生成开题报告。',
        '<button class="btn btn-primary btn-sm" onclick="App.goto(\'tasks\')">去创建任务 →</button>') + '</div>';
      return;
    }
    const taskOptions = state.tasks.map(function (t) {
      return '<option value="' + esc(t.id) + '"' + (state.propTaskId === t.id ? ' selected' : '') + '>' + esc(t.topic) + '</option>';
    }).join('');
    el.innerHTML = '<div class="card toolbar-card">'
      + '<label class="field-label">选择任务</label>'
      + '<select class="input" id="propTaskSel" style="max-width:320px" onchange="App.propTaskChange(this.value)">' + taskOptions + '</select>'
      + '<span class="grow"></span>'
      + '<button class="btn btn-ghost btn-sm" onclick="App.exportProposal(\'md\')">⬇ 导出 MD</button>'
      + '<button class="btn btn-ghost btn-sm" onclick="App.exportProposal(\'docx\')">⬇ 导出 DOCX</button>'
      + '<button class="btn btn-primary btn-sm" id="btnGenAll" onclick="App.generateAll()">⚡ 一键生成全部空分块</button>'
      + '</div>'
      + '<div class="card section-card" id="templateCard"><div class="loading">加载模板信息…</div></div>'
      + '<div class="card section-card" id="sectionsCard"><div class="loading">加载分块…</div></div>';
  }

  async function propTaskChange(v) {
    state.propTaskId = v || '';
    state.propSections = [];
    state.propTemplate = null;
    renderProposal();
    await loadProposalData();
  }

  async function loadProposalData() {
    const tid = state.propTaskId;
    if (!tid) return;
    try {
      state.propTemplate = await API.template(tid);
    } catch (e) {
      state.propTemplate = null; // 未上传 404，静默
    }
    try {
      const r = await API.proposal(tid);
      state.propSections = (r && r.sections) || [];
    } catch (e) {
      state.propSections = [];
      if (!API.isNetworkError(e)) UI.toast('加载分块失败：' + e.message, 'error');
    }
    renderTemplateCard();
    renderSectionsCard();
  }

  function renderTemplateCard() {
    const holder = $('#templateCard');
    if (!holder) return;
    if (!state.propTemplate) {
      holder.innerHTML = '<div class="card-title">📎 学校模板</div>'
        + UI.emptyState('📎', '未上传学校模板',
          '上传学校的开题报告模板（docx / pdf / md / txt），系统解析文本并自动检测分块；不上传则使用默认分块结构。',
          '<label class="btn btn-primary btn-sm" style="cursor:pointer">上传模板<input type="file" accept=".docx,.pdf,.md,.txt" style="display:none" onchange="App.uploadTemplate(this)" /></label>');
      return;
    }
    const t = state.propTemplate;
    holder.innerHTML = '<div class="card-title">📎 学校模板</div>'
      + '<div class="form-row">'
      + UI.badge('📄 ' + t.filename, 'badge-blue')
      + UI.badge('检测到 ' + ((t.sections && t.sections.length) || 0) + ' 个分块', 'badge-green')
      + '<span class="grow"></span>'
      + '<label class="btn btn-ghost btn-sm" style="cursor:pointer">更换模板<input type="file" accept=".docx,.pdf,.md,.txt" style="display:none" onchange="App.uploadTemplate(this)" /></label>'
      + '</div>'
      + ((t.sections && t.sections.length)
        ? '<div class="chip-row" style="margin-top:10px">' + t.sections.map(function (k) {
          return '<span class="chip">' + esc(sectionTitle(k)) + ' <code>' + esc(k) + '</code></span>';
        }).join('') + '</div>'
        : '');
  }

  async function uploadTemplate(input) {
    const file = input.files && input.files[0];
    if (!file) return;
    const tid = state.propTaskId;
    if (!tid) { UI.toast('请先选择任务', 'error'); return; }
    const form = new FormData();
    form.append('file', file);
    try {
      const r = await API.uploadTemplate(tid, form);
      state.propTemplate = r;
      UI.toast('模板上传成功：' + (r.filename || file.name) + '，检测到 ' + ((r.sections && r.sections.length) || 0) + ' 个分块', 'success');
      await loadProposalData();
    } catch (e) {
      UI.toast('模板上传失败：' + e.message, 'error');
    }
    input.value = '';
  }

  function sectionStatusMeta(st) {
    if (st === 'empty') return ['未生成', 'badge-gray'];
    if (st === 'draft') return ['草稿', 'badge-blue'];
    if (st === 'edited') return ['已编辑', 'badge-amber'];
    return [st || '未知', 'badge-gray'];
  }

  function renderSectionsCard() {
    const holder = $('#sectionsCard');
    if (!holder) return;
    const secs = state.propSections;
    if (!secs.length) {
      holder.innerHTML = '<div class="card-title">📑 报告分块</div>'
        + UI.emptyState('📑', '暂无分块', '上传学校模板后自动检测分块，或使用默认分块结构生成开题报告。') + '</div>';
      return;
    }
    holder.innerHTML = '<div class="card-title">📑 报告分块（' + secs.length + '）'
      + '<span class="muted small">「生成」可先点「＋ 说明」附加本节要求；点「预览」就地展开内容</span></div>'
      + secs.map(function (s) {
        const meta = sectionStatusMeta(s.status);
        const wordCount = s.content ? s.content.length : 0;
        return '<div class="section-item" id="sec-item-' + esc(s.key) + '">'
          + '<div class="section-item-head">'
          + '<span class="section-key">' + esc(s.key) + '</span>'
          + '<b>' + esc(s.title) + '</b>'
          + UI.badge(meta[0], meta[1])
          + '<span class="muted small">· ' + wordCount + ' 字</span>'
          + (s.updated_at ? '<span class="muted small">更新于 ' + UI.fmtDate(s.updated_at) + '</span>' : '')
          + '<span class="grow"></span>'
          + (s.content ? '<button class="btn btn-ghost btn-sm" id="btn-sec-preview-' + esc(s.key) + '" onclick="App.toggleSectionPreview(' + jsq(s.key) + ')">预览</button>' : '')
          + '<button class="btn btn-ghost btn-sm" onclick="App.openSectionEditor(' + jsq(s.key) + ')">' + (s.content ? '编辑' : '手动编写') + '</button>'
          + '<button class="btn btn-ghost btn-sm" onclick="App.toggleSectionInstr(' + jsq(s.key) + ')">＋ 说明</button>'
          + '<button class="btn btn-primary btn-sm" onclick="App.generateSection(' + jsq(s.key) + ', true)">' + (s.content ? '重新生成' : '生成') + '</button>'
          + '</div>'
          + (s.content ? '<div class="section-preview hidden" id="sec-preview-' + esc(s.key) + '"></div>' : '')
          + '<div class="section-instr hidden" id="sec-instr-' + esc(s.key) + '">'
          + '<input class="input" style="flex:1" id="sec-instr-input-' + esc(s.key) + '" placeholder="本节额外说明（可选）：例如「重点结合收藏文献的最新方法，不少于 800 字」" />'
          + '<button class="btn btn-primary btn-sm" onclick="App.generateSection(' + jsq(s.key) + ', true)">带说明生成</button>'
          + '</div>'
          + '</div>';
      }).join('');
  }

  function toggleSectionInstr(key) {
    const row = $('#sec-instr-' + key);
    if (row) row.classList.toggle('hidden');
  }

  /** 行内预览：展开/收起切换 */
  function toggleSectionPreview(key) {
    const box = $('#sec-preview-' + key);
    if (!box) return;
    if (box.classList.contains('hidden')) {
      expandSectionPreview(key, true);
    } else {
      box.classList.add('hidden');
      updatePreviewToggleLabel(key, false);
    }
  }

  /**
   * 就地展开分块内容预览（Markdown 渲染 + 滚动到该行）。
   * @param {string} key 分块 key
   * @param {boolean} scroll 是否滚动到该行
   */
  function expandSectionPreview(key, scroll) {
    const box = $('#sec-preview-' + key);
    const item = $('#sec-item-' + key);
    if (!box || !item) return;
    const s = state.propSections.find(function (x) { return x.key === key; });
    if (!s) return;
    box.innerHTML = '<div class="sec-preview-body md-body">' + MD.render(s.content || '') + '</div>'
      + '<div class="sec-preview-foot">'
      + '<button class="btn btn-ghost btn-sm" onclick="App.toggleSectionPreview(' + jsq(key) + ')">收起</button>'
      + '<button class="regen-link" onclick="App.generateSection(' + jsq(key) + ', true)">不满意？重新生成本节</button>'
      + '</div>';
    box.classList.remove('hidden');
    updatePreviewToggleLabel(key, true);
    if (scroll) {
      setTimeout(function () {
        item.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 30);
    }
  }

  /** 同步「预览 / 收起」切换按钮文案 */
  function updatePreviewToggleLabel(key, expanded) {
    const btn = $('#btn-sec-preview-' + key);
    if (btn) btn.textContent = expanded ? '收起' : '预览';
  }

  async function generateSection(key, withInstr) {
    if (!hasLLM()) { UI.toast('请先到设置页配置大模型 API', 'error'); goto('settings'); return; }
    let instruction = '';
    if (withInstr) {
      const inp = $('#sec-instr-input-' + key);
      if (inp) instruction = inp.value.trim();
    }
    try {
      const r = await API.generateSection(state.propTaskId, key, instruction);
      const jobId = extractJobId(r);
      if (!jobId) { UI.toast('生成任务已提交（未返回 job_id）', 'info'); await loadProposalData(); return; }
      await runJob(jobId, '生成分块：' + sectionTitle(key), async function (result) {
        UI.toast('分块「' + sectionTitle(key) + '」生成完成', 'success');
        await loadProposalData(); // 刷新该行内容/字数/状态
        // 自动展开新生成的内容，让用户立刻看到
        setTimeout(function () { expandSectionPreview(key, true); }, 60);
      });
    } catch (e) {
      UI.toast('生成失败：' + e.message, 'error');
    }
  }

  async function generateAll() {
    if (!hasLLM()) { UI.toast('请先到设置页配置大模型 API', 'error'); goto('settings'); return; }
    const empties = state.propSections.filter(function (s) { return !s.content; }).length;
    if (!empties) { UI.toast('没有空分块需要生成', 'info'); return; }
    try {
      const r = await API.generateAll(state.propTaskId);
      const jobId = extractJobId(r);
      if (!jobId) { UI.toast('生成任务已提交（未返回 job_id）', 'info'); await loadProposalData(); return; }
      await runJob(jobId, '一键生成全部空分块（' + empties + ' 个）', async function (result) {
        const failed = (result && result.failed) || [];
        const generated = (result && result.generated) || [];
        const ok = generated.length;
        UI.toast('生成完成：成功 ' + ok + ' 个' + (failed.length ? '，失败 ' + failed.length + ' 个' : ''), failed.length ? 'info' : 'success');
        await loadProposalData();
        // 自动展开第一个新生成的分块并滚动到它，让用户立刻看到内容
        if (generated.length) {
          const first = generated[0];
          setTimeout(function () { expandSectionPreview(first, true); }, 60);
        }
      });
    } catch (e) {
      UI.toast('生成失败：' + e.message, 'error');
    }
  }

  function openSectionEditor(key) {
    const s = state.propSections.find(function (x) { return x.key === key; });
    if (!s) return;
    state.editorKey = key;
    state.editorMode = 'edit';
    UI.openModal('编辑分块：' + s.title, ''
      + '<div class="editor-toolbar">'
      + '<button class="btn btn-ghost btn-sm" onclick="App.editorTab(\'edit\')">✏️ 编辑</button>'
      + '<button class="btn btn-ghost btn-sm" onclick="App.editorTab(\'preview\')">👁 预览</button>'
      + '<span class="grow"></span><span class="muted small">支持 Markdown</span>'
      + '</div>'
      + '<textarea id="editorArea" class="editor-area">' + esc(s.content || '') + '</textarea>'
      + '<div id="editorPreview" class="editor-preview md-body hidden"></div>'
      + '<div class="editor-foot">'
      + '<span class="muted small">保存后状态标记为「已编辑」</span>'
      + '<span class="grow"></span>'
      + '<button class="btn btn-ghost" onclick="UI.closeModal()">取消</button>'
      + '<button class="btn btn-primary" onclick="App.saveSection()">💾 保存分块</button>'
      + '</div>', true);
  }

  function editorTab(mode) {
    state.editorMode = mode;
    const area = $('#editorArea');
    const prev = $('#editorPreview');
    if (!area || !prev) return;
    if (mode === 'edit') {
      prev.classList.add('hidden');
      area.classList.remove('hidden');
    } else {
      prev.innerHTML = MD.render(area.value);
      prev.classList.remove('hidden');
      area.classList.add('hidden');
    }
  }

  async function saveSection() {
    const key = state.editorKey;
    const area = $('#editorArea');
    if (!key || !area) return;
    try {
      await API.saveSection(state.propTaskId, key, area.value);
      UI.toast('分块已保存', 'success');
      UI.closeModal();
      await loadProposalData(); // 刷新该行内容/字数/状态
      // 保存后自动展开该行，让用户看到保存结果
      setTimeout(function () { expandSectionPreview(key, true); }, 60);
    } catch (e) {
      UI.toast('保存失败：' + e.message, 'error');
    }
  }

  function exportProposal(format) {
    const tid = state.propTaskId;
    if (!tid) { UI.toast('请先选择任务', 'error'); return; }
    if (!state.propSections.length) { UI.toast('尚无分块内容，请先生成或编写', 'error'); return; }
    if (state.backendOnline === false) { UI.toast('后端未连接，无法导出', 'error'); return; }
    window.open('/api/tasks/' + encodeURIComponent(tid) + '/proposal/export?format=' + format, '_blank');
  }

  /* ============================================================
   * 视图 5：评审与答辩
   * ============================================================ */

  async function enterReview() {
    if (!state.tasks.length) await loadTasks();
    if (state.tasks.length && !state.tasks.some(function (t) { return t.id === state.revTaskId; })) {
      state.revTaskId = state.tasks[0].id;
    }
    renderReview();
    await Promise.all([loadReviewData(), loadDefenseData()]);
  }

  function renderReview() {
    const el = $('#view-review');
    if (!el) return;
    if (!state.tasks.length) {
      el.innerHTML = '<div class="card">' + UI.emptyState('👥', '暂无任务', '先创建调研任务并生成开题初稿，再进行多智能体评审。',
        '<button class="btn btn-primary btn-sm" onclick="App.goto(\'tasks\')">去创建任务 →</button>') + '</div>';
      return;
    }
    const taskOptions = state.tasks.map(function (t) {
      return '<option value="' + esc(t.id) + '"' + (state.revTaskId === t.id ? ' selected' : '') + '>' + esc(t.topic) + '</option>';
    }).join('');
    const running = state.reviewRunning && state.reviewRunningTaskId === state.revTaskId;
    el.innerHTML = '<div class="card toolbar-card">'
      + '<label class="field-label">选择任务</label>'
      + '<select class="input" id="revTaskSel" style="max-width:320px" onchange="App.revTaskChange(this.value)">' + taskOptions + '</select>'
      + '<span class="grow"></span>'
      + '<button class="btn btn-primary" id="btnStartReview" onclick="App.startReview()"' + (running ? ' disabled' : '') + '>'
      + (running ? '⏳ 评审中…' : '🚀 启动多智能体评审') + '</button>'
      + '</div>'
      + '<div id="reviewBody"><div class="card"><div class="loading">加载评审结果…</div></div></div>'
      + '<div class="card section-card" id="defenseCard"><div class="loading">加载答辩问题清单…</div></div>';
  }

  async function revTaskChange(v) {
    state.revTaskId = v || '';
    state.reviewData = null;
    state.defenseData = null;
    renderReview();
    await Promise.all([loadReviewData(), loadDefenseData()]);
  }

  async function loadReviewData() {
    const tid = state.revTaskId;
    if (!tid) { renderReviewBody(); return; }
    try {
      state.reviewData = await API.review(tid);
    } catch (e) {
      state.reviewData = null; // 无则 404，静默
    }
    renderReviewBody();
  }

  const REVIEW_AGENT_ICONS = { academic: '📖', logic: '🧩', feasibility: '✅', format: '📐' };
  const SEVERITY_META = {
    high: { cls: 'sev-high', label: '高' },
    medium: { cls: 'sev-medium', label: '中' },
    low: { cls: 'sev-low', label: '低' }
  };
  const SEVERITY_ORDER = { high: 0, medium: 1, low: 2 };

  function scoreClass(score) {
    return score >= 80 ? 'good' : (score >= 60 ? 'mid' : 'bad');
  }

  function reviewCardHtml(r) {
    const icon = REVIEW_AGENT_ICONS[r.agent] || '🤖';
    const issues = (r.issues || []).slice().sort(function (a, b) {
      return (SEVERITY_ORDER[a.severity] || 1) - (SEVERITY_ORDER[b.severity] || 1);
    });
    return '<div class="review-card card">'
      + '<div class="review-head">'
      + '<span class="review-icon">' + icon + '</span>'
      + '<div class="grow"><b>' + esc(r.agent_name || r.agent) + '</b>'
      + '<div class="muted small">' + esc(r.provider_id || '默认服务商') + ' · ' + esc(r.model || '') + '</div></div>'
      + '<div class="review-score ' + scoreClass(r.score) + '">' + (r.score == null ? '—' : r.score) + '<small>/100</small></div>'
      + '</div>'
      + '<div class="review-summary">' + esc(r.summary) + '</div>'
      + '<div class="issue-list">'
      + (issues.length
        ? issues.map(function (it) {
          const sev = SEVERITY_META[it.severity] || SEVERITY_META.medium;
          return '<div class="issue ' + sev.cls + '">'
            + '<div class="issue-head">'
            + UI.badge('严重度：' + sev.label, sev.cls)
            + (it.section ? UI.badge(sectionTitle(it.section), 'badge-plain') : '')
            + (it.applied === true ? UI.badge('✅ 已处理', 'badge-green') : '')
            + '</div>'
            + '<div class="issue-problem">❌ ' + esc(it.problem) + '</div>'
            + (it.suggestion ? '<div class="issue-suggestion">💡 建议：' + esc(it.suggestion) + '</div>' : '')
            + (it.evidence ? '<div class="issue-evidence">📎 依据：' + esc(it.evidence) + '</div>' : '')
            // 已处理意见不再提供「辅助修改」入口
            + (it.applied === true ? ''
              : '<div class="issue-foot">'
              + '<button class="btn btn-primary btn-sm" onclick="App.applyReview(' + jsq(it.section || '') + ', ' + jsq(it.suggestion || '') + ')">🛠 辅助修改该节</button>'
              + '</div>')
            + '</div>';
        }).join('')
        : '<div class="muted">🎉 该评审未发现问题</div>')
      + '</div>'
      + '</div>';
  }

  function mergedCardHtml(m) {
    const suggs = (m.final_suggestions || []).slice().sort(function (a, b) { return (a.priority || 1) - (b.priority || 1); });
    return '<div class="card merged-card">'
      + '<div class="merged-head"><h3>🧭 一致性汇总（coordinator）</h3>'
      + '<div class="review-score ' + scoreClass(m.overall_score) + '">' + (m.overall_score == null ? '—' : m.overall_score) + '<small>/100</small></div></div>'
      + '<div class="verdict">评审结论：' + UI.badge(m.verdict || '—', 'badge-verdict') + '</div>'
      + (m.strengths && m.strengths.length
        ? '<div class="merged-block"><h4>✅ 报告优点</h4><ul class="plain-list">' + m.strengths.map(function (s) { return '<li>' + esc(s) + '</li>'; }).join('') + '</ul></div>'
        : '')
      + (m.conflicts && m.conflicts.length
        ? '<div class="merged-block"><h4>⚖️ 评审冲突与裁决</h4>' + m.conflicts.map(function (c) {
          return '<div class="conflict"><div class="conflict-topic">' + esc(c.topic) + '</div>'
            + '<ul class="plain-list">' + (c.opinions || []).map(function (o) { return '<li>💬 ' + esc(o) + '</li>'; }).join('') + '</ul>'
            + '<div class="conflict-res">⚖️ 裁决：' + esc(c.resolution) + '</div></div>';
        }).join('') + '</div>'
        : '')
      + '<div class="merged-block"><h4>📋 最终修改建议（按优先级排序）</h4>'
      + (suggs.length
        ? suggs.map(function (s) {
          return '<div class="sugg">'
            + '<div class="sugg-head">'
            + UI.badge('优先级 ' + (s.priority || 1), 'badge-pri')
            + (s.section ? UI.badge(sectionTitle(s.section), 'badge-plain') : '')
            + (s.applied === true ? UI.badge('✅ 已处理', 'badge-green') : '')
            + '</div>'
            + '<div class="sugg-action">🛠 ' + esc(s.action) + '</div>'
            + (s.reason ? '<div class="sugg-reason">理由：' + esc(s.reason) + '</div>' : '')
            // 已处理建议不再提供「辅助修改」入口
            + (s.applied === true ? ''
              : '<div class="sugg-foot">'
              + '<button class="btn btn-primary btn-sm" onclick="App.applyReview(' + jsq(s.section || '') + ', ' + jsq(s.action || '') + ')">🛠 辅助修改该节</button>'
              + '</div>')
            + '</div>';
        }).join('')
        : '<div class="muted">无修改建议</div>')
      + '</div>'
      + '</div>';
  }

  /** 当前任务是否正在评审 */
  function isReviewRunning() {
    return state.reviewRunning && state.reviewRunningTaskId === state.revTaskId;
  }

  /** 评审进行中的加载态（点击「启动评审」后立即显示） */
  function reviewRunningHtml() {
    return '<div class="card section-card">'
      + '<div class="review-running">'
      + '<div class="review-running-ico">👥</div>'
      + '<div class="review-running-body">'
      + '<b>多智能体评审进行中（4 个评审角色并行）…</b>'
      + '<div class="muted small">学术规范 / 逻辑 / 可行性 / 格式 四个评审角色正在并行评审，随后由 coordinator 汇总冲突并给出最终建议。'
      + '通常需要 30~60 秒，具体进度见右下角进度面板，请耐心等待。</div>'
      + '<div class="review-running-bar"></div>'
      + '</div>'
      + '</div>'
      + '</div>';
  }

  /** 同步页头「启动评审」按钮的运行态（禁用 + 「⏳ 评审中…」） */
  function updateReviewButton() {
    const btn = $('#btnStartReview');
    if (!btn) return;
    const running = isReviewRunning();
    btn.disabled = running;
    btn.textContent = running ? '⏳ 评审中…' : '🚀 启动多智能体评审';
  }

  function renderReviewBody() {
    const holder = $('#reviewBody');
    if (!holder) return;
    // 评审进行中：立即显示加载态，而不是「尚未评审」
    if (isReviewRunning()) {
      holder.innerHTML = reviewRunningHtml();
      return;
    }
    const r = state.reviewData;
    if (!r || !r.results || !r.results.length) {
      holder.innerHTML = '<div class="card section-card">' + UI.emptyState('👥', '尚未评审',
        '点击右上角「启动多智能体评审」开始：4 个评审角色并行评审 + 一致性汇总。', '')
        + '</div>';
      return;
    }
    // 存在已处理意见 → 顶部显示「评审已过时」黄色提示条
    const hasApplied = (r.results || []).some(function (res) {
      return (res.issues || []).some(function (it) { return it.applied === true; });
    }) || (r.merged && (r.merged.final_suggestions || []).some(function (s) { return s.applied === true; }));
    holder.innerHTML = (hasApplied ? reviewStaleHtml() : '')
      + '<div class="review-grid">' + r.results.map(reviewCardHtml).join('') + '</div>'
      + (r.merged ? mergedCardHtml(r.merged) : '');
  }

  /** 「评审已过时」黄色提示条（存在 applied===true 的意见时显示） */
  function reviewStaleHtml() {
    return '<div class="banner-warn">'
      + '<span class="banner-warn-ico">⚠️</span>'
      + '<div class="banner-warn-body">已完成部分修改，当前评审结果可能已过时——点击右上角「🚀 启动多智能体评审」获取最新整体评审。</div>'
      + '</div>';
  }

  async function startReview() {
    const tid = state.revTaskId;
    if (!tid) return;
    if (!hasLLM()) { UI.toast('请先到设置页配置大模型 API', 'error'); goto('settings'); return; }
    if (isReviewRunning()) return; // 防止重复点击
    try {
      const r = await API.startReview(tid);
      const jobId = extractJobId(r);
      if (!jobId) { UI.toast('评审任务已提交（未返回 job_id，请稍后刷新查看）', 'info'); await loadReviewData(); return; }
      // 点击即时反馈：切换运行态，按钮禁用 + 正文立即显示加载态
      state.reviewRunning = true;
      state.reviewRunningTaskId = tid;
      updateReviewButton();
      renderReviewBody();
      const jobResult = await runJob(jobId, '多智能体评审（4 角色 + 一致性汇总）');
      if (jobResult) {
        const overall = (jobResult.merged && jobResult.merged.overall_score != null) ? jobResult.merged.overall_score : '—';
        UI.toast('评审完成：综合得分 ' + overall, 'success');
      }
      // 无论成败都刷新（成功渲染结果；失败恢复「尚未评审」空态）
      await loadReviewData();
    } catch (e) {
      UI.toast('启动评审失败：' + e.message, 'error');
    } finally {
      // 无论成功/失败都恢复按钮
      if (state.reviewRunningTaskId === tid) {
        state.reviewRunning = false;
        state.reviewRunningTaskId = '';
      }
      updateReviewButton();
      if (state.view === 'review' && state.revTaskId === tid) renderReviewBody();
    }
  }

  /**
   * 「辅助修改该节」入口。
   * overall（或空分块）意见不能直接发送：先弹选择器挑选具体分块；
   * 普通分块意见直接打开补充说明模态框。
   * @param {string} section issue.section（可能为 '' 或 'overall'）
   * @param {string} suggestionText issue.suggestion
   */
  function applyReview(section, suggestionText) {
    if (!hasLLM()) { UI.toast('请先到设置页配置大模型 API', 'error'); goto('settings'); return; }
    const isOverall = !section || section === 'overall';
    if (isOverall) {
      openApplySectionPicker(suggestionText);
      return;
    }
    openApplyInstrModal(section, suggestionText);
  }

  /** 普通分块意见：补充说明模态框（目标分块固定） */
  function openApplyInstrModal(section, suggestionText) {
    UI.openModal('辅助修改分块', ''
      + '<p class="muted" style="margin-bottom:10px">目标分块：<b>' + esc(sectionTitle(section)) + '</b></p>'
      + '<label class="field-label">补充要求（可选，已带入评审建议）</label>'
      + '<textarea id="applyInstr" class="input" rows="3" style="margin-top:6px" placeholder="例如：保留原结构，只按建议修改第 2 段">'
      + esc(suggestionText || '') + '</textarea>'
      + '<div class="editor-foot">'
      + '<button class="btn btn-ghost" onclick="UI.closeModal()">取消</button>'
      + '<button class="btn btn-primary" onclick="App.confirmApply(' + jsq(section) + ')">开始修改</button>'
      + '</div>');
  }

  /** overall 意见：先选具体分块（选项来自缓存 state.propSections，必要时拉取 GET proposal） */
  async function openApplySectionPicker(suggestionText) {
    let secs = state.propSections;
    if (!secs.length || state.propTaskId !== state.revTaskId) {
      try {
        const p = await API.proposal(state.revTaskId);
        secs = (p && p.sections) || [];
        if (state.propTaskId === state.revTaskId) state.propSections = secs;
      } catch (e) {
        secs = [];
      }
    }
    if (!secs.length) {
      UI.toast('该任务还没有分块，请先到「开题报告」页生成初稿', 'info');
      return;
    }
    const options = secs.map(function (s) {
      return '<option value="' + esc(s.key) + '">' + esc(s.title) + '（' + esc(s.key) + '）</option>';
    }).join('');
    UI.openModal('选择要修改的分块', ''
      + '<p class="muted" style="margin-bottom:10px">该意见为整体性意见，请选择要应用的具体分块：</p>'
      + '<label class="field-label">目标分块</label>'
      + '<select class="input" id="applySectionSel" style="margin-top:6px">' + options + '</select>'
      + '<label class="field-label" style="display:block;margin-top:12px">补充要求（可选，已带入评审建议）</label>'
      + '<textarea id="applyInstr" class="input" rows="3" style="margin-top:6px" placeholder="例如：保留原结构，只按建议修改第 2 段">'
      + esc(suggestionText || '') + '</textarea>'
      + '<div class="editor-foot">'
      + '<button class="btn btn-ghost" onclick="UI.closeModal()">取消</button>'
      + '<button class="btn btn-primary" onclick="App.confirmApplyFromPicker()">开始修改</button>'
      + '</div>');
  }

  /** 从分块选择器中确认：用选中的真实分块 key 调 POST apply */
  function confirmApplyFromPicker() {
    const sel = $('#applySectionSel');
    const section = sel ? sel.value : '';
    if (!section) { UI.toast('请选择要修改的分块', 'error'); return; }
    confirmApply(section);
  }

  async function confirmApply(section) {
    const instr = $('#applyInstr') ? $('#applyInstr').value.trim() : '';
    UI.closeModal();
    try {
      const r = await API.applyReview(state.revTaskId, section, instr);
      const jobId = extractJobId(r);
      if (!jobId) { UI.toast('修改任务已提交（未返回 job_id）', 'info'); await refreshProposalCache(); return; }
      const jobResult = await runJob(jobId, '辅助修改：' + sectionTitle(section));
      if (jobResult) {
        UI.toast('已按评审意见修改：' + sectionTitle(section), 'success');
        await refreshProposalCache();
        if (jobResult.diff) showDiffModal(section, jobResult.diff);
        // 后端已把该分块相关意见标记 applied=true：重新拉取评审数据，让「✅ 已处理」徽章立即显示
        await loadReviewData();
      } else {
        await refreshProposalCache(); // 失败恢复
      }
    } catch (e) {
      // 400（如仍传了 overall 等非法分块）：展示后端 detail 并引导重新选择
      if (e && e.status === 400) {
        UI.toast('修改失败：' + e.message, 'error', 6000);
        UI.toast('该意见为整体性意见，请先选择具体分块后重试', 'info', 6000);
      } else {
        UI.toast('辅助修改失败：' + e.message, 'error');
      }
    }
  }

  /** 「修改对比」模态框：渲染统一 diff 文本（- 删除红 / + 新增绿 / @@ 灰色） */
  function showDiffModal(section, diffText) {
    const lines = String(diffText || '').split('\n');
    const html = lines.map(function (l) {
      let cls = 'diff-line';
      if (l.charAt(0) === '-') cls += ' diff-del';
      else if (l.charAt(0) === '+') cls += ' diff-add';
      else if (l.indexOf('@@') === 0) cls += ' diff-hunk';
      return '<span class="' + cls + '">' + esc(l) + '</span>';
    }).join('');
    UI.openModal('修改对比：' + sectionTitle(section), ''
      + '<pre class="diff-pre">' + html + '</pre>'
      + '<div class="editor-foot">'
      + '<button class="btn btn-ghost" onclick="UI.closeModal()">关闭</button>'
      + '<button class="btn btn-primary" onclick="App.gotoSectionPreview(' + jsq(section) + ')">查看该节</button>'
      + '</div>');
  }

  /** 「查看该节」：跳转到开题报告页并展开该分块的行内预览 */
  async function gotoSectionPreview(key) {
    UI.closeModal();
    if (state.propTaskId !== state.revTaskId) {
      state.propTaskId = state.revTaskId;
      state.propSections = [];
    }
    goto('proposal');           // 触发 enterProposal → renderProposal + loadProposalData
    await loadProposalData();   // 确保分块数据就绪（重复调用无害）
    const found = state.propSections.some(function (s) { return s.key === key && s.content; });
    if (!found) {
      UI.toast('该分块暂无内容，可在「开题报告」页先生成', 'info');
      return;
    }
    setTimeout(function () { expandSectionPreview(key, true); }, 60);
  }

  /** 刷新对应分块（若开题报告视图正在展示该任务） */
  async function refreshProposalCache() {
    if (state.propTaskId !== state.revTaskId) return;
    try {
      const p = await API.proposal(state.revTaskId);
      state.propSections = (p && p.sections) || [];
      if (state.view === 'proposal') renderSectionsCard();
    } catch (e) { /* 忽略 */ }
  }

  async function loadDefenseData() {
    const tid = state.revTaskId;
    if (!tid) { renderDefenseCard(); return; }
    try {
      state.defenseData = await API.defense(tid);
    } catch (e) {
      state.defenseData = null; // 无则 404，静默
    }
    renderDefenseCard();
  }

  function renderDefenseCard() {
    const holder = $('#defenseCard');
    if (!holder) return;
    const d = state.defenseData;
    const hasContent = d && d.content;
    holder.innerHTML = '<div class="card-title">🎤 答辩问题清单</div>'
      + (hasContent
        ? '<div class="md-body">' + MD.render(d.content) + '</div>'
        + '<div class="form-row" style="margin-top:12px">'
        + '<span class="muted small">生成于 ' + UI.fmtDate(d.created_at) + '</span><span class="grow"></span>'
        + (hasLLM() ? '<button class="btn btn-ghost btn-sm" onclick="App.startDefense()">重新生成</button>' : '')
        + '</div>'
        : UI.emptyState('🎤', '尚未生成答辩问题清单', '基于开题报告初稿，生成开题答辩可能被问到的问题清单，辅助答辩准备。',
          hasLLM() ? '<button class="btn btn-primary" onclick="App.startDefense()">生成答辩问题清单</button>' : ''));
  }

  async function startDefense() {
    const tid = state.revTaskId;
    if (!tid) return;
    if (!hasLLM()) { UI.toast('请先到设置页配置大模型 API', 'error'); goto('settings'); return; }
    try {
      const r = await API.startDefense(tid);
      const jobId = extractJobId(r);
      if (!jobId) { UI.toast('生成任务已提交（未返回 job_id）', 'info'); await loadDefenseData(); return; }
      await runJob(jobId, '生成答辩问题清单', async function (result) {
        UI.toast('答辩问题清单生成完成', 'success');
        await loadDefenseData();
      });
    } catch (e) {
      UI.toast('生成失败：' + e.message, 'error');
    }
  }

  /* ============================================================
   * 视图 6：设置
   * ============================================================ */

  async function enterSettings() {
    renderSettingsShell();
    await Promise.all([loadSettings(), loadPresets()]);
  }

  function renderSettingsShell() {
    const el = $('#view-settings');
    if (!el) return;
    el.innerHTML = ''
      /* ---- 服务商管理 ---- */
      + '<div class="card section-card">'
      + '<div class="card-title">🤖 大模型服务商 <span class="muted small">兼容 OpenAI API 的服务均可接入</span></div>'
      + '<div class="form-row" style="margin-bottom:14px">'
      + '<select class="input" id="presetSel" style="max-width:320px" onchange="App.addPreset()"><option value="">＋ 从预设添加服务商…</option></select>'
      + '</div>'
      + '<div id="providerList"><div class="loading">加载中…</div></div>'
      + '</div>'
      /* ---- 默认服务商 ---- */
      + '<div class="card section-card">'
      + '<div class="card-title">🎯 默认服务商</div>'
      + '<div class="form-row">'
      + '<select class="input" id="defaultProviderSel" style="max-width:340px"></select>'
      + '<button class="btn btn-primary btn-sm" onclick="App.saveDefaultProvider()">保存</button>'
      + '</div>'
      + '<p class="muted small" style="margin-top:8px">未单独指定角色的任务使用默认服务商；默认值留空时取第一个启用的服务商。</p>'
      + '</div>'
      /* ---- 角色映射 ---- */
      + '<div class="card section-card">'
      + '<div class="card-title">🧩 角色 → 服务商映射</div>'
      + '<div class="role-grid" id="roleGrid"></div>'
      + '<div class="form-row" style="justify-content:flex-end"><button class="btn btn-primary" onclick="App.saveRoleProviders()">保存角色映射</button></div>'
      + '</div>'
      /* ---- 源文件保存目录 ---- */
      + '<div class="card section-card">'
      + '<div class="card-title">📁 源文件保存目录</div>'
      + '<div class="form-row">'
      + '<input class="input" id="downloadDir" style="flex:1;min-width:260px" placeholder="例如 D:/grad-prep/files" />'
      + '<button class="btn btn-primary btn-sm" onclick="App.saveDownloadDir()">保存</button>'
      + '</div>'
      + '<p class="muted small" style="margin-top:8px">收藏文献时下载的 PDF 等源文件保存到此目录。</p>'
      + '</div>'
      /* ---- 检索参数 ---- */
      + '<div class="card section-card">'
      + '<div class="card-title">🔎 检索参数</div>'
      + '<div class="form-grid3">'
      + '<label>每源最多结果数<input class="input" id="soMaxPer" type="number" min="1" style="margin-top:6px" /></label>'
      + '<label>结果总数上限<input class="input" id="soMaxTotal" type="number" min="1" style="margin-top:6px" /></label>'
      + '<label>请求超时（秒）<input class="input" id="soTimeout" type="number" min="1" style="margin-top:6px" /></label>'
      + '</div>'
      + '<div class="form-row" style="justify-content:flex-end;margin-top:12px"><button class="btn btn-primary btn-sm" onclick="App.saveSearchOptions()">保存检索参数</button></div>'
      + '</div>';
  }

  async function loadSettings() {
    try {
      state.settings = await API.settings();
    } catch (e) {
      state.settings = null;
      if (!API.isNetworkError(e)) UI.toast('加载设置失败：' + e.message, 'error');
    }
    renderSettingsData();
  }

  async function loadPresets() {
    try {
      state.presets = (await API.presets()) || [];
    } catch (e) {
      state.presets = [];
      if (!API.isNetworkError(e)) UI.toast('加载预设失败：' + e.message, 'error');
    }
    renderSettingsData();
  }

  function providerCardHtml(p) {
    const keyHint = p.api_key
      ? '已保存（…' + p.api_key.slice(-4) + '），留空则保持不变'
      : '请填写 API Key';
    return '<div class="provider-card">'
      + '<div class="provider-head">'
      + '<b>' + esc(p.name) + '</b>'
      + UI.badge(p.id, 'badge-plain')
      + (p.enabled ? UI.badge('已启用', 'badge-green') : UI.badge('已停用', 'badge-gray'))
      + (p.note ? '<span class="muted small">' + esc(p.note) + '</span>' : '')
      + '<span class="grow"></span>'
      + '<button class="btn btn-danger-ghost btn-sm" onclick="App.deleteProvider(' + jsq(p.id) + ', ' + jsq(p.name) + ')">删除</button>'
      + '</div>'
      + '<div class="form-grid2">'
      + '<label>名称<input class="input" id="pv-' + esc(p.id) + '-name" value="' + esc(p.name) + '" style="margin-top:6px" /></label>'
      + '<label>模型<input class="input" id="pv-' + esc(p.id) + '-model" value="' + esc(p.model) + '" placeholder="例如 deepseek-chat" style="margin-top:6px" /></label>'
      + '<label class="span2">Base URL<input class="input" id="pv-' + esc(p.id) + '-base" value="' + esc(p.base_url) + '" style="margin-top:6px" /></label>'
      + '<label>API Key<input class="input" type="password" autocomplete="off" id="pv-' + esc(p.id) + '-key" placeholder="' + esc(keyHint) + '" style="margin-top:6px" /></label>'
      + '<label>Embedding 模型<input class="input" id="pv-' + esc(p.id) + '-emb" value="' + esc(p.embedding_model) + '" placeholder="可选（向量检索用）" style="margin-top:6px" /></label>'
      + '<label class="check-pill span2" style="width:max-content"><input type="checkbox" id="pv-' + esc(p.id) + '-enabled"' + (p.enabled ? ' checked' : '') + ' /> 启用该服务商</label>'
      + '</div>'
      + '<div class="form-row" style="justify-content:flex-end;margin-top:12px">'
      + '<button class="btn btn-ghost btn-sm" onclick="App.testProvider(' + jsq(p.id) + ')">🔌 测试连接</button>'
      + '<button class="btn btn-primary btn-sm" onclick="App.saveProvider(' + jsq(p.id) + ')">保存服务商</button>'
      + '</div>'
      + '</div>';
  }

  function renderSettingsData() {
    if (state.view !== 'settings') return;
    const s = state.settings;
    const provList = $('#providerList');
    if (!provList) return;

    /* 服务商列表 */
    if (!s || !s.providers || !s.providers.length) {
      provList.innerHTML = UI.emptyState('🤖', '尚未配置服务商', '从上方预设添加，或使用任意兼容 OpenAI API 的服务。');
    } else {
      provList.innerHTML = s.providers.map(providerCardHtml).join('');
    }

    /* 预设下拉（过滤已存在的 id，避免覆盖） */
    const presets = state.presets || [];
    const existing = new Set((s && s.providers ? s.providers : []).map(function (p) { return p.id; }));
    const addable = presets.filter(function (p) { return !existing.has(p.id); });
    const sel = $('#presetSel');
    if (sel) {
      sel.innerHTML = '<option value="">＋ 从预设添加服务商…</option>'
        + addable.map(function (p) {
          return '<option value="' + esc(p.id) + '">' + esc(p.name) + (p.note ? '（' + esc(p.note) + '）' : '') + '</option>';
        }).join('');
    }

    /* 默认服务商 */
    const defSel = $('#defaultProviderSel');
    if (defSel) {
      defSel.innerHTML = '<option value="">（默认：第一个启用的服务商）</option>'
        + ((s && s.providers) || []).map(function (p) {
          return '<option value="' + esc(p.id) + '"' + (s.default_provider_id === p.id ? ' selected' : '') + '>' + esc(p.name) + '</option>';
        }).join('');
    }

    /* 角色映射（10 行下拉） */
    const roleGrid = $('#roleGrid');
    if (roleGrid) {
      roleGrid.innerHTML = ROLES.map(function (r) {
        const key = r[0];
        return '<div class="role-row"><span class="role-name">' + esc(r[1]) + '</span>'
          + '<select class="input" id="role-' + key + '"><option value="">跟随默认服务商</option>'
          + ((s && s.providers) || []).map(function (p) {
            return '<option value="' + esc(p.id) + '"' + ((s.role_providers && s.role_providers[key] === p.id) ? ' selected' : '') + '>' + esc(p.name) + '</option>';
          }).join('')
          + '</select></div>';
      }).join('');
    }

    /* 下载目录 / 检索参数 */
    const dd = $('#downloadDir');
    if (dd) dd.value = s ? (s.download_dir || '') : '';
    const so = (s && s.search_options) || {};
    const mp = $('#soMaxPer'); if (mp) mp.value = so.max_results_per_source != null ? so.max_results_per_source : 10;
    const mt = $('#soMaxTotal'); if (mt) mt.value = so.max_total_results != null ? so.max_total_results : 80;
    const to = $('#soTimeout'); if (to) to.value = so.request_timeout != null ? so.request_timeout : 30;
  }

  async function addPreset() {
    const sel = $('#presetSel');
    const id = sel.value;
    if (!id) return;
    sel.value = '';
    const preset = (state.presets || []).find(function (p) { return p.id === id; });
    if (!preset) return;
    try {
      const body = {
        id: preset.id, name: preset.name, base_url: preset.base_url, api_key: '',
        model: preset.model || '', embedding_model: preset.embedding_model || '',
        enabled: true, note: preset.note || ''
      };
      await API.upsertProvider(body);
      UI.toast('已添加预设「' + preset.name + '」，请填写 API Key 并保存', 'success');
      await loadSettings();
    } catch (e) {
      UI.toast('添加失败：' + e.message, 'error');
    }
  }

  async function saveProvider(id) {
    const cur = state.settings && state.settings.providers ? state.settings.providers.find(function (p) { return p.id === id; }) : null;
    const val = function (f) {
      const el = document.getElementById('pv-' + id + '-' + f);
      return el ? el.value.trim() : '';
    };
    const enabledEl = document.getElementById('pv-' + id + '-enabled');
    const body = {
      id: id,
      name: val('name') || (cur ? cur.name : id),
      base_url: val('base'),
      api_key: val('key') || (cur ? cur.api_key : ''),
      model: val('model'),
      embedding_model: val('emb'),
      enabled: enabledEl ? enabledEl.checked : true,
      note: cur ? (cur.note || '') : ''
    };
    try {
      await API.upsertProvider(body);
      UI.toast('服务商「' + body.name + '」已保存', 'success');
      await loadSettings();
    } catch (e) {
      UI.toast('保存失败：' + e.message, 'error');
    }
  }

  async function deleteProvider(id, name) {
    if (!UI.confirm('确定删除服务商「' + name + '」？相关角色映射与默认设置会一并清理。')) return;
    try {
      await API.deleteProvider(id);
      UI.toast('服务商「' + name + '」已删除', 'success');
      await loadSettings();
    } catch (e) {
      UI.toast('删除失败：' + e.message, 'error');
    }
  }

  async function testProvider(id) {
    const keyEl = document.getElementById('pv-' + id + '-key');
    const apiKey = keyEl ? keyEl.value.trim() : '';
    try {
      const r = await API.testProvider(id, apiKey);
      UI.toast((r && r.ok ? '✅ ' : '❌ ') + ((r && r.message) || (r && r.ok ? '连接成功' : '连接失败')),
        (r && r.ok) ? 'success' : 'error', 6000);
    } catch (e) {
      UI.toast('测试失败：' + e.message, 'error', 6000);
    }
  }

  async function saveDefaultProvider() {
    try {
      const r = await API.saveSettings({ default_provider_id: $('#defaultProviderSel').value });
      state.settings = r;
      UI.toast('默认服务商已保存', 'success');
    } catch (e) {
      UI.toast('保存失败：' + e.message, 'error');
    }
  }

  async function saveRoleProviders() {
    const role_providers = {};
    ROLES.forEach(function (r) {
      const el = $('#role-' + r[0]);
      if (el && el.value) role_providers[r[0]] = el.value;
    });
    try {
      const r = await API.saveSettings({ role_providers: role_providers });
      state.settings = r;
      UI.toast('角色映射已保存', 'success');
    } catch (e) {
      UI.toast('保存失败：' + e.message, 'error');
    }
  }

  async function saveDownloadDir() {
    try {
      const r = await API.saveSettings({ download_dir: $('#downloadDir').value.trim() });
      state.settings = r;
      UI.toast('源文件保存目录已更新', 'success');
    } catch (e) {
      UI.toast('保存失败：' + e.message, 'error');
    }
  }

  async function saveSearchOptions() {
    const search_options = {
      max_results_per_source: parseInt($('#soMaxPer').value, 10) || 10,
      max_total_results: parseInt($('#soMaxTotal').value, 10) || 80,
      request_timeout: parseInt($('#soTimeout').value, 10) || 30
    };
    try {
      const r = await API.saveSettings({ search_options: search_options });
      state.settings = r;
      UI.toast('检索参数已保存', 'success');
    } catch (e) {
      UI.toast('保存失败：' + e.message, 'error');
    }
  }

  /* ============================================================
   * 初始化
   * ============================================================ */

  function bindShell() {
    document.querySelectorAll('.nav-item').forEach(function (b) {
      b.addEventListener('click', function () { goto(b.getAttribute('data-view')); });
    });
    // api.js 通过事件广播后端可达性，banner 自动同步
    window.addEventListener('api:online', function () { setBackendState(true); });
    window.addEventListener('api:offline', function () { setBackendState(false); });
    // 未捕获的 Promise 异常兜底为 toast，避免静默失败
    window.addEventListener('unhandledrejection', function (e) {
      const msg = (e.reason && e.reason.message) ? e.reason.message : '发生未知错误';
      if (!/NetworkError|ApiError/.test(msg)) UI.toast('操作失败：' + msg, 'error');
    });
  }

  async function init() {
    UI.bind();
    bindShell();
    goto('overview');
    await checkBackend();
    await Promise.all([loadSettings(), loadTasks(), loadStats()]);
    goto(state.view); // 数据就绪后重渲染当前视图
  }

  /* ================= 对外暴露（供 inline onclick 调用） ================= */

  window.App = {
    goto: goto,
    retryBackend: retryBackend,
    // 任务
    createTask: createTask,
    deleteTask: deleteTask,
    openTask: openTask,
    closeTask: closeTask,
    toggleTaskEdit: toggleTaskEdit,
    saveTaskEdit: saveTaskEdit,
    startSearch: startSearch,
    // 文献
    applyPaperFilters: applyPaperFilters,
    resetPaperFilters: resetPaperFilters,
    toggleOrder: toggleOrder,
    gotoPage: gotoPage,
    changePageSize: changePageSize,
    toggleSelectAll: toggleSelectAll,
    togglePaperSelect: togglePaperSelect,
    toggleCollect: toggleCollect,
    batchCollect: batchCollect,
    openPaperDrawer: openPaperDrawer,
    imgFail: imgFail,
    toggleCollectFromDrawer: toggleCollectFromDrawer,
    summarizePaper: summarizePaper,
    translatePaper: translatePaper,
    parseFulltext: parseFulltext,
    previewFileByPath: previewFileByPath,
    // 文献库
    libTaskChange: libTaskChange,
    applyLibFilter: applyLibFilter,
    gotoLibPage: gotoLibPage,
    changeLibPageSize: changeLibPageSize,
    toggleLibSelect: toggleLibSelect,
    toggleLibSelectAll: toggleLibSelectAll,
    startSurvey: startSurvey,
    // 开题报告
    propTaskChange: propTaskChange,
    uploadTemplate: uploadTemplate,
    toggleSectionInstr: toggleSectionInstr,
    toggleSectionPreview: toggleSectionPreview,
    generateSection: generateSection,
    generateAll: generateAll,
    openSectionEditor: openSectionEditor,
    editorTab: editorTab,
    saveSection: saveSection,
    exportProposal: exportProposal,
    // 评审与答辩
    revTaskChange: revTaskChange,
    startReview: startReview,
    applyReview: applyReview,
    confirmApply: confirmApply,
    confirmApplyFromPicker: confirmApplyFromPicker,
    gotoSectionPreview: gotoSectionPreview,
    startDefense: startDefense,
    // 设置
    addPreset: addPreset,
    saveProvider: saveProvider,
    deleteProvider: deleteProvider,
    testProvider: testProvider,
    saveDefaultProvider: saveDefaultProvider,
    saveRoleProviders: saveRoleProviders,
    saveDownloadDir: saveDownloadDir,
    saveSearchOptions: saveSearchOptions
  };

  init();

})();
