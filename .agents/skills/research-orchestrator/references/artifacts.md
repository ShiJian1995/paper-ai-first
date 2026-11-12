# 阶段产物字段

下面是字段约定，不是已完成的研究。所有 JSON 使用 UTF-8；所有文件都在选定的 `papers/<id>/` 内。

## 文献与选题

`literature/selection.json`：`candidates`（对象数组，每项含题目、研究缺口、数据来源、可行性和风险），`selected_topic`，`selection_reason`，`evidence_ids`（非空字符串数组），`data_sources`（含来源页、可得性、许可说明），`gap_paper_ids`，`counterevidence_paper_ids`（用于检验拟议缺口的研究，不要求其必然反对）。

逐篇分析清单交给 `paper-add <json>`：`id`、`canonical_work_id`（同一研究的预印本和出版版本共用）、`title`、`published_date`（YYYY-MM-DD）、`source_url`、`source_path`（实际全文）、`reading_level`（full_text/abstract）、`topics`、`checked_by`，可选 `doi`、`arxiv`。`analysis` 对象必须包含 `problem`、`method`、`data`、`findings`、`limitations`、`gap`、`relevance`、`evidence_locator` 的实质内容；不能用通用套话或重复摘要代替阅读。门禁按研究 ID、规范化题目、DOI 和 arXiv 版本去重；跨版本对应仍需研究者核验。计入至少 100 篇全文分析，摘要记录仅初筛。

`literature/trends.json`：`as_of`（最近 30 天内实际核查的日期）、`search_strategy`、`coverage`、`hot_topics`（每项有 `topic`、`evidence_paper_ids`、`recent_search_source`、`reason`）、`unresolved_problems`、`counterevidence`、`sources`、`limitations`。记录最近/此前各 12 个月的比较和经典工作，说明数据库覆盖和样本偏差。`corpus-audit` 的计数仅针对收集的语料，不自动证明全领域热度。

证据登记 JSON：`id`、`claim`、`source_url`、`source_path`（本论文内真实全文文件）、`locator`（页/节/表/行）、`support`（supports/contradicts/limited）、`checked_by`、`checked_at`。用 `evidence-add <json>` 登记，工具添加 SHA-256。需要先实际阅读来源；程序无法检查论断的语义支持关系。

## 数据

下载清单字段：`id`、`url`（HTTPS）、`source_page`、`license`、`license_url`、`kind`（observational/benchmark/simulation/synthetic）、`description`、`sha256`（已知时填 64 位哈希）、`max_bytes`。仿真/合成另需 `generation_method` 与 `limitations`。

示例见根目录 `examples/iris.dataset.json`。第一下载可生成本地内容锁；首次下载哈希不是发布者提供的真实性证明。正式共享清单应锁定已审查的版本。数据变化使用新 ID，保留旧数据与旧实验。

## 方案与实验

`protocol/plan.json`：`selected_topic`、`hypothesis`、`baseline`、`metric`、`split`、`datasets`（已登记 ID 数组）、`evidence_ids`、`experiments`（实验矩阵）、`acceptance`。同时记录研究类型、样本纳入排除、随机性、失败处理、统计方法与计算预算。

运行配置见 `examples/iris.experiment.json`。`sources` 必须列出所有执行源文件和依赖锁；`command` 为 argv 数组，支持 `{python}`、`{output}`、`{data:<id>}`。不要嵌入凭据，输出只写 `{output}`。

`protocol/results.json`：`run_ids`（纳入论文的成功原始运行）、`reproduction_ids`（相应通过的复跑 ID）、`interpretation`、`limitations`。每项结果有局限与失败分析，不能只保留最佳结果。正式随机实验按方案运行多个种子和不确定性估计。

## 稿件与审查

`manuscript/claims.json` 为数组，每项有 `claim`、`location`、`evidence_ids` 和/或 `run_ids`。机器门禁仅核查已登记条目，无法检测漏列的正文论断；需另外逐段全文审查。

`reviews/review.json`：`reviewer`（明确 AI 内部预审或真实审稿来源）、`round`、`assessment`、`issues`。每条问题有 `id`、`severity`（critical/major/minor）、`status`（open/resolved）、`response`；附修改位置和证据。重大问题必须闭环。

`submission/journals.json`：候选期刊数组。逐项保存范围匹配证据、来源链接、核查日期、费用币种与类型、投稿类型、模板、AI 使用要求、数据/代码要求、推荐依据。未知指标明确未知，不推测影响因子或审稿周期。
