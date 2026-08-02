# 镂刻 - **超越氛围编程，自是精密镂刻**

![LouKe pipeline](docs/hero.png)

[🇺🇸 English](README.md) · [🇨🇳 中文](README.zh.md)

**LouKe 是一套规格先行、测试驱动、工具对齐 Agent 行为的多 Agent 协作开发方法。**

**louke还没有达到正式发布水平，请暂勿在你的项目中安装并使用。预计将在2周内（8/15）达到完整可用水平**

---

## 1. 为什么是 LouKe？

你不可能凭借一句话式的氛围编程就造出一个真正可用的软件。当我们进行氛围编程时：

- 你并没有想清楚想要一个什么样的软件，却希望 Agent 知道
- 文字始终是写意的，包含了很大的想象空间，而软件必须是精确的
- 讲述了许多 Story，但无论是 AI，还是你自己，都没有形成一个完整的施工图

一个真正可用的软件，它可能包含成百上千个子项需求，数以万计的执行路径和边界检查条件。

我们必须依赖具体、详尽的规范、验收标准和测试计划。人类必须参与、指导这些文档的生成，通过工具将它们拆解成为数以百（千）计的、可跟踪的子项目，让 Agent 的代码与这些子项目一一对应，才有可能构造成一个可回退、可追踪、可信的软件生产过程。

这就是镂刻的价值。超越氛围编程，把智能体编程变成精密制造，完美实现你规定的每一个细节。

即使是 spec-kit / superpowers / oh-my-openagent，依然没人把 spec 做成"编程契约"。一份 spec 要成为契约，得同时满足三件事：

- **子需求之间是正交关系** —— 子需求之间不矛盾、不重复，已经过奥卡姆剃刀的修剪。
- **颗粒度合适** —— 你不可能要求 Agent 能读完上万字的文档，并且还能把握住其中每一个小小的细节。除非你把它们拆成一项项可以完美装进一个 PR 的任务里。
- **可追踪** —— 从需求到代码到测试，每一条线索都必须可以双向追溯：向前能查到源头，向后能查到落点。任何一条需求如果找不到对应的代码和测试，它就是挂在墙上的空头支票。

而 LouKe 与这些框架相比，有着截然不同的设计哲学：LouKe 把所有这些做成了"基础设施即检查点"（Infrastructure-as-Checkpoint）——可追踪的闭环不在 AI 的自律里，而在外部 CLI 在 commit-time 的强制执行里。exit 0/1 是 OS 进程返回值，绕不过。工程世界只认这一种语言。

因为程序员会犯错，所以我们才有测试。Agent 也会犯错，不靠 AI 的自律，靠可被严格对齐的规范和工具。

## 2. LouKe 如何做到？

LouKe 把上面的契约三原则落到 5 件可观测的事上。每件都有一条 lk 命令或可追溯的产物对应——不只是 prompt，而是工具：

- **spec → GitHub issue，commit 必带 issue 引用** —— Lex 把每个 FR 自动转成一个 issue，Devon 的 commit message 强制 `#NNN` 格式。需求到代码，单向追溯，永不丢失

- **test ↔ AC-FRXXXX-YY 自动关联，CI 静态校验双向闭合** —— 每个测试 docstring 必带 `AC-FRXXXX-YY` 编号。`lk agent archer ci-scan` 在 commit-time 校验：每条 AC 必被测试引用，每个测试必引用 AC。不闭合，merge 阻断

- **反模式 CI 门禁 + 身份一致性检查** —— `lk agent keeper gate` 静态扫 8 类反模式（`assert True` / `try/except: pass` / 无 issue skip / mock 框架核心 等）。`lk agent scout identity-check` 在流程启动前锁定 gh/git 身份一致性。违规即阻塞

- **项目 wiki 自动蒸馏** —— 基于 LLM compounding engineering 理念，`.LouKe/raw/`（每 Agent 的会话记录）→ `.LouKe/wiki/`（结构化知识）。事实、决定、现状一目了然且可 lint

- **苏格拉底式需求询问** —— Sage 多轮追问模糊的 story，直到磨出可追踪的 `spec.md` + `acceptance.md`

`LouKe` 定义了 12 个专业 Agent、10 阶段流水线、一个 `lk` CLI——让每次转换都是真正的检查，不是"agent 互相 review"那种软约束。每个 Agent 都有自己专属的工具箱，在每个 holdpoint 上，工作被卡点验证。

## 3. LouKe vs 其它

| 框架                                      | spec 是不是契约？                               | review 由谁做                                          | 强制层                             | spec → code → test 闭环                |
| ----------------------------------------- | ----------------------------------------------- | ------------------------------------------------------ | ---------------------------------- | -------------------------------------- |
| **spec-kit**（GitHub）                    | spec.md 是源头，但无 MECE / 粒度 / 可追踪约束   | 无 review                                              | 无                                 | 手工 + 社交                            |
| **superpowers**（obra，240k★）            | plan.md 是文本，无 AC 编号，无 commit-time 校验 | subagent review（同 model 自检）                       | prompt 级自律                      | TDD 间接保证（test ↔ spec 无 ID 绑定） |
| **oh-my-openagent**（code-yeongyu，64k★） | agent 自消化 spec                               | team of agents（同 LLM 不同 prompt）                   | hooks / middleware                 | task 自定，无 FR ↔ test 绑定           |
| **LouKe**                                 | FR-XXXX / AC-FRXXXX-YY + `lk agent archer ci-scan`    | 12 个不同 persona（实施者 ≠ 评审者，跨阶段语境不重叠） | `lk` CLI exit 0/1（OS 进程返回值） | FR ↔ issue ↔ commit ↔ AC ↔ test 全链路 |

## 4. 架构

![](docs/arch.png)

<!--
  agents/*.md              templates/*.md                LouKe/                LouKe/_tools/*.py
  (12 prompts)            (spec, acceptance,           (12 agents +          (Python scripts,
                          test-plan, security-          init/board/models)   wrapped by lk)
                          checklist)
       │                       │                            │                      │
└───────────┬───────────┴────────────┬───────────────┘                      │
                    │                        │                                      │
                    ↓                        ↓                                      ↓
             AI 助手                    工具强制                              被 lk 包装
          (OpenCode ——               hold points
           当前唯一                   (lk agent keeper gate,
           支持的宿主)                   lk agent judge
                                       security-audit)

  两层记忆:
    .LouKe/raw/    →   事件级, per-agent 会话记录
    .LouKe/wiki/   →   蒸馏后的知识, 由 Librarian 维护
-->

- **12 Agent** = 实施者与评审者是不同 persona，跨阶段语境不重叠
- **`lk` CLI** = OS 进程级合同，`exit 0/1` 不可绕过
- **两层记忆** = `raw/`（事件级）+ `wiki/`（蒸馏级），由 Librarian 维护
- **承诺** = spec → code → test 三段双向可达，任一节点断裂都查得到源头

## 5. 流水线

| 阶段        | 实施者        | 评审者               | 说明                                |
| ----------- | ------------- | -------------------- | ----------------------------------- |
| M-FOUND     | Scout         | Warden               | 项目奠基 + 权限门                   |
| M-SPEC      | Sage          | Maestro, Lex                  | spec + FR → issue                   |Maestro 进行内容审核， Lex 进行格式审核|
| M-TESTPLAN  | Archer        | Sage                 | 测试计划（Sage 有独有 spec 上下文） |
| M-ARCH      | Archer        | Prism                | 架构 + 接口                         |
| M-LOCK      | Maestro       | 用户                 | 3 信号锁定                          |
| M-DEV       | Devon         | **Prism → Keeper ★** | 代码 + 单元测试                     |
| M-E2E       | Shield        | **Prism → Keeper ★** | e2e 测试                            |
| M-BUGFIX    | Devon         | **Keeper ★**         | Bug 修复                            |
| M-SECURITY  | Judge（S 级） | 用户                 | 深度安全审计                        |
| M-MILESTONE | Librarian     | Maestro              | raw → wiki 蒸馏                     |

★ **HOLD POINT**——工具强制检查（`lk` CLI 返回 0/1；不通过就不前进）。`★` 仅标 commit-time 阻断 merge 的 PROD gate；stage transition 的 hold point 不单独标。

**核心原则：实施者 ≠ 评审者。始终。**

### 5.1 M-SPEC 内部：Sage ↔ Lex 三阶段交互

M-SPEC **不是** "Sage 一路产 spec → Lex 末尾审一次"。Lex 的三阶段在三个不同触发点跑，Maestro 必须主动触发阶段一/三（阶段二由 Sage Step 6 handoff，但仍经 Maestro 转发）。跳过任一阶段会使 M-LOCK 的 Lex 信号失效。

```mermaid
sequenceDiagram
    participant U as 用户
    participant M as Maestro
    participant S as Sage
    participant L as Lex

    U->>M: Story（"做用户认证"）
    M->>S: M-SPEC 启动
    S->>U: Step 1: 聊天里问 ≤7 个问题
    S->>S: Step 2: 起草 spec.md + acceptance.md
    S->>U: Step 3: spec 内 quote 追问（≤5 轮）
    S->>S: Step 4: 加 HTML 锚点
    S->>S: Step 5: 创建 GitHub issue + 关联 Project
    Note over M: Maestro 触发 Lex 阶段一
    M->>L: verify-acceptance（L1-L5）+ quote-check
    L-->>M: [通过] / [拒绝]
    alt 阶段一拒绝
        M->>S: 修 spec.md（原样转发工具 stderr）
        S->>S: 修正
        M->>L: 重跑阶段一
    end
    S->>S: Step 6: quote-check exit 0 → handoff
    Note over S: Sage Step 6 通知 Lex 阶段二（经 Maestro）
    M->>L: issue 覆盖 + Project 关联检查
    L-->>M: [通过] / [拒绝]
    alt 阶段二拒绝
        M->>S: 补建/补关联 issue
        S->>S: 修正
        M->>L: 重跑阶段二
    end
    Note over M: Maestro 触发 Lex 阶段三
    M->>L: verify-issue（L1-L8 schema）
    L-->>M: [通过] / [拒绝]
    alt 阶段三拒绝
        M->>S: 修 issue schema 字段
        S->>S: 修正
        M->>L: 重跑阶段三
    end
    Note over M: 3 信号齐：Sage quote-check ✓ + Lex 三阶段 ✓
    M->>U: M-LOCK: 确认 spec 锁定
    U-->>M: 已确认
    M->>M: 推进到 M-TESTPLAN
```

**关键规则**：
- 阶段一失败 → 只改 spec；阶段二失败 → 只改 issue；阶段三失败 → 只改 issue schema 字段
- 若修正时发现根因在上游 → 退回 M-SPEC 对应步骤，从阶段一重跑
- Maestro 退回时原样转发工具输出（stderr/stdout）给 Sage，不转述

## 6. 12 个 Agent

每个 agent 的默认 primary 模型（带同档 fallback）。通过 `~/.LouKe/models.json`（用户级）或 `.LouKe/models.json`（项目级）覆盖；查看 `lk models list` / `lk models doctor` 了解当前绑定，用 `lk models bind <abstract> <full>` 改写。

### 6.1 Agent 权限矩阵 (v0.6-009)

5 个 agent 有显式 `permission:` 块（YAML 对象，11-13 键）约束工具访问；其余 7 个也走显式块（每个 11 keys）— 12 个 agent 都显式声明 permission。**所有 11 个 subagent 都有 `task: deny`** 以强制"Maestro 是唯一编排者"的设计。

| Agent | Mode | `question` | `edit` | 备注 |
|---|---|---|---|---|
| **Maestro** | `primary` | ❌ | ✅ | 指挥家；`task: allow` 调 subagent；`external_directory: ask`；13 键 |
| **Warden** | `subagent` | ❌ | ❌ | 只读审计；11 键 |
| **Judge** | `subagent` | ✅ | ❌ | 只读安全审计；11 键；可向用户确认 |
| **Archer** | `subagent` | ✅ | ✅ | 写 spec 产物；11 键；路径靠 prompt 限制 |
| **Librarian** | `subagent` | ❌ | ✅ | 写 wiki；11 键；路径靠 prompt 限制 |
| **Sage** | `subagent` | ✅ | (默认) | 交互式 spec 澄清 |
| **Scout** | `subagent` | ✅ | (默认) | 交互式项目奠基 |
| Lex / Devon / Shield / Keeper / Prism / Warden / Librarian | `subagent` | ❌ | `task: deny`, `question: deny` | 非交互式；显式 permission 块 |

> 跑 `lk agent lint` 校验所有 agent frontmatter 合规。

### 6.2 分层编排 (v0.6-009)

**Maestro 是唯一的 `mode: primary` agent**。其余 11 个都是 `mode: subagent`——它们**不**在 OpenCode `<Leader>a` 列表里，不能被切换为 primary。Maestro 通过 `task` 工具编排它们。

- 用户**只**在 `<Leader>a` 看到 Maestro
- Maestro 在隔离子会话里派发工作给 subagent
- Subagent `question` 调用冒泡到**主窗口**（2026-07-03 实测确认）
- 用户全程不需要按 `<Leader>a` 切换主代理
- Subagent 完成后焦点自动回到 Maestro
- 想看 subagent 实时进度：按 `<Leader>+Down` 进入子会话；`<Leader>+Up` 返回

### 6.3 12 个 Agent (参考表)

| Agent         | 职责                                   | 智力档位 | 开源示例            | 闭源示例（参考）                        |
| ------------- | -------------------------------------- | :------: | ------------------- | --------------------------------------- |
| **Maestro**   | 指挥家 — 协调整支流水线                |    A     | `minimax-m3`        | `gpt-5.6`, `fable`                      |
| **Sage**      | 贤者 — 苏格拉底式追问需求              |    A     | `glm-5.2`           | `gpt-5.6`, `fable`                      |
| **Judge**     | 裁判 — S 级深度安全审计                |    S     | `minimax-m3`        | `gpt-5.6`, `fable`                      |
| **Archer**    | 射手/架构师 — 设计 test-plan + 架构    |   S/A    | `glm-5.2`           | `gpt-5.6`, `fable`                      |
| **Devon**     | 锻造者 — R-G-R 编码                    |    A     | `kimi-2.7-code`     | `opus-4.8`, `gpt-5.5`                   |
| **Prism**     | 棱镜 — 多角度代码评审（反模式 + 安全） |    A     | `deepseek-v4-pro`   | `opus-4.8`, `gpt-5.5`                   |
| **Shield**    | 盾牌 — 写 e2e 测试脚本                 |    A     | `kimi-2.6`          | `opus-4.8`, `gpt-5.5`                   |
| **Lex**       | 律法 — 规范级结构校验                  |    B     | `deepseek-v4-flash` | `gpt-5.4-mini`, `gpt-5.4`, `sonnet-4.6` |
| **Warden**    | 看守人 — 守门、确认退出条件            |    B     | `glm-5`             | `gpt-5.4-mini`, `gpt-5.4`, `sonnet-4.6` |
| **Keeper**    | 门禁守护者 — 守住质量门禁              |    B     | `minimax-2.7`       | `gpt-5.4-mini`, `gpt-5.4`, `sonnet-4.6` |
| **Scout**     | 勘探者 — 探路、确认前置条件            |    B     | `glm-5`             | `gpt-5.4-mini`, `gpt-5.4`, `sonnet-4.6` |
| **Librarian** | 图书管理员 — 整合 Wiki、项目记忆       |    B     | `minimax-2.7`       | `gpt-5.4-mini`, `gpt-5.4`, `sonnet-4.6` |

## 7. 使用指南
### 7.1. 安装

> **平台**：macOS / Linux。Windows 用户请走 [WSL2](https://learn.microsoft.com/zh-cn/windows/wsl/) 或 Docker。`install.sh` 自带 `uname -s` 检查，在不支持的平台上会清晰报错并退出。

```bash
# 标准 pip-based 安装（推荐）：自动建 venv、配 PATH、链接 lk 到 ~/.local/bin
curl -sSL https://raw.githubusercontent.com/zillionare/LouKe/main/install.sh | bash

# 或固定版本
curl -sSL https://raw.githubusercontent.com/zillionare/LouKe/main/install.sh | bash -s -- v0.3.0

# 或开发模式（clone 后 editable 安装）
git clone https://github.com/zillionare/LouKe
cd LouKe
./install.sh --editable

# 验证
lk --help
```

`install.sh` 干 4 件事：

1. 在 `~/.LouKe/venv/` 建独立 venv（不污染系统 Python）
2. `pip install LouKe` 装到 venv
3. `~/.local/bin/lk` → venv 内 `lk` 的符号链接，并 append PATH 到 shell rc
4. 验证 + 打印卸载指引

卸载：`rm -rf ~/.LouKe/venv ~/.local/bin/lk`

### 7.2. 30 秒上手

```bash
# 新项目（创建 <name>/ 目录，含 .LouKe/ 骨架 + OpenCode agents + issue template + CI workflow）
lk init my-project
cd my-project

# 接入既有 git 仓库（非破坏式，在现有代码旁添加 .LouKe/）
cd ~/work/my-existing-repo && lk init .
```

`lk init` 会：

1. 建项目结构（`.louke/{templates,project,project/specs,wiki/pages,wiki/decisions,raw}/`）
2. 复制 louke 包内的 templates 到 `.louke/templates/`（spec / acceptance / prd / bug-fix / …）
3. 装 `.github/ISSUE_TEMPLATE/feature.yml`（4 位 FR schema）+ `.github/ISSUE_TEMPLATE/bug.yml`
4. 写 `default_agent: maestro` 到项目级 `opencode.json`
5. 从已安装 louke 包的 agent 提示词生成 `.opencode/agents/*.md`（每 agent 含解析后的 `model:` 字段）。升级 louke 后重跑 `lk board opencode` 即可刷新
6. 可选：装每日 wiki 蒸馏 cron（`--no-cron` 跳过）

> **Agent 提示词归包所有**。12 个 agent 提示词住在已安装的 `louke` Python 包里 — 故意没有项目侧副本可改（也不应改）。`lk board opencode` 把它们落到 `.opencode/agents/` 给 OpenCode 用。之前开放项目覆盖 agent 的尝试被移除，因为会引发过期格式漂移。

然后启动 OpenCode——默认 primary agent 就是 **Maestro**。在聊天里直接说要做什么，例如：

> "我们想加一个用户认证功能——用户名密码登录，再加一个 Google 登录。"

之后的事，全部由 Maestro 调度流水线。你不需要手动切 agent；Sage 的追问、Judge 的安全发现都会从 Maestro 回到你这里。

### 7.3. 一个完整的会话长什么样

沿用"加用户认证"为例，时间线单线展开：

1. **M-FOUND** — `lk agent scout foundation` 创建 repo、GitHub Project、Test Issue 验证权限
2. **M-SPEC** — Sage 在聊天里追问（MFA？session 超时？rate limiting？）；Lex 找出 3 个结构问题；Sage 修复。**3 信号齐**时锁定：`lk agent sage quote-check` exit 0 + Lex 3 阶段通过 + 你在 IDE 确认
3. **M-TESTPLAN** — Archer 写 `test-plan.md`（3 层策略 + AC 追溯 + 反模式规则）；Sage 评审（持 M-SPEC 独有上下文）
4. **M-ARCH** — Archer 写 `architecture.md` + `interfaces.md`；Prism 查 spec/code 一致性
5. **M-LOCK** — Spec 锁定。实现开始
6. **M-DEV** — Devon 用 R-G-R 编码。每次 commit 前缀 `test: red` / `feat: green` / `refactor`。Prism 评审（反模式 + 安全 quick scan）；`lk agent keeper gate` 跑 commit 格式 + 测试
7. **M-E2E** — Shield 写 e2e（B 级，固定方法：Playwright/testclient/DB）；同 Prism + Keeper
8. **M-SECURITY** — `lk agent judge security-audit` 做 pattern 扫描 + S 级语义审查。**你**最终拍板
9. **M-MILESTONE** — `lk agent librarian distill` 蒸馏会话到 wiki；`lk agent maestro advance --stage M-MILESTONE` 关闭

每一步的转换是不同 agent；每个 hold point 是工具强制；每个 handoff 是显式 trace。

以上流程由 Maestro 自动调度——你只需要在 OpenCode 里对 Maestro 说"做用户认证"，它会依次调起 Scout/Sage/Lex/Archer/Devon/Shield/Judge/Librarian。下面是你（通过 Maestro 对话）看到的每一步。

### 7.4. 配置 Agent 模型

每个月都有新的模型发布。因此，你可能需要动态调整 Agent 的模型。每个 agent 有默认模型；日常开发中把编码 Agent 切到本地小模型即可省大部分 token。

```bash
# 查看当前绑定
lk models list
lk models doctor            # 检查是否有 missing/failed 解析

# 临时把某个 agent 切到便宜模型
lk models bind devon kimi-2.7-code
lk models unbind devon       # 恢复默认
```

`models.json` 优先级：**项目级**（`.LouKe/models.json`）> **用户级**（`~/.LouKe/models.json`）。

### 7.5. Sage 的需求讨论 - 回到邮件对话时代！

Sage 会在拿到 Story 之后，立即在会话窗口中，开启一轮需求澄清，但只会问少于7个问题。更多的问题不适合以这样的方式来澄清。LouKe 把电子邮件中的 inline comment 风格带回来。

我们用 Markdown quote block 开启讨论：

````markdown
## FR-0100 画一个圆

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ⚠️          |

你将绘制一个圆，半径是 0.5m。

> Sage: 请问画笔的颜色和粗细怎么确定？
````

Sage 觉得这个需求没有说清楚，无法验收。于是，他问： 请问画笔的颜色和粗细怎么确定？

你用 **多一层 `>`** 缩进来回复：

````markdown
> Sage: 请问画笔的颜色和粗细怎么确定？
>> Aaron: 提供一个工具箱，让用户自己选择
>>> Sage: 需求已确认。
````

这是标准的邮件会话语法。如果觉得 spec 表述错而不需要讨论，可以直接改 spec；Sage 会对 diff 找到你的修改，如有疑问再开会话。

### 7.6. GitHub Projects：管理发布

LouKe 使用 Github Project 来管理发布。一次发布从 Story 开始，Sage 拆解需求，创建 Github issue，并自动关联到 Github Project。Release Notes 也自然来自于这个 Project。

不过我们还附赠了一件小小的礼物，通过创建一个名为{repo}-backlog 的 project，我们送给你一个灵感收集箱。如果你有什么灵感，一时无法排进当下的发布当中，你会发现这个 project 非常好用。后续的发布就从这里开始规划。

`lk agent scout foundation` 给每个 repo 建两个 Project：

- **`{repo}-{version}`** —— per-release，跟踪当期 milestone 的 issue
- **`{repo}-backlog`** —— per-repo（永久），存放未排期的 idea

`gh issue create --no-milestone` 创建的 issue 自然进 backlog；planning 时用 `gh project item-add` 把 backlog issue 拉进当期 release。

### 7.7. pre-commit 质量门禁

项目的 `.pre-commit-config.yaml` 会在 commit 时自动跑 lint、format、typecheck 与测试 —— 零 token、无需手动触发。使用 `--no-verify` 跳过 hooks 是反模式，会破坏"基础设施即检查点"的契约。模板说明见 `louke/templates/pre-commit/README.md`。

## 8. 常用命令速查

### 8.1. 项目初始化
lk init my-project                         # 新项目
lk init .                                  # 接入既有仓库
lk agent scout foundation --repo owner/repo --version v0.1 --spec-id v0.1-001-init
lk agent scout identity-check --repo owner/repo
lk agent scout invite-owner owner/repo --version v0.1

### 8.2. 流水线推进
lk agent maestro status                          # 查看当前阶段
lk agent maestro advance --stage M-DEV           # 推进到下一阶段
lk agent maestro regress --stage M-SPEC --reason "spec 遗漏 NFR"
lk agent maestro escalate --reason "用户连续 3 轮未回复"

### 8.3. 代码质量
lk agent archer ci-scan --spec ID                # AC 引用闭合校验
lk agent keeper gate                             # commit 格式 + R-G-R 顺序 + 反模式扫描
lk agent judge security-audit --release releases/v0.1

### 8.4. 模型管理
lk models list                             # 查看 agent→模型绑定
lk models doctor                           # 诊断缺失/模糊匹配
lk models bind devon kimi-2.7-code         # 临时覆盖
lk models unbind devon

### 8.5. Wiki
lk agent librarian lint                          # 健康检查
lk agent librarian distill                       # 蒸馏 raw 会话到 wiki pages

## 9. 排错指引

**`lk: command not found`** —— `~/.local/bin` 不在 PATH。在 shell rc 里追加 `export PATH=$HOME/.local/bin:$PATH` 并 `source`（或重开终端）。

**`lk agent scout foundation` 失败并提示 `gh not authenticated`** —— 先 `gh auth login`，然后 `lk agent scout identity-check` 验证。

**Sage 对同一段需求反复追问** —— 可能是：
- 你的回复没多一层 `>` 缩进，Sage 没识别为新回复
- 你直接改了原文——Sage 会通过 git diff 发现修改，追问确认。此时在修改处回复"✓ resolved"即可

**commit 被 `lk agent keeper gate` 拦下** —— 终端会打印具体哪一类反模式命中。常见原因：

- commit message 不符合 R-G-R 前缀规范（如写了 `feat: add login` 而不是 `feat: green add login`）
- `feat: green` 出现在 `test: red` 之前（R-G-R 顺序错）
- test docstring 没带 `AC-FRXXXX-YY`
- 写了 `assert True` / `try/except: pass` / mock 框架核心

**OpenCode 启动后看不到 12 个 agent** —— 检查 `.opencode/agents/` 目录和 `opencode.json` 的 `default_agent` 字段；必要时重跑 `lk init --force`。

**想知道"现在走到哪一步了"** —— `lk agent maestro status` 一句话告诉你。

## 10. 未来增强（不在 v0.6-008 范围）

- **[#78](https://github.com/zillionare/LouKe/issues/78)** —— `.LouKe/project` 作为独立私有 GitHub repo（git submodule 引入），把 spec/wiki 与公开代码隔离
- **[#79](https://github.com/zillionare/LouKe/issues/79)** —— `LouKe serve` web 服务，渲染 + 可选在线编辑 wiki / spec / acceptance / test-plan

## 11. 许可证

MIT

## 12. 更新历史

Louke 遵循 [语义化版本](https://semver.org/)。CLI (`lk`) 通过 `pip install --upgrade louke` 自更新；项目级状态（`.louke/`, `~/.louke/models.json`）升级时保留。Agent 提示词来自已安装的包，所以升级 louke 会自动带上 agent 提示词的变更 —— `lk upgrade` 后跑 `lk board opencode` 即可刷新 `.opencode/agents/`。

### v0.6.0 — v0.6.13 (2026-07-04)

| 版本 | 重点 |
|---|---|
| **v0.6.13** | `lk models doctor` critical bugfix: `ok` 变量遮蔽了 import 的 `ok` 函数（与 v0.6.8 在 `set-model` 修过的同模式, 但 `doctor` 漏修了). 任何有 alias 的 model 都会 crash. 加了回归测试. |
| v0.6.12 | 清理: 删 6 个 agent prompt 里的内部 spec 引用 (`(v0.6-008 FR-0710)`, `(FR-0070)` 等). 这些是发行给用户的, 不该有内部追踪 ID. |
| v0.6.11 | 清理: 删 4 个交互式 subagent prompt 里冗余的 `(实测确认 2026-07-03 14:00 by Aaron)` 注释. |
| v0.6.10 | Subagent 调度澄清: `agents/Maestro.md` 显式写 "只**用 `task` 工具调子 agent, 不要用 `opencode run`". Spec FR-0070.7 文档化两种 invocation 模式 (生产 TUI vs CLI 测试). |
| v0.6.9 | `lk agent set-model` 重设计: 直接写 `.opencode/agents/<name>.md` (output), 不改 package source. **临时** — 下次 `lk board opencode` 用包 source 重新生成覆盖. |
| v0.6.8 | `lk agent set-model` bugfix: `ok` 变量遮蔽了 import 的 `ok` 函数 → `TypeError: 'bool' object is not callable`. |
| v0.6.7 | `lk agent list-models` — 表格显示所有 agent 的 `models:` chain + 当前 resolved model. `--unbound-only` flag. |
| v0.6.6 | `lk agent set-model <name> <abstract>` — 一条命令改 agent 模型. 交互式 bind + probe 后保存. |
| v0.6.5 | `lk models bind` 在保存前用 `opencode run --model <m> "ping"` probe. 失败时提示 `[r]etry / [s]kip / [a]ssign-force`. |
| v0.6.4 | `lk board opencode` 要求 git 仓库 (或显式 `--root <path>`). 防止在随机目录误创建文件. |
| v0.6.3 | `lk models bind` 排序: 用 Levenshtein 距离代替子串匹配. 对命名风格不匹配的候选排序更准 (如 `kimi-2.6` ↔ `kimi-k2.6`). |
| v0.6.2 | `lk board opencode` 和 `lk models doctor` 加进度输出: 5 步 / 4 步编号 + ANSI 颜色 (✓/✗/⚠) + Spinner. |
| v0.6.1 | Source `agents/*.md` 改 v0.6.0 风格 (`mode: primary/subagent`, `permission:` 块). |
| v0.6.0 | Agent 权限收紧 + 分层编排. 4 角色 (Warden / Judge / Archer / Librarian) + Maestro 显式 `permission:` 块 (11-13 keys). 11 agent 改 `mode: subagent`; Maestro 是唯一 `mode: primary`. |

### v0.3.0 (2026-06-29) — 首次公开发布

12 个专门化 agent, 10 阶段流水线 (M-FOUND → M-MILESTONE), `lk init` / `lk agent scout foundation` / `lk agent archer ci-scan` / `lk agent keeper gate`, OpenSpec 风格 YAML issue 模板, 129 个 bats 测试.

---

更早 (pre-v0.6) 的 release notes 见 `.github/RELEASE_NOTES_v0.X.md`.
