# 毕业设计前期准备 Agent（grad-prep-agent）

> 🎓 一站式解决毕设最痛苦、最耗时的环节：**选题后的文献调研与筛选、开题报告生成与评审**。
> 核心问题：*“我搜到的文献，到底怎么用于我的毕业设计！”*

流程：**搜索 → 解析 → 筛选 → 总结 → 用户反馈 → 生成初稿 → 多智能体评审 → 答辩问题清单**。

---
<img width="1891" height="1267" alt="image" src="https://github.com/user-attachments/assets/e70aa3cd-940f-4d1a-861e-4a3405276add" />

## 一、快速开始

环境要求：Windows 10/11，Python 3.10+（建议 3.11）。

### 方式 A：一键脚本（推荐）

```bat
setup_env.ps1    # powershell -ExecutionPolicy Bypass -File setup_env.ps1
                 # 自动创建 .venv、安装核心依赖（默认清华 PyPI 镜像，失败自动换阿里云），
                 # 并尝试安装可选依赖（BGE 向量检索 + OCR）
start.bat        # 启动应用，浏览器自动打开 http://127.0.0.1:8000
```

> 自定义 pip 镜像：`$env:PIP_MIRROR="https://mirrors.aliyun.com/pypi/simple/"; .\setup_env.ps1`
> BGE/reranker 模型下载默认走 `hf-mirror.com` 国内镜像；要改用官方源，设置环境变量 `HF_ENDPOINT=https://huggingface.co` 后重启。

### 方式 B：手动安装

```bat
python -m venv .venv
.venv\Scripts\python -m pip install -U pip
.venv\Scripts\python -m pip install -r requirements.txt

:: 可选（完整的三重混合检索 + 图片/扫描件 OCR，约 500MB，一次性下载）：
.venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python -m pip install -r requirements-optional.txt

.venv\Scripts\python run.py            :: 启动，访问 http://127.0.0.1:8000
```

> 未安装可选依赖时系统**自动降级**：向量检索缺失 → BM25 + LLM 精排；OCR 缺失 → 跳过图片文字提取（文本型 PDF 不受影响）。
> 国内网络下载 BGE 模型慢时，可先设置环境变量 `HF_ENDPOINT=https://hf-mirror.com` 再启动。

### 第一步必做：配置大模型 API

打开「设置」页 → 从预设添加服务商（DeepSeek / OpenAI / Kimi / 通义千问 / 智谱 / 硅基流动，或自填任意 **OpenAI 兼容**接口）→ 填写 API Key → 测试连接。可以给不同角色（检索规划 / 总结 / 翻译 / 开题生成 / 四位评审 / 汇总主席 / 答辩）指定不同服务商。

## 二、使用流程（对应 6 个页面）

1. **任务与检索**：创建任务（选题、专业、年份范围、来源多选、可选文献直链）→ 启动检索；任务参数（年份/来源/选题等）随时可改并重新检索。Agent 自动：拆解选题为子问题并生成中英文检索词 → 多源并行抓取（**Semantic Scholar / arXiv / CrossRef / PubMed / OpenAlex**，OpenAlex 免费稳定、能检索中英文文献并常带开放获取 PDF）→ 统一解析清洗 → 三重混合检索（BM25 + BGE 向量 + reranker，RRF 融合）排序。结果列表支持筛选、排序、勾选收藏（自动下载源文件到本地）。知网/万方因反爬与页面改版已从来源中移除，中文文献请用 OpenAlex 检索，或用「任务 → 导入文献」上传知网导出的 EndNote/RefWorks 文本。
2. **文献库**：已收藏文献 → 单篇结构化总结（重点回答“这篇文献怎么用于我的毕设”）/ 中英翻译（先建术语对照表再翻译，含关键片段译文，空回复自动重试）→ 多选生成主题聚类综述。文献详情支持「解析全文」：自动下载开放获取 PDF 提取**真实关键片段、图注与表格**；PubMed 等无 PDF 的文献自动从来源页提取**真实图表**。取消收藏会同时删除该文献的本地文件与图片（仅其自身文件夹）。
3. **开题报告**：上传学校模板（docx/pdf/md/txt，自动检测章节结构）→ 分块生成（可带额外说明、随时手动修改、预览切换）→ 一键生成全部空分块 → 导出 Markdown / Word。
4. **评审与答辩**：多智能体评审（学术规范 / 逻辑 / 可行性 / 格式，四角色并行 + 主席 Agent 冲突消解汇总）→ 按建议一键辅助修改 → 生成答辩问题清单（含考察意图与回答要点）。
5. **概览 / 设置**：统计信息、服务商与角色映射、下载目录、检索参数。

## 三、项目结构

```
grad-prep-agent/
├── app/
│   ├── main.py            # FastAPI 入口
│   ├── config.py          # 设置加载（data/settings.json）
│   ├── db.py              # SQLite 薄封装（WAL、线程安全）
│   ├── schemas.py         # 全局数据模型（API 契约的代码化）
│   ├── utils.py           # 清洗/分块/RRF 融合/宽松 JSON 解析等
│   ├── jobs.py            # 后台任务管理 + SSE 进度事件
│   ├── llm/               # 统一 LLM 客户端（OpenAI 兼容多服务商）+ 提示词库
│   ├── search/            # 检索规划器 + 6 个来源适配器 + 编排引擎
│   ├── parse/             # HTML/PDF/OCR/表格解析 → 统一结构 + 文献导入
│   ├── retrieve/          # BM25 / BGE 向量 / reranker + RRF 三重混合检索
│   ├── store/             # 本地文件下载、SQLite 仓库
│   ├── agents/            # 总结/翻译/开题生成/多智能体评审/答辩
│   └── api/               # REST 路由 + SSE
├── web/                   # 纯静态前端（无构建、无 CDN）
├── tests/                 # 测试用例集与评测脚本（≥15 条用例、4 个评测脚本）
├── scripts/smoke_test.py  # 离线冒烟测试（35 项，验证降级路径）
├── installer/             # Inno Setup 安装脚本 + 打包说明
├── run_desktop.py         # 桌面模式入口（原生窗口，无浏览器地址栏）
├── 打包.bat               # 一键打包为 Windows 安装程序（详见 installer/README.md）
├── docs/API.md            # 前后端 API 契约
├── data/                  # 运行时数据（settings.json、SQLite、文献源文件、模型缓存）
└── run.py / start.bat / setup_env.ps1
```

## 四、关键技术点（论文可用章节）

1. **多源抓取与统一解析方法**：每个来源一个适配器（`search/sources`），统一收敛到 `SearchHit`；HTML（citation meta + readability 正文）、PDF（PyMuPDF 文本/图片/图注 + pdfplumber 表格）、扫描件（RapidOCR）；脏数据清洗规则集中在 `parse/unifier.py`。图表说明**真实来自文献图注**，不由 AI 生成，文献无图则无。
2. **多轮查询 / 三重混合检索**：选题拆解 4~6 个子问题 × 中英文检索词 → 多源并行 → BM25 粗筛 → BGE 向量语义匹配 → bge-reranker 精排（未装则 LLM 兜底）→ RRF 融合。三路得分独立保存（bm25_score / vector_score / rerank_score），便于做消融实验。
3. **用户偏好反馈**：收藏行为持久化到本地（SQLite + 用户指定文件夹）；收藏文献用于结构化总结、综述聚类与开题生成，形成「反馈 → 生成」闭环。
4. **多智能体评审与一致性处理**：学术规范 / 逻辑 / 可行性 / 格式四个评审 Agent（可分别指定不同模型 API）并行输出结构化意见（score/issues 含 severity/evidence），主席 Agent 负责冲突消解与最终修改建议（priority 排序）。
5. **验证方案**：`tests/` 提供 ≥15 条测试用例与 4 个评测脚本，覆盖：5 专业检索召回（top-k 相关 ≥70%）、10 篇摘要人工评分（≥4/5）、10 段翻译术语一致率（≥95%）、5 篇初稿预埋问题检出率（≥80%）。

## 五、桌面模式与安装包打包

```bat
:: 桌面模式（原生窗口，无浏览器地址栏；需要 pip install pywebview）
.venv\Scripts\python.exe run_desktop.py

:: 一键打包 Windows 安装程序（桌面快捷方式 + 独立窗口）
::   打包.bat       精简版（默认，约1~3分钟，排除 torch/BGE/OCR，运行在降级模式）
::   打包-full.bat  完整版（含 BGE 向量检索 + OCR，约10~20分钟，体积数百 MB）
打包.bat
```

详细步骤（含 Inno Setup 6 安装、产物路径、安装行为与限制）见 **`installer/README.md`**。产物为 `dist\installer\GradPrepAgent_Setup.exe`；安装后应用数据存于 `%LOCALAPPDATA%\GradPrepAgent`。打包预检可运行 `scripts/precheck_packaging.py`。

## 六、开发自检

```bat
:: 模块级冒烟测试（35 项：配置/数据库/文献导入/混合检索降级/流水线容错/Job 管理等，
:: 覆盖「无网络、未配置 LLM、未安装可选依赖」三种降级路径）
.venv\Scripts\python.exe scripts\smoke_test.py

:: 端到端测试（需先启动服务；26 项：全部核心 API + SSE + 真实检索）
.venv\Scripts\python.exe scripts\e2e_local.py
```

## 七、常见问题

- **启动后页面显示「后端未连接」**：确认 `start.bat` 或 `python run.py` 窗口没有报错；若端口被占用，用 `python run.py --port 9000` 换端口。
- **向量检索没有生效（检索日志提示 torch 加载失败 WinError 1114）**：CPU 版 torch 在个别 Windows 环境会 DLL 初始化失败。可重装一次：`.venv\Scripts\python.exe -m pip install --force-reinstall --no-deps torch --index-url https://mirrors.aliyun.com/pytorch-wheels/cpu/ --timeout 300`；不修复也不影响使用——系统自动降级为 BM25 + LLM 精排。
- **BGE 模型下载慢**：默认走 hf-mirror.com；仍慢可用环境变量 `HF_ENDPOINT=https://huggingface.co` 换官方源（海外网络）。
- **检索结果里向量分/精排分为 0**：属于正常降级状态（未安装可选依赖或模型未下载成功），见下一条。首次检索后可在「设置 → 检索参数」调大每源结果数。
- **知网抓取失败**：知网反爬严格，属预期行为。推荐用「任务 → 导入文献」上传知网导出的 EndNote/RefWorks 文本，稳定可靠。
- **API Key 存储位置**：`data/settings.json`（本机明文），请勿将 data 目录提交到版本库。
- **端口占用**：`python run.py --port 9000`。
- **前端没有界面**：确认 `web/index.html` 存在，重启后访问 `/`。

## 八、边界

本项目只覆盖「文献调研 → 开题报告初稿」链路；不含中期检查、正文写作、查重降重。本阶段文献库暂不做跨任务去重。
