# Review Round 2 — Archer 重做版设计评审

- **评审对象**：architecture.md (321L) / interfaces.md (263L) / test-plan.md (378L)
- **交叉引用**：spec.md (SHA f1e29c40…) / acceptance.md (SHA cff523ca…)
- **评审日期**：2026-07-25
- **结论**：**P2（修订后通过）** — 无 P0 / P1，4 项 P2 建议；主线设计可进入 Shield/Devon

---

## 通过项（BS→FR 溯源）

### 1. Validator 移除完整且一致

三份文档中 `lk check stubs`、`interface_declarations.py`、`validate_interface_declarations`、`declaration_validation` checkpoint 的全部引用已清除。替代模型 `downstream-atdd` 在以下位置明确表述：

- architecture.md §4.1："FR-0101明确不引入独立声明validator、`interface_stubs` CLI、`declaration_validation` checkpoint或baseline前formal validator evidence"
- architecture.md §4.2：checkpoint 从 10 项缩减为 9 项，无 `declaration_validation`
- architecture.md §2 模块表 Design Declaration："不设置FR-0101专用validator或baseline前自证门禁"
- architecture.md §11.2 design-contract job："不增加FR-0101 declaration validator"
- architecture.md §12 激活前置："不要求已从FR-0101移除的声明validator"
- interfaces.md IF-DECLARATION-01：`assurance.mode="downstream-atdd"` 且"明确不存在FR-0101专用validator/CLI"；Python API / Candidate CLI 行已删除
- interfaces.md §8 锁定清单：无 `interface_declarations.py`
- test-plan.md §6.5 IF-DECLARATION-01："无专用validator"
- test-plan.md §7.2 AC-FR0101-02："不引入专用validator"

下游保证链完整：Archer 交付声明 + closed manifest + 源码 readback（bootstrap_manual/unvalidated）→ Shield 从真实 production path import/collect，签名/路径/token 错误表现为 collection 失败或不可归因 RED → Devon 遇不可达声明走 FR-0201 revision return → Prism 审查同一声明、测试和 RED revision。

### 2. FR-1701 覆盖完整

- architecture.md §5.4：wordcount seed、Replay Agent Adapter 协议（语义键 `{workflow_run_id,stage_id,role,task_contract_digest,turn_ordinal}`、exact-once 消费、digest 核对）、13 阶段成功旅程 7 步、13 个 `fail_before_completion` 变体、finally 清理
- architecture.md §2：新增 Replay Agent Adapter + Full Lifecycle Harness 模块，职责/不拥有职责/公开观察边界完整
- architecture.md §3：依赖方向新增 `verified Louke wheel + lifecycle fixtures -> Full Lifecycle Harness`、`Runtime dispatch -> Replay Agent Adapter -> schema-valid prerecorded result -> Runtime Facts`
- architecture.md §7：FR-1701 不增加新页面，同一 Project Status stage timeline 显示 13 项 canonical stage；M-SECURITY 禁用时文本 "Disabled / passed-through"
- architecture.md §11.2：`full-lifecycle` CI job 依赖 `artifact-verify` 同 digest wheel，timeout 60 分钟
- interfaces.md IF-LIFECYCLE-01：9 行完整合同（dedicated e2e selection、scenario manifest、replay public API、production server、lifecycle evidence、disabled security、human journey、fail-each-stage、isolation/teardown）
- test-plan.md §1.3 anti-cheat #11（伪造全阶段旅程）/ #12（伪装安装态）
- test-plan.md §2.1 `full_lifecycle/` fixture 目录、§2.3 专用执行命令、§2.4 `full-lifecycle-wordcount` / `full-lifecycle-fail-each-stage` 数据集
- test-plan.md §5 验收门槛 #12、§6.2 Replay Adapter 不可替换、§6.4 Full lifecycle orchestrator、§6.5 IF-LIFECYCLE-01 行
- test-plan.md §7.2 AC-FR1701-01 / AC-FR1701-02 行，CI job 含 `full-lifecycle`

### 3. AC 39/39 闭合

test-plan.md §7.2 列出 39 行（18 FR × 各自 AC + 4 NFR），每行含 observable interface、required layer(s)、CI gate/job 和分配理由。§4 声明 "全部18个FR、4个NFR及39个唯一AC"；§1.4 `--expected-count 39`；§5 门槛 #4 "39/39 AC均闭合"。与 acceptance.md 逐条核对一致。

### 4. SHA identity 一致

| 文档 | Story | Spec | Acceptance |
|---|---|---|---|
| spec.md frontmatter | 254eb9c7… | f1e29c40… | cff523ca… |
| acceptance.md frontmatter | 254eb9c7… | f1e29c40… | cff523ca… |
| architecture.md frontmatter | 254eb9c7… | f1e29c40… | cff523ca… |
| test-plan.md frontmatter | — | — | cff523ca… (39 AC) |

五份文档 SHA 完全一致。

### 5. Checkpoint 数一致

architecture.md §4.2 固定 9 项语义值：shield_test_preparation → pre_implementation_red → prism_test_review → test_freeze → devon_implementation → required_green → semantic_discrimination → restored_green → m_test_closure。§7 "九项checkpoint摘要"。interfaces.md IF-ATDD-CHECKPOINT-01 projection 与之一致。无 `declaration_validation`。

### 6. 桩锁定清单一致

interfaces.md §8 列出 7 个 stub 文件 + 3 个 production route：

- `louke/runtime/atdd_checkpoint.py` (7 functions)
- `louke/runtime/host_required_tests.py` (1 function)
- `louke/runtime/semantic_discrimination.py` (2 functions)
- `louke/runtime/atdd_failure_routing.py` (1 function)
- `louke/runtime/atdd_projection.py` (1 function)
- `louke/web/api/project_status.py` + `louke/web/app.py` (3 routes)
- `louke/opencode/replay.py` (1 function, IF-LIFECYCLE-01)

与 architecture.md §4.1 stub 列表一致。`replay.py` 已加入，`interface_declarations.py` 已移除。

### 7. 其它通过项

- M-SECURITY：success 场景 `security_audit="disabled"` → `kind=stage-disabled` evidence + 占 ordinal + 自动继续；failure 矩阵含 enabled M-SECURITY failure 变体。spec/acceptance/architecture/interfaces/test-plan 五处一致
- Lex：agent results 列表 "Scribe、Sage、Lex、Archer、Shield、Devon、Prism" 含 Lex（architecture.md §5.4 step 3、test-plan.md §2.4 full-lifecycle-wordcount）
- CI DAG：`artifact-verify -> full-lifecycle -> required`；`integration + e2e-standin -> atdd-discrimination -> required`。full-lifecycle 与 integration/e2e-standin 可并行
- Replay Adapter 不写 workflow facts、不调真实 LLM、不接受未知/乱序 fixture；anti-cheat #11 门禁 "production CLI/HTTP ledger、append-only stage evidence、artifact producer identity"
- 隔离/清理：host/control/publish-sink/home/venv 五分离；finally 停止 server/子进程并删除；清理不确定 → attention + CI 失败

---

## P2 建议（不阻塞 Shield/Devon）

### P2-1：`--wheel` 占位符命名不一致

architecture.md §5.4 使用 `<verified-louke-wheel>`，interfaces.md IF-LIFECYCLE-01 和 test-plan.md §2.3 使用 `<verified-wheel>`。建议统一为 `<verified-wheel>`（更简洁，且 CI job 名 `artifact-verify` 已隐含 Louke 语境）。

### P2-2：`interface_declarations.py` 代码库孤儿

设计文档已完全移除该文件，但代码库中 `louke/runtime/interface_declarations.py` 仍存在（无公开 API）。建议 Devon 实现时清理，或在 §4.1 增加一句实现注释："Devon 应移除已废弃的 `louke/runtime/interface_declarations.py`"。

### P2-3：`--profile all` 与 `full-lifecycle` 专用命令的 CI 重叠

architecture.md §5.4 说 "`--profile all` 必须包含 005 目录"，而 `e2e-standin` job 执行 `--profile all --runtime both`。若 `test_full_lifecycle.py` 被 `--profile all` 发现，则 full lifecycle 测试在 `e2e-standin` 和 `full-lifecycle` 两个 job 中各跑一次。建议明确：

- 方案 A：`test_full_lifecycle.py` 使用 `@pytest.mark.v014_005_full_lifecycle` 标记，`--profile all` 默认排除该 marker（`-m "not v014_005_full_lifecycle"`），仅 `full-lifecycle` job 专用执行
- 方案 B：接受重叠，在 §11.2 注明 `e2e-standin` 中的 full lifecycle 测试为 smoke 级（仅 success 场景），完整 1+13 矩阵只在 `full-lifecycle` job 执行

### P2-4：`full-lifecycle` 60 分钟 timeout 余量

1 success（含 Playwright 浏览器旅程）+ 13 failure 变体共 14 个场景，60 分钟 timeout 平均 ~4 分/场景。成功旅程含 wheel 安装、server 启动、13 阶段推进、真实 build/publish、Playwright 交互，单次可能 15-20 分钟。建议：

- 成功旅程与 13 failure 变体在 pytest 内按 fail-fast 排序（success 先跑，failure 按 stage 顺序）
- 若实现后发现 timeout 不足，在 §11.2 调整为 90 分钟（仍需 Archer 确认）

---

## 遗留观察（非设计缺陷）

- `louke/serve.py` 和 `louke/opencode/dispatch.py` 的 `replay` backend 扩展在 §5.4 描述但未列入 §4.1 stub 清单——这是正确的（它们是既有生产文件扩展，不是新 stub），但 Devon task package 的 write scope 应包含这两个文件（IF-TASK-01 "设计列出的Runtime/Web/tool/runner/workflow配置" 已覆盖）
- architecture.md §8 末尾和 interfaces.md §6 IF-PROJECT-STATUS-UI-01 在 SSH 传输中被截断，评审基于可见内容；截断部分为 §8 prompt/capability 最后几行和 §6 UI 合同表格尾部，与本轮 validator/FR-1701 评审焦点无关
