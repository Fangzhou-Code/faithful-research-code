# Faithful Research Code

[English](README.md) | [简体中文](README.zh-CN.md)

面向科研代码生成、论文复现、实验实现、消融研究和 Artifact 发布的 Codex Skill。

它把科研代码视为“可执行的科学主张”：代码不仅需要运行，还必须能够从论文、公式、协议或用户决定追踪到实现、实验命令、原始结果和最终结论，并禁止未经授权的静默语义回退。

## 为什么实现这个 Skill

Codex 是通用代码智能体，其默认行为更像一名软件工程师，而不是科研人员。面对缺失输入、运行异常或环境差异时，它往往优先保证程序可用并继续运行，例如加入默认值、兼容分支、自动重试、备用后端、数据过滤或优雅降级。

这种工程思维适合生产系统，却不一定适合科研代码。科研代码的首要目标不是“尽量运行成功”，而是**忠实执行被声明的方法**。一个看似合理的回退可能改变研究对象、数据分布、算法路径、训练状态、评估协议或统计分母，使最终结果不再代表论文或研究者提出的方法；更严重的是，程序仍可能正常结束，让这种偏差难以被发现。

因此，我们实现 `faithful-research-code`，让 Codex 在科研任务中从“工程可用性优先”切换为“方法忠实性和证据可追踪性优先”：未知项必须暴露，语义变化必须获得授权，完整技术流程必须能够检查，代码只实现研究所需的最小功能。它不会移除认证、权限、路径、资源限制和破坏性操作确认等真实安全机制，而是防止工程便利机制在未经授权时改变科研语义。

## 背景

通用代码生成工具通常从生产工程角度追求可用性、兼容性和持续运行，因此可能自动加入：

- 缺失依赖时切换备用实现；
- 解析失败后跳过样本；
- OOM 后自动减小 batch size 或切换精度；
- 对异常值执行裁剪、补值或过滤；
- checkpoint 不匹配时宽松加载；
- 失败试验不进入统计分母；
- 官方评估器不可用时改用代理指标。

这些机制在工程系统中可能合理，但在科研代码中可能改变数据分布、算法路径、训练状态、评估协议或论文结论。

## 目标

`faithful-research-code` 要求 Codex：

1. 按来源定义的方法生成最小且直接的科研代码；
2. 显式暴露论文、补充材料、参考实现和用户要求之间的冲突；
3. 默认不允许改变科研语义；
4. 展示完整技术流程、模块原理、输入输出和制品传递；
5. 区分主实验、消融实验、方法改编和精确复现；
6. 将论文主张追踪到命令、配置、原始结果、聚合和图表；
7. 保留认证、权限、资源限制和破坏性操作确认等真实安全边界。

## 适用任务

- `EXACT_REPRODUCTION`：按指定来源复现论文结果；
- `SPEC_IMPLEMENTATION`：实现给定公式、算法或实验协议；
- `ADAPTATION`：在保留指定组成部分的同时进行明确授权的修改；
- `ABLATION`：只改变一个声明的科学因素；
- `AUDIT`：审查现有代码是否偏离科研方法。

普通 Web 开发、生产服务重构、认证安全和纯文档编辑不应触发本 Skill。

## 核心工作流

```mermaid
flowchart LR
    A["论文、公式、协议、用户决定"] --> B["科研合同与冲突账本"]
    B --> C["完整方法流程与科学不变量"]
    C --> D["最小充分代码实现"]
    D --> E["主实验、消融与统计协议"]
    E --> F["原始结果与聚合/绘图"]
    F --> G["论文主张与 Artifact 证据"]
    D --> H["语义回退审计"]
    H --> G
```

### 1. 科研合同

每个关键选择被分类为：

- `METHOD_DEFINED`：由方法或来源明确规定；
- `PROTOCOL_DEFINED`：由数据集、benchmark 或评估器规定；
- `USER_DEFINED`：由用户明确授权；
- `UNKNOWN`：现有证据无法确定。

`UNKNOWN` 不会被静默实现，而是阻塞、参数化、明确授权或排除在结论之外。

### 2. 完整代码流程

Skill 要求报告每个阶段或 round 的：

- 调用方式和执行条件；
- 输入及其来源；
- 技术原理与来源规则；
- 代码位置；
- 输出制品；
- 下游使用方式；
- 失败行为；
- 实际验证方法。

对于 Prompt、检索、正负样本、记忆、训练记录、奖励和评估器，还需展示选择规则、插入位置、解析方式和因果用途。

### 3. 论文主张到结果的追踪

每个主要结论、结果表格和结果图需要映射到：

```text
论文主张
  -> 精确命令
  -> 冻结配置
  -> 数据/模型/评估器版本与哈希
  -> seeds 与运行记录
  -> 原始输出
  -> 聚合或绘图代码
  -> 期望结果与容差
  -> 实际执行状态
```

报告值不得手工复制到表格或图片中。

### 4. 调参、统计与基线公平性

对于结果型实验，Skill 要求预先声明：

- 超参数搜索空间、方法和预算；
- 验证集和测试集访问边界；
- checkpoint、阈值和最优配置选择规则；
- 实验单位、seed、运行次数和估计量；
- 不确定性、失败运行和统计分母；
- 基线的数据、调参预算、算力、选择规则和评估器差异。

### 5. Reviewer-ready Artifact

当任务面向论文发布、公开仓库或 Artifact Evaluation 时，Skill 还会要求：

- 冻结代码版本与环境；
- 区分 smoke test 和完整复现；
- 每项主张对应可执行命令；
- 数据、模型、许可证和访问限制；
- 时间、GPU/CPU、内存、存储、网络和外部服务成本；
- 匿名审稿版与正式归档版的发布状态；
- 已知限制和适用的伦理、隐私或 AI 使用披露。

这些发布要求不会强制施加到单个公式或局部确定性实现上。

## 安装

### 使用 Codex Skill Installer

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo Fangzhou-Code/faithful-research-code \
  --path faithful-research-code
```

如果本地已经存在同名 Skill，安装器会停止。请先备份或移动旧版本，再执行安装。

### 手动安装

```bash
git clone https://github.com/Fangzhou-Code/faithful-research-code.git
cp -R faithful-research-code/faithful-research-code ~/.codex/skills/
```

安装后，在下一次 Codex 对话中使用：

```text
$faithful-research-code 请按照论文公式和补充材料实现主实验，并禁止未经授权的语义回退。
```

## 使用示例

### 论文复现

```text
Use $faithful-research-code to reproduce the paper's main experiment, map every reported result to its command and raw artifacts, and expose unresolved source conflicts.
```

### 消融实验

```text
Use $faithful-research-code to remove only the auxiliary loss, keep every other scientific factor fixed, and document main and ablation experiments separately.
```

### 代码审计

```text
Use $faithful-research-code to audit this training pipeline for sample dropping, clipping, checkpoint fallback, backend switching, and denominator changes. Do not edit unless requested.
```

## README 输出要求

实现类任务会生成或更新项目自己的 `README.md`，包括：

- 背景；
- Gap / 挑战；
- 科研方法贡献；
- 支持范围与限制；
- 主实验；
- 消融实验；
- 参数作用和科学影响；
- 完整代码流程和技术原理；
- 论文结果复现映射；
- 调参与统计协议；
- Artifact 发布和验证状态。

生成内容必须来自实际代码和已有来源，不得虚构命令、结果、贡献、许可证或伦理审批。

## Python 语义回退审计器

仓库附带一个辅助审计器：

```bash
python faithful-research-code/scripts/audit_semantic_fallbacks.py \
  path/to/changed_code \
  --min-severity low
```

JSON 审计轨迹：

```bash
python faithful-research-code/scripts/audit_semantic_fallbacks.py \
  path/to/changed_code \
  --json
```

来源明确授权的操作可以使用带理由的抑制标记：

```python
# research-fidelity: allow=RF301 reason="Equation 4 requires clipping before reduction"
value = value.clip(-1, 1)
```

被抑制项仍保留在 JSON 记录中。该工具是 Python AST 启发式审计器，不是科研忠实性的完整证明；YAML、Shell、Slurm、Notebook、聚合和绘图路径仍需人工检查。

## 仓库结构

```text
.
├── README.md
├── README.zh-CN.md
└── faithful-research-code/
    ├── SKILL.md
    ├── agents/openai.yaml
    ├── assets/research-readme-template.md
    ├── references/code-generation-contract.md
    ├── scripts/audit_semantic_fallbacks.py
    └── tests/
```

README 位于 GitHub 仓库根目录，不属于实际安装的 Skill 包。

## 验证

运行单元测试：

```bash
python3 -m unittest discover \
  -s faithful-research-code/tests \
  -p 'test_*.py'
```

当前测试覆盖 Skill 合同、触发边界、审计退出码、JSON 兼容性、抑制轨迹以及典型科研语义回退。

## 局限

- 审计器目前只静态分析 Python；
- Skill 无法替代论文作者对未知协议的确认；
- 测试通过不等同于论文数值复现；
- 作者自行运行不能声明为独立第三方复现；
- 不同会议的匿名、伦理和 Artifact 政策仍应以目标会议当期规则为准。

## 许可证

当前发布目录尚未包含许可证文件。在选择开源许可证前，默认著作权规则仍然适用。
