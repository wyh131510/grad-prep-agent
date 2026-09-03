# -*- coding: utf-8 -*-
"""所有 LLM 提示词模板集中管理（便于统一调优与论文引用）。"""
from __future__ import annotations

# ---------------------------------------------------------------- 检索规划


def plan_prompt(topic: str, major: str, years: str, requirements: str) -> str:
    return f"""你是资深学术文献检索专家。请把下面的毕业设计选题拆解成 4~6 个检索子问题，并为每个子问题生成 2~4 个检索词（中英文都有）。

【选题】{topic}
【专业】{major or "未指定"}
【年份范围】{years or "不限"}
【补充要求】{requirements or "无"}

拆解要求：
1. 子问题覆盖：定义与背景、主流方法/技术、数据集与评测、难点与挑战、前沿进展 等角度；
2. 检索词要具体、可被学术检索引擎直接使用（英文用学术惯用表达，中文用国内惯用表达）；
3. 每个子问题说明一句拆解理由（rationale）。

只输出 JSON，格式：
{{"sub_questions": [{{"question": "...", "rationale": "...", "queries": [{{"text": "...", "lang": "en"}}, {{"text": "...", "lang": "zh"}}]}}]}}"""


# ---------------------------------------------------------------- 精排（LLM 兜底）


def rerank_prompt(query: str, doc_title: str, doc_abstract: str) -> str:
    return f"""你是文献相关性评判专家。请判断这篇文献与查询的相关程度。

【查询】{query}
【文献标题】{doc_title}
【文献摘要】{doc_abstract[:1200]}

只输出 JSON：{{"score": 0~100 的整数, "reason": "一句话理由"}}"""


# ---------------------------------------------------------------- 翻译


def glossary_prompt(domain: str, samples: str) -> str:
    return f"""你是{domain}领域的资深译审。请基于给出的文献片段，建立一份「英文术语 → 中文译名」对照表。

要求：
1. 术语选择领域核心概念（10~25 个），中文译名采用该领域通用译法；
2. 同一英文术语只能有一个中文译名，保证一致性；
3. 只输出 JSON：{{"glossary": {{"term": "译名", ...}}}}"""


def translate_prompt(text: str, glossary: dict, context: str) -> str:
    g = "\n".join(f"- {k} → {v}" for k, v in glossary.items()) or "（暂无）"
    return f"""你是学术文献资深翻译，请把下面的英文翻译成高质量中文。

【术语对照表（必须严格遵守）】
{g}

【翻译要求】
1. 术语必须使用上表译名，保持全文一致；
2. 忠实原文，信息完整，不增删内容，不自行发挥；
3. 学术语气，符合中文学术论文行文习惯，长句适当拆分；
4. 保留数字、公式、专有名词缩写（如 CNN、ResNet）的通用写法；
5. 只输出译文本身，不要任何解释。

【上下文说明】{context}

【原文】
{text}"""


# ---------------------------------------------------------------- 单篇总结


def paper_summary_prompt(paper: dict, topic: str, major: str) -> str:
    return f"""你是文献阅读助手，请精读以下文献信息并输出结构化总结。若信息缺失，字段填"文献未提及"。

【我的选题】{topic}（{major or "专业未指定"}）

【文献信息】
标题：{paper.get("title", "")}
作者：{", ".join(paper.get("authors", []))}
年份：{paper.get("year", "")}
出处：{paper.get("venue", "")}
关键词：{", ".join(paper.get("keywords", []))}
摘要：{paper.get("abstract", "")}
关键片段：
{paper.get("snippets_text", "") or "（无）"}
图表说明：
{paper.get("figures_text", "") or "（无）"}

输出 JSON：
{{
  "research_question": "本文要解决的研究问题",
  "method": "核心方法/模型/技术路线",
  "contributions": ["贡献1", "贡献2"],
  "dataset": "使用的数据集/实验对象",
  "metrics": "评价指标与主要结果",
  "limitations": "局限与不足",
  "relevance_to_topic": "与我的选题的关联：可借鉴的思路/方法/数据，以及建议在我的毕设中如何使用（重点回答『这篇文献怎么用于我的毕业设计』）",
  "key_points": ["3~5 条要点，每条一句话"],
  "language": "zh"
}}"""


# ---------------------------------------------------------------- 综述聚类


def survey_cluster_prompt(paper_list: str) -> str:
    return f"""你是文献调研专家。以下是若干篇收藏文献的简要信息（编号|标题|摘要），请把它们按研究主题聚类。

{paper_list}

要求：
1. 聚成 2~5 个主题，每篇文献归入最相关的一个主题（一篇只归一类）；
2. 主题命名要体现研究侧重；
3. 每个主题输出一段 150~250 字的中文综述（综合该主题下各文献的贡献，客观陈述）。

只输出 JSON：
{{"clusters": [{{"theme": "主题名", "paper_ids": ["p_xxx"], "summary": "综述段落"}}]}}"""


def survey_write_prompt(clusters: str, topic: str, major: str, references: str) -> str:
    return f"""你是学术写作助手。基于以下主题聚类结果，为「{topic}」（{major or ""}）写一份文献调研综述（Markdown 格式）。

【聚类结果】
{clusters}

【参考文献编号表（综述中引用文献请严格使用该编号）】
{references}

写作要求：
1. 开头一段总述（研究背景与调研范围）；
2. 每个主题一节（## 二级标题），内容基于聚类 summary 展开，并在该节末尾用 [1][2] 形式标注所属文献编号；
3. 结尾一段总结：现有研究的不足与我的毕设切入点；
4. 客观综述，不虚构文献、不编造数据；
5. 文末「## 参考文献」小节：原样列出上面的参考文献编号表。"""


# ---------------------------------------------------------------- 多智能体评审


def review_prompt(
    role_name: str, scope: str, criteria: str, proposal: str, template_hint: str, materials: str
) -> str:
    return f"""你是「{role_name}」，一位严格的毕业设计开题报告评审专家，独立评审、只认报告本身。

【你的评审范围】{scope}
【必须逐项检查的要点】{criteria}
【学校模板要求（评审依据之一）】
{template_hint or "（未提供，按通用学术规范评审）"}
【文献调研材料（判断依据，注意报告引用的文献是否与之一致）】
{materials or "（无）"}

【待评审的开题报告（Markdown，共 {len(proposal)} 字）】
{proposal}

请输出 JSON：
{{
  "score": 0~100 的整数（90+优秀；80~89良好；70~79中等；60~69及格；<60不合格）,
  "summary": "总体评价，150 字以内",
  "issues": [
    {{
      "severity": "high|medium|low",
      "section": "问题所在分块 key（background/literature_review/objectives/methodology/feasibility/schedule/references，跨节问题填 overall）",
      "problem": "具体问题描述，必须指明位置或引用原文",
      "suggestion": "具体、可操作的修改建议",
      "evidence": "报告中佐证该问题的原文片段（80 字内，无原文证据则填『整体性判断』）"
    }}
  ]
}}

要求：issues 3~8 条，按严重程度从高到低排序；评分严格，宁可尖锐，不可含糊。"""


def coordinator_prompt(results_json: str, topic: str) -> str:
    return f"""你是评审委员会主席。四位评审专家已对开题报告「{topic}」完成独立评审，结果如下：

{results_json}

请完成一致性处理并输出 JSON：
{{
  "overall_score": 四位专家评分的平均分（整数）,
  "verdict": "通过 | 修改后通过 | 不通过",
  "conflicts": [
    {{"topic": "冲突点简述", "opinions": ["专家A认为…", "专家B认为…"], "resolution": "裁决结论与理由"}}
  ],
  "final_suggestions": [
    {{"priority": 1, "section": "分块 key", "action": "具体修改动作（可执行）", "reason": "依据（引用相关专家的意见）"}}
  ],
  "strengths": ["报告优点"]
}}
要求：conflicts 只列真正存在分歧的点（无则空数组）；final_suggestions 合并去重后按优先级排序，5~12 条。"""


def apply_review_prompt(
    section_title: str, content: str, issues_text: str, suggestions_text: str, instruction: str
) -> str:
    return f"""你是开题报告修改助手。请根据评审意见修改「{section_title}」分块。

【当前内容】
{content}

【针对本节的评审问题】
{issues_text or "（无）"}

【汇总后的最终修改建议（本节相关）】
{suggestions_text or "（无）"}

【用户补充要求】{instruction or "无"}

要求：
1. 输出修改后的完整分块内容（Markdown，以“## {section_title}”开头）；
2. 逐条落实可执行的评审意见；对不成立的意见，在文末以 <!-- 未采纳：原因 --> 注释说明；
3. 保留原内容中合理的部分，不要无中生有、不要编造文献与数据。"""


# ---------------------------------------------------------------- 答辩问题


def defense_prompt(topic: str, major: str, proposal: str, materials: str) -> str:
    return f"""你是毕业设计开题答辩专家。基于以下开题报告，预测答辩委员会最可能提出的问题。

【选题】{topic}（{major or "专业未指定"}）
【文献调研材料摘要】
{materials or "（无）"}
【开题报告（共 {len(proposal)} 字）】
{proposal}

输出 JSON（4 类，每类 3~5 个问题）：
{{
  "categories": [
    {{"name": "选题与背景理解", "questions": [{{"question": "问题", "intent": "考察意图", "hint": "参考回答要点（30~80字）"}}]}},
    {{"name": "方法与技术细节", "questions": [...]}},
    {{"name": "可行性与风险", "questions": [...]}},
    {{"name": "工作量与进度安排", "questions": [...]}}
  ]
}}
要求：问题具体、犀利，直指报告薄弱处；hint 给出能帮学生答好的要点。"""


# ---------------------------------------------------------------- 开题报告


SECTION_TITLES = {
    "background": "课题背景与研究意义",
    "literature_review": "国内外研究现状",
    "objectives": "研究内容与目标",
    "methodology": "研究方案与技术路线",
    "feasibility": "可行性分析",
    "schedule": "进度安排",
    "references": "参考文献",
}


def proposal_section_prompt(
    section_key: str,
    section_title: str,
    topic: str,
    major: str,
    requirements: str,
    template_hint: str,
    materials: str,
    existing: dict,
    instruction: str,
) -> str:
    ctx = "；".join(f"{k}：{v[:80]}" for k, v in existing.items() if v)
    return f"""你是毕业设计开题报告写作专家。请撰写开题报告的分块内容，输出 Markdown。

【选题】{topic}
【专业】{major or "未指定"}
【补充要求】{requirements or "无"}
【学校模板中本节的说明】{template_hint or "（无，按通用学术规范撰写）"}
【可用的文献调研材料（必须基于这些材料撰写，不得虚构文献）】
{materials or "（暂无收藏文献，请给出通用结构与提示用户补充）"}

【本节任务】{section_title}（{section_key}）

【已写好的其他分块（保持衔接一致）】
{ctx or "（无）"}

【用户额外要求】{instruction or "无"}

写作要求：
1. 只输出本节内容，以“## {section_title}”开头；
2. 引用文献用 [编号] 标注，与文末参考文献一致；
3. 内容充实（800~1500 字），贴合专业实际，技术路线可落地；
4. 若本块为参考文献（references），输出与上文引用一致的参考文献列表（格式：GB/T 7714）。"""
