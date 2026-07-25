# 最小首次设置、Project 创建引导与 Project Status — Architecture

- **Spec ID**：`v0.14-004-workspace-onboarding-workflow-status`
- **设计日期**：2026-07-24
- **Story identity**：`sha256:f2595e5aa1c71ca829fcc2d27458aa599381d2ca51bf6e25e85df422000475af`
- **Spec identity**：`sha256:4d9aec6c0073a225b0aaeff2a530671f5b6ea233775c1a167beadf716508e5cd`
- **Acceptance identity**：`sha256:19bf2d0d9f4dc8d3cd27baa126a3a5fd92cc3e153e51c40f4180babbeabaaa81`

## 1. 范围与宿主事实

本设计取代本目录旧版“连续多步骤 Setup Wizard”设计。首次 Setup 只创建首用户并真实验证至少一个 OpenCode 模型；Git/GitHub/repository 检查只在空 Project 中点击 `New Project` 后运行。本文接入既有 `v0.14-001` 的 Release/Foundation/Scribe 合同和 `v0.14-002`、`v0.14-003` 的后续阶段合同，不复制 Runtime 状态机。

已核对的宿主事实如下：

- 宿主是 MIT License 的 Python 包，`pyproject.toml` 要求 Python `>=3.11`，公开 CLI 为 `lk`，Web 入口为 `lk serve` / `python -m louke serve`。
- Web 使用 Starlette；运行时依赖约束以 `pyproject.toml` 为准：`pre-commit>=3,<5`、`markdown>=3.6,<4`、`pyyaml>=6,<7`、`starlette>=0.38,<1`、`uvicorn>=0.30,<1`、`httpx>=0.27,<1`、`jsonschema>=4,<5`。
- `pyproject.toml:[project].version` 是 Python wheel/sdist 的权威版本源；当前值为 `0.14.0`。构建物为恰好一个 wheel 和一个 sdist，公开安装态版本出口是 `lk --version` 与 `importlib.metadata.version("louke")`。
- Runtime 已有 SQLite `workflow_runs`、append-only `workflow_events`、`step_attempts` 和 gate facts；这些是 Project Status 的事实基础。现有 `workflow_status.py` 只投影单一 phase 列表，不足以证明完整 attempt 历史。
- `ReleaseEntryService`、Foundation/Scribe/Story 服务、Dev Docs 深链、session/CSRF 和幂等基础可复用；旧内存 `ProjectStore` Project API 不能成为新 Project 的写 authority。
- `tests/e2e/run-project-venv` 与 `tests/e2e/run_e2e.py` 已发现 `tests/integration/v014_workspace_onboarding` 与 `tests/e2e/v014_workspace_onboarding`；Playwright 由 `tests/e2e/playwright-requirements.txt` 固定为 `1.54.0`。
- `.github/workflows/louke-ci.yml` 是唯一 Louke 托管 CI，但当前 AC gate 仍写死 `--expected-count 43`；本 revision 的事实是 44 个唯一 AC，必须更新。
- 仓库没有依赖 lockfile；CI 当前对 pytest、build、mypy 等使用无上界安装。这不是 `N/A`，第 10 节要求 Devon 补一个 CI 专用、完全解析且固定版本的 constraints 文件。

## 2. 模块边界

| 模块 | 职责 | 不拥有的职责 | 公开观察边界 |
|---|---|---|---|
| `Setup Gate` | 在每个页面/API 请求前读取当前 workspace 的 Setup manifest；只放行 Setup 必需入口 | 不通过 cookie、首用户存在或 executable 存在推断完成 | redirect、`SETUP_REQUIRED` 错误、Setup projection |
| `Setup Application` | 创建/恢复首用户、发起模型验证、原子完成 Setup | 不检查 Git/GitHub，不创建 Project/release/workflow | `/setup`、Setup HTTP API、Setup manifest |
| `OpenCode Adapter` | 枚举已配置候选并执行最小真实模型请求，提供超时和脱敏结果 | 不携带 Story/Louke artifact，不把静态配置当成功 | model-check result、stand-in invocation record |
| `Workbench Presentation` | 呈现 Projects activity、空 Project/New Project、Environment Wizard、Project Status、Guide 与 Dev Docs 导航 | 不推导 Runtime 状态或执行外部命令 | 浏览器 URL、可访问名称、可见状态和动作 |
| `Project Context` | 从持久 Release/Project/Run 绑定选择零个或唯一活跃 Project | 不按列表顺序、最近访问或 Guide 猜测 | Projects context read model |
| `Environment Gate` | 仅在 `New Project` 后编排 `gh`、auth/scopes、repository/binding/main 检查及重试 | 不修改认证；不把 readiness 当后续外部操作成功 | Environment check API/Wizard projection |
| `GitHub/Git Adapters` | 以 argv 调用 `gh`/`git`，验证 scope、remote identity 和 canonical `main`；在 Human 确认范围内初始化/绑定 | 不覆盖不明 remote/文件，不自动安装 `gh` | redacted check/binding operation evidence |
| `Release Entry` | 规范化 planned release identity，生成无副作用 Preview，幂等 Confirm/恢复 | 不绕过 Environment Gate，不建立第二 Project/Run | Preview/Confirm/status API |
| `Foundation/Scribe` | reconcile 同一 Project/release/Run/GitHub Project/branch/spec identity，dispatch Scribe 并持久化 canonical `story.md` | 不创建平行身份，不覆盖冲突 Story | Foundation status、Story artifact、Dev Docs URL |
| `Runtime Projection` | 从 pinned workflow definition、run、events、attempts、artifacts/evidence/actions 生成 Project Status | 不 dispatch、不估算百分比、不让客户端改 active pointer | Project Status 和 attempt detail API |
| `Return Application` | 由 Runtime 计算合法历史 attempt、预览影响并在 Human Confirm 后复核执行回拨 | 不自动撤销外部副作用，不删除历史 | return preview/confirm/status API、return edge evidence |
| `Guide Session` | 绑定 empty/project context，先记录 Runtime 状态消息，再异步追加去重的 Guide 建议和普通对话 | 不拥有检查、Project、artifact、action 或 workflow authority | Guide session/messages API、sidebar chat |
| `Document Surface` | 打开绑定 Project/spec/revision 的最新 `story.md`，保留返回 Project Status 的上下文 | 不静默切换 Project/revision | Dev Docs 页面、document API、稳定深链 |
| `Fact Stores` | 原子保存 users、Setup manifest、release request、Project/Run binding、Runtime event/attempt、Guide ledger 和 operation evidence | 不保存明文 secret；浏览器 draft 不写入 workspace | 版本化文件/SQLite与各 read model |
| `Compatibility Router` | 将旧 `/projects`、Project/Run/Story 深链解析到同一 Workbench Project 事实 | 不保留第二套可写 Project/Run | 303 redirect 或 canonical read-only projection |

## 3. 依赖方向与 authority

```text
Browser
  -> Setup Gate -> Setup Application -> OpenCode Adapter
  -> Workbench Presentation
       -> Project Context -> Fact Stores
       -> Environment Gate -> GitHub/Git Adapters
       -> Release Entry -> Foundation/Scribe -> Document Surface
       -> Runtime Projection -> Runtime/program + Fact Stores
       -> Return Application -> Runtime/program
       -> Guide Session -> Runtime/Environment projections
       -> Compatibility Router -> Project Context
```

1. Runtime/program 是 workflow state、revision、attempt、合法 action、dispatch、回拨和阶段推进的唯一 authority。Presentation 与 Guide 只消费带 identity/revision 的 projection。
2. `Setup Gate` 在路由分派前运行。Setup 未完成时，页面请求以 `303 /setup` 收敛；非 Setup API 返回 `428 SETUP_REQUIRED`，不能执行被请求 handler 后再重定向。
3. 所有 mutation 都需要 same-origin CSRF、`expected_revision` 与 `Idempotency-Key`；除首次首用户创建外还需要authenticated Human。`GET /setup`为零用户场景建立workspace/revision-bound pre-auth Setup session及CSRF token，首用户成功后立即旋转为authenticated session；该pre-auth capability不能调用其它API。同 key/同 payload返回同一结果；同 key/异 payload或stale revision返回稳定`409`并携带当前readback URL/revision。
4. 外部 operation 必须先记录稳定 operation identity，再执行，再 readback。结果未知保持 `uncertain` 并阻断后续；重试先 reconcile，只有确认未发生时才重放。
5. Guide message 不能携带 Runtime action token。Guide 只返回 owning surface URL；正式 surface 再从 Runtime 取得当前 action capability。

## 4. 首次 Setup 与全局保护

### 4.1 Setup manifest

沿用 `.louke/web-setup-state.json` 路径但升级到 schema version `2`。它只包含 workspace identity、`status=pending_user|pending_model|complete`、首用户非秘密 identity、最近 model-check 的 revision/status/redacted diagnosis、完成时间和单调 revision。有效 `complete` 必须同时引用已持久首用户和一次 `passed` 的真实 model-check evidence；字段缺失、未知 schema、损坏或 workspace identity 不匹配均 fail closed。

旧 version `1` 的 `identity/repository/dependencies/review/applying/complete` 不能按旧 step 数直接视为完成。升级 adapter 只在可核对到“首用户已存在 + 真实 model probe passed evidence”时映射为 v2 complete；否则保留首用户并迁移为 `pending_model`。因此已有真正符合新完成条件的 workspace 不重做 Setup，无法证明者得到明确迁移原因。

首用户继续使用 `.louke/web-users.json` 的 scrypt verifier。创建命令验证pre-auth Setup session/CSRF后，在同一临界区检查“零用户”；写成功后作废pre-auth capability、签发当前用户authenticated session/CSRF，并把 Setup manifest 推进到 `pending_model`。重复同 identity/idempotency key返回同一 principal；不同 identity 或并发输家返回冲突，不增加用户数。

### 4.2 真实模型验证

`OpenCode Adapter` 复用 `louke.models.probe_model` 的真实 `opencode run --model <id> <minimal-prompt>` 能力，但把 executable、候选发现和真实调用分开记录。最小 prompt 固定为 `please echo hi`，stdin 为空，不包含 workspace 文件、Story、artifact、credential 或 Runtime event。候选来自当前 workspace 可见的已配置模型，按稳定 model id 排序逐一尝试；单次 15 秒、整次检查 60 秒，首个确认成功即通过。到总 deadline 仍无成功属于 `failed` 或 `uncertain`，绝不沿用旧成功。

模型成功后，Setup Application 以原子 compare-and-swap 写 v2 `complete`。写入失败/结果未知时仍由 gate 视为未完成并停在模型验证；不得先开放 Workbench。完成后不在普通登录/刷新时重复模型调用。

### 4.3 页面连续性

`/setup` 只有两个可见上下文：`Create first user` 与 `Verify OpenCode model`。首用户成功后立即切换后者；模型检查有 idle/running/passed/failed/uncertain 状态，失败显示对象、已知事实、影响、非秘密原因和 Retry。后台结果不夺取焦点。Setup 完成后 `continue_url=/workbench?activity=projects`；Setup 外功能在完成前均不可见/不可操作。

## 5. Projects 与 New Project

### 5.1 登录落点与单活跃 Project

认证成功总是进入 Workbench 的 Projects activity。`Project Context` 只接受三种结果：`empty`、`active`、`conflict`。一个 active binding 显示其 Project Status；零个显示说明和唯一主动作 `New Project`；多个或身份链不一致显示 conflict，隐藏/禁用 `New Project` 和 Project 选择。已发布历史不再作为登录默认落点。

Project 的 canonical object chain 是：

```text
project_id -> planned_release_identity -> github_project_node_id
           -> request_id -> run_id -> spec_id -> latest_story_revision
```

该链由 release request/Foundation evidence 持久化。旧内存 `/api/projects/create` 不参与新写入；历史 Workflow Runs 可只读映射到链中的 `run_id`。

### 5.2 按需 Environment Gate

只有 `New Project` click 创建 Environment check revision。检查顺序固定为：

1. `gh_executable`：PATH 中可执行且 `gh --version` 成功；
2. `gh_auth_scopes`：`gh auth status` 能唯一确定 GitHub host/identity，scopes 完整包含 `gist, project, repo, workflow`；
3. `repository_binding`：当前根目录是 Git worktree，remote 可唯一映射为当前 GitHub repository；
4. `canonical_main`：refresh/readback 能确认非歧义 `refs/remotes/<remote>/main`，Foundation 可使用其 SHA。

检查进行中 Wizard 显示“正在检查”和当前 step；通过的 step 收起，不要求点击。第一个失败/uncertain step 停止继续，显示诊断、影响、Retry 和适用的 repository binding action。结果 revision 投影到同一 Guide session。进入 Story 输入、Preview 和 Confirm 前都重新验证结果没有超过 60 秒且相关事实 fingerprint 未变化；否则自动回到检查。

### 5.3 Repository 初始化/binding

repository URL 只接受可规范化为 `github.com/<owner>/<repo>` 的 HTTPS 或 SSH Git URL；拒绝 userinfo/password、控制字符、本地路径、`file://` 与身份歧义。Preview 显示 workspace、redacted repository identity、将新增的 Git metadata/remote/main 以及不会纳入提交的工作树文件。Human Confirm 后才执行：

- 非 Git workspace：`git init -b main`，只创建一个无内容 bootstrap commit；使用命令级 Louke author 参数，不修改用户全局 Git config，不 stage 工作树文件。
- 已有 Git、无 binding：保留现有 commits/worktree；若已有 `origin` 指向不同 identity 则冲突，不覆盖。绑定使用可用 remote 名称并 readback canonical identity。
- 新建且确认为空的 remote：从已确认本地 main 推送 `refs/heads/main`；若已有 HEAD，则 main 指向该已归属 commit；无 HEAD 时只推送上述空 commit。
- 非空 remote 缺少 main、main 歧义/diverged、push 后 identity/SHA 不匹配、部分成功或未知：保持 blocked，保存 operation evidence 并提供 Reconcile/Retry，不 force push、不删除文件。

`ShellFoundationAdapter.preflight` 必须改为只读 refresh/compare；它不得再在 Preview/Confirm 阶段偷偷创建 local main。Environment Gate 已成功建立/验证 main 后，Foundation仍再次读取最新 remote/main，防止 readiness 与创建之间变化。

### 5.4 浏览器 draft、Preview 与 Confirm

浏览器 draft 使用 `localStorage`，key 为 `louke.new-project.v1:<workspace_id>:<principal_id>`；只保存 Story、原始 release version、`resume_step=input|preview` 和保存时间。恢复时总先重新跑/复核 Environment Gate；`resume_step=preview` 只表示重新生成 Preview，不复用旧 preview token。quota/写失败显示 `Draft not saved`，不能伪报恢复能力。Cancel 保留 draft；只有 canonical Story 成功加载后清除。

planned release version 使用现有 Python 技术基线的 `packaging.version.Version` 规范化为 PEP 440 canonical identity；只有一段或两段 release tuple 时补齐到三段，因此 Human 输入 `0.14`/`v0.14` 都映射为 canonical `0.14.0`、tag `v0.14.0`、branch `releases/0.14.0`。已有三段及合法 prerelease/postrelease 标识按 PEP 440 保留；非法/本地版本被拒绝。Preview 绑定 Story digest、canonical release、workspace/repository fingerprint、environment revision 与 preview revision，只读且无 Foundation/Project/Story 副作用。

Confirm 复用并扩充 `ReleaseEntryService`：先复核 preview、readiness freshness 和单活跃 Project，再以 request digest/idempotency key reconcile Foundation。Foundation manifest 固定 `project_id/request_id/run_id/github_project/release_branch/spec_id`，并在受控 release worktree 中把 `.louke/project/project.toml:[project].version` 与 `release_branch` 原子写为上述 planned identity；任一步 uncertain 都返回同一 Project 的 recovery status。Scribe 只在 Foundation ready 后以确认输入初始化 Story；Story revision readback 成功才返回 Dev Docs continue URL。

## 6. Project Status、节点详情与回拨

### 6.1 Read model

`Runtime Projection` 读取 run pinned definition，而不是硬编码客户端列表。对新 definition，批准节点 canonical id 是 `M-REQ-APPROVAL`；读取历史 `M-LOCK-1` 时 projection 的 `canonical_step_id` 映射为 `M-REQ-APPROVAL` 并保留 `source_alias=M-LOCK-1`。Issues 只出现在批准 attempt 的 evidence。

时间线由两类节点组成：

- `attempt`：按 append-only event/attempt 的实际 sequence 排列，每一轮独立，带稳定 `attempt_id`；回拨后的重做产生新节点，旧节点不覆盖；
- `pending_placeholder`：来自 pinned definition、尚无 attempt 的后续 canonical stage，只为完整展示 `M-START` 至 `M-MILESTONE`，不可选为已发生 evidence 或回拨目标。

服务端明确返回 `display_state=completed|active|pending|attention|invalidated`、active pointer、return edges 和选中状态，客户端不从文件存在、聊天或百分比推导。初始视口把 active attempt 置中并至少保留前后各三个节点；全历史通过水平滚动和 Home/End/方向键可达，不要求缩放。

active card 在 running 时显示 owner、attempt ordinal、`started_at/observed_at/elapsed_seconds`；在 `waiting_human|blocked|conflict|uncertain` 时显示 reason、impact 和 Runtime 提供的唯一 primary action。共同显示 canonical state、run revision、artifact/operation、最近 evidence/error 和 owning surface。每 5 秒 readback；一次网络失败立即标 stale，或最后成功 readback 超过 15 秒也标 stale。stale 时所有 mutation 禁用，只读导航保留；重连自动刷新，revision 改变时提示并保留可安全恢复的输入。

### 6.2 节点详情

详情由稳定 `attempt_id` 查询，显示开始/结束、status、owner、artifact/revision、关键 evidence/error、transition reason、与 active attempt 的区别、当前 return eligibility 和 owning URL。选中仅写 URL query/history state，不写 Runtime。返回 URL携带 `selected_attempt`；目标 missing/stale/forbidden 显示对应结果，不回退到其他 Project。

### 6.3 回拨

只有 Runtime projection 当前返回 `return_allowed=true` 的历史 attempt 显示动作。Preview 是无副作用操作，返回 target、当前 active、会 invalidated/reworked 的下游 artifact/review/evidence、不可自动逆转的外部后果和 bound revision。Human Confirm 后 Runtime 再次验证相同 Project、target attempt、definition 和 revision；成功以一个原子 transition 更新 active pointer、append return edge/audit，并按 owning 合同标记下游 stale/superseded/reconcile。取消、stale、并发推进、Agent/Guide 调用或不支持 target 均不改变状态。

## 7. Guide session

Projects sidebar 始终有 Guide：空 Project session key 为 workspace + principal + `empty`；活跃 Project key 增加 `project_id`。切换 context 时旧消息可作为明确标识的历史查看，但不能投影为当前事实。

每个 Environment check revision 的消息顺序由 server sequence 保证：先 append `runtime_status`（权威 step/result），再异步产生 `guide_advice`（解释/建议）。去重键为 `(session_id, check_revision, error_code)`。建议必须包含影响、修复方法和 owning Wizard URL；确定性 error-code 模板是 Agent 不可用时的完整 fallback。Guide 生成失败追加可区分的 `guide_error`，不移除 Runtime 消息、不改变 check 结果，也不阻塞 Wizard。

普通用户 message 只追加对话。服务端不解析对话为 install/auth/bind/create/return command；这些动作只能在 owning surface 使用 Runtime capability。

## 8. 资产复用、替代与退役

| 资产 | 处置 | 理由/实现边界 |
|---|---|---|
| `louke/web/store.py` user/session persistence | 复用并迁移 | 保留 scrypt 首用户；Setup state 升级为 v2 CAS manifest |
| `louke/models.py::probe_model` | 复用 adapter 能力 | 必须增加结构化结果、候选/总超时和调用记录；静态 list 不算成功 |
| `louke/web/pages/setup.py` 旧六步 Wizard | 替代并退役旧路径 | 改为首用户/模型两上下文；删除 repository/dependencies/review/applying 产品路径。Archer 已交付接口桩（§14），Devon 替换行为体 |
| `louke/web/api/readiness.py` 一体化 readiness | 拆分替代 | OpenCode probe归 Setup；gh/Git归按需 Environment Gate；Store/Catalog 不成为用户门禁 |
| `louke/web/api/projects.py` 内存 Project create | 新写入退役、历史只读兼容 | 新 Project 必须走持久 `ReleaseEntryService`/Runtime；不得双写 |
| `louke/runtime/release_entry.py`、Foundation、Story/Scribe | 复用并收紧 | 加 Environment revision、canonical version、单 Project identity 与 recovery；Foundation preflight只读 |
| `louke/runtime/store.py` runs/events/attempts | 复用 | Project Status新增 projection，不另建 workflow store |
| `louke/web/workflow_status.py` | 替代 projection | 增完整 definition、attempt、return edge、artifact/action/readback 字段 |
| `louke/web/entry_resolver.py` | 替代规则 | 移除 `released` 默认落点；只返回 Setup、Projects active/empty/conflict |
| `guide_projection.py` / `guide_context.py` | 复用 authority边界并持久化扩充 | 增 context、ordered runtime/advice message 和 dedupe ledger |
| `louke/web/setup_journey.py` 旧六步模型 | 删除（耦合页面迁移） | 页面桩已移除对 `setup_journey` 的 import；Devon 实现页面后该模块成为死代码，必须删除。`tests/unit/web/test_setup_journey.py` 同步删除 |
| 旧 v0.14-004 integration/e2e | fixture/harness 可复用，断言重写 | 旧 Setup Wizard 行为不计入当前 44 AC evidence，不允许保留相反断言 |
| `louke/web/opencode_probe.py` 诊断合同 | 修复（无需桩） | 函数签名正确；`run_minimal` 的 `diagnosis` 必须改为 `{object,known_facts,impact,recovery_url}` 四字段并 redact `stderr_snippet`，当前实现泄漏 provider secret |
| Issue `#322`—`#342` | `reconcile-required` | Requirement ID 仍存在，但本调用没有可信 remote body/readback；Runtime/Sage必须按当前三份 digest逐条比较后复用或 supersede，Devon不得把旧 PASS 当实现证据 |
| Issue `#343` (`NFR-0501`) | `removed/superseded` | 当前 locked Spec/Acceptance 没有该 requirement；不得为它发明实现或 AC |

## 9. 技术选型、版本与取舍

| 选择 | 解决的问题 | 放弃的替代 | 主要风险与缓解 |
|---|---|---|---|
| Python `>=3.11` + Starlette 原生页面 | 继承现有包、session、路由和安装态服务 | 引入 React/Vue/Node build | 原生交互复杂；用 typed read model、可访问语义和 Playwright约束 |
| SQLite Runtime facts + versioned JSON Setup/users | 复用真实持久化、事务和 append-only history | 浏览器/Guide 状态、Redis、新数据库 | 跨文件原子性；Setup 单 manifest CAS，Project/Runtime统一 SQLite，外部操作用 ledger/readback |
| stdlib `subprocess` argv adapters | 隔离真实 `git`/`gh`/`opencode` 并支持 stand-in | shell string、GitPython | 平台输出差异；JSON/稳定 command、timeout、redaction、Windows/POSIX contract tests |
| `packaging.version`（CI tooling pin `26.2`） | PEP 440 planned/package identity canonicalization | 自写 regex、SemVer-only 库 | PEP 440 normalization可能改变显示；Preview同时显示原始与 canonical，Confirm绑定 canonical |
| pytest `9.1.1`、pytest-asyncio `1.4.0`、pytest-cov `7.0.0`、Playwright `1.54.0`、build `1.5.0` | 与 Python 3.11+ 和现有 runner匹配，固定 CI 直接工具 | Cypress/Jest、新 runner | 当前仓库无 lock；Devon生成 `tests/requirements-ci.txt` 完全解析 constraints，所有 CI install使用它 |
| pre-commit hooks `pre-commit-hooks v6.0.0`、ruff `v0.15.20`、mypy `v2.1.0` | 继承既有质量栈和固定 hook环境 | CI临时安装 latest mypy/ruff | hook环境首次下载；以 hook rev和cache key固定，不再额外运行未固定 latest mypy |
| 5 秒 poll + 15 秒 stale、外部单调用15秒/检查总60秒 | 让状态及时且失败有界 | WebSocket-only、无限等待 | poll负载；仅活跃 Projects surface轮询，ETag/revision无变化可返回轻量结果 |

本 Spec新增唯一运行时直接依赖 `packaging>=24.2,<27`，用于 planned release canonicalization；Devon必须把它加入 `pyproject.toml`，CI constraints固定 `26.2`。不得继续依赖构建后端偶然提供的transitive `packaging`。

## 10. 测试可替换性与数据边界

- `OpenCode Adapter`、`GitHub/Git Adapters`、Guide generator、clock 和 Runtime action dispatcher均从应用装配边界注入；默认 CI替换外部进程/服务，不替换 Louke application、projection或store。
- unit 使用纯 projection、临时 SQLite/目录、固定 clock；integration 启动真实 Starlette app并通过公开 HTTP、持久文件/SQLite和外部 stand-in观察。
- e2e 从构建 wheel安装 `lk serve`，使用真实 Chromium、临时 HOME/workspace、外部 executable stand-ins；必须从页面动作走完，不调用内部对象推进。
- L3 protected smoke 使用真实 OpenCode最小模型与 GitHub sandbox repository，只在 tag/manual release运行；identity和teardown evidence与 source SHA/artifact digest绑定。
- 支持布局：`1024x768` 100% zoom；`1280x720` 在 100% 与 200% text zoom。Project Status全历史入口、Guide、错误和主要动作在这些组合下可达。

## 11. Planned release 与宿主 artifact 版本同步

> **继承范围说明**：本节锁定的是宿主项目已有 release identity、Python wheel/sdist、project-local adapter 与公开版本出口的接线合同，**不是 STR-1405 新增的用户功能范围**。本 Story 的新增交点仅是 §5.4 `New Project` 产生并持久化 planned release identity；其后 prepare/build/extract/install/publish 继续继承宿主机制。Devon审阅和实现本 Story时应优先关注 §4—§7，只按本节修复该 identity 接线与既有adapter验证缺口，不重建release系统。

### 11.1 Identity 与 artifact 范围

Human 输入经 `packaging.version.Version` 得到 canonical planned release，例如 `0.15.0`。外部表示固定为 tag `v0.15.0`、release branch `releases/0.15.0`、`.louke/project/project.toml:[project].version = "0.15.0"`。New Project Confirm 持久化 planned identity和Foundation资源，但**不在规划阶段改写** `pyproject.toml`；Python package version只在同一 release进入真实构建前由 adapter准备。

必须验证的宿主 artifacts：

| Artifact | 版本提取 | 安装/运行公开出口 |
|---|---|---|
| wheel `dist/louke-<version>-py3-none-any.whl` | `.dist-info/METADATA: Version` | clean venv `lk --version`、`importlib.metadata.version("louke")` |
| sdist `dist/louke-<version>.tar.gz` | top-level `PKG-INFO: Version` | 从 sdist 构建 wheel后同上 |
| GitHub Release/tag | tag去单个前导 `v` 后 PEP 440 canonical | GitHub release tag/name；不是 package版本的替代证据 |

### 11.2 Project-local adapter

继续选用 `tools/louke_python_release_adapter.py`，Devon扩充而不另选工具：

1. `prepare --tag TAG --source pyproject.toml --planned-source .louke/project/project.toml --evidence PATH`：先验证 TAG canonical等于 planned source，再原子写/验证 package source；失败不构建。
2. `verify-dist --source pyproject.toml --planned-source ... --tag TAG --dist dist --evidence PATH`：要求恰好一个 wheel/sdist，逐个提取版本并同时比较 planned、tag、package source。
3. `verify-installed --expected VERSION --wheel PATH --sdist PATH --evidence PATH`：在隔离 venv分别验证 wheel安装态和由 sdist构建的安装态 `lk --version` / metadata。

退出码 `0` 只表示所有确定比较通过；缺失/非法 identity、prepare失败、build失败、artifact缺失/多余、提取失败、任何不匹配、安装/运行出口不匹配或结果不确定均非零并阻断 publish。evidence分别标识 `identity_prepared`、`source_prepared`、`artifacts_built`、`artifact_versions_verified`；只有最后一类允许 publish，不新增 Runtime 状态字段。

## 12. GitHub Actions CI 合同

> **继承范围说明**：本节是 Louke 托管的宿主 CI 基线，**不是 STR-1405 新增的产品旅程**。本 revision 对CI的增量仅为承接 §4—§7 的新测试资产、把本 Spec traceability更新为44个AC、固定新增`packaging`依赖，并验证 §11 的同一 planned/artifact identity；其余runner、build、install matrix、权限、evidence和publish DAG均继承现有 `.github/workflows/louke-ci.yml`，不得借本 Story另建一套workflow。

### 12.1 Runner、触发、权限与可复现性

Devon更新现有 `.github/workflows/louke-ci.yml`，不得创建名称冲突的第二聚合 workflow。触发：PR到 `main`/`releases/**`、这些分支push、`v*` tag、manual。主验证 runner `ubuntu-22.04/Python 3.12`；unit矩阵 Python `3.11,3.12,3.13,3.14`；安装矩阵保留 Ubuntu/macOS/Windows和现有支持版本。

默认权限 `contents: read`；fork PR无 secret、无 `pull_request_target`。real-smoke只在 protected `release-smoke` environment，publish只在 `release` environment并单独授予 `contents: write`/PyPI secret。Devon把现有floating major refs一起迁移为2026-07-24回读的完整commit SHA（YAML保留版本注释），不得自行选择floating ref：

| Action | 完整SHA |
|---|---|
| `actions/checkout` | `11d5960a326750d5838078e36cf38b85af677262` |
| `actions/setup-python` | `a26af69be951a213d495a4c3e4e4022e16d87065` |
| `actions/upload-artifact` | `ea165f8d65b6e75b540449e92b4886f43607fa02` |
| `actions/download-artifact` | `d3f86a106a0bac45b974a628896c90dbdf5c8093` |
| `actions/cache` | `0057852bfaa89a56745cba8c7296529d2fc39830` |
| `softprops/action-gh-release` | `3bb12739c298aeb8a4eeaf626c5b8d85266b0e65` |

未来升级必须经dependency PR同时更新此CI合同和workflow；未知或未批准action禁止执行。

Devon创建 `tests/requirements-ci.txt`，固定完全解析的 CI Python依赖，至少锁定第9节测试工具；所有 cache key包含 OS、Python、该文件 digest、`pyproject.toml` 和 Playwright requirements digest。缓存不得含 workspace facts、credential、浏览器 draft或测试结果。

### 12.2 Job DAG 与命令

```text
quality ───────────────────────────────┐
ac-trace ──────────────────────────────┤
build-artifacts -> artifact-verify ────┤
                 -> unit matrix ───────┤
                 -> integration ───────┤
                 -> e2e-standin ───────┤
                 -> install-matrix ────┤
                                       -> required
required + artifact-verify -> real-smoke -> publish   (tag/manual protected only)
```

| Job | 必须执行的宿主入口 | 失败语义/证据 |
|---|---|---|
| `quality` | `python -m pip install -c tests/requirements-ci.txt -e .`；`pre-commit run --all-files` | 任一 hook失败阻断；不再另装latest mypy |
| `ac-trace` | 两次 `python tools/check_ac_traceability.py ...`；本 Spec使用 `--expected-count 44` | 缺失/未知AC、数量不等、零测试或反作弊违规失败 |
| `build-artifacts` | branch/PR先 inspect source；release先执行第11节 prepare；随后 `python -m build --wheel --sdist` | 上传 prepared identity、source snapshot、wheel/sdist、SHA-256/source SHA；任何fallback后结果不确定失败 |
| `artifact-verify` | 第11节 `verify-dist` 与 `verify-installed` | wheel、sdist和两种安装态全部匹配；上传 verified identity JSON |
| `unit` | `/tmp/lk-venv/bin/python -m pytest -q tests/unit --cov=louke.runtime --cov-report=xml --cov-report=term-missing --cov-fail-under=95` | 每个matrix shard成功；JUnit/coverage |
| `integration` | `tests/e2e/run-project-venv integration` | 必须收集本 Spec路径且非零；JUnit、redacted adapter evidence |
| `e2e-standin` | `tests/e2e/run-project-venv e2e --profile all --runtime both` | wheel安装态、真实Chromium；失败trace/screenshot、runner evidence |
| `install-matrix` | 复用 `install.sh`/`install.ps1` 并从 verified wheel安装 | local/global公开CLI与version匹配 |
| `required` | `if: always()`聚合全部必需 needs | workflow名 `Louke CI`、job名 `required`，稳定 check `Louke CI / required`；失败/取消/超时/skipped/缺失/未知均失败 |
| `real-smoke` | `tests/e2e/run-project-venv real-smoke --profile v014 --runtime local` | 真实OpenCode/GitHub sandbox，identity/teardown report；不属于PR required secrets |
| `publish` | 只上传 build-artifacts job产生且 artifact-verify验证的相同digest | 不重新prepare/rebuild；required、real-smoke、artifact identity任一不current即阻断 |

Timeout：quality/ac-trace 15分钟；build/artifact/unit 20分钟；integration 25分钟；e2e/install 35分钟；required 5分钟；real-smoke 60分钟。测试失败不自动 rerun。

`artifact-verify`、`ac-trace`、integration/e2e evidence保留30天；失败浏览器trace和脱敏日志14天；release artifact按发布保留策略。每份 evidence至少含 source SHA、planned/package version、artifact SHA-256、Python/OS、suite/profile、AC集合和结果。

## 13. Machine-contract、prompt 与实现交接

当前任务输入未提供 program-owned exact active machine-contract schema reference、instance路径或对应逐路径授权；本 Spec也未把 Agent prompt列为规范性工件。因此本 design revision不生成、自证或激活 machine-contract/prompt candidate。Runtime必须在缺少 exact active reference时 fail closed，不能从旧 instance或本设计文档推断 schema。

在上述 program输入缺口之外，产品模块、公开接口、测试资产、数据、版本 adapter 和 CI方案均已确定：Devon可以按 `interfaces.md` 实现，Shield可以按 `test-plan.md` 独立准备 integration/e2e。实现不得保留旧连续 Setup Wizard作为平行成功路径，也不得把旧 Issue/test PASS当当前 44 AC evidence。

## 14. 接口桩（Interface Stubs）

> 本节遵循 Archer.md §5.3.5 接口桩约定。桩是 interfaces.md 的可执行形态，让 Shield 的契约测试在 Devon 实现之前即可 collect/import。

### 14.1 已交付桩

| 桩文件 | 合同 token | 替换目标 | composition root 接线 |
|---|---|---|---|
| `louke/web/pages/setup.py` | `IF-SETUP-01`、`IF-SETUP-02` | 旧 982 行六步 Wizard 页面 | `louke/web/app.py:82` `from .pages.setup import create_app as _create_setup_page_app`；`app.py:341` `Mount("/setup", app=setup_page_app)` |

桩签名锁定如下：

- `create_app() -> Starlette`：只注册 `/` 路由（`setup_root` handler）；旧六步路由 `/identity/`、`/repository/`、`/dependencies/`、`/review/`、`/applying/`、`/complete/` 不注册，自然 404。
- `async setup_root(request: Request) -> Response`：行为体 `raise NotImplementedError("IF-SETUP-01")`。Devon 实现时根据 `request.app.state.workspace_root` 读取 v2 manifest projection，按 `pending_user`/`pending_model`/`complete` 渲染对应上下文。
- `async _fetch_setup_status(api_base: str, *, request: Request | None = None) -> dict`：测试 seam，行为体 `raise NotImplementedError("IF-SETUP-01")`。生产实现调用 `GET /api/setup/status`；测试通过 `patch.object(setup_page, "_fetch_setup_status", ...)` 注入真实 projection。
- `async _post_first_user(api_base: str, *, name: str, credential: str) -> dict`：测试 seam，行为体 `raise NotImplementedError("IF-SETUP-02")`。生产实现调用 `POST /api/setup/first-user`。

### 14.2 不需要桩的模块

以下模块已存在且签名/路由与 interfaces.md 一致，Shield 测试可直接 import/collect：

| 模块 | 状态 | 备注 |
|---|---|---|
| `louke/web/setup_state.py` | ✓ 已实现 | v2 manifest 三态 CAS、`SetupManifest`/`ModelCheck`/`SetupStatus` |
| `louke/web/setup_gate.py` | ✓ 已实现 | `SetupGateMiddleware` 全局入口保护 |
| `louke/web/first_user.py` | ✓ 已实现 | 首用户创建命令 |
| `louke/web/setup_projection.py` | ✓ 已实现 | `read()` 返回 IF-SETUP-01 projection dict |
| `louke/web/environment_gate.py` | ✓ 已实现 | `start_check`/`repository_preview`/`repository_confirm` |
| `louke/web/draft_storage.py` | ✓ 已实现 | `create_draft`/`draft_key` |
| `louke/web/guide_session.py` | ✓ 已实现 | `create_session` |

### 14.3 Devon 实现交接清单

1. **替换 `louke/web/pages/setup.py` 桩行为体**：实现 `setup_root` 根据 manifest status 渲染两上下文页面；实现 `_fetch_setup_status`/`_post_first_user` seam 调用真实 API。不得修改 `create_app()` 签名或路由注册。
2. **修复 `louke/web/opencode_probe.py` 诊断**：`run_minimal` 的 timeout 和 nonzero-exit diagnosis 必须改为 `{object, known_facts, impact, recovery_url}` 四字段结构，并 redact `stderr_snippet` 中的 provider secret。函数签名不变。
3. **删除 `louke/web/setup_journey.py`**：页面桩已移除对该模块的 import；Devon 实现页面后确认无其它引用，删除该模块及 `tests/unit/web/test_setup_journey.py`。
4. **删除旧六步测试**：按 Shield 的 `deprecated-tests-removal-list.md` 删除 14 个 integration + 4 个 e2e 旧六步 Wizard 测试文件，并清理 conftest skip 规则。

### 14.4 ATDD 闭合

- Shield 的 `tests/unit/web/pages/test_setup.py`（已在 commit `121dcfc` 改写为两上下文合同）可直接 collect：`setup_page.create_app()` 返回 Starlette app，`GET /` 触发 `NotImplementedError("IF-SETUP-01")` 产生可归因 RED。
- `tests/e2e/v014_workspace_onboarding/test_journey_setup_wizard.py`（已在 `121dcfc` 改写）同理：浏览器访问 `/setup` 得到 500（NotImplementedError），测试在首步断言失败，RED 可归因到 `IF-SETUP-01`。
- 旧六步路由 `/repository/`、`/dependencies/`、`/review/`、`/applying/` 在桩中不注册，返回 404；`test_setup_retired_step_routes_removed` 直接 GREEN。
- Devon 实现页面后，上述测试从 RED 转 GREEN，无需修改测试签名或断言。
