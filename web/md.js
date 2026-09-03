/* ==========================================================================
 * md.js —— 最小 Markdown 渲染器（纯 JS、零依赖、无 CDN）
 * 支持：#~###### 标题、- * + 无序列表、1. 有序列表、GFM 表格(|...|)、
 *        **加粗**、*斜体*、[文字](链接)、`行内代码`、```代码块```、
 *        > 引用、--- 分隔线、段落换行。
 * 安全：任何输入都先整体做 HTML 转义，再套用 Markdown 规则（防 XSS）。
 * 用法：MD.render(markdownText) → HTML 字符串
 * ========================================================================== */
'use strict';
(function () {

  /** HTML 转义（防 XSS 的第一道防线） */
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /** 链接地址白名单：仅允许 http/https/mailto/锚点/相对路径，其余一律 # */
  function safeUrl(u) {
    return /^(https?:|mailto:|ftp:|#|\/|\.\/|\.\.\/)/i.test(u) ? u : '#';
  }

  /** 行内规则（输入已转义，输出安全 HTML） */
  function inline(s) {
    return s
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
      .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, function (m, text, url) {
        return '<a href="' + safeUrl(url) + '" target="_blank" rel="noopener noreferrer">' + text + '</a>';
      });
  }

  /** 表格行拆分（去掉首尾 | 后按 | 切分） */
  function splitRow(line) {
    let t = line.trim();
    if (t.charAt(0) === '|') t = t.slice(1);
    if (t.charAt(t.length - 1) === '|') t = t.slice(0, -1);
    return t.split('|');
  }

  /** 是否为 GFM 表格分隔行（如 | --- | :---: |） */
  function isTableDelim(line) {
    return /^\s*\|?[\s:|-]+\|?\s*$/.test(line) && line.indexOf('-') !== -1;
  }

  /** 是否为需要截断「段落」的块级起始行 */
  function isBlockStart(line) {
    return /^(#{1,6})\s/.test(line)
      || /^\s*([-*_])(?:\s*\1){2,}\s*$/.test(line)
      || /^&gt;\s?/.test(line)
      || /^\s*[-*+]\s+/.test(line)
      || /^\s*\d+[.)]\s+/.test(line)
      || /^\u0000CODE\d+\u0000$/.test(line.trim())
      || line.trim().charAt(0) === '|';
  }

  /** 块级解析（输入为已转义文本，逐行处理） */
  function blocks(text) {
    const lines = text.split('\n');
    const out = [];
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (!line.trim()) { i++; continue; }

      /* ---- GFM 表格 ---- */
      if (line.trim().charAt(0) === '|' && i + 1 < lines.length && isTableDelim(lines[i + 1])) {
        const header = splitRow(line);
        const rows = [];
        let j = i + 2;
        while (j < lines.length && lines[j].trim().charAt(0) === '|') { rows.push(splitRow(lines[j])); j++; }
        let html = '<table><thead><tr>'
          + header.map(function (c) { return '<th>' + inline(c.trim()) + '</th>'; }).join('')
          + '</tr></thead><tbody>';
        rows.forEach(function (r) {
          html += '<tr>' + r.map(function (c) { return '<td>' + inline(c.trim()) + '</td>'; }).join('') + '</tr>';
        });
        html += '</tbody></table>';
        out.push(html);
        i = j;
        continue;
      }

      /* ---- 标题 #~###### ---- */
      const h = /^(#{1,6})\s+(.*)$/.exec(line);
      if (h) {
        const n = h[1].length;
        out.push('<h' + n + '>' + inline(h[2]) + '</h' + n + '>');
        i++;
        continue;
      }

      /* ---- 分隔线 --- ---- */
      if (/^\s*([-*_])(?:\s*\1){2,}\s*$/.test(line)) { out.push('<hr>'); i++; continue; }

      /* ---- 引用 > （转义后 > 变为 &gt;） ---- */
      if (/^&gt;\s?/.test(line)) {
        const q = [];
        while (i < lines.length && /^&gt;\s?/.test(lines[i])) {
          q.push(lines[i].replace(/^&gt;\s?/, ''));
          i++;
        }
        out.push('<blockquote>' + blocks(q.join('\n')) + '</blockquote>');
        continue;
      }

      /* ---- 无序列表 - * + ---- */
      if (/^\s*[-*+]\s+/.test(line)) {
        const items = [];
        while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
          items.push('<li>' + inline(lines[i].replace(/^\s*[-*+]\s+/, '')) + '</li>');
          i++;
        }
        out.push('<ul>' + items.join('') + '</ul>');
        continue;
      }

      /* ---- 有序列表 1. ---- */
      if (/^\s*\d+[.)]\s+/.test(line)) {
        const items = [];
        while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
          items.push('<li>' + inline(lines[i].replace(/^\s*\d+[.)]\s+/, '')) + '</li>');
          i++;
        }
        out.push('<ol>' + items.join('') + '</ol>');
        continue;
      }

      /* ---- 代码块占位符（转义前已提取，最后还原为 <pre>，不得包进 <p>） ---- */
      if (/^\u0000CODE\d+\u0000$/.test(line.trim())) { out.push(line.trim()); i++; continue; }

      /* ---- 段落：连续非空行合并，遇块级起始行截断，行内换行 ---- */
      const buf = [line];
      i++;
      while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i])) { buf.push(lines[i]); i++; }
      out.push('<p>' + buf.map(inline).join('<br>') + '</p>');
    }
    return out.join('\n');
  }

  /** 对外入口 */
  function render(src) {
    if (src === null || src === undefined) return '';
    let text = String(src).replace(/\r\n?/g, '\n');

    /* 1. 先提取围栏代码块，避免内部内容被转义或误解析 */
    const codes = [];
    text = text.replace(/```([^\n]*)\n([\s\S]*?)```/g, function (m, lang, code) {
      codes.push({ lang: (lang || '').trim(), code: code });
      return '\u0000CODE' + (codes.length - 1) + '\u0000';
    });

    /* 2. 整体 HTML 转义（防 XSS 关键一步） */
    text = esc(text);

    /* 3. 块级 + 行内解析 */
    let html = blocks(text);

    /* 4. 还原代码块（内容在还原时才转义） */
    html = html.replace(/\u0000CODE(\d+)\u0000/g, function (m, idx) {
      const c = codes[Number(idx)];
      if (!c) return '';
      const langTag = c.lang ? '<span class="md-code-lang">' + esc(c.lang) + '</span>' : '';
      return '<pre><code>' + langTag + esc(c.code) + '</code></pre>';
    });

    return html;
  }

  window.MD = { render: render };
})();
