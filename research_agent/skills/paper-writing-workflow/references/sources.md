# 子技能固定版本

项目已有的 `paper-lookup`、`literature-review`、`scientific-writing`、`peer-review` 使用项目 `skills.lock.json` 的固定副本。`research-orchestrator`、`experiment-runner`、`paper-review-revise`、`journal-matcher` 使用当前项目版本。

下列外部模块均以 MIT 许可发布。打开本次选中的 SKILL.md，再以该文件所在目录为基准读取所需的 references、模板或脚本。使用原始文件时可将 GitHub 的 `/blob/<commit>/` 链接改为 `https://raw.githubusercontent.com/<owner>/<repo>/<commit>/<path>`。在可联网的环境可直接读取固定版本，无需整库安装。需要执行脚本时，从同一提交取得所需模块和相对依赖，保留它们的目录结构及许可声明；执行前检查脚本行为和所需运行环境。远程只读取公开技能材料，不传送论文草稿、数据或日志。

| 技能入口 | 读哪些内容 |
|---|---|
| [citation-management](https://github.com/K-Dense-AI/scientific-agent-skills/blob/2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5/skills/citation-management/SKILL.md) | DOI 与 BibTeX 读核心工作流，按需运行元数据提取、格式化或校验脚本。区分出版记录匹配与全文支持论断。 |
| [academic-writing-skills-zh-cn](https://github.com/WenyuChiou/academic-writing-skills/blob/70e6d20921160fcf541bc4137ec4f6ca2875a069/skills/academic-writing-skills-zh-cn/SKILL.md) | 引言用 introduction-and-study-context，局部文字修改用 prose-and-citation-editing，返修用 reviewer-response-workflow。保留用户的稿件语言。 |
| [ai-research-writing-skill](https://github.com/jin-s13/ai-research-writing-skill/blob/e8b5de964737350757b5b17d8a658a22943c9595/SKILL.md) | 实验交接读 research-handoff 或 artifacts；图表读 figure-workflow。只加载本次需要的路线，并将结果定位到实际产物。 |
| [ml-paper-writing](https://github.com/Orchestra-Research/AI-Research-SKILLs/blob/773a52944ba4747a18bd4ae9ade53fff041adcbc/20-ml-paper-writing/ml-paper-writing/SKILL.md) | 选择与目标会议和任务匹配的章节、模板和检查表，逐项对照当届官方要求。 |
