# 测试用例文档 —— grad-prep-agent 验证与评测

> 依据 `D:\dsh_workplace\project-design.html`「验证与评测方案」一节制定；所有接口调用严格遵循 `docs/API.md` v1.0 契约。
> 共 20 条用例，覆盖 5 类：A 检索召回（5）、B 统一解析（6）、C 文献摘要（2）、D 翻译质量（2）、E 评审有效性（5）。

## 0. 统一约定

**用例格式**：每条用例包含 8 个字段——ID、类别、前置条件、输入、操作步骤、预期结果、通过标准、实际结果（留空待填）。

**控制变量法约定**（对应设计文档要求）：
- A 类：5 个不同专业选题使用**同一检索配置**（同一份 `sample_topics.json`、相同 top-k、相同年份跨度逻辑），**单一变化因素 = 专业/选题**；每专业另备 1 个对照选题（`sample_topics.json` 中第 2 个），用于同专业内换题对照，排除"选题表达方式"的干扰。
- B/C/D 类：**同一批文献**分别做解析、摘要、翻译评测，变化因素仅为评测对象能力。
- E 类：5 篇初稿使用**同一套 4 角色评审配置**（academic/logic/feasibility/format），变化因素仅为初稿专业与预埋问题类型。
- 如需对比"模型配置"因素：在其他条件不变的前提下仅更换 Settings 中角色服务商映射后重跑同一评测脚本，对比两次报告。

**通过标准总表**（摘自设计文档，必须逐项落实）：

| 评测项 | 用例规模 | 通过标准 |
|---|---|---|
| 检索召回质量 | 5 个不同专业选题 | top-k 内相关比例 ≥ 70% |
| 文献摘要质量 | 10 篇文献 | 平均评分 ≥ 4/5，且无关键信息丢失 |
| 翻译质量 | 10 段英文文献 | 术语一致率 ≥ 95%，无漏译错译 |
| 评审有效性 | 5 个开题报告初稿 | 预埋真实逻辑问题检出率 ≥ 80% |

**前置条件通用项**：后端服务已启动（`http://127.0.0.1:8000`）、已配置至少一个服务商 API Key、已安装 `requests`（`pip install requests`）、测试机可访问外网（检索类用例）。所有脚本产物写入 `tests/output/`。

---

## 1. A 类：检索召回（5 条）

### TC-A1 ｜ 检索召回 · 计算机专业选题
| 字段 | 内容 |
|---|---|
| ID | TC-A1 |
| 类别 | A 检索召回 |
| 前置条件 | 服务已启动且配置 API Key；可访问 semantic_scholar / arxiv / crossref |
| 输入 | topic=基于深度学习的路面裂缝检测方法研究；major=计算机科学与技术；year_from=2019；year_to=2025；sources=["semantic_scholar","arxiv","crossref"]；top_k=10（对应 `sample_topics.json` 第 1 条） |
| 操作步骤 | 1) 运行 `python tests/eval_retrieval.py --topic-index 0`；2) 脚本创建任务 → 启动检索 Job → 轮询 `GET /api/jobs/{job_id}` 至非 running → `GET /api/tasks/{id}/papers?sort=score&limit=10` 导出 top-10；3) 打开 `tests/output/retrieval_{任务id}.csv`，人工逐行判读标题+摘要，在 relevant 列填 1（直接针对裂缝检测/深度学习分割方法）/ 0（不相关）；4) 运行 `python tests/eval_retrieval.py --topic-index 0 --annotate-done` 统计 |
| 预期结果 | CSV 含 10 行，列齐全（编号/标题/年份/来源/url/摘要前300字/relevant）；年份在 2019~2025 范围内；任务与 Job 状态正常流转 |
| 通过标准 | 该选题 top-k 相关比例 ≥ 70%（相关文献 ≥ 7/10） |
| 实际结果 | （待填） |

### TC-A2 ｜ 检索召回 · 机械专业选题
| 字段 | 内容 |
|---|---|
| ID | TC-A2 |
| 类别 | A 检索召回 |
| 前置条件 | 服务已启动且配置 API Key；可访问 semantic_scholar / crossref / cnki |
| 输入 | topic=数控机床主轴热误差建模与补偿方法研究；major=机械工程；year_from=2016；year_to=2025；sources=["semantic_scholar","crossref","cnki"]；top_k=10（对应 `sample_topics.json` 第 3 条） |
| 操作步骤 | 同 TC-A1，`--topic-index 2`；人工标注标准：relevant=1 当且仅当文献针对机床热误差/误差补偿/主轴热变形主题 |
| 预期结果 | 同 TC-A1；中英文文献混排，来源字段与 sources 匹配 |
| 通过标准 | 该选题 top-k 相关比例 ≥ 70% |
| 实际结果 | （待填） |

### TC-A3 ｜ 检索召回 · 电气专业选题
| 字段 | 内容 |
|---|---|
| ID | TC-A3 |
| 类别 | A 检索召回 |
| 前置条件 | 服务已启动且配置 API Key；可访问 semantic_scholar / crossref / cnki |
| 输入 | topic=含高比例新能源的配电网电压协调控制策略研究；major=电气工程；year_from=2018；year_to=2025；sources=["semantic_scholar","crossref","cnki"]；top_k=10（对应 `sample_topics.json` 第 5 条） |
| 操作步骤 | 同 TC-A1，`--topic-index 4`；人工标注标准：relevant=1 当且仅当文献针对配电网电压控制/新能源接入/储能或逆变器调控主题 |
| 预期结果 | 同 TC-A1；选题拆解计划（plan）含中英文双语查询词 |
| 通过标准 | 该选题 top-k 相关比例 ≥ 70% |
| 实际结果 | （待填） |

### TC-A4 ｜ 检索召回 · 土木专业选题
| 字段 | 内容 |
|---|---|
| ID | TC-A4 |
| 类别 | A 检索召回 |
| 前置条件 | 服务已启动且配置 API Key；可访问 semantic_scholar / crossref / cnki |
| 输入 | topic=装配式混凝土框架结构节点抗震性能研究；major=土木工程；year_from=2015；year_to=2025；sources=["semantic_scholar","crossref","cnki"]；top_k=10（对应 `sample_topics.json` 第 7 条） |
| 操作步骤 | 同 TC-A1，`--topic-index 6`；人工标注标准：relevant=1 当且仅当文献针对装配式节点/灌浆套筒连接/抗震试验主题 |
| 预期结果 | 同 TC-A1 |
| 通过标准 | 该选题 top-k 相关比例 ≥ 70% |
| 实际结果 | （待填） |

### TC-A5 ｜ 检索召回 · 经管专业选题
| 字段 | 内容 |
|---|---|
| ID | TC-A5 |
| 类别 | A 检索召回 |
| 前置条件 | 服务已启动且配置 API Key；可访问 semantic_scholar / crossref / cnki |
| 输入 | topic=电商平台供应链中断风险传导与韧性提升策略研究；major=管理科学与工程；year_from=2017；year_to=2025；sources=["semantic_scholar","crossref","cnki"]；top_k=10（对应 `sample_topics.json` 第 9 条） |
| 操作步骤 | 同 TC-A1，`--topic-index 8`；人工标注标准：relevant=1 当且仅当文献针对供应链中断/韧性/风险传导主题（仅泛泛谈供应链管理的判 0） |
| 预期结果 | 同 TC-A1 |
| 通过标准 | 该选题 top-k 相关比例 ≥ 70% |
| 实际结果 | （待填） |

> **A 类汇总口径**：TC-A1~A5 的 5 个选题相关比例取平均（脚本 `--annotate-done` 自动计算前 5 个选题平均值），**5 选题平均 ≥ 70% 判定 PASS**；每选题比例同时记录。对照选题（`sample_topics.json` 第 2/4/6/8/10 条）用于控制变量对照实验，不计入通过标准平均值。

---

## 2. B 类：统一解析（6 条）

**字段齐全度检查项**（Paper 契约）：title、authors（非空数组）、year、venue、source、url、abstract、keywords、snippets（含 section/page）、figures（caption 来自原文，非 AI 生成）、无脏数据（导航文字、页眉页脚、乱码、HTML 标签残留）。

### TC-B1 ｜ 解析 · HTML 页面（arXiv / Semantic Scholar 详情页）
| 字段 | 内容 |
|---|---|
| ID | TC-B1 |
| 类别 | B 统一解析 |
| 前置条件 | 已完成至少一个含 arXiv/Semantic Scholar 来源的检索任务，`optional.embedding=true` |
| 输入 | 检索任务中来源为 arxiv/semantic_scholar 的 paper_id 若干 |
| 操作步骤 | 1) `GET /api/papers/{paper_id}` 取 Paper 详情；2) 对照原始网页人工核对 title/authors/year/venue/url/doi/abstract 是否与原文一致；3) 检查 abstract 中无导航菜单、推荐列表、版权声明等非正文内容 |
| 预期结果 | 6 个核心字段（标题/作者/年份/来源/url/摘要）齐全且与原文一致；摘要纯净无混入 |
| 通过标准 | 字段齐全率 100%，无脏数据混入（清洗效果合格） |
| 实际结果 | （待填） |

### TC-B2 ｜ 解析 · HTML 页面（知网/万方详情页）
| 字段 | 内容 |
|---|---|
| ID | TC-B2 |
| 类别 | B 统一解析 |
| 前置条件 | 已完成含 cnki 来源的检索任务 |
| 输入 | 检索任务中来源为 cnki 的中文文献 paper_id 若干 |
| 操作步骤 | 1) `GET /api/papers/{paper_id}`；2) 核对中文标题/作者/年份/摘要是否完整，有无乱码或字段错位（如作者与机构串列）；3) 核对 keywords 是否提取正确 |
| 预期结果 | 中文字段无乱码、无字段错位；标题/摘要/作者/年份齐全 |
| 通过标准 | 字段齐全率 100%，编码正确（UTF-8 无乱码） |
| 实际结果 | （待填） |

### TC-B3 ｜ 解析 · 文本型 PDF（单栏论文）
| 字段 | 内容 |
|---|---|
| ID | TC-B3 |
| 类别 | B 统一解析 |
| 前置条件 | 已收藏并下载至少一篇文本型 PDF 论文（collect 时 download=true） |
| 输入 | 该文献 paper_id（含本地 pdf_url/file_path） |
| 操作步骤 | 1) `GET /api/papers/{paper_id}`；2) 对照 PDF 原文核对标题/摘要/作者/年份；3) 检查 snippets 是否含真实段落与节号（section 如 "3.2 网络结构"、page 页码）；4) 检查 figures 的 caption 是否来自原文图注、page 是否正确，无则应为空数组 |
| 预期结果 | 字段齐全；snippets 取自原文正文；figures 仅含原文真实图表说明，页码正确 |
| 通过标准 | 标题/摘要/作者/年份齐全率 100%；图表说明真实来源于该文献（无 AI 编造）；若有图表，caption 与原文一致 |
| 实际结果 | （待填） |

### TC-B4 ｜ 解析 · 文本型 PDF（双栏排版）
| 字段 | 内容 |
|---|---|
| ID | TC-B4 |
| 类别 | B 统一解析 |
| 前置条件 | 已收藏一篇双栏排版的期刊 PDF 论文 |
| 输入 | 该文献 paper_id |
| 操作步骤 | 1) `GET /api/papers/{paper_id}`；2) 抽查 abstract 与 snippets 是否出现"左右栏串行"（跨栏句子拼接错乱）；3) 检查页眉页脚（期刊名、DOI 角标）是否被剔除、正文中公式/数字有无乱码 |
| 预期结果 | 双栏文本按阅读顺序正确拼接；页眉页脚未混入正文；公式与数字无乱码 |
| 通过标准 | 清洗效果合格：无跨栏串行、无页眉页脚残留、无乱码 |
| 实际结果 | （待填） |

### TC-B5 ｜ 解析 · 扫描型 PDF / 图片 OCR
| 字段 | 内容 |
|---|---|
| ID | TC-B5 |
| 类别 | B 统一解析 |
| 前置条件 | `GET /api/health` 返回 `optional.ocr=true`（OCR 依赖已启用）；已导入一篇扫描型 PDF（或文献页图片） |
| 输入 | 该文献 paper_id |
| 操作步骤 | 1) `GET /api/papers/{paper_id}`；2) 核对 OCR 结果中标题/作者/年份/摘要是否可识别、与原文相符；3) 记录 OCR 识别错误（错字、漏字）数量；4) 检查 figures 是否提取了扫描件中的图表说明 |
| 预期结果 | 标题/作者/年份可正确识别；摘要主体完整（个别生僻字符错误可接受）；图表说明被提取 |
| 通过标准 | 标题/作者/年份识别正确率 100%；摘要可读性合格（错字率 ≤ 5%），字段齐全度合格 |
| 实际结果 | （待填） |

### TC-B6 ｜ 解析 · 失败边界与脏数据防护
| 字段 | 内容 |
|---|---|
| ID | TC-B6 |
| 类别 | B 统一解析 |
| 前置条件 | 准备一份解析失败的样本：损坏 PDF / 无文字内容页面 / 403 页面 |
| 输入 | 上述样本的 URL 或本地文件路径 |
| 操作步骤 | 1) 触发解析（检索或导入流程）；2) 观察 Job 状态与错误信息；3) 确认失败文献不会以"空标题+乱码摘要"进入文献库污染后续检索排序 |
| 预期结果 | 解析失败返回明确错误（Job status=error 且 error 字段可读），不产生脏数据记录 |
| 通过标准 | 失败可感知（有明确错误信息），且不污染文献库（无脏数据入库） |
| 实际结果 | （待填） |

---

## 3. C 类：文献摘要（2 条）

**评分维度与权重**（1~5 分，0.5 为一档）：

| 维度 | 权重 | 评分要点 |
|---|---|---|
| 关键信息保留 | 40% | 研究问题/方法/贡献/数据集/指标/局限是否齐全，且与原文摘要一致（无编造、无张冠李戴） |
| 与选题关联性阐述 | 30% | `relevance_to_topic` 是否明确指出与本人选题的关联点与可用之处（而非套话） |
| 结构完整性 | 30% | PaperSummary 各字段非空、语言为中文（language=zh）、无乱码、无截断 |

### TC-C1 ｜ 摘要 · 单篇摘要字段与关联性检查
| 字段 | 内容 |
|---|---|
| ID | TC-C1 |
| 类别 | C 文献摘要 |
| 前置条件 | 存在已入库文献（建议取 A 类检索任务中相关文献） |
| 输入 | paper_id 一个，如 `python tests/eval_summary.py --papers p_xxx` |
| 操作步骤 | 1) 脚本 `POST /api/papers/{id}/summarize` 并轮询 Job；2) 打开 `tests/output/summary_{paper_id}.json` 对照原文；3) 检查 research_question/method/contributions/dataset/metrics/limitations/relevance_to_topic/key_points 是否非空且忠实于原文；4) 重点检查 relevance_to_topic 是否具体关联所属任务选题 |
| 预期结果 | 各字段非空、语言 zh、内容与原文一致；relevance_to_topic 给出具体关联点 |
| 通过标准 | 字段齐全且忠实原文；relevance_to_topic 具体有效 |
| 实际结果 | （待填） |

### TC-C2 ｜ 摘要 · 10 篇批量评分（通过标准主用例）
| 字段 | 内容 |
|---|---|
| ID | TC-C2 |
| 类别 | C 文献摘要 |
| 前置条件 | 10 篇已入库文献的 paper_id（建议覆盖 5 个专业、中英文各半） |
| 输入 | `python tests/eval_summary.py --papers-file tests/output/summary_papers.json`（或 `--papers p_1,...,p_10`） |
| 操作步骤 | 1) 脚本对每篇调用 summarize 并轮询，导出 `tests/output/summary_scores.csv` 与每篇 `summary_{paper_id}.json`；2) 人工按上述三维度对每篇打 1~5 分填入"得分(1~5)"列，发现关键信息丢失时在"备注"写"丢失/缺失/遗漏"字样；3) 运行 `python tests/eval_summary.py --annotate-done` 汇总 |
| 预期结果 | 评分表含 10 行（编号/标题/得分/备注）；每篇摘要可评分、无生成失败 |
| 通过标准 | 平均评分 ≥ 4/5，且无关键信息丢失（无任何一篇得分 <3、备注无丢失标注） |
| 实际结果 | （待填） |

**评分表模板**（即 `summary_scores.csv` 结构，人工填写后交脚本汇总）：

| 编号 | 标题 | 得分(1~5) | 备注 |
|---|---|---|---|
| p_xxx | （文献标题） | （留空待填） | （留空待填） |
| …共 10 行… | | | |

---

## 4. D 类：翻译质量（2 条）

**检查方法**：对照 `tests/translation_samples.json` 中每段样本的 `key_terms`（标准译法），检查译文中术语是否统一采用标准译法、同一术语前后是否一致；检查标题+摘要是否完整翻译（无漏句、无错译、无漏译）。

### TC-D1 ｜ 翻译 · 单段翻译与术语对照表遵守
| 字段 | 内容 |
|---|---|
| ID | TC-D1 |
| 类别 | D 翻译质量 |
| 前置条件 | 已把 `tests/translation_samples.json` 中 TS-01 样本导入文献库（导入后得到 paper_id）；服务已配置翻译角色服务商 |
| 输入 | `python tests/eval_translation.py --papers-json my_papers.json`（该文件第 1 个 id 对应 TS-01） |
| 操作步骤 | 1) 脚本 `POST /api/papers/{id}/translate` 并轮询 Job；2) 打开 `tests/output/translation_{paper_id}.json`；3) 检查 TranslationResult：title_zh 正确、abstract_zh 完整、glossary 非空；4) 逐条核对 key_terms 各次出现是否使用标准译法 |
| 预期结果 | title_zh/abstract_zh 完整无漏译；glossary 覆盖主要术语；术语译法符合 key_terms 标准译法 |
| 通过标准 | 该段术语一致率 ≥ 95% 且无漏译错译 |
| 实际结果 | （待填） |

### TC-D2 ｜ 翻译 · 10 段批量人工检查（通过标准主用例）
| 字段 | 内容 |
|---|---|
| ID | TC-D2 |
| 类别 | D 翻译质量 |
| 前置条件 | 前置条件：已将 `tests/translation_samples.json` 的 10 段样本（计算机视觉/机械制造/电力系统/土木工程/管理科学各 2 段）作为文献导入文献库，并把 10 个 paper_id 按样本顺序写入 JSON 数组文件 |
| 输入 | `python tests/eval_translation.py --papers-json translation_papers.json` |
| 操作步骤 | 1) 脚本逐段调用 translate 并轮询，导出 `tests/output/translation_scores.csv` 与每段 `translation_{paper_id}.json`；2) 人工逐段对照译文与 key_terms：统计"术语各次出现采用标准译法的次数 / 总出现次数"得术语一致率(%)，填入表；检查有无漏译/错译，填信息完整=是/否，问题记入备注；3) 运行 `python tests/eval_translation.py --papers-json translation_papers.json --annotate-done` 汇总 |
| 预期结果 | 检查表含 10 行（编号/原文标题/术语一致率/信息完整/备注）；每段产出完整译文与术语表 |
| 通过标准 | 术语一致率均值 ≥ 95%，且全部样本信息完整=是（无漏译、无错译） |
| 实际结果 | （待填） |

**检查表模板**（即 `translation_scores.csv` 结构）：

| 编号 | 原文标题 | 术语一致率(%) | 信息完整(是/否) | 备注 |
|---|---|---|---|---|
| TS-01 | LiteSeg: Lightweight Semantic Segmentation... | （留空待填） | （留空待填） | |
| …共 10 行… | | | | |

---

## 5. E 类：评审有效性（5 条）

**方法**：每稿预埋 2~3 个真实逻辑问题（标准答案见各用例「预埋问题清单」）。脚本把初稿各节经 `PUT /api/tasks/{id}/proposal/sections/{key}` 写入 → `POST /api/tasks/{id}/review` 启动 4 角色评审 → `GET /api/tasks/{id}/review` 取 merged 与 4 个 results → 将全部 issue 文本与预埋问题关键词（含同义词扩展）比对。**总体通过标准：5 稿预埋问题检出率 ≥ 80%**（共 13 个预埋问题，需检出 ≥ 11 个；`eval_review.py` 自动判定）。

### TC-E1 ｜ 评审 · 计算机专业初稿（proposal_1.md）
| 字段 | 内容 |
|---|---|
| ID | TC-E1 |
| 类别 | E 评审有效性 |
| 前置条件 | 服务已启动且已配置 4 个评审角色服务商；`tests/proposals/proposal_1.md`、`defects_1.json` 就绪 |
| 输入 | `python tests/eval_review.py`（自动处理 proposal_1.md + defects_1.json，topic=基于深度学习的路面裂缝检测方法研究，major=计算机科学与技术，year 2019-2025，sources=["semantic_scholar","arxiv","crossref"]） |
| 操作步骤 | 1) 脚本创建任务 → 逐节 PUT 写入初稿 → POST review → 轮询 Job → GET review；2) 脚本将 4 个 results（academic/logic/feasibility/format）与 merged 的全部 issue 文本与下列标准答案关键词比对；3) 查看 `tests/output/review_report.json` 中该稿检出情况 |
| 预期结果 | 评审 Job 正常完成，产出 4 份评审结果 + 一致性汇总；原始结果存 `tests/output/review_{任务id}.json` |
| 通过标准 | 见 E 类总体标准；本稿预埋 3 个问题，期望检出 ≥ 2（并计入总体 ≥80%） |
| 实际结果 | （待填） |

**预埋问题清单（标准答案）**：
| 问题 | 类型 | 命中关键词（含同义词） |
|---|---|---|
| D1 研究目标含"嵌入式设备实时部署与推理加速"，技术路线只有 PC 端训练与精度对比，无模型转换/量化/部署环节 | 研究问题与技术路线不匹配 | 部署/嵌入式/技术路线（模型转换、量化、推理加速、移植） |
| D2 全部数据集构建、网络设计与实验仅安排第 11-12 周共 2 周 | 工作量安排不合理 | 工作量/进度/时间安排（任务量、工期） |
| D3 可行性分析只重复背景意义，未论证公开数据集可得性、GPU 算力、嵌入式开发板等条件 | 可行性论证缺失 | 可行性/数据集/资源（算力、硬件、开发板） |

### TC-E2 ｜ 评审 · 机械专业初稿（proposal_2.md）
| 字段 | 内容 |
|---|---|
| ID | TC-E2 |
| 类别 | E 评审有效性 |
| 前置条件 | 同 TC-E1；proposal_2.md、defects_2.json 就绪 |
| 输入 | `python tests/eval_review.py`（topic=数控机床主轴热误差建模与补偿方法研究，major=机械工程，year 2016-2025，sources=["semantic_scholar","crossref","cnki"]） |
| 操作步骤 | 同 TC-E1 |
| 预期结果 | 同 TC-E1 |
| 通过标准 | 见 E 类总体标准；本稿预埋 2 个问题，期望全部检出（并计入总体 ≥80%） |
| 实际结果 | （待填） |

**预埋问题清单（标准答案）**：
| 问题 | 类型 | 命中关键词（含同义词） |
|---|---|---|
| D1 技术路线依赖"机床厂商内部数据库"，未说明数据获取渠道、合作依据或替代方案 | 实验数据可得性未论证 | 数据/可得/厂商（获取、来源、可得性） |
| D2 目标为"补偿使加工精度提升 40%"，实验只验证热误差预测残差，无补偿后加工验证环节 | 研究目标与验证指标不匹配 | 补偿/验证/指标（加工实验、试切、评价指标、残差） |

### TC-E3 ｜ 评审 · 电气专业初稿（proposal_3.md）
| 字段 | 内容 |
|---|---|
| ID | TC-E3 |
| 类别 | E 评审有效性 |
| 前置条件 | 同 TC-E1；proposal_3.md、defects_3.json 就绪 |
| 输入 | `python tests/eval_review.py`（topic=含高比例新能源的配电网电压协调控制策略研究，major=电气工程，year 2018-2025，sources=["semantic_scholar","crossref","cnki"]） |
| 操作步骤 | 同 TC-E1 |
| 预期结果 | 同 TC-E1 |
| 通过标准 | 见 E 类总体标准；本稿预埋 3 个问题，期望检出 ≥ 2（并计入总体 ≥80%） |
| 实际结果 | （待填） |

**预埋问题清单（标准答案）**：
| 问题 | 类型 | 命中关键词（含同义词） |
|---|---|---|
| D1 研究内容为多资源"协调"控制与通信约束鲁棒性，技术路线只有集中式优化模型，无协调架构与通信约束建模 | 研究问题与技术路线不匹配 | 协调/分布式/技术路线（协同、多时间尺度、就地控制、分层控制、通信约束） |
| D2 参考文献章节为"（待补充）"，引用文献缺失，不符合模板格式 | 格式不符合模板要求 | 参考文献/格式/模板 |
| D3 可行性分析未说明仿真平台（OpenDSS/MATLAB）、算例数据与求解工具 | 可行性论证缺失 | 可行性/仿真/平台（仿真平台、算例） |

### TC-E4 ｜ 评审 · 土木专业初稿（proposal_4.md）
| 字段 | 内容 |
|---|---|
| ID | TC-E4 |
| 类别 | E 评审有效性 |
| 前置条件 | 同 TC-E1；proposal_4.md、defects_4.json 就绪 |
| 输入 | `python tests/eval_review.py`（topic=装配式混凝土框架结构节点抗震性能研究，major=土木工程，year 2015-2025，sources=["semantic_scholar","crossref","cnki"]） |
| 操作步骤 | 同 TC-E1 |
| 预期结果 | 同 TC-E1 |
| 通过标准 | 见 E 类总体标准；本稿预埋 2 个问题，期望全部检出（并计入总体 ≥80%） |
| 实际结果 | （待填） |

**预埋问题清单（标准答案）**：
| 问题 | 类型 | 命中关键词（含同义词） |
|---|---|---|
| D1 8 个足尺试件的全部拟静力试验与有限元模拟压在第 15 周 1 周内 | 工作量安排不合理 | 工作量/进度/试验（试件、拟静力、加载） |
| D2 文献综述称灌浆套筒连接研究"已较成熟"，研究内容却把"验证其可行性"作为主要创新点，前后矛盾 | 研究内容前后矛盾 | 成熟/创新点/矛盾（已较成熟、研究较多、创新、新颖性） |

### TC-E5 ｜ 评审 · 经管专业初稿（proposal_5.md）
| 字段 | 内容 |
|---|---|
| ID | TC-E5 |
| 类别 | E 评审有效性 |
| 前置条件 | 同 TC-E1；proposal_5.md、defects_5.json 就绪 |
| 输入 | `python tests/eval_review.py`（topic=电商平台供应链中断风险传导与韧性提升策略研究，major=管理科学与工程，year 2017-2025，sources=["semantic_scholar","crossref","cnki"]） |
| 操作步骤 | 同 TC-E1 |
| 预期结果 | 同 TC-E1 |
| 通过标准 | 见 E 类总体标准；本稿预埋 3 个问题，期望检出 ≥ 2（并计入总体 ≥80%） |
| 实际结果 | （待填） |

**预埋问题清单（标准答案）**：
| 问题 | 类型 | 命中关键词（含同义词） |
|---|---|---|
| D1 方案依赖某电商平台全量交易与物流数据，未说明获取渠道、脱敏处理与合规依据 | 数据可得性与合规性未论证 | 数据/可得/合规（脱敏、隐私、授权） |
| D2 研究问题为中断风险"传导机理"，技术路线全是机器学习预测建模，无复杂网络/系统动力学等机理建模手段 | 研究问题与技术路线不匹配 | 机理/预测/技术路线（复杂网络、系统动力学、级联、回归、机器学习） |
| D3 可行性分析泛泛而谈，未论证计算资源、软件工具与团队研究基础 | 可行性论证缺失 | 可行性/资源/工具 |

---

## 6. 用例统计

| 类别 | 编号 | 数量 |
|---|---|---|
| A 检索召回 | TC-A1 ~ TC-A5 | 5 |
| B 统一解析 | TC-B1 ~ TC-B6 | 6 |
| C 文献摘要 | TC-C1 ~ TC-C2 | 2 |
| D 翻译质量 | TC-D1 ~ TC-D2 | 2 |
| E 评审有效性 | TC-E1 ~ TC-E5 | 5 |
| **合计** | | **20** |
