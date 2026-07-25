# STR-1405: 最小首次设置、状态落点与按需环境引导

---

| Story ID | 创建时间                  | 分流建议         |
| :------- | :------------------------ | :--------------- |
| STR-1405 | 2026-07-23T20:13:19+09:00 | Go（Agent 建议） |

---

## 1. 原始输入

> 现在我们开始新的 story, 版本号依然是0.14. sotry是：首次 Workspace Onboarding、Project 创建引导与 Project Status 驾驶舱

> story 对用户首次旅程描写得不对。请按以下进行修改：
>
> 首次Workspace onboarding 就这么一件事：
>
> 1. 创建首个用户
> 2. 检查 opencode 是否可用，是否至少配置了一个可用模型 -- 需要通过 opencode run "please echo hi" 类似的命令来进行检查
> 3. 跳转到 workbench。
>
> wizard 完成后，记录状态。未完成之前，访问任何地址都跳转回 /setup 来。
>
> 当用户登录后，如果当前正处在活跃开发状态，则跳转 project status，显示最新的工作流状态。
> 当用户登录后，否则，显示空的 workbench，此时进行 environment 检查，即：
>   1. 检查github cli 有没有安装；若通过，则执行 gh auth status，看是否登录，token_scope 是否包含 gist, project, repo, workflow,缺一则向用户提示权限不足，当前可以继续，但正式开始新的 project 前，需要补齐。
>   2. 检查当前目录是不是 git目录（已完成初始化），如果没有，请用户提供 repo 的 url，完成 git 初始化（含与 repo 的绑定）
>    检测由 runtime 执行，把检测到的状态发到 guide 的聊天窗口，询问人类是否要安装 gh，完成 git 初始化。
>
> 按这些要求，修正 story.md

## 2. 用户意图

- 为Workspace 指定首位用户，以及检查 opencode/model 可用性
- 指定用户登录后的 landing page 及行为
- 提供创建 Project 的 wizard 行为说明
- 提供 Project Status 视图和操作说明

## 3. 核心操作路径

### 3.0 产品现状（v0.14-003 截止）

本 Story 是对现有产品的修改，不是在空白上新建。以下为 v0.14-003 截止时各路径的产品现状，作为每条路径的变更基线：

| 路径 | 现状 | 本 Story 变更 |
|------|------|---------------|
| 首次 Setup | 六步 wizard（identity → repository → dependencies → review → applying → complete），v1 manifest 以 `current_step` + `completed_steps[]` 记录进度，首次 Setup 包含 Git 初始化与 GitHub 配置 | 替换为三态 manifest（pending_user → pending_model → complete）；Git/GitHub 移至 §3.3；增加 OpenCode 真实模型运行检查 |
| 登录落点 | 登录后落点为 workbench 首页或 legacy home page（取决于项目版本和 `?legacy=1`）；`entry_resolver` 含 `released` 落点和 `setup_step` 参数；无活跃 Project 路由 | 移除 `released`/`setup_step`；统一进入 Projects 页面；活跃 Project 显示 Status，无活跃显示 New Project；sidebar 增加 Guide |
| 创建 Project | 概念为 "Workflow Runs"，用户从 Runs 页面创建 run；无环境 readiness 门禁；无 Story/版本预览确认 | 用户可见概念统一为 "Project"；New Project 增加环境门禁；增加预览确认；创建后跳转 Dev Docs |
| Project Status | run detail 页面（`/runs/{run_id}`）展示阶段列表；无水平时间线、无回拨操作、无"上卡下图"布局 | 重设计为 Project Status 驾驶舱；增加时间线（含回边）、活跃节点卡片、回拨指针 |
| 入口保护 | 基于 `setup_only` 标志和 `list_users()` 检查，仅拦截根路径 | 改为 SetupGateMiddleware 全局拦截，Allowlist 放行 Setup 必需路径 |

下游 Spec/Architecture/Acceptance 必须基于此现状描述变更，而非从零设计。

### 3.1 首次运行的最小 Setup

- **产品现状**：见 §3.0 表格"首次 Setup"行。v0.13 的六步 wizard 将 Git 初始化、GitHub 配置、依赖检查全部压在首次 Setup 中，导致首次体验过重。v1 manifest 以步骤列表记录进度，无 CAS 保护。
- **用户起点**：用户在当前目录首次启动 Louke；该 workspace 尚无 Setup 完成记录，也没有首用户。
- **入口/触发**：用户访问产品任意用户入口时，系统统一将其带到 `/setup`。

1. 用户在 `/setup` 创建首个本地用户。
2. Runtime 检查 OpenCode 是否可调用，并通过一次真实、无产品副作用的最小运行（例如 `opencode run "please echo hi"`）验证至少一个已配置模型能够成功响应；仅发现命令或读取模型配置不算通过。
3. 若检查失败，用户留在 `/setup`，看到可定位的失败原因与重试入口；已成功创建的首用户不要求重复创建。
4. 当首用户和 OpenCode 实际模型检查均成功后，系统持久化该 workspace 的 Setup 完成状态，并跳转到 Workbench。

- **完成结果**：用户已拥有可登录身份，且 Louke 已证明 OpenCode/模型具备执行最小任务的能力；Setup 不要求配置 Git、GitHub CLI、repository、release 或 Project。
- **继续/返回**：Setup 完成后进入 Workbench；刷新、重启或再次登录读取已记录状态，不重复运行首次 Wizard。Setup 未完成时，访问其他用户页面仍返回 `/setup`，直到修复并重试成功。

### 3.2 登录后的状态落点

- **产品现状**：见 §3.0 表格"登录落点"行。v0.13 的 `entry_resolver` 含 `released` 落点（已发布项目的落地页）和 `setup_step` 参数（Setup 进度感知），登录后根据项目版本和 legacy 参数选择 workbench 首页或旧版 home page。无"活跃 Project → Status"的路由逻辑，无 Guide sidebar 关联。
- **用户起点**：Setup 已完成，用户从登录页成功登录。
- **入口/触发**：登录成功后，在 workbench 中，进入 Projects 页面

1. 若存在活跃开发，显示活跃 project 的 status(main panel)
2. 若不存在活跃开发，则在main panel 中央，显示一个New Project的按钮（含提示）
3. 在 sidbar 处，显示 Agent 对话框（使用 Guide 的 session），并与当前的 project 关联

- **完成结果**：返回用户立即回到当前工作；尚未开始工作的用户可以创建新的 project。

### 3.3 创建新的 Project

> **Aaron**: 即现在页面上的 Workflow Runs。Workflow Runs 实际上是一次规划中的 Release。我们现在统一称为 Project -- 与 Github Project 对应。我们通过 Project 来管理发布。

- **产品现状**：见 §3.0 表格"创建 Project"行。当前用户从 Runs 页面创建 "Workflow Run"，无环境 readiness 门禁（gh 安装、gh auth、Git repo 检查不在创建流程中），Story 与 release version 输入无预览确认步骤，创建后无明确跳转目标。
- **用户起点**：用户已登录、Setup 已完成，当前没有活跃开发，系统正在显示空 project
- **入口/触发**：用户点击『New Project』 按钮

用户点击 New Project 按钮后，按以下步骤操作：
1. 运行环境检查wizard（模态对话框），并把正在进行的步骤发往 Guide 对话框，用户可以通过对话以获得解释
   1. Runtime 检查 GitHub CLI (`gh`) 是否安装
   2. 若已安装，Runtime 执行 `gh auth status` 检查登录状态，并检查当前 token scope 是否包含 `gist`、`project`、`repo`、`workflow`。未登录或缺少任一 scope 时，Guide 明确说明缺项及影响。
   3. Runtime 检查当前 workspace 是否已经是初始化完成的 Git repository，如果不是，显示输入框，要求用户填写 repository URL，并在点击下一步时，完成绑定。

   三步中任意一步错误将阻断创建 Project 流程。用户可以通过 Guide 获得帮助。检查在后台完成，只有检查不通过时，才在 UI 上显示这一步。
2. 用户输入故事、release version，进入下一步之前暂时保存（浏览器即可）
3. 显示 Story/版本预览，创建和取消按钮。点击创建将由 Scribe 生成 Story 文档，用户被重定向到 Dev Docs，加载刚刚创建的 Story。

- **完成结果**：重定向到 Dev Docs 页面，并且加载最新 story.md 文档。
- **继续/返回**：在完成创建之前中断，回到浏览器，状态保持。

### 3.4 Project Status

- **产品现状**：见 §3.0 表格"Project Status"行。当前 run detail 页面（`/runs/{run_id}`）以阶段列表展示 workflow 进度，数据来自 Runtime read model。无水平时间线可视化（含回边），无回拨操作入口，无"上卡下图"布局，无节点详情浮层。
- **用户起点**：见 §3.2（登录后进入 Projects 页面，存在活跃 Project）。
- **入口/触发**：落地页初始化

- 展示完整的工作流（从 M-START, M-STORY, M-SPEC, ...直到 M-MILESTONE）
- 展示活跃节点的详细状态
- 显示回拨指针，使得用户可以通过界面操作，回到之前的步骤
- 展示选中节点的详细状态

> **布局参考（非约束，供 M-DESIGN 输入）**
>
> 采用"上卡下图"结构：
>
> - **顶部大卡片**：当前活跃节点（如 M-SPEC）的实时状态。Running 模式显示 Owner、轮次、运行时长；Attention 模式（waiting_human / blocked / conflict）显示原因、影响和唯一动作入口。视觉参考：GitLab CI Pipeline 顶部卡片。
> - **中部水平时间线**：整个项目状态流转的线性序列，用带箭头连线连接所有历史节点。每次轮次（含打回重做）作为独立节点按时间顺序排列，不折叠、不覆盖；打回用回边箭头表示"从这里回到那里"。视觉参考：GitHub Actions Workflow Run 的 Job 图表（取线性序列 + 回边，不取并行 DAG 分叉）。节点过多时支持横向滚动/缩放，默认视口聚焦当前阶段 ± 3。
> - **底部交互**：点击时间线任一节点弹出详情浮层，包含：开始/结束时间、责任方、产出 artifact（可跳转 Dev Docs）、状态转移原因（打回/阻塞时的 reason）、是否允许回拨（允许时回拨按钮在浮层内）。
>
> 此参考描述布局意图，不约束具体组件、框架或像素实现。

### 3.5 行为种子

### BS-01 最小且可恢复的首次 Setup

- EARS: `WHEN workspace 尚无 Setup 完成记录, THE 系统 SHALL 将用户入口统一导向 /setup，并仅要求创建首用户和通过一次真实 OpenCode 模型运行；IF 任一项未完成, THE 系统 SHALL 保持 Setup 未完成并允许从已完成项继续`
- 来源: §3.1 / Human 审核文本
- 说明: 首次 Workspace onboarding 不承载 Git、GitHub、repository、release 或 Project 创建工作。

### BS-02 真实验证 OpenCode 与模型

- EARS: `WHEN Runtime 检查首次运行能力, THE 系统 SHALL 执行一次类似 opencode run "please echo hi" 的最小真实调用，并仅在至少一个模型成功响应时通过；THE 系统 SHALL NOT 仅凭 executable 存在或配置声明判定可用`
- 来源: §3.1 / Human 审核文本
- 说明: 防止用户完成 Setup 后才发现 OpenCode 或所有已配置模型均不可工作。

### BS-03 Setup 完成前的全局入口保护

- EARS: `WHILE Setup 未完成, WHEN 用户访问任一用户功能地址, THE 系统 SHALL 将其带回 /setup；WHEN Setup 成功, THE 系统 SHALL 持久化完成状态并允许进入 Workbench`
- 来源: §3.1 / Human 审核文本
- 说明: 刷新、重启和深链访问均不能绕过首次必需能力检查。

### BS-04 登录后进入 Projects 上下文

- EARS: `WHEN 已完成 Setup 的用户登录, THE 系统 SHALL 在 Workbench 中进入 Projects 页面；IF 存在活跃 Project, THE 系统 SHALL 在 main panel 显示其 Project Status；IF 不存在活跃 Project, THE 系统 SHALL 在 main panel 显示带提示的 New Project 主动作`
- 来源: §3.2 / Human 审核文本
- 说明: 登录落点始终围绕当前 Project；用户无需从通用聊天或 Runs 页面寻找当前工作。

### BS-05 Guide 与当前 Project 上下文关联

- EARS: `WHILE 用户位于 Projects 页面, THE 系统 SHALL 在 sidebar 显示 Guide session，并将其与当前 Project 关联；IF 当前为空 Project, THE Guide SHALL 使用该空上下文解释 New Project 创建和环境检查`
- 来源: §3.2–§3.3 / Human 审核文本
- 说明: Guide 提供与当前页面一致的解释，不成为 Project 或 workflow 状态的数据源。

### BS-06 New Project 的按需环境门禁

- EARS: `WHEN 用户点击 New Project, THE Runtime SHALL 在模态 Wizard 后台检查 gh 安装、gh 登录、gist/project/repo/workflow token scopes 以及当前 Git repository/binding；IF 任一检查失败, THE 系统 SHALL 阻断 Project 创建并仅在 UI 中显示未通过步骤，同时将进展与失败状态发送给 Guide`
- 来源: §3.3 / Human 审核文本
- 说明: 环境检查只在用户开始创建 Project 时执行，不膨胀首次 Setup，也不在空 Workbench 中无故打扰用户。

### BS-07 Repository URL 与绑定恢复

- EARS: `IF New Project 环境检查发现当前 workspace 不是已初始化的 Git repository, THE 系统 SHALL 请求 repository URL；WHEN 用户提交并继续, THE Runtime SHALL 完成 Git 初始化与 repository binding，并仅在重新检查通过后允许进入 Story 输入`
- 来源: §3.3 / Human 审核文本
- 说明: 避免用户在后续 workflow 中才遇到缺失 remote/main 或绑定不可信的问题。

### BS-08 Story/版本预览与创建结果

- EARS: `WHEN 环境检查通过且用户输入故事与 release version, THE 系统 SHALL 暂存输入并展示 Story/版本预览及创建、取消动作；WHEN 用户确认创建, THE 系统 SHALL 由 Scribe 生成 Story 文档并跳转 Dev Docs 加载最新 story.md；WHEN 用户取消或创建前中断, THE 系统 SHALL NOT 创建 Project 或 Story，并 SHALL 保留浏览器中的未完成输入`
- 来源: §3.3 / Human 审核文本
- 说明: 用户在产生 Project/Story 副作用前能核对目标，创建后直接看到可继续工作的正式产物。

### BS-09 Project Status 与回拨

- EARS: `WHEN main panel 显示活跃 Project Status, THE 系统 SHALL 展示从 M-START 到 M-MILESTONE 的完整 workflow、活跃节点详情、选中节点详情及 Runtime 允许的回拨指针；WHEN 用户发起回拨, THE 系统 SHALL 在用户可见地说明影响并仅执行当前状态允许的回退`
- 来源: §3.4 / Human 审核文本 / 安全与可恢复惯例
- 说明: 用户能理解和检查完整进度，也能通过正式界面回到此前步骤，而不是手工修改 Runtime 状态。

## 4. 范围、约束与例外

### 4.1 必须保持的产品约束

- 首次 Setup 只包含首用户创建和 OpenCode/可用模型真实检查；GitHub CLI、Git repository、repository URL/binding、release 与 Project 均不得成为首次 Setup 步骤。
- Setup 完成状态按 workspace 持久化；仅创建用户、发现 `opencode` executable 或读取模型配置均不能标记完成。
- Setup 未完成期间，所有用户功能入口统一返回 `/setup`；为呈现和提交 Setup 所必需的内部接口及静态资源可以工作，但不得形成绕过 Setup 的用户路径。
- 登录后统一进入 Workbench 的 Projects 页面；活跃 Project Status 或空 Project/New Project 状态在 main panel 呈现，Guide session 在 sidebar 呈现。
- Environment Wizard 仅由 `New Project` 触发；三类检查中任一失败均阻断 Project 创建，已通过步骤不在 UI 中展开为无意义流程。
- `gh auth status` 与 token scope 用于 New Project readiness，不替代后续真实 GitHub 操作各自的认证和权限结果。
- Story 与 release version 在预览确认前不得创建 Project、Story 文档或启动 workflow；确认创建后由 Scribe 生成 Story，并以 Dev Docs 中加载的最新 `story.md` 作为可见结果。
- 活跃状态、节点详情、回拨合法性与执行结果必须来自 Runtime 持久化事实；Guide 或前端不得自行推导、改写或推进 workflow。

### 4.2 非常规要求

- 无

### 4.3 Out-of-Scope

- 不在首次 Setup 中创建或选择 repository、release、Project、Story 或 workflow。
- 不在本 Story 中定义 `gh` 的具体安装命令、操作系统包管理器、OpenCode 配置格式、API schema、组件树或 Runtime 回拨算法。
- 不用 `gh auth status` 或 scope 声明预判未来 push、Issue/PR、GitHub Project、workflow 或 release 操作一定成功；实际操作仍处理其真实权限结果。
- 不把 Guide 作为 Environment 检查、Project Status、Scribe 产物或 workflow 转移的权威来源。
- 不要求在本 Story 中重命名所有历史 `Workflow Runs` 数据或迁移历史记录；用户可见的新旅程统一使用 Project 概念。

## 5. 重要推导与证据

### D-01 Setup 与 New Project Environment 是两个门槛

- **结论**：首次 Setup 只证明用户可登录且模型可工作；Git/GitHub readiness 只在用户点击 `New Project` 后检查，并在检查通过前阻断 Project 创建。
- **依据**：§3.1 将首次 onboarding 限定为首用户与 OpenCode/model；§3.3 将 environment Wizard 明确挂在 `New Project` 后，并规定任一步错误都阻断创建。
- **影响**：首次进入保持最短路径，同时 Project 不会在缺少 GitHub/Git 基础条件时开始。

### D-02 模型可用性必须由实际执行证明

- **结论**：Setup 对 OpenCode 的成功标准是至少一个模型完成最小真实请求，而不是命令存在、配置存在或模型列表非空。
- **依据**：§3.1 指定使用 `opencode run "please echo hi"` 类似命令；provider、凭证、网络或模型错误都可能使静态配置无法实际运行。
- **影响**：检查产生一次最小模型调用，但不创建 Louke Project、Git 资源或 workflow 副作用。

### D-03 Project 是用户可见的发布管理对象

- **结论**：当前页面上的 Workflow Runs 在本旅程中统一表述为 Project；一个 Project 对应 GitHub Project，并承载一次规划中的 Release。
- **依据**：§3.3 Aaron 审核说明明确给出概念映射："Workflow Runs 实际上是一次规划中的 Release。我们现在统一称为 Project"。
- **影响**：登录落点、New Project、Project Status 和 Guide 解释必须使用同一用户概念；下游 Spec 需识别与现有 Runtime run 命名之间的兼容边界。

### D-04 Environment 检查采用"后台检查、仅显露失败项"

- **结论**：Environment Wizard 仍是创建 Project 的门禁，但检查通过的步骤不逐页要求用户确认；UI 只在失败时显示对应步骤，全部通过后直接进入 Story/release version 输入。
- **依据**：§3.3 明确"检查在后台完成，只有检查不通过时，才在 UI 上显示这一步"。
- **影响**：保留必要门禁而不重演冗长 Wizard；Guide 可持续解释后台进展和失败原因。

### D-05 Guide 是上下文解释层，Runtime 是检查与状态 authority

- **结论**：Runtime 执行 Environment 检查并提供 Project/workflow 状态；Guide 接收状态、解释进展和帮助用户处理失败，但不能将聊天内容当作检查通过或 workflow 推进证据。
- **依据**：§3.2 将 Guide session 关联当前 Project；§3.3 指定 Runtime 检查并把步骤发往 Guide；当前项目已有 Guide projection 与 Runtime authority 边界。
- **影响**：Guide 故障不能改变检查结果，用户也不会因一句聊天回复而绕过 Project 创建门禁。

### D-06 Scope 齐全不等于未来操作必然有权限

- **结论**：缺少 `gist`、`project`、`repo` 或 `workflow` 中任一 scope 时 Environment 检查失败；四项齐全只使该门禁通过，不保证后续每个 GitHub 操作成功。
- **依据**：§3.3 明确四项 scope 是 Project 创建门槛；既有 backlog 合同明确 `gh auth status` 只证明认证健康，真实远程操作仍须处理自身权限结果。
- **影响**：满足 Human 的创建政策，同时不把粗粒度 token 信息伪报为资源级权限证明。

### D-07 创建前输入仅需浏览器内恢复

- **结论**：故事与 release version 在确认创建前可以只保存在浏览器；中断后回到同一浏览器应恢复，跨设备或清除浏览器数据后的恢复不属于承诺。
- **依据**：§3.3 明确"进入下一步之前暂时保存（浏览器即可）"和"回到浏览器，状态保持"。
- **影响**：避免为未确认草稿引入 workspace 级正式产物，同时保护普通刷新或短暂中断下的用户输入。

### D-08 回拨必须是 Runtime 支持的产品动作

- **结论**：Project Status 可以显示和执行回拨，但只对 Runtime 能证明可回退的节点开放，并在执行前说明将失效或重做的后续工作。
- **依据**：§3.4 要求通过界面回到之前步骤；回拨可能使后续 artifact、review 或外部状态失效，属于重要且可能有破坏性的产品动作。
- **影响**：Sage 需要展开回拨的用户结果与边界，但具体状态机、算法和补偿策略留给后续设计。

## 6. 开放产品决定

- 无。

## 7. 必要性、风险与分流建议

- **既有能力**：已有首用户 API/登录、OpenCode Runtime 调用入口、Setup 状态、Workbench/Projects 入口、Runtime workflow read model、Dev Docs、Scribe 及 Guide projection，可作为重做基础。
- **冲突**：本次审核文本取代旧 Story 中 repository/review/apply 等多步骤首次 Wizard，也取代"空 Workbench 自动运行 Environment 检查"的前一版描述；Environment 检查现在只由 `New Project` 触发。现有 Spec、Architecture、Acceptance 与实现需重新对齐。
- **重要风险**：真实模型检查可能受 provider、网络或费用影响；Environment 后台检查若错误缓存可能放行失效环境；Git 初始化/binding 失败不得留下被误认为可用的状态；回拨可能使已完成的后续工作失效，因此必须由 Runtime 限定并明确影响。
- **分流建议**：Go — 前 94 行已经由 Human 审核，形成 Setup、登录落点、New Project 和 Project Status 四条相连路径；后续应据此重做 Spec，而不是继续修补旧 Wizard。

## 8. 可追溯信息

- **Story ID**：`STR-1405`
- **创建时间**：`2026-07-23T20:13:19+09:00`
- **关联 Spec/Issue**：`v0.14-004-workspace-onboarding-workflow-status`；现有下游文档需按本 Story revision 重做
- **Sage peer review**：`Pending`（Scribe 不得填写通过结果）
