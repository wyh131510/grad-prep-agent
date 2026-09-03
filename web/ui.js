/* ==========================================================================
 * ui.js —— 通用 UI 组件
 * toast 提示、危险操作确认、模态框、详情抽屉、全局任务进度面板、
 * 空状态、未配置大模型引导条、HTML 转义等工具函数。
 * 依赖：无（App 全局对象由 app.js 提供，仅用于引导条跳转）
 * ========================================================================== */
'use strict';
(function () {

  function $(sel) { return document.querySelector(sel); }

  /* ---------------- 基础工具 ---------------- */

  /** HTML 转义：所有插入 innerHTML 的用户数据必须先经过它（防 XSS） */
  function esc(s) {
    if (s === null || s === undefined) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /** 将任意 JS 值安全嵌入 onclick="..." 等以双引号定界的 HTML 属性 */
  function jsq(v) {
    return JSON.stringify(String(v))
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;');
  }

  /** 日期格式化：ISO 8601 → YYYY-MM-DD HH:mm */
  function fmtDate(s) {
    if (!s) return '—';
    const d = new Date(s);
    if (isNaN(d.getTime())) return String(s).slice(0, 16);
    const p = function (n) { return (n < 10 ? '0' : '') + n; };
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate())
      + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }

  /* ---------------- Toast ---------------- */

  const TOAST_ICONS = { info: 'ℹ️', success: '✅', error: '❌' };

  /**
   * 弹出全局提示
   * @param {string} msg 提示内容
   * @param {string} type info | success | error
   * @param {number} timeout 显示毫秒数（可选）
   */
  function toast(msg, type, timeout) {
    const box = $('#toastBox');
    if (!box) return;
    type = type || 'info';
    const t = document.createElement('div');
    t.className = 'toast toast-' + type;
    t.innerHTML = '<span class="toast-ico">' + (TOAST_ICONS[type] || TOAST_ICONS.info)
      + '</span><span class="toast-msg">' + esc(msg) + '</span>';
    box.appendChild(t);
    requestAnimationFrame(function () { t.classList.add('show'); });
    const ms = timeout || (type === 'error' ? 5000 : 3200);
    setTimeout(function () {
      t.classList.remove('show');
      setTimeout(function () { t.remove(); }, 320);
    }, ms);
    while (box.children.length > 5) box.removeChild(box.firstChild);
  }

  /** 危险操作确认框（原生 confirm） */
  function confirm(msg) { return window.confirm(msg); }

  /* ---------------- 小部件 ---------------- */

  /** 徽章/胶囊标签 */
  function badge(text, cls) {
    return '<span class="badge ' + (cls || '') + '">' + esc(text) + '</span>';
  }

  /** 空状态（图标 + 标题 + 说明 + 引导按钮） */
  function emptyState(icon, title, desc, actionHtml) {
    return '<div class="empty-state">'
      + '<div class="empty-icon">' + (icon || '📭') + '</div>'
      + '<div class="empty-title">' + esc(title) + '</div>'
      + (desc ? '<div class="empty-desc">' + esc(desc) + '</div>' : '')
      + (actionHtml ? '<div class="empty-action">' + actionHtml + '</div>' : '')
      + '</div>';
  }

  /** 未配置大模型服务商的醒目引导条（用于检索/总结/翻译/生成/评审入口） */
  function llmGuide(hint) {
    return '<div class="llm-guide">'
      + '<span class="llm-guide-ico">🤖</span>'
      + '<div class="llm-guide-body"><b>请先到设置页配置大模型 API</b>'
      + '<div>' + esc(hint || '本功能需要调用大模型（选题拆解 / 文献总结 / 翻译 / 初稿生成 / 评审等），当前尚未配置可用的服务商。') + '</div></div>'
      + '<button class="btn btn-white btn-sm" onclick="App.goto(\'settings\')">前往设置 →</button>'
      + '</div>';
  }

  /* ---------------- 模态框 ---------------- */

  function openModal(title, bodyHtml, wide) {
    const m = $('#modal');
    if (!m) return;
    $('#modalTitle').textContent = title || '';
    $('#modalBody').innerHTML = bodyHtml || '';
    m.classList.toggle('modal-wide', !!wide);
    $('#modalMask').hidden = false;
    m.hidden = false;
    document.body.classList.add('no-scroll');
  }
  function closeModal() {
    $('#modal').hidden = true;
    $('#modalMask').hidden = true;
    document.body.classList.remove('no-scroll');
  }

  /* ---------------- 详情抽屉 ---------------- */

  function openDrawer(title, bodyHtml) {
    $('#drawerTitle').textContent = title || '';
    $('#drawerBody').innerHTML = bodyHtml || '';
    $('#drawerMask').hidden = false;
    $('#drawer').hidden = false;
    document.body.classList.add('no-scroll');
  }
  function closeDrawer() {
    $('#drawer').hidden = true;
    $('#drawerMask').hidden = true;
    document.body.classList.remove('no-scroll');
  }

  /* ---------------- 全局任务进度面板（SSE 长任务） ---------------- */

  let jobHideTimer = null;

  const jobPanel = {
    /** 打开面板并初始化 */
    open: function (label) {
      const p = $('#jobPanel');
      if (!p) return;
      if (jobHideTimer) { clearTimeout(jobHideTimer); jobHideTimer = null; }
      $('#jobTitle').textContent = label || '任务进行中';
      $('#jobSub').textContent = '准备中…';
      $('#jobState').textContent = '';
      $('#jobBar').style.width = '0%';
      $('#jobPercent').textContent = '0%';
      $('#jobLog').innerHTML = '';
      p.classList.remove('job-done', 'job-error');
      p.hidden = false;
    },
    /** event: log → 更新进度条（0~1）+ 日志行 */
    log: function (progress, message) {
      const p = $('#jobPanel');
      if (!p || p.hidden) return;
      const pct = Math.max(0, Math.min(100, Math.round((Number(progress) || 0) * 100)));
      $('#jobBar').style.width = pct + '%';
      $('#jobPercent').textContent = pct + '%';
      if (message) {
        $('#jobSub').textContent = message;
        const line = document.createElement('div');
        line.className = 'job-log-line';
        line.textContent = '[' + new Date().toLocaleTimeString() + '] ' + message;
        const logEl = $('#jobLog');
        logEl.appendChild(line);
        logEl.scrollTop = logEl.scrollHeight;
        while (logEl.children.length > 200) logEl.removeChild(logEl.firstChild);
      }
    },
    /** event: result → 完成态 */
    done: function (message) {
      const p = $('#jobPanel');
      if (!p || p.hidden) return;
      $('#jobBar').style.width = '100%';
      $('#jobPercent').textContent = '100%';
      $('#jobSub').textContent = message || '任务完成';
      $('#jobState').textContent = '✔ 已完成';
      p.classList.remove('job-error');
      p.classList.add('job-done');
      this._scheduleHide();
    },
    /** event: error → 失败态 */
    fail: function (message) {
      const p = $('#jobPanel');
      if (!p || p.hidden) return;
      $('#jobState').textContent = '✘ 失败';
      $('#jobSub').textContent = message || '任务执行失败';
      p.classList.remove('job-done');
      p.classList.add('job-error');
      this._scheduleHide();
    },
    cancelHide: function () { if (jobHideTimer) { clearTimeout(jobHideTimer); jobHideTimer = null; } },
    resumeHide: function () { this._scheduleHide(); },
    _scheduleHide: function () {
      if (jobHideTimer) clearTimeout(jobHideTimer);
      jobHideTimer = setTimeout(function () {
        const p = $('#jobPanel');
        if (p) p.hidden = true;
        jobHideTimer = null;
      }, 5000);
    },
    close: function () {
      const p = $('#jobPanel');
      if (p) p.hidden = true;
      if (jobHideTimer) { clearTimeout(jobHideTimer); jobHideTimer = null; }
    }
  };

  /* ---------------- 全局事件绑定 ---------------- */

  function bind() {
    $('#drawerClose').addEventListener('click', closeDrawer);
    $('#drawerMask').addEventListener('click', closeDrawer);
    $('#modalClose').addEventListener('click', closeModal);
    $('#modalMask').addEventListener('click', closeModal);

    const jp = $('#jobPanel');
    $('#jobClose').addEventListener('click', function () { jobPanel.close(); });
    jp.addEventListener('mouseenter', function () { jobPanel.cancelHide(); });
    jp.addEventListener('mouseleave', function () { jobPanel.resumeHide(); });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { closeModal(); closeDrawer(); }
    });
  }

  window.UI = {
    esc: esc,
    jsq: jsq,
    fmtDate: fmtDate,
    toast: toast,
    confirm: confirm,
    badge: badge,
    emptyState: emptyState,
    llmGuide: llmGuide,
    openModal: openModal,
    closeModal: closeModal,
    openDrawer: openDrawer,
    closeDrawer: closeDrawer,
    jobPanel: jobPanel,
    bind: bind
  };
})();
