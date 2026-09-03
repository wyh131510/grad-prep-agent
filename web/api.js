/* ==========================================================================
 * api.js —— 后端 API 封装层（严格按 docs/API.md v1.0 契约）
 * - 所有接口使用相对路径 /api/...，不写死主机地址
 * - 错误处理：HTTP 非 2xx 时读取 {"detail": ...} 抛出带说明的 Error；
 *   网络层失败（后端未启动 / 以 file:// 打开）抛出「后端未连接」错误
 * - 长任务（检索/生成/评审/下载）统一返回 {"job_id": "..."}，
 *   由 app.js 用 EventSource('/api/jobs/{id}/events') 订阅进度
 * ========================================================================== */
'use strict';
(function () {

  const BASE = '/api';

  /**
   * 通用请求封装。
   * @param {string} method HTTP 方法
   * @param {string} path   以 / 开头的接口路径
   * @param {*} body        请求体（isForm 为 true 时传 FormData）
   * @param {boolean} isForm 是否 multipart 上传
   */
  async function request(method, path, body, isForm) {
    let res;
    try {
      const opts = { method: method, headers: {} };
      if (body !== undefined && body !== null) {
        if (isForm) {
          opts.body = body; // FormData：浏览器自动设置 boundary
        } else {
          opts.headers['Content-Type'] = 'application/json';
          opts.body = JSON.stringify(body);
        }
      }
      res = await fetch(BASE + path, opts);
    } catch (e) {
      // 网络层失败：后端未启动，或页面以 file:// 协议打开
      window.dispatchEvent(new Event('api:offline'));
      const err = new Error('无法连接后端服务，请确认后端已启动');
      err.name = 'NetworkError';
      throw err;
    }

    // 只要能收到 HTTP 响应，说明后端在线
    window.dispatchEvent(new Event('api:online'));

    let data = null;
    try { data = await res.json(); } catch (e) { data = null; }

    if (!res.ok) {
      const detail = (data && (data.detail || data.message)) || ('请求失败（HTTP ' + res.status + '）');
      const err = new Error(detail);
      err.name = 'ApiError';
      err.status = res.status;
      throw err;
    }
    return data;
  }

  const API = {
    request: request,
    get: function (p) { return request('GET', p); },
    post: function (p, b) { return request('POST', p, b); },
    put: function (p, b) { return request('PUT', p, b); },
    del: function (p) { return request('DELETE', p); },
    upload: function (p, form) { return request('POST', p, form, true); },

    /** 是否为网络层失败（后端不可达） */
    isNetworkError: function (e) { return !!e && e.name === 'NetworkError'; },
    /** 是否为 404（契约中多处「无则 404」） */
    isNotFound: function (e) { return !!e && e.name === 'ApiError' && e.status === 404; },

    /* ---------------- 系统 ---------------- */
    health: function () { return API.get('/health'); },
    stats: function () { return API.get('/stats'); },

    /* ---------------- 设置 ---------------- */
    settings: function () { return API.get('/settings'); },
    saveSettings: function (part) { return API.put('/settings', part); },
    presets: function () { return API.get('/settings/presets'); },
    upsertProvider: function (p) { return API.post('/settings/providers', p); },
    deleteProvider: function (id) { return API.del('/settings/providers/' + encodeURIComponent(id)); },
    testProvider: function (id, apiKey) {
      return API.post('/settings/providers/' + encodeURIComponent(id) + '/test', { api_key: apiKey || '' });
    },

    /* ---------------- 任务 ---------------- */
    tasks: function () { return API.get('/tasks'); },
    createTask: function (body) { return API.post('/tasks', body); },
    /** 编辑任务检索条件（部分更新：topic/major/year_from/year_to/sources/requirements/urls 均可选） */
    updateTask: function (id, body) { return API.put('/tasks/' + encodeURIComponent(id), body); },
    deleteTask: function (id) { return API.del('/tasks/' + encodeURIComponent(id)); },
    task: function (id) { return API.get('/tasks/' + encodeURIComponent(id)); },
    /** 启动检索 Job；feedback 为用户补充的检索反馈（可选） */
    startSearch: function (id, feedback) {
      return API.post('/tasks/' + encodeURIComponent(id) + '/search', { feedback: feedback || '' });
    },
    /** 选题拆解计划；未生成时 404 */
    plan: function (id) { return API.get('/tasks/' + encodeURIComponent(id) + '/plan'); },

    /* ---------------- 文献 ---------------- */
    papers: function (taskId, query) {
      const qs = new URLSearchParams();
      Object.keys(query || {}).forEach(function (k) {
        const v = query[k];
        if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
      });
      const q = qs.toString();
      return API.get('/tasks/' + encodeURIComponent(taskId) + '/papers' + (q ? '?' + q : ''));
    },
    paper: function (id) { return API.get('/papers/' + encodeURIComponent(id)); },
    /** 全局文献接口（文献库视图）：GET /api/papers?q=&collected=true&sort=&order=&limit=&offset= */
    allPapers: function (query) {
      const qs = new URLSearchParams();
      Object.keys(query || {}).forEach(function (k) {
        const v = query[k];
        if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
      });
      const q = qs.toString();
      return API.get('/papers' + (q ? '?' + q : ''));
    },
    /** 收藏（可选自动下载源文件），返回 Job */
    collect: function (pid, download) {
      return API.post('/papers/' + encodeURIComponent(pid) + '/collect', { download: download !== false });
    },
    /** 取消收藏（同时删除本地文件与图片） */
    uncollect: function (pid) { return API.del('/papers/' + encodeURIComponent(pid) + '/collect'); },
    /** 批量收藏，返回 Job */
    batchCollect: function (taskId, ids, download) {
      return API.post('/tasks/' + encodeURIComponent(taskId) + '/papers/collect', {
        paper_ids: ids, download: download !== false
      });
    },
    summarize: function (pid) { return API.post('/papers/' + encodeURIComponent(pid) + '/summarize', {}); },
    translate: function (pid) { return API.post('/papers/' + encodeURIComponent(pid) + '/translate', {}); },
    /** 解析全文 / 提取图表（关键片段、真实图表），返回 Job */
    parseFulltext: function (pid) { return API.post('/papers/' + encodeURIComponent(pid) + '/parse_fulltext', {}); },
    /** 多篇调研综述（主题聚类），返回 Job */
    survey: function (taskId, ids) {
      return API.post('/tasks/' + encodeURIComponent(taskId) + '/survey', { paper_ids: ids });
    },
    getSurvey: function (taskId) { return API.get('/tasks/' + encodeURIComponent(taskId) + '/survey'); },

    /* ---------------- 开题报告 ---------------- */
    /** 上传学校模板（multipart: file 字段） */
    uploadTemplate: function (taskId, form) {
      return API.upload('/tasks/' + encodeURIComponent(taskId) + '/template', form);
    },
    template: function (taskId) { return API.get('/tasks/' + encodeURIComponent(taskId) + '/template'); },
    proposal: function (taskId) { return API.get('/tasks/' + encodeURIComponent(taskId) + '/proposal'); },
    /** 生成单个分块，返回 Job */
    generateSection: function (taskId, key, instruction) {
      return API.post('/tasks/' + encodeURIComponent(taskId) + '/proposal/sections/' + encodeURIComponent(key) + '/generate',
        { instruction: instruction || '' });
    },
    /** 用户手动保存分块 */
    saveSection: function (taskId, key, content) {
      return API.put('/tasks/' + encodeURIComponent(taskId) + '/proposal/sections/' + encodeURIComponent(key), { content: content });
    },
    /** 一键生成全部空分块，返回 Job */
    generateAll: function (taskId) {
      return API.post('/tasks/' + encodeURIComponent(taskId) + '/proposal/generate_all', {});
    },

    /* ---------------- 评审与答辩 ---------------- */
    startReview: function (taskId) { return API.post('/tasks/' + encodeURIComponent(taskId) + '/review', {}); },
    review: function (taskId) { return API.get('/tasks/' + encodeURIComponent(taskId) + '/review'); },
    /** 依据评审意见辅助修改某分块，返回 Job */
    applyReview: function (taskId, section, instruction) {
      return API.post('/tasks/' + encodeURIComponent(taskId) + '/review/apply',
        { section: section, instruction: instruction || '' });
    },
    startDefense: function (taskId) { return API.post('/tasks/' + encodeURIComponent(taskId) + '/defense', {}); },
    defense: function (taskId) { return API.get('/tasks/' + encodeURIComponent(taskId) + '/defense'); }
  };

  window.API = API;
})();
