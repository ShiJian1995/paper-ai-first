# Paper AI First

在 Codex 中使用的多论文研究工作流。用户在调用时提供研究方向，由 Codex 负责文献阅读、公开数据获取、方案、代码、实验、写作和修改；本仓库提供可执行的状态、溯源、复现和 GitHub 同步工具。

**每篇论文独立存放在 `papers/<论文ID>/`。正式选题必须基于至少 100 篇去重后的全文实质分析，以及最近核查的研究趋势。** 不要求用户提供自有真实数据，不虚构实验结果。

## 直接在 Codex 中使用

在此项目聊天中输入：

```text
使用 $research-orchestrator 新建论文，ID 为 battery-soh-01。
研究大方向：电池健康状态估计。
先检索当前研究趋势，至少分析100篇去重后的领域论文，
比较尚未解决的问题和公开数据可得性，再给出候选选题。
数据由你自主获取；代码同步到当前GitHub仓库；不要开始虚构结果的写作。
```

继续已有论文：

```text
使用 $research-orchestrator 继续论文 battery-soh-01，从已有记录恢复。
```

另开论文时使用新 ID。中文题目可以改变，ID 保持稳定。遇到多篇论文且用户未明确目标时，智能体应询问，不自动猜测。

本次安装了四个固定版本的上游科研技能和四个本地技能。下一轮对话可使用；若客户端尚未刷新目录，在同一项目重新打开聊天。`AGENTS.md` 也指定了入口。

## 环境与命令

核心运行时只依赖 Python 3.11+ 标准库和 Git；不需要额外模型 API Key。具体研究依赖按论文单独锁定，领域技能的可选外部服务需另行配置。Windows 和 Linux 均有测试配置。

```powershell
python paper.py doctor
python paper.py list
python paper.py create --id paper-001 --title "第一篇论文" --direction "你的研究大方向"
python paper.py --paper paper-001 status
python paper.py --paper paper-001 next
```

所有论文操作都必须指定 `--paper`。`--workspace` 可显式指定工作空间路径，默认使用此脚本所在目录，不受终端当前目录影响。

```text
paper-ai-first/
├── AGENTS.md                      共享约束
├── .agents/skills/                共享科研技能
├── research_agent/                工作流运行时
├── workspace.config.json          仓库与工作空间配置
└── papers/
    ├── paper-001/
    │   ├── research/             独立方向、预算、状态与事件记录
    │   ├── literature/           检索、全文、逐篇分析与证据
    │   ├── data/                 数据来源清单与原始数据
    │   ├── protocol/             选题后形成的方案和结果解释
    │   ├── src/                  本论文代码
    │   ├── configs/              本论文实验配置
    │   ├── runs/                 输入快照、日志和真实产物
    │   ├── analysis/             分析与绘图代码
    │   ├── manuscript/           稿件及论断证据表
    │   ├── reviews/              审稿、修改与回复
    │   ├── submission/           期刊匹配与投稿准备
    │   └── reports/              明确选择公开的运行证据
    └── paper-002/                与 paper-001 完全分开的研究文件
```

## 文献与选题门禁

流程是 `intake → literature → protocol → experiments → manuscript → review → submission`。

```powershell
python paper.py --paper paper-001 advance
python paper.py --paper paper-001 search "research query" --limit 20
python paper.py --paper paper-001 paper-add literature/intake/paper-0001.json
python paper.py --paper paper-001 corpus-audit
```

`search` 真实请求 Crossref 并保存响应与检索参数，仅做元数据发现。Codex 再调用已安装的 `paper-lookup` 和 `literature-review`，使用学科数据库、作者仓库和合法全文补充。

每篇论文记录问题、方法、数据、结果、局限、研究缺口、相关性和证据位置。至少 100 篇独立论文的全文分析才能通过选题门禁；摘要仅初筛，重复 DOI、相同题目和关联预印本版本不重复计数。趋势报告须在最近 30 天内实际核查，覆盖近期热点、未解决问题、反例和检索局限。计数程序不能判断分析是否深刻，也不能检测所有跨版本关系；Codex 必须实际阅读和核查，不能填充套话凑数。

产物字段见 [.agents/skills/research-orchestrator/references/artifacts.md](.agents/skills/research-orchestrator/references/artifacts.md)。未满足门禁时 `advance` 返回非零；此后每次推进也重新检查先前门禁。

## 数据与真实实验

数据来源清单明确来源页、下载地址、许可、版本和类型。观测数据、基准数据、仿真与合成数据分别标注。下载支持体积限制、有限重试和 SHA-256 校验；首次下载可以生成本地内容锁，但不等同于独立发布者的真实性证明。数据版本变化需使用新 ID。

```powershell
python paper.py --paper paper-001 fetch data/manifests/dataset.json
python paper.py --paper paper-001 run configs/baseline.json
python paper.py --paper paper-001 reproduce <运行ID>
python paper.py --paper paper-001 verify-run <运行ID>
```

运行配置采用 argv 数组，源码文件列表必须完整；运行在本论文的独立代码和数据副本中。输出写到 `{output}`，至少包含有限数值组成的 `metrics.json`。程序保留代码、数据哈希、配置、环境、退出码和日志，失败不能成为成功结果。支持次数、单次时长和累计时长预算，以及超时终止进程树。

`reproduce` 重放已归档代码而非已修改的工作目录。默认比较全部输出哈希；非确定性实验可事先设定有科学依据的指标容差。修改结果、源快照或配置后不能通过验证。

**快照复跑证明执行重复性，不证明方法正确、无数据泄漏或具有学术创新。** 正式研究还需要领域测试、依赖锁、干净环境重跑与适当的不确定性分析。第一版支持本地受信任 Python 实验；目录隔离不等于操作系统安全沙箱，代码执行前仍需检查。远程 GPU 和无人值守调度尚未接入。

## GitHub 同步

目标为用户指定的公开仓库 [ShiJian1995/paper-ai-first](https://github.com/ShiJian1995/paper-ai-first)。共享系统和各篇论文分别同步：

```powershell
python paper.py framework-plan
python paper.py framework-sync --message "Update research workflow"
python paper.py --paper paper-001 export-run <已核验的运行ID>
python paper.py --paper paper-001 github-plan
python paper.py --paper paper-001 github-sync --message "paper-001: reproduce baseline"
```

同步采用路径白名单、常见凭据扫描和远端提交核验；没有强推或远端覆盖。同一时刻共享 Git 索引只允许一个同步操作。其他论文暂存区有变更时拒绝混合提交。

公开：系统代码；该论文的 `src/`、`configs/`、`analysis/`、`scripts/`、来源清单和明确导出的 `reports/`。本地：研究状态、原始数据、全文、稿件、审稿意见、原始日志和密钥。导出文件内容仍需审阅；路径白名单不能识别所有敏感内容。

进入结果撰写前，每项纳入结果必须复跑通过，并能在已推送的提交中找到相同的运行清单和源代码快照。正常运行依赖可用 Git 凭据；连接器登录不自动保证本机 Git 认证。

克隆仓库后，已有论文代码可以用 `python paper.py restore --id <ID> --title "论文名称"` 重建本地运行状态，再按已公开清单重新下载数据并运行配置。该操作不会恢复原本未上传的论文全文、阅读记录或历史日志；这些本地文件需由工作空间备份保存。

## 测试与公开数据演示

```powershell
python -m unittest discover -s tests -v
python scripts/verify_skills.py
python scripts/smoke.py
```

演示只在 `papers/system-smoke/` 中工作。从 [UCI Iris 官方页面](https://archive.ics.uci.edu/dataset/53/iris) 获取 CC BY 4.0 数据，使用归档内的 `bezdekIris.data`。采用固定种子、分层训练/测试划分、只在训练集拟合的标准化、1-NN 与多数类基线。示例没有新研究贡献，不能用作你的论文成果。网络失败会明确失败，不回退为伪造数据。

## Skills 与限制

上游：`paper-lookup`、`literature-review`、`scientific-writing`、`peer-review`；来源版本及逐文件校验值在 `skills.lock.json`，许可证在 `THIRD_PARTY_NOTICES.md`。

本地：`research-orchestrator`、`experiment-runner`、`paper-review-revise`、`journal-matcher`。

写作和内部审稿由 Codex 结合技能完成，CLI 本身不会生成论文，也没有后台常驻模型。上游要求的人工事实核验不得由模型冒名完成；投稿准备可以自动推进，最终作者核验与实际投稿单独处理。文献真实性、科学结论和期刊匹配仍需基于实际证据。期刊费用、政策和热度资料必须实时检索。
