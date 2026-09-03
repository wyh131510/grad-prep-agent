# grad-prep-agent API 契约 v1.0

> 本文件是前后端并行开发的唯一契约。后端 `app/` 与前端 `web/` 必须严格按此实现。
> 基地址：`http://127.0.0.1:8000`，所有接口前缀 `/api`。
> 请求/响应均为 JSON（文件上传除外）。错误响应统一为 `{"detail": "错误说明"}`，HTTP 状态码 4xx/5xx。

## 通用约定

- 时间字段格式：ISO 8601 字符串，如 `2025-01-15T10:30:00`
- 长任务（检索/生成/评审/下载）统一为**后台 Job**，通过 SSE 推送进度：
  - 启动接口立即返回 `{"job_id": "..."}`
  - 前端用 `EventSource('/api/jobs/{job_id}/events')` 订阅进度
- SSE 事件格式（每条带自增 id）：
  ```
  id: 3
  event: log
  data: {"progress": 0.42, "message": "正在抓取 arXiv..."}
  ```
  - `event: log`     data = `{progress: 0~1, message: str}`（进度+说明）
  - `event: result`  data = 任务结果对象（因任务而异，见各接口）
  - `event: error`   data = `{message: str}`
  - 服务端发送 `error` 或 `result` 后关闭流（任务终结）
- Job 查询：`GET /api/jobs/{job_id}` → `{id, type, label, status: "running"|"done"|"error", progress, message, result, error}`

## 数据模型

### Task（调研任务）
```json
{
  "id": "t_ab12cd",
  "topic": "基于深度学习的路面裂缝检测方法研究",
  "major": "计算机科学与技术",
  "year_from": 2019, "year_to": 2025,
  "sources": ["semantic_scholar", "arxiv", "crossref", "cnki"],
  "requirements": "重点关注轻量化模型",
  "urls": [],                           // 可选：用户提供的文献直链（HTML/PDF，整篇解析入库）
  "status": "created|searching|searched|failed",
  "plan": null,                       // TopicPlan，搜索完成后写入
  "paper_count": 0,
  "collected_count": 0,
  "created_at": "2025-01-15T10:30:00"
}
```

### TopicPlan（选题拆解计划）
```json
{
  "sub_questions": [
    {
      "question": "路面裂缝检测常用的深度学习模型有哪些？",
      "rationale": "摸清主流方法",
      "queries": [
        {"text": "pavement crack detection deep learning", "lang": "en"},
        {"text": "路面裂缝检测 深度学习", "lang": "zh"}
      ]
    }
  ]
}
```

### Paper（统一解析后的文献）
```json
{
  "id": "p_3f9a2c1d",
  "task_id": "t_ab12cd",
  "title": "DeepCrack: Learning Hierarchical Convolutional Features for Crack Detection",
  "title_zh": "",                      // 翻译后填充
  "authors": ["Qin Zou", "Zhang Zhang"],
  "year": 2019,
  "venue": "IEEE TIP",
  "source": "semantic_scholar",        // semantic_scholar|arxiv|crossref|pubmed|openalex|direct_url|import
  "doi": "10.1109/TIP.2018.2878966",
  "arxiv_id": "",
  "url": "https://...",
  "pdf_url": "https://...",            // 可能为空
  "abstract": "原文摘要……",
  "abstract_zh": "",                   // 翻译后填充
  "keywords": ["crack detection"],
  "citations": 620,
  "is_open_access": true,
  "snippets": [                        // 关键片段（来自全文解析，可能为空数组）
    {"text": "……", "section": "3.2 网络结构", "page": 4}
  ],
  "figures": [                         // 图表说明：真实来自文献解析，无则空数组
    {"caption": "Fig. 2. 网络结构图", "description": "……", "page": 5, "image": "t_ab12cd/p_xxx/fig_2.png"}
  ],
  "score": 0.87,                       // 混合检索最终分 0~1
  "bm25_score": 0.82, "vector_score": 0.0, "rerank_score": 0.91,
  "collected": false,
  "file_path": "",                     // 收藏下载后的本地相对路径（相对 download_dir）
  "download_status": "none",           // none | downloading | done | failed（下载状态可视化）
  "download_note": "",                 // 下载失败原因说明
  "summary": null,                     // PaperSummary，单篇总结后填充
  "translation": null,                 // TranslationResult，翻译后填充
  "created_at": "2025-01-15T10:35:00"
}
```

### PaperSummary（单篇结构化总结）
```json
{
  "research_question": "……",
  "method": "……",
  "contributions": ["……"],
  "dataset": "……",
  "metrics": "……",
  "limitations": "……",
  "relevance_to_topic": "……",         // 与我的选题的关联与可用之处
  "key_points": ["……"],
  "language": "zh"
}
```

### TranslationResult
```json
{
  "title_zh": "……",
  "abstract_zh": "……",
  "snippets_zh": ["关键片段1译文", "关键片段2译文"],
  "glossary": {"crack detection": "裂缝检测", "……": "……"},
  "quality_note": "术语一致性已按词汇表对齐"
}
```

### ProposalSection（开题报告分块）
```json
{"key": "background", "title": "课题背景与研究意义", "content": "Markdown……", "status": "empty|draft|edited", "updated_at": "..."}
```
默认分块 key（模板上传后以模板检测为准）：
`background`（课题背景与研究意义）、`literature_review`（国内外研究现状）、`objectives`（研究内容与目标）、`methodology`（研究方案与技术路线）、`feasibility`（可行性分析）、`schedule`（进度安排）、`references`（参考文献）

### ReviewIssue / ReviewResult / MergedReview
```json
// ReviewResult（单个评审 Agent 输出）
{
  "agent": "academic",                  // academic|logic|feasibility|format
  "agent_name": "学术规范评审",
  "provider_id": "deepseek", "model": "deepseek-chat",
  "score": 82,                          // 0~100
  "summary": "总体评价……",
  "issues": [
    {"severity": "high|medium|low", "section": "literature_review", "problem": "……", "suggestion": "……", "evidence": "……"}
  ]
}
// MergedReview（一致性汇总）
{
  "overall_score": 80,
  "verdict": "修改后通过",
  "conflicts": [{"topic": "……", "opinions": ["评审A认为……", "评审B认为……"], "resolution": "……"}],
  "final_suggestions": [{"priority": 1, "section": "……", "action": "……", "reason": "……"}],
  "strengths": ["……"]
}
```

### ProviderConfig（大模型服务商）
```json
{"id": "deepseek", "name": "DeepSeek", "base_url": "https://api.deepseek.com/v1",
 "api_key": "sk-...", "model": "deepseek-chat", "embedding_model": "",
 "enabled": true}
```

### Settings
```json
{
  "download_dir": "D:/path/to/files",   // 源文件保存目录，可改
  "default_provider_id": "deepseek",    // 默认服务商；空则取第一个启用的
  "role_providers": {                   // 角色 → 服务商映射；未配置的角色用默认服务商
    "planner": "deepseek", "summary": "deepseek", "translate": "deepseek",
    "proposal": "deepseek", "academic": "deepseek", "logic": "moonshot",
    "feasibility": "deepseek", "format": "deepseek", "coordinator": "deepseek",
    "defense": "deepseek"
  },
  "search_options": {"max_results_per_source": 10, "max_total_results": 80, "request_timeout": 30},
  "providers": [ /* ProviderConfig[] */ ]
}
```

---

## 接口清单

### 0. 系统
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | `{"status":"ok","version":"0.1.0","optional":{"embedding":true,"ocr":false}}` |
| GET | `/api/stats` | 概览统计：`{tasks, papers, collected, proposals, reviews}`（任务数/文献数/收藏数/有初稿任务数/已评审任务数） |
| GET | `/api/jobs` | 最近 20 个 Job 快照数组 |
| GET | `/api/jobs/{job_id}` | 单个 Job 快照 |
| GET | `/api/jobs/{job_id}/events` | SSE 进度流（EventSource） |
| GET | `/api/files/preview?path=files/t_xxx/p_xxx/fig_1.png` | 预览本地保存的文件（图片/PDF），仅限 download_dir 内，路径非法返回 403 |

### 1. 设置
| 方法 | 路径 | 请求 | 说明 |
|---|---|---|---|
| GET | `/api/settings` | — | 完整 Settings |
| PUT | `/api/settings` | 部分 Settings 字段 | 更新 download_dir/default_provider_id/role_providers/search_options |
| GET | `/api/settings/presets` | — | 内置服务商预设（无 key）数组 |
| POST | `/api/settings/providers` | ProviderConfig | 新增或按 id 覆盖 |
| DELETE | `/api/settings/providers/{provider_id}` | — | 删除服务商 |
| POST | `/api/settings/providers/{provider_id}/test` | `{"api_key": "可选，覆盖已存 key"}` | `{"ok": true, "message": "连接成功，模型响应正常"}` |

### 2. 任务
| 方法 | 路径 | 请求 | 说明 |
|---|---|---|---|
| POST | `/api/tasks` | `{topic, major, year_from, year_to, sources[], requirements, urls[]}` | 创建任务，返回 Task；urls 为可选的文献直链列表 |
| GET | `/api/tasks` | — | 任务列表（新→旧） |
| GET | `/api/tasks/{task_id}` | — | 任务详情（含 plan） |
| PUT | `/api/tasks/{task_id}` | `{topic, major, year_from, year_to, sources[], requirements, urls[]}`（均可选） | 编辑任务参数（年份/来源等），便于调整后重新检索 |
| DELETE | `/api/tasks/{task_id}` | — | 级联删除任务及其文献 |
| POST | `/api/tasks/{task_id}/import` | multipart: `file`(txt/ris) | 导入知网等导出的 EndNote/RIS 文献记录，返回 Job |
| POST | `/api/tasks/{task_id}/search` | `{"feedback": "可选，用户补充的检索反馈"}` | 启动检索 Job：拆解选题→多源抓取→解析→混合检索排序 |
| GET | `/api/tasks/{task_id}/plan` | — | 返回 TopicPlan；未生成时 404 |

**search Job 的 result**：`{"papers": 60, "plan": {...}, "queries": 24, "sources_ok": [...], "sources_failed": [...]}`

### 3. 文献
| 方法 | 路径 | 请求 | 说明 |
|---|---|---|---|
| GET | `/api/papers` | query: `q` `task_id`(可选) `collected` `sort` `order` `limit` `offset` | 全局文献列表（文献库页使用），返回 `{"total": n, "items": [Paper]}` |
| GET | `/api/tasks/{task_id}/papers` | query: `q`(标题/摘要关键词) `year_from` `year_to` `source` `collected` `sort`(score|year|citations|title) `order`(desc|asc) `limit` `offset` | 返回 `{"total": n, "items": [Paper]}`；未收藏文献 default sort=score |
| GET | `/api/papers/{paper_id}` | — | Paper 完整详情 |
| POST | `/api/papers/{paper_id}/collect` | `{"download": true}` | 收藏（可选自动下载源文件；下载后自动解析全文提取关键片段与图表），返回 Job |
| DELETE | `/api/papers/{paper_id}/collect` | — | 取消收藏，**同时删除该文献的本地文件与图片目录**（仅其自身文件夹），返回 `{"ok": true}` |
| POST | `/api/papers/{paper_id}/parse_fulltext` | `{}` | 按需解析全文：下载 PDF 提取关键片段/图表/表格；无 PDF 时（如 PubMed）从来源页提取真实图表，返回 Job |
| POST | `/api/tasks/{task_id}/papers/collect` | `{"paper_ids": [...], "download": true}` | 批量收藏，返回 Job |
| POST | `/api/papers/{paper_id}/summarize` | `{}` | 单篇结构化总结，返回 Job |
| POST | `/api/papers/{paper_id}/translate` | `{}` | 标题+摘要翻译（含术语表），返回 Job |
| POST | `/api/tasks/{task_id}/survey` | `{"paper_ids": [...]}` | 多篇调研综述（主题聚类），返回 Job |

**collect Job result**：`{"collected": 10, "downloaded": 7, "failed": [{"title":"...","reason":"无开放获取 PDF"}]}`
**summarize Job result**：PaperSummary（同时写回 paper.summary）
**translate Job result**：TranslationResult（同时写回 paper.title_zh/abstract_zh/translation）
**survey Job result**：`{"clusters": [{"theme": "...", "papers": ["p_xxx", ...], "summary": "..."}], "content": "Markdown 综述全文"}`（另存于 GET survey）

| GET | `/api/tasks/{task_id}/survey` | — | `{"content": "...", "clusters": [...], "created_at": "..."}`；无则 404 |

### 4. 开题报告
| 方法 | 路径 | 请求 | 说明 |
|---|---|---|---|
| POST | `/api/tasks/{task_id}/template` | multipart: `file`(docx/pdf/md/txt) | 上传学校模板，解析为文本并检测分块；返回 `{filename, content_md, sections: ["background", ...]}` |
| GET | `/api/tasks/{task_id}/template` | — | 同上；未上传 404 |
| GET | `/api/tasks/{task_id}/proposal` | — | `{"sections": [ProposalSection]}`（模板存在时按模板分块，否则默认分块） |
| POST | `/api/tasks/{task_id}/proposal/sections/{key}/generate` | `{"instruction": "可选：本节的额外要求"}` | 生成单个分块，返回 Job |
| PUT | `/api/tasks/{task_id}/proposal/sections/{key}` | `{"content": "Markdown"}` | 用户手动修改/保存分块 |
| POST | `/api/tasks/{task_id}/proposal/generate_all` | `{}` | 依次生成所有空分块，返回 Job |
| GET | `/api/tasks/{task_id}/proposal/export` | query: `format=md|docx` | 下载合并后的完整报告 |

**section generate Job result**：`{"key": "background", "content": "Markdown"}`（同时写回）
**generate_all Job result**：`{"generated": ["background", ...], "failed": []}`

### 5. 评审与答辩
| 方法 | 路径 | 请求 | 说明 |
|---|---|---|---|
| POST | `/api/tasks/{task_id}/review` | `{}` | 启动多智能体评审（4 角色并行 + 一致性汇总），返回 Job |
| GET | `/api/tasks/{task_id}/review` | — | `{"results": [ReviewResult×4], "merged": MergedReview, "created_at": "..."}`；无则 404 |
| POST | `/api/tasks/{task_id}/review/apply` | `{"section": "background", "instruction": "可选补充要求"}` | 依据评审意见辅助修改某分块，返回 Job |
| POST | `/api/tasks/{task_id}/defense` | `{}` | 生成答辩问题清单，返回 Job |
| GET | `/api/tasks/{task_id}/defense` | — | `{"content": "Markdown", "created_at": "..."}`；无则 404 |

**review Job result**：`{"results": [...], "merged": {...}}`（同时写回）
**apply Job result**：`{"key": "background", "content": "修改后的 Markdown"}`（同时写回）
**defense Job result**：`{"content": "Markdown 问题清单"}`（同时写回）

---

## 前端页面要求（6 个视图，SPA，无路由库）

1. **概览**：项目介绍 + 全流程示意 + 统计卡片（/api/stats）+ 快速开始按钮（跳到任务页）。
2. **任务与检索**：创建任务表单（选题/专业/年份/来源多选/补充要求）→ 任务卡片列表 → 任务详情：启动检索、SSE 进度条+日志流、选题拆解计划展示（子问题+查询词）、文献表格（筛选：关键词/年份/来源/已收藏；排序：相关度/年份/被引）、每行勾选收藏、点开详情抽屉（摘要/关键片段/图表图片/单篇总结/翻译按钮）。
3. **文献库**：所有已收藏文献（按任务分组或平铺+筛选）→ 单篇：总结/翻译展示、打开本地文件 → 多选生成综述（主题聚类结果 + 综述全文 Markdown 渲染）。
4. **开题报告**：模板上传（含解析结果预览）→ 分块列表：状态徽章（空/草稿/已编辑）、生成按钮（可带额外说明）、Markdown 编辑器（textarea+预览切换）、导出 md/docx。
5. **评审与答辩**：评审按钮 → 4 个评审 Agent 结果卡片（分数、总结、问题列表，按 severity 着色）+ 一致性汇总（冲突与裁决、最终修改建议）→ 一键辅助修改某分块 → 答辩问题清单生成与展示。
6. **设置**：服务商管理（预设一键填充、增删改、连接测试）、默认服务商与角色映射（下拉选择）、源文件保存目录（可编辑）、检索参数（每源结果数/总数上限/超时）。

## 前端实现约束

- 纯静态：`web/index.html` + `web/style.css` + `web/app.js`（可拆多文件），**无构建步骤、无外部 CDN**（离线可用）。
- 技术：原生 JS + fetch + EventSource；自带一个最小 Markdown 渲染器（标题/列表/表格/加粗/斜体/链接/代码块/引用即可）。
- 视觉：参考 `D:\dsh_workplace\project-design.html` 的设计语言（主色 `#4f46e5`，渐变 hero，卡片+圆角+阴影，中文字体栈）；侧边栏导航布局。
- 交互细节：所有长任务走 SSE 进度条+日志；错误 toast；空状态提示；危险操作（删除任务）confirm；API Key 输入框密码型、显示时脱敏（只显示后 4 位）；未配置服务商时在各功能入口给出去设置页的引导链接。
- 文件预览：图片用 `<img src="/api/files/preview?path=...">`，PDF 用 `<iframe src="/api/files/preview?path=...">`。
- 不实现任何 mock 数据；后端接口按本契约全部可用。
