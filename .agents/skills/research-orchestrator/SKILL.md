---
name: research-orchestrator
description: 在本工作空间启动或继续一篇论文的研究流程，协调选题、公开数据获取、文献、实验、写作与投稿准备；按论文 ID 隔离文件与进度。
---

# 研究总控

从工作空间根目录运行 `python paper.py list`。明确论文 ID 后，所有路径解释为 `papers/<id>/` 内的相对路径。用户提供新方向时用 `create --id <slug> --title <title> --direction <direction>`；用户未给方向且只是搭建系统，不生成真实论文。

读取该论文的 `research/project.json`、`research/state.json` 与阶段产物，运行 `python paper.py --paper <id> next`。用户授权范围内连续完成有依赖的阶段；缺少数据时先寻找公开替代，缺少关键科学决策时集中提出有依据的选项。

## 阶段衔接

1. **intake**：明确研究问题、资源与预算。预算只涵盖本地运行时间和次数，不授权付费 API/GPU。读已有文件获取事实，不重复问用户。
2. **literature**：使用相邻的 `paper-lookup` 和 `literature-review` 技能。Crossref 快速发现可运行 `search "query" --limit 10`；使用专业学科数据库和全文补充。正式定题前完成至少 100 篇独立论文的全文实质分析，逐篇 `paper-add`，用 `corpus-audit` 核验。标题、搜索摘要和重复预印本版本不能凑数；全文不可得则扩大公开来源检索并如实记录缺口。分别分析最近 12 个月、此前 12 个月及奠基工作，结合近期综述、会议/期刊论文和检索覆盖，记录热点的时间证据、未解决问题与反例。热度不能替代问题价值，也不能把样本中的频率宣称为全领域增长。输出 `literature/trends.json` 与 `literature/selection.json`，每个候选问题关联分析过的论文 ID。用户只给宽泛方向时允许提出检索范围，正式选题仍需达到门禁。
3. **protocol**：从论文的数据来源追踪下载地址与许可。创建清单并 `fetch`，不要求用户提供自有真实数据。生成研究方案 `protocol/plan.json`，在获得结果前确定划分、指标、对照、消融与接受标准。方案依研究类型调整，不预设改善幅度。
4. **experiments**：使用 `experiment-runner`。代码放本论文 `src/`。执行、分析、复跑，保留失败，写 `protocol/results.json`。明确导出可公开运行证据并同步本论文代码。
5. **manuscript**：使用相邻 `scientific-writing`，先构建证据对应表，再写正文。主稿为 `manuscript/paper.md`；`claims.json` 关联论断与证据或实验 ID。按用户格式调用已安装的 PDF/Word 技能。未完成的人工作者核验保持待核验，不谎称已验证。
6. **review**：使用 `paper-review-revise`，必要时读取 `peer-review` 的检查流程。形成意见、修改与回复对应关系。重大科学问题回到方案/实验，保留版本与历史，不为了过门禁降低标准。
7. **submission**：使用 `journal-matcher`，准备候选期刊和投稿材料。用户未授权时不实际投稿、不发布论文、不改仓库可见性。

每阶段完成后运行 `advance`，失败则修复证据或产物。对之前阶段的实质修改重新检查受影响的证据与实验；`advance` 只是结构和完整性检查，不是学术认可。

## 产物格式和恢复

字段格式见 [references/artifacts.md](references/artifacts.md)。引用该文件时只读取当前阶段需要的部分。

运行结束时在当前论文 `research/next.md` 记录完成项、未决项、下一条命令和有关实验 ID。新聊天从这些文件恢复。并行工作不得修改其他论文；默认每篇串行推进。`research/.lock` 包含进程 PID，遇到锁先检查进程，不能盲目删除。

## GitHub

先 `github-plan` 检查当前论文发布文件，再 `github-sync --message "..."`。公开仓库只承载该论文允许公开的代码和导出证据。不同论文的代码路径是 `papers/<id>/src/`，禁止混合引用实验结果。
