# tests/ —— 验证与评测套件

对应 `project-design.html`「验证与评测方案」一节：用可量化标准验证「检索 → 解析 → 摘要 → 翻译 → 评审」全链路。接口契约见 `docs/API.md`。

## 1. 目录结构

```
tests/
├── test_cases.md            # 20 条测试用例（5 类，含预埋问题标准答案与人工评分表）
├── sample_topics.json       # 10 个选题（5 个专业各 2 个；前 5 个为 A 类评测选题，后 5 个为同专业对照选题）
├── translation_samples.json # 10 段英文标题+摘要样本（5 领域各 2 段，含 key_terms 标准译法）
├── proposals/               # E 类：5 篇预埋问题的开题报告初稿 + 标准答案
│   ├── proposal_N.md        #   第 N 稿（用 ## 标题分节，节名与默认分块一致）
│   └── defects_N.json       #   第 N 稿预埋问题标准答案（2~3 条，各含 1~3 个命中关键词）
├── eval_retrieval.py        # A 检索召回评测
├── eval_summary.py          # C 文献摘要评测
├── eval_translation.py      # D 翻译质量评测
├── eval_review.py           # E 评审有效性评测
├── output/                  # 脚本自动创建；评测产物（gitignore 已忽略）
└── .gitignore
```

## 2. 评测准备

1. **启动服务**：在项目根目录执行 `python run.py`（或双击 `start.bat`），默认监听 `http://127.0.0.1:8000`。
   验证：浏览器或脚本访问 `GET /api/health`，应返回 `{"status":"ok",...}`。
2. **配置 API Key**：在 Web 设置页添加服务商并填入 API Key（或通过 `POST /api/settings/providers`），
   确保默认服务商与各角色（planner/summary/translate/proposal/academic/logic/feasibility/format/coordinator）映射齐全。
   未配置时脚本会收到接口错误并打印 SKIP 原因退出。
3. **可选依赖**：
   - Python 3.8+，`pip install requests`（4 个脚本唯一第三方依赖）；
   - 检索类用例需要外网访问所选文献源；
   - B 类扫描型 PDF/图片 OCR 用例需要服务端 OCR 依赖可用（`/api/health` 中 `optional.ocr=true`）。
4. **E 类翻译前置**：把 `translation_samples.json` 的 10 段样本作为文献导入文献库，
   按样本顺序把 10 个 paper_id 写入一个 JSON 数组文件（如 `tests/output/translation_papers.json`），供 `--papers-json` 使用。

## 3. 脚本用法

所有脚本支持 `--base-url`（默认 `http://127.0.0.1:8000`）；流程统一为**两段式：脚本导出 → 人工标注/评分 → `--annotate-done` 汇总判定**。
约定：前置条件缺失（服务未启动/未配置 API Key）时打印明确提示并以 **exit 0 + SKIP** 退出；正常跑完 exit 0（FAIL 是评测结论，不是脚本异常）。

### 3.1 A 检索召回（eval_retrieval.py）

```bash
# 第一段：对全部 10 个选题执行检索并导出 top-10 文献清单
python tests/eval_retrieval.py
# 只跑第 0 个选题（TC-A1）
python tests/eval_retrieval.py --topic-index 0 --top-k 10
# 人工打开 tests/output/retrieval_{任务id}.csv，在 relevant 列填 1/0 后汇总：
python tests/eval_retrieval.py --annotate-done
```

- 流程：`POST /api/tasks` → `POST /api/tasks/{id}/search` → 轮询 `GET /api/jobs/{job_id}` → `GET /api/tasks/{id}/papers?sort=score&limit=K`。
- 产物：`output/retrieval_{任务id}.csv`（列：编号、标题、年份、来源、url、摘要前300字、relevant 空列）、`output/retrieval_tasks.json`（任务元数据）、`output/retrieval_report.json`。
- 判定：每个选题 top-k 相关比例（relevant=1 占比）；**前 5 个选题（每专业第 1 个）平均比例 ≥ 70% → PASS**；单跑某选题时按该选题判定。相关判定标准：标题+摘要是否直接针对选题的核心研究问题。

### 3.2 C 文献摘要（eval_summary.py）

```bash
# 第一段：对 10 篇文献生成结构化摘要并导出评分表
python tests/eval_summary.py --papers p_xxx,p_yyy,...
# 或从 JSON 文件读取（字符串数组或 [{"id","title"}] 数组）
python tests/eval_summary.py --papers-file my_papers.json
# 人工按 1~5 分填 output/summary_scores.csv 后汇总：
python tests/eval_summary.py --annotate-done
```

- 流程：对每篇 `POST /api/papers/{id}/summarize` → 轮询 Job；摘要原文存 `output/summary_{paper_id}.json` 供评分对照。
- 产物：`output/summary_scores.csv`（编号、标题、得分(1~5)、备注）、`output/summary_report.json`。
- 判定：**平均分 ≥ 4/5 且无关键信息丢失**（无得分 <3、备注无"丢失/缺失/遗漏"标注、10 篇全部评分）→ PASS。

### 3.3 D 翻译质量（eval_translation.py）

```bash
# 前置：translation_samples.json 的 10 段样本已入库，10 个 paper_id 按序写入 JSON 数组文件
python tests/eval_translation.py --papers-json translation_papers.json
# 人工对照 output/translation_{paper_id}.json 中译文与 key_terms，填术语一致率与信息完整后：
python tests/eval_translation.py --papers-json translation_papers.json --annotate-done
```

- 流程：对每篇 `POST /api/papers/{id}/translate` → 轮询 Job；译文（title_zh/abstract_zh/glossary）与样本 key_terms 存 `output/translation_{paper_id}.json`。
- 产物：`output/translation_scores.csv`（编号、原文标题、术语一致率(%)、信息完整(是/否)、备注）、`output/translation_report.json`。
- 判定：**术语一致率均值 ≥ 95% 且全部样本信息完整=是（无漏译/错译）** → PASS。
- 术语一致率人工算法：样本 key_terms 各次出现中采用标准译法的次数 / 总出现次数 × 100%。

### 3.4 E 评审有效性（eval_review.py）

```bash
python tests/eval_review.py
```

- 流程：对 `proposals/` 下每份 defects_N.json：创建任务 → 解析 proposal_N.md 的 `##` 分节并逐节 `PUT /api/tasks/{id}/proposal/sections/{key}` →
  `POST /api/tasks/{id}/review` → 轮询 Job → `GET /api/tasks/{id}/review` 取 merged 与 4 个 results →
  将全部 issue 文本与预埋问题关键词（含脚本内置同义词表 + defects 内 synonyms）比对。
- 产物：`output/review_{任务id}.json`（评审原始结果）、`output/review_report.json`。
- 判定：**5 稿预埋问题总体检出率 ≥ 80% → PASS**（13 个预埋问题需检出 ≥ 11 个）；任一稿流程失败按未检出计入且整体 FAIL。
  检出定义：4 个评审角色或一致性汇总的输出文本命中缺陷关键词/同义词任一个。

## 4. 报告解读

| 报告 | 关键字段 | 含义 |
|---|---|---|
| retrieval_report.json | `tasks[].ratio / pass`、`primary_average_ratio`、`overall_pass` | 每选题 top-k 相关比例与通过情况；5 专业平均比例；总判定 |
| summary_report.json | `papers[].得分`、`average`、`issues`、`overall_pass` | 每篇得分；平均分；低分/丢失标注/未评分问题；总判定 |
| translation_report.json | `samples[].术语一致率/信息完整`、`avg_term_consistency`、`problems`、`overall_pass` | 每段检查结果；术语一致率均值；漏译/未标注问题；总判定 |
| review_report.json | `drafts[].defects[].detected/matched_keyword/detected_by`、`overall_rate`、`detections_by_agent`、`overall_pass` | 每稿每个预埋问题是否命中、命中词与检出角色；总体检出率；各角色贡献；总判定 |

## 5. 与通过标准的对应关系

| 设计文档评测项 | 脚本 | 指标 | 通过标准 |
|---|---|---|---|
| 检索召回质量（5 个不同专业选题） | eval_retrieval.py | top-k 相关比例（5 专业平均） | ≥ 70% |
| 文献摘要质量（10 篇文献） | eval_summary.py | 人工 1~5 分均值 + 关键信息完整性 | ≥ 4/5 且无关键信息丢失 |
| 翻译质量（10 段英文文献） | eval_translation.py | 术语一致率均值 + 信息完整度 | ≥ 95% 且无漏译错译 |
| 评审有效性（5 个开题初稿） | eval_review.py | 预埋真实逻辑问题检出率 | ≥ 80% |
| 控制变量 | 全部 | 同一批数据只改变单一因素（专业/选题/模型配置） | 结果可对比、可归因 |

控制变量实操：A 类 5 专业共用同一检索配置；E 类 5 稿共用同一 4 角色评审配置；对比不同模型配置时仅更换 Settings 角色映射后重跑同一脚本。

## 6. 注意事项

- 评测会在数据库中**创建真实任务与文献记录**，如需清理请经 `DELETE /api/tasks/{task_id}` 手动处理。
- 脚本重跑时会保留 CSV 中已有的人工标注（按 编号/paper_id 匹配），不会覆盖评分结果。
- 检索类评测受网络与文献源波动影响，建议固定时间段集中执行，控制变量对比须使用同一运行环境。
- CSV 采用 utf-8-sig 编码，Excel 可直接打开；如用 WPS/Excel 另存后编码异常，请勿转码。
- 所有评测结论以 `output/*_report.json` 的 `overall_pass` 字段为准。
