# 契约测试先行与真实交付表面验证 — Test Plan

- **Spec ID**：`v0.14-005-atdd-process-improvement`
- **Created**：2026-07-25
- **Related acceptance**：`.louke/project/specs/v0.14-005-atdd-process-improvement/acceptance.md`
- **Related interfaces**：`.louke/project/specs/v0.14-005-atdd-process-improvement/interfaces.md`（唯一断言依据，见 §6.5）
- **Acceptance identity**：`sha256:cff523caa12f2d587adabe8a9b2afda260fb8b62ab58c81beb59b6b95ddf9a4d`（39个唯一AC）
- **Bootstrap qualification**：完整Runtime、active schema registry、registry/prompt validators及candidate runners/adapters尚未部署；FR-0101不含专用声明validator。bootstrap/manual结果只能显示`unvalidated`或attention，不表示本计划、machine contract、gate或阶段已通过。

## 1. 立场与边界（Stance and Boundaries）

### 1.1 黑盒声明（Black-box Statement）

本计划只从`interfaces.md`定义的公开出口断言：

- Runtime task/checkpoint/freeze/failure/evidence JSON readback及其digest、revision和current/stale资格；
- 宿主project-local runner命令、精确collection、JUnit/coverage/动态production module与surface evidence；
- production `louke.web.app.create_app()`注册的Project Status HTTP路由，以及同一Workbench Project Status中的可见状态、动作、focus和恢复上下文；
- 隔离Git worktree、构建artifact、counterexample执行、teardown及原candidate恢复后的公开readback；
- candidate schema/instance/prompt source-transform-render-readback文件，以及真实wheel/sdist和clean install后的公开版本/package出口；
- 外部Git、进程、clock和provider stand-in的协议ledger、文件系统边界与污染扫描。
- FR-1701 scenario/replay/Human-action清单、同一WorkflowRun的13阶段Project Status、wordcount真实build/local publish artifact和finally cleanup ledger。

Integration和E2E必须加载candidate source或verified installed product，走真实public package、production composition root、route table或CLI。测试不得以test-owned app、替换`louke.*`模块、monkeypatch Runtime核心或罐头SUT制造RED/GREEN。

### 1.2 不可观察对象（Non-observable Objects）

测试不得直接依赖：

- Runtime内部类层次、私有状态机、队列、缓存、数据库私表或provider/session transport metadata；
- handler实例、前端组件树、CSS class和未公开中间payload；
- Agent自报、Issue状态、聊天内容、文件存在本身或非current review作为workflow事实；
- 通过测试侧直接写SQLite私表、旧`project-state.json`或预计算页面/API响应来制造checkpoint状态。

若验收需要的结果不能从`interfaces.md`出口观察，测试记录testability gap并返回M-DESIGN；不得窥探内部状态补洞。

### 1.3 作弊模式（CI enforced interception）

| # | 作弊模式 | 本Spec典型症状 | 门禁 |
|---|---|---|---|
| 1 | 为实现改断言 | Devon实现不符合同后修改冻结测试或反例 | freeze digest、write-scope及PR review |
| 2 | skip/零收集逃避 | 声明命令缺失、Chromium未启动或Node未安装时skip | runner exact node set；skip/xfail/zero collection失败 |
| 3 | 任意RED冒充有效RED | import/setup/service/permission错误被记为目标失败 | IF-VALID-RED-01分类与failure token检查 |
| 4 | 形状代替行为 | 只断言symbol、字段、selector或HTTP 200存在 | behavior/surface/side-effect binding检查 |
| 5 | 替换SUT | `sys.modules`、test app、mock route或罐头module产生GREEN | loaded production path/digest、composition root和anti-cheat scan |
| 6 | Ground truth引用实现 | expected evidence digest或projection由被测函数生成 | ground-truth import taboo与独立stdlib计算 |
| 7 | 无效mutation算kill | build/import/setup失败被计为识别语义错误 | `killed|survived|invalid`分类；invalid阻断 |
| 8 | stale/manual冒充current | bootstrap结果、旧review或旧candidate解锁Devon/M-VERIFY | identity envelope、schema qualification和freshness gate |
| 9 | 测试污染生产空间 | patch当前worktree、读取真实HOME/credential | sandbox containment、canary和before/after digest |
| 10 | trivial pass | `assert True`、sole `is not None`、吞异常 | static scan + Prism测试审查 |
| 11 | 伪造全阶段旅程 | fixture直接写Runtime state、调内部推进函数或预置最终artifact | production CLI/HTTP ledger、append-only stage evidence、artifact producer identity |
| 12 | 伪装安装态 | full lifecycle从Louke源码树import或自行重建不同wheel | `--wheel`digest、venv `module_paths`、Louke仓库before/after readback |

### 1.4 防护（Safeguards）

1. **AC强制追踪**
   - 每个测试函数首行docstring/comment至少包含一个`AC-FRXXXX-YY`或`AC-NFRXXXX-YY`。
   - `tools/check_ac_traceability.py`对当前Acceptance使用`--expected-count 39`；每个AC至少被引用一次，未知AC失败。
   - 同一AC在§7.2要求多个测试层时，IF-HOST-TEST-EVIDENCE-01的`ac_layers`必须包含所有必需层；较低层不能替代integration/e2e。
2. **冻结与scope**
   - Shield bundle、counterexample、RED和Prism review绑定同一test revision；Devon write set排除全部冻结路径。
   - 声明、测试、runner、adapter或candidate identity变化使依赖证据stale，不能复用旧GREEN/review。
3. **动态SUT证明**
   - evidence记录loaded production module path/digest、composition root、surface invocation、可测coverage和service lifecycle。
   - shape/symbol检查只作声明辅助，不闭合行为AC。
4. **语义判别**
   - 每个新增/改变required行为绑定安全counterexample；005不允许描述性fallback。
   - mutation只在隔离worktree和product venv执行；survived、invalid、unknown、teardown或恢复不确定均阻断。
5. **可测性fallback**
   - 缺公开出口返回M-DESIGN；Spec/Acceptance未决定产品结果返回M-SPEC/M-ACC，不默认测试正确。

### 1.5 测试分工（Test Division of Labor）

- **Unit**：Devon；覆盖identity/digest、schema解析、classification、freshness/stale、checkpoint capability、错误映射、redaction和确定性projection规则。
- **Integration**：Shield；覆盖`interfaces.md`全部跨模块出口、真实Runtime/store/application接线、project-local runner、声明/任务/freeze/失败分流、production HTTP route和语义adapter失败/恢复矩阵。
- **E2E**：Shield；覆盖安装态Workbench主成功旅程、一个代表性失败→合法返回→新attempt→继续旅程，以及FR-1701同digest wheel的1 success+13逐阶段failure全生命周期；只走公开CLI、页面/API动作。
- **Ground Truth**：独立于被测实现的小型stdlib脚本、Git/build标准出口或固定fixture数据；不得导入`louke.*`计算expected。
- **Review**：Prism依据current Test Plan/Interfaces独立审查Shield资产；Runtime/program持久化review/freeze/route，Agent不推进状态。

---

## 2. 测试环境（Test Environment）

### 2.1 目录布局

```text
tests/
├── unit/                                              # Devon；镜像louke模块
├── integration/
│   └── v014_atdd_process_improvement/                # Shield；跨模块与失败矩阵
├── e2e/
│   ├── run-project-venv                              # 唯一宿主bootstrap
│   ├── run_e2e.py                                    # 增加005 discovery/atdd子命令
│   ├── playwright-requirements.txt                   # Playwright 1.54.0
│   └── v014_atdd_process_improvement/                # Shield；安装态Workbench与FR-1701全生命周期旅程
├── fixtures/
│   └── v014_atdd_process_improvement/
│       ├── scenarios/                                # Runtime公开fixture manifests
│       ├── counterexamples/                          # 隔离执行patch，不参与正常discovery
│       ├── hosts/node-cli/                           # Node 22.17.1 public CLI fixture
│       ├── full_lifecycle/                           # wordcount seed、replay results、13-stage failures
│       ├── counterexamples.manifest.json
│       └── test-bundle.manifest.json
└── ground_truth/                                     # 不得import louke.*
```

声明桩位于真实production路径，不放在`tests/`：`louke/runtime/{atdd_checkpoint,host_required_tests,semantic_discrimination,atdd_failure_routing,atdd_projection}.py`、`louke/opencode/replay.py`和`louke/web/api/project_status.py`；`louke/web/app.py`注册三个production routes。FR-0101不新增声明validator模块或CLI。

### 2.2 命名约定

- Python文件：`test_<surface>__<scenario>.py`；测试名称使用`test_ac_<fr-or-nfr>_<number>_<scenario>`，但本计划不锁定具体函数清单。
- test node、case和evidence identity分别使用`node_`、`case_`、`ev_`前缀；run/attempt/task/freeze用`run_`、`att_`、`task_`、`freeze_`。
- 所有fixture identity和clock固定；secret使用可检索哨兵`SECRET_V014005_*`，每run附随机后缀。
- 浏览器定位只使用role/name/label/live-region/公开文本；不依赖DOM层次或生成class。
- 每个required测试在test bundle中显式列`ac_ids`、`interface_ids`、`layer`、`production_surface`、`behavior_class`和`counterexample_ids`。

### 2.3 执行

| 层/门禁 | 本地/CI确定命令 | 环境与退出语义 |
|---|---|---|
| Quality | `pre-commit run --all-files` | 固定hook；合法RED不触发required suite；任一适用静态检查失败非零 |
| Unit | `python -m pytest -q tests/unit --cov=louke.runtime --cov-report=xml --cov-report=term-missing --cov-fail-under=95` | verified wheel的clean venv；Python 3.11—3.14矩阵；零收集失败 |
| Integration | `tests/e2e/run-project-venv integration` | 必须发现005路径；临时HOME/workspace，无公网；全绿、无skip/xfail、teardown成功才0 |
| E2E | `tests/e2e/run-project-venv e2e --profile all --runtime both -m "not v014_005_full_lifecycle"` | verified wheel、local/global、真实Chromium、production server；发现005常规旅程但deselect full-lifecycle专用矩阵；runner负责start/readiness/finally teardown |
| Full lifecycle | `tests/e2e/run-project-venv e2e --profile v014 --runtime local --wheel <verified-wheel> tests/e2e/v014_atdd_process_improvement/test_full_lifecycle.py -m v014_005_full_lifecycle --maxfail=1` | CI复用artifact-verify同digest wheel；marker已注册；1 success+13 failpoint；90分钟timeout；无真实LLM/公网/secret；temp wordcount/publish sink全部清理才0 |
| Pre-RED | `tests/e2e/run-project-venv atdd --phase pre-red --spec v0.14-005-atdd-process-improvement --bundle <path> --evidence <path>` | Devon按设计实现前为`candidate-change-required`；精确collection与有效RED才形成可用evidence |
| Post-GREEN | `tests/e2e/run-project-venv atdd --phase post-green --spec v0.14-005-atdd-process-improvement --bundle <path> --evidence <path>` | 全counterexample killed、隔离清理、原candidate未变且restored full GREEN才0 |
| L3 release smoke | `tests/e2e/run-project-venv real-smoke --profile v014 --runtime local` | 仅tag/manual protected environment；命令未实现则release path失败，不在PR降级 |

默认顺序为quality/design-contract/ac-trace→build/artifact verify→unit/host-compat/integration/e2e/full-lifecycle→discrimination→required。各suite不依赖前一suite遗留状态；中断也必须执行teardown。Full lifecycle内部固定为`success`第一，随后按M-START→M-MILESTONE顺序运行13个failpoint；`--maxfail=1`确保任一意外失败立即停止，通用E2E不得重复运行该矩阵。

### 2.4 测试数据

| 数据集 | 内容 | 来源/复现 | 用途 |
|---|---|---|---|
| `declaration-valid` | closed path/token/signature/route及纯raise声明 | candidate manifest+源码readback | M-DESIGN readback及Shield production collection/valid RED |
| `declaration-invalid-matrix` | 缺token、错signature/route、额外成功逻辑、未知文件/未声明import | 对临时副本施加固定patch | Shield collection不可归因/invalid test asset及Devon scope拒绝；不调用专用validator |
| `checkpoint-current` | 九项checkpoint、同baseline current evidence | IF-TEST-HARNESS-01通过公开Runtime port载入 | 主成功旅程/projection |
| `checkpoint-stale-conflict` | declaration/test/candidate/runner identity漂移、旧action | 固定事件/evidence manifests | stale/cooldown/409/恢复 |
| `task-scope-matrix` | Shield/Devon合法与跨空间write sets | 固定task manifests | 最小权限和冻结保护 |
| `red-matrix` | assertion failure、匹配stub token、零收集、import/setup/service/permission、skip/xfail | runner fixture | valid/invalid RED分类 |
| `failure-routing` | test、implementation、design、requirement、safety代表性差异 | 同identity contract/evidence/Prism诊断 | owner/return target |
| `counterexamples` | 每个changed behavior最小production patch及expected assertion token | Shield frozen assets | pre/post语义判别 |
| `sandbox-matrix` | killed、survived、invalid、中断、restart、cleanup失败 | 临时Git worktree与固定进程控制 | 安全恢复/NFR |
| `host-python-web` | Louke wheel+Starlette HTTP/Workbench | 当前宿主真实构建 | Python/Web production surface |
| `host-node-cli` | Node 22.17.1、npm 10.9.2、`node --test`、V8 coverage、CLI stdout | in-repo无第三方fixture | 技术栈中立 |
| `prompt-closed-set` | 四canonical source、staging render、trusted reviewer binding、active unchanged readback | candidate bundle | prompt scope/自审阻断 |
| `secret-canary` | HOME/credential/provider/session哨兵 | 每run合成 | 全artifact/log/ledger扫描 |
| `full-lifecycle-wordcount` | temp Python wordcount seed、13-stage exact catalog、Scribe/Sage/Lex/Archer/Shield/Devon/Prism预录results、Human actions、local build/publish合同 | wordcount seed复制到temp host；closed scenario manifest绑定prompt/Agent I/O/task/request/result digest并复制到分离的只读temp control | FR-1701 success journey |
| `full-lifecycle-fail-each-stage` | 13个只在目标canonical stage公开依赖失败的变体，含enabled M-SECURITY failure；success场景则security disabled | 同一manifest的closed failure catalog | 停留、owner/recovery、无后续artifact、无平行run |

fixture只含合成数据，不含真实credential、真实HOME、生产provider或预计算成功页面。Unit与E2E使用不同identity和失败组合，避免对固定样本过拟合。

---

## 3. Ground Truth 方法

### 3.1 原则

| 待验证规则 | 独立真值来源 |
|---|---|
| AC/IF/layer闭包 | 直接解析锁定Acceptance token集合和test bundle JSON集合；不调用Runtime projection |
| JSON canonical digest | 独立stdlib脚本以UTF-8、sorted-key、compact separators计算SHA-256 |
| path/signature/route/token | Python `ast`独立bootstrap readback + production Starlette route table；不形成FR-0101 formal validator evidence |
| current/stale关系 | fixture声明的identity依赖图与append-only sequence；expected由集合比较得到 |
| 精确collection | runner raw node ids与test-bundle expected集合的双向差集 |
| production SUT身份 | 已加载模块`__file__`原始bytes digest、wheel RECORD/METADATA和composition root route readback |
| counterexample范围/恢复 | 系统Git的`rev-parse/status/diff`、artifact SHA-256和临时worktree路径边界 |
| artifact版本 | 直接读取wheel ZIP METADATA、sdist tar PKG-INFO、clean install metadata/`lk --version` |
| secret/污染 | canary对日志、evidence、artifact和workspace的全量bytes搜索；执行前后refs/path/digest集合差分 |

本Spec验证流程规则而非数值算法，不引入算法参考库。固定expected枚举只来自Acceptance/Interfaces公开合同和fixture输入，不来自被测输出。

### 3.2 Ground Truth 隔离

1. 独立脚本放在`tests/ground_truth/`，不得`import louke`或读取Louke生成的expected projection。
2. 只允许stdlib、fixture文件、系统Git、标准wheel/sdist格式及本计划固定测试工具。
3. counterexample expected assertion token来自Interfaces/Test Plan绑定，不能从mutation执行错误文本反推。
4. Ground Truth和counterexample manifest变更需Shield专项审查并使旧freeze/review stale。

---

## 4. 测试范围（Test Scope）

本计划覆盖同目录`spec.md`全部18个FR、4个NFR及`acceptance.md`的39个唯一AC；均为Valid/Testable/Decided。

| Valid | Testable | Decided |
|---|---|---|
| ✅ | ✅ | ✅ |

范围包括：M-DESIGN同路径声明、M-IMPL内Shield-before-Devon checkpoint、有效RED/Prism/freeze、完整task package、真实production composition、宿主required gates、M-TEST语义判别与恢复、failure routing/stale传播、同一Project Status用户旅程、四角色prompt/bootstrap迁移、双技术栈fixture、FR-1701临时wordcount的13阶段success/逐阶段failure、最小权限/evidence完整性/安全恢复及0.14.0 artifact验证。

不新增顶级stage、平行Project/WorkflowRun、独立ATDD结果页、第二runner、Louke运行时Node依赖或新release identity。像素视觉稿、非Chromium浏览器和真实provider业务旅程不在默认PR范围；protected L3只验证既有release smoke合同。

---

## 5. 验收门槛（Acceptance Criteria）

1. Runtime unit coverage`>=95%`；新增确定性规则均有unit证据。
2. `interfaces.md`全部跨模块接口至少有integration覆盖；关键错误、identity、权限和恢复边界不可仅由unit代替。
3. Workbench主成功旅程和代表性失败→return/retry→恢复旅程有verified-wheel Chromium E2E。
4. 39/39 AC均闭合`observable interface → required layer(s) → CI job`；零收集、未知AC或缺少必需层失败。
5. 每个新增/改变required测试有可执行counterexample；005不接受描述性fallback。
6. required integration/e2e无skip/xfail，production target动态执行且每个可测目标coverage>0；Runtime unit总覆盖率`>=95%`。
7. 每个post-GREEN case为`killed`，原candidate/checkout/artifact未变，受影响及全量required suites恢复GREEN。
8. bootstrap/manual、inactive schema、stale/unknown/cancel/timeout/teardown不确定均不得解锁baseline、派发、freeze、M-VERIFY或publish。
9. Python Web和Node CLI两fixture均按各自project-local合同完成build/runner/surface/coverage/adapter证据，不套用错误默认值。
10. secret canary零命中，所有sandbox无越权读取/写入或未确认污染。
11. wheel/sdist、sdist重建wheel、clean install版本及prompt/schema/route package readback均与canonical`0.14.0`和同source digest一致。
12. FR-1701必须从artifact-verify同digest wheel运行1个完整success及13个逐阶段失败场景；同一run阶段序列、Agent/Human公开入口、真实wordcount build/local publish、Project Status、provider零调用和teardown证据任一缺失/不确定均失败。

---

## 6. 外部依赖分层测试（External Dependency Layered Testing）

### 6.1 三项不可避免约束

| # | 约束 | 结果 |
|---|---|---|
| C1 | PR不能使用生产provider/GitHub credential或真实用户HOME | 默认使用临时HOME、合成credential和协议stand-in；真实smoke仅protected |
| C2 | mutation、timeout、lease和freshness不能依赖真实长时间或污染当前checkout | fixed clock、受控进程与隔离Git worktree |
| C3 | 不可mock Louke核心Runtime、projection、route或目标production module | 只替换系统外Git/进程/clock/provider；required路径走真实composition root |

### 6.2 Controllable与Mock边界

- 可控替身：Git subprocess、外部provider/session adapter、wall clock、进程中断/重启控制、loopback service和临时filesystem/HOME。
- 不可替换：ATDD checkpoint/task/freeze、Host Required-Test Adapter、Failure Routing、Runtime Facts/Projection、Starlette `create_app()`、Workbench presentation及FR-1701 production Runtime/CLI；Replay Adapter只替代系统外LLM provider，不推进workflow。
- counterexample patch是隔离production变体输入，不是正常测试中的mock；它不得修改tests/contracts/workflow/runner/credential。

### 6.3 三层金字塔

| Layer | 名称 | 时间/环境 | 证据职责 | Default |
|---|---|---|---|---|
| L1 | Deterministic | fixed clock、纯fixture、临时store | schema/digest/classification/freshness/权限/错误映射 | ✅ |
| L2 | Contract stand-in | real package/app/runner + external stand-ins | 跨模块接线、双技术栈、RED/GREEN、mutation、failure/recovery | ✅ |
| L3 | Real env smoke | protected real provider/GitHub sandbox | release前最小真实外部协议与teardown | tag/manual only |

同一AC可同时需要L1、L2、E2E；层级职责不同，低层结果不能替代required integration/E2E。

### 6.4 测试基础设施责任合同

| Component | 必须提供的外部行为 | 不实现的行为 |
|---|---|---|
| Runtime fixture importer | 通过公开store/application port追加合法Project/Run/attempt/evidence并readback | 不直写私表、不生成业务结果、不自建route |
| Git sandbox orchestrator | detached worktree、path containment、patch/build/cleanup、before/after refs/digest | 不决定测试是否忠实、不修改当前checkout |
| Process/provider stand-in | 协议一致响应、延迟/失败/中断和redacted ledger | 不推进checkpoint、不返回预计算projection |
| Fixed clock | 提供确定now/advance和freshness边界 | 不映射current/stale或owner |
| Host runner adapter | 执行project-local命令并规范化raw report | 不从语言/后缀猜默认runner，不替换SUT |
| Browser orchestrator | 安装verified wheel、启动production server、readiness、Chromium、finally teardown | 不调用内部函数推进状态 |
| Node fixture harness | Node 22.17.1 build/test/CLI/V8 coverage公开出口 | 不要求Louke安装Node运行时依赖 |
| Full lifecycle orchestrator | 创建分离的temp wordcount host/control/Git/HOME/venv/local sink、安装指定wheel、通过production CLI/Workbench驱动13阶段并产出finally ledger | 不把Louke测试资产放入wordcount host、不从Louke源码import、不直接写workflow状态、不调用真实LLM、不把预建宿主artifact当release结果 |

### 6.5 Assertion basis — 与interfaces.md闭合

| Interface出口 | 必需覆盖层 | 主要观察 |
|---|---|---|
| `IF-EVIDENCE-01` | unit + integration + CI | 最小identity、canonical digest、qualification、redaction、缺失/漂移失败 |
| `IF-ERROR-01` | unit + integration + e2e | HTTP/command错误、CSRF/idempotency/revision、fail-closed |
| `IF-DECLARATION-01` | integration + ac-trace | manifest/source readback、production collection/import、valid RED token绑定、同revision review与Devon write-scope/revision；无专用validator |
| `IF-REGISTRY-01` | unit + integration + design-contract | Draft 2020-12、exact refs、candidate-not-installed、`SCHEMA_NOT_ACTIVE` |
| `IF-PROMPT-01` | integration + design-contract + artifact-verify | 四source closed set、确定render、trusted reviewer、active unchanged/package readback |
| `IF-ATDD-CHECKPOINT-01` | unit + integration + e2e | 九项顺序、派发前置、freeze、declaration return、M-TEST closure |
| `IF-TASK-01` | unit + integration | 完整权威输入、write/forbidden scopes、freshness/conflict |
| `IF-TEST-BUNDLE-01` | integration + ac-trace | AC/IF/layer/surface/counterexample绑定、classification、freeze protection |
| `IF-HOST-RUNNER-01` | integration + e2e + host-compat | project-local discovery、真实surface、host-neutral dispatch、退出语义 |
| `IF-HOST-TEST-EVIDENCE-01` | unit + integration + e2e + CI | exact nodes、AC layers、production digest、surface、lifecycle、coverage |
| `IF-VALID-RED-01` | unit + integration + ac-trace | assertion/token RED与import/setup/skip等invalid RED区分 |
| `IF-DISCRIM-01` | integration + atdd-discrimination | manifest scope、killed/survived/invalid、隔离、恢复后全绿 |
| `IF-TEST-HARNESS-01` | integration + e2e | 公开fixture导入、readback、无私表/test app捷径 |
| `IF-FAILURE-ROUTE-01` | unit + integration + e2e | 六类classification、owner/return、current Prism诊断、无锚点争议 |
| `IF-REVISION-01` | unit + integration + e2e | declaration/test/candidate漂移、cooldown/stale、合法retry/history |
| `IF-PROJECT-STATUS-01` | unit + integration + e2e + artifact-verify | GET/detail/action、ETag、production三route、capability复核 |
| `IF-PROJECT-STATUS-UI-01` | integration + e2e | 同一Workbench、状态/owner/evidence/动作、keyboard、reconnect/readonly |
| `IF-PROJECT-RUN-01` | integration + e2e + CI | project.toml命令/paths、discovery、start/readiness/teardown ownership |
| `IF-LIFECYCLE-01` | integration + e2e + full-lifecycle | installed wheel、replay/Human公开入口、13阶段、真实wordcount build/local publish、逐阶段失败、隔离/teardown |
| `IF-PRECOMMIT-01` | integration + quality | 保留快速hooks、合法RED可提交、readback与required边界 |
| `IF-TRACE-01` | integration + ac-trace | 39/39、多层、counterexample和anti-cheat闭包 |
| `IF-CI-01` | CI contract integration | DAG、完整SHA、最小权限、mandatory evidence、required fail-closed |
| `IF-RELEASE-01` | unit + integration + artifact-verify + install-matrix | prepare→build→extract→install→prompt/schema/route readback |

---

## 7. CI Gate与需求级分配

### 7.1 AC traceability命令

```bash
python tools/check_ac_traceability.py \
  --acceptance .louke/project/specs/v0.14-005-atdd-process-improvement/acceptance.md \
  --tests tests \
  --expected-count 39
```

该宿主入口已经存在；005参数与资产扫描接线由Devon按Interfaces实现。`tools/check_atdd_assets.py`当前为`candidate-change-required`，不存在时`ac-trace`失败，不得跳过。

### 7.2 AC → observable interface → required layer(s) → CI job

以下是需求责任分配，不是测试函数清单。

| AC | Observable interface | Required layer(s) | CI gate/job | 分配理由 |
|---|---|---|---|---|
| `AC-FR0001-01` | IF-ATDD-CHECKPOINT-01、IF-PROJECT-STATUS-01、IF-PROJECT-STATUS-UI-01 | unit + integration + e2e | unit、integration、e2e-standin、ac-trace | 派发前置与M-VERIFY继续动作必须同时证明Runtime接线和同一用户surface |
| `AC-FR0001-02` | IF-ATDD-CHECKPOINT-01、IF-FAILURE-ROUTE-01、IF-PROJECT-STATUS-UI-01 | unit + integration + e2e | unit、integration、e2e-standin | canonical stage不变及失败停留/返回是主旅程连续性 |
| `AC-FR0101-01` | IF-DECLARATION-01 | integration | integration、ac-trace | M-DESIGN manifest/source readback与Shield production collection共同证明同路径公开声明；bootstrap检查不形成formal PASS |
| `AC-FR0101-02` | IF-DECLARATION-01、IF-ATDD-CHECKPOINT-01、IF-VALID-RED-01 | integration | integration、ac-trace | 错签名/路径/token必须表现为collection失败或不可归因RED并阻止freeze/Devon；不引入专用validator |
| `AC-FR0201-01` | IF-DECLARATION-01、IF-TASK-01、IF-REVISION-01 | unit + integration | unit、integration、design-contract | public声明冻结、implementation region和越权/stale跨task与facts |
| `AC-FR0201-02` | IF-ATDD-CHECKPOINT-01、IF-REVISION-01、IF-PROJECT-STATUS-UI-01 | unit + integration + e2e | unit、integration、e2e-standin | 声明修订return、cooldown和新包恢复需代表性公开交互 |
| `AC-FR0301-01` | IF-TASK-01、IF-TEST-BUNDLE-01、IF-PROJECT-RUN-01 | integration | integration、ac-trace | Shield授权资产及完整绑定由跨模块manifest/runner闭合 |
| `AC-FR0301-02` | IF-TEST-BUNDLE-01、IF-REVISION-01 | unit + integration | unit、integration、ac-trace | baseline delta分类与mtime无关适合确定性规则和bundle接线 |
| `AC-FR0401-01` | IF-HOST-RUNNER-01、IF-HOST-TEST-EVIDENCE-01 | integration + e2e | host-compat、integration、e2e-standin | integration/public package及最终用户surface均需动态生产身份 |
| `AC-FR0401-02` | IF-HOST-TEST-EVIDENCE-01、IF-TEST-HARNESS-01 | unit + integration | unit、integration、ac-trace | SUT替换/test app和合法外部stand-in边界需负向接线检查 |
| `AC-FR0501-01` | IF-TEST-BUNDLE-01、IF-HOST-TEST-EVIDENCE-01、IF-TRACE-01 | integration + e2e | integration、e2e-standin、ac-trace | 行为/副作用必须落公开结果；用户surface行为由E2E证明 |
| `AC-FR0601-01` | IF-VALID-RED-01、IF-HOST-TEST-EVIDENCE-01 | unit + integration | unit、integration、ac-trace | assertion/token失败与基础设施错误分类需完整负向矩阵 |
| `AC-FR0601-02` | IF-DISCRIM-01、IF-VALID-RED-01、IF-TEST-BUNDLE-01 | integration | integration、atdd-discrimination、ac-trace | 每个changed test反例必须真实隔离执行，005无描述性fallback |
| `AC-FR0701-01` | IF-TEST-BUNDLE-01、IF-ATDD-CHECKPOINT-01、IF-PROJECT-STATUS-01 | integration + e2e | integration、e2e-standin、ac-trace | 同revision程序证据/review/freeze及用户可达证据需两层 |
| `AC-FR0701-02` | IF-REGISTRY-01、IF-TEST-BUNDLE-01、IF-REVISION-01 | unit + integration | unit、design-contract、integration | unsupported fail-closed及声明升级stale由schema与freeze接线证明 |
| `AC-FR0801-01` | IF-TASK-01、IF-EVIDENCE-01 | unit + integration | unit、integration、design-contract | 完整输入、identity、scope和冲突阻断是task package合同 |
| `AC-FR0901-01` | IF-DECLARATION-01、IF-HOST-RUNNER-01、IF-PROJECT-STATUS-01 | integration + e2e | integration、e2e-standin、artifact-verify | production composition/route/CLI行为及无占位需安装态surface证明 |
| `AC-FR1001-01` | IF-PROJECT-RUN-01、IF-HOST-TEST-EVIDENCE-01 | integration + e2e | integration、e2e-standin、host-compat | 宿主required suites、无skip和动态surface不能由局部selector替代 |
| `AC-FR1101-01` | IF-REGISTRY-01、IF-DISCRIM-01、IF-PROJECT-RUN-01 | integration | design-contract、integration、host-compat | project-local adapter选择/能力/identity及错误默认adapter拒绝 |
| `AC-FR1101-02` | IF-DISCRIM-01、IF-HOST-TEST-EVIDENCE-01 | integration | atdd-discrimination、integration、e2e-standin | 每个语义错误被目标断言识别且恢复后全required GREEN |
| `AC-FR1101-03` | IF-TRACE-01、IF-HOST-TEST-EVIDENCE-01、IF-ATDD-CHECKPOINT-01 | unit + integration + e2e | ac-trace、unit、integration、e2e-standin | AC→IF→layer→surface→mutation闭包及用户surface动态证据 |
| `AC-FR1201-01` | IF-PROJECT-STATUS-01、IF-PROJECT-STATUS-UI-01 | integration + e2e | integration、e2e-standin | checkpoint、owner、证据链接与return context是用户关键观察旅程 |
| `AC-FR1201-02` | IF-PROJECT-STATUS-UI-01、IF-ERROR-01、IF-REVISION-01 | unit + integration + e2e | unit、integration、e2e-standin | Continue capability、防直链绕过及失败恢复必须真实UI/API闭合 |
| `AC-FR1301-01` | IF-FAILURE-ROUTE-01、IF-PROJECT-STATUS-01 | unit + integration + e2e | unit、integration、e2e-standin | 六类owner/return和current Prism诊断需规则、持久化、可见投影 |
| `AC-FR1301-02` | IF-FAILURE-ROUTE-01、IF-TASK-01、IF-REVISION-01 | unit + integration | unit、integration | 有锚点争议与合同gap返回上游，不允许修改冻结测试 |
| `AC-FR1401-01` | IF-REVISION-01、IF-EVIDENCE-01、IF-PROJECT-STATUS-UI-01 | unit + integration + e2e | unit、integration、e2e-standin | 全identity stale传播及历史可见需要三层职责 |
| `AC-FR1401-02` | IF-REVISION-01、IF-ERROR-01、IF-PROJECT-STATUS-01 | unit + integration + e2e | unit、integration、e2e-standin | 合法target新attempt、错误/stale retry无副作用需公开动作证明 |
| `AC-FR1501-01` | IF-PRECOMMIT-01、IF-TEST-BUNDLE-01 | integration + CI | quality、design-contract、ac-trace | 合法RED与快速hooks共存，删除既有hook或跳静态检查失败 |
| `AC-FR1501-02` | IF-PROJECT-RUN-01、IF-CI-01、IF-EVIDENCE-01 | integration + e2e + CI | integration、e2e-standin、atdd-discrimination、required | Runtime/CI必须对同candidate执行完整required闭包，pre-commit不可替代 |
| `AC-FR1601-01` | IF-PROMPT-01、IF-TASK-01、IF-ATDD-CHECKPOINT-01 | integration + CI | design-contract、artifact-verify、integration | 四角色closed prompt、supersession及Runtime authority需source/render/package readback |
| `AC-FR1601-02` | IF-EVIDENCE-01、IF-REGISTRY-01、IF-PROJECT-STATUS-UI-01 | unit + integration + e2e | unit、design-contract、integration、e2e-standin | bootstrap/manual可见但不解锁，schema缺失正式流程fail closed |
| `AC-FR1701-01` | IF-LIFECYCLE-01、IF-PROJECT-STATUS-01、IF-PROJECT-STATUS-UI-01、IF-EVIDENCE-01 | integration + e2e | integration、full-lifecycle、ac-trace | 13阶段同一run顺序、逐阶段前置/artifact/evidence、success及13个failure停留/恢复必须由production组合和用户surface共同证明 |
| `AC-FR1701-02` | IF-LIFECYCLE-01、IF-HOST-RUNNER-01、IF-EVIDENCE-01 | integration + e2e | integration、full-lifecycle、ac-trace | Replay/Human公开入口、真实provider零调用、temp wordcount与Louke仓库隔离及finally清理由安装态旅程证明 |
| `AC-NFR0001-01` | IF-HOST-RUNNER-01、IF-HOST-TEST-EVIDENCE-01、IF-DISCRIM-01 | integration | host-compat、integration、atdd-discrimination | Python Web与Node CLI按各自build/runner/surface/coverage/adapter证明中立性 |
| `AC-NFR0101-01` | IF-TASK-01、IF-DECLARATION-01、IF-PROMPT-01 | unit + integration | unit、design-contract、integration | 五类空间identity/write scope及四角色越权拒绝 |
| `AC-NFR0101-02` | IF-EVIDENCE-01、IF-DISCRIM-01、IF-TEST-HARNESS-01 | integration + e2e | integration、e2e-standin、atdd-discrimination | HOME/credential/真实资源canary和未知污染必须覆盖全部sandbox/surface |
| `AC-NFR0201-01` | IF-EVIDENCE-01、IF-HOST-TEST-EVIDENCE-01、IF-REVISION-01 | unit + integration | unit、integration、required | 全证据identity、失败/取消/timeout和可追溯重试不覆盖历史 |
| `AC-NFR0201-02` | IF-REGISTRY-01、IF-EVIDENCE-01 | unit + integration + CI | design-contract、unit、integration | 最小candidate schema存在、manual资格可辨且不能宣告正式成功 |
| `AC-NFR0301-01` | IF-DISCRIM-01、IF-REVISION-01、IF-PROJECT-STATUS-UI-01 | integration + e2e | atdd-discrimination、integration、e2e-standin | 成功/survived/invalid/中断/重启均隔离，恢复不确定可见attention并阻断 |

### 7.3 GitHub Actions gate合同

| Trigger | Mandatory jobs | 附加job |
|---|---|---|
| pull request到`main`/`releases/**` | quality、design-contract、ac-trace、build-artifacts、artifact-verify、unit matrix、host-compat、integration、e2e-standin、full-lifecycle、atdd-discrimination、install-matrix、required | 无secret；禁止`pull_request_target`；无real-smoke/publish |
| push `main`/`releases/**` | 同PR | 非tag不publish |
| tag `v*` | 全部mandatory | protected real-smoke；通过后publish |
| manual | 全部mandatory | 只有合法release identity和protected审批后才real-smoke/publish |

Runner/矩阵、action完整SHA、cache key、timeout和权限以`architecture.md`§11为锁定合同。稳定required check唯一为`Louke CI / required`；`required`使用`if: always()`严格检查每个mandatory need，failed/cancelled/timed_out/skipped/missing/unknown任一结果均不得成功。

### 7.4 Release/version验证顺序

1. 读取`pyproject.toml:[project].version=0.14.0`作为canonical package identity；release时比较branch`releases/0.14.0`和tag`v0.14.0`。
2. 使用既有`tools/louke_python_release_adapter.py prepare`准备或校验版本源；命令未实现/失败即阻断。
3. `python -m build --wheel --sdist`真实构建，要求恰好一个wheel和一个sdist并绑定source SHA。
4. 独立从wheel METADATA和sdist PKG-INFO提取版本/SHA-256，逐artifact与canonical identity比较。
5. 使用adapter `verify-dist`、`verify-installed`，从wheel clean install及sdist重建wheel clean install复核`lk --version`、`importlib.metadata.version("louke")`、四canonical prompts、registry/schema和三个Project Status routes。
6. 只有artifact version/readback evidence current、`Louke CI / required`成功且release场景real-smoke成功才允许publish；publish只消费同digest artifact，不重新build。

缺失/非法identity、source处理失败、build失败、artifact缺失/多余/无法提取、任一版本/route/prompt/schema出口不匹配或结果不确定均阻断publish。

---

## 8. Judge Review Checklist

- [x] 测试策略覆盖虚假RED、SUT替换、形状代行为、stale review、无效mutation kill、污染和bootstrap冒充active等主要风险。
- [x] 39个AC均有`observable interface → required layer(s) → CI job`责任分配。
- [x] 本计划不维护具体测试函数清单；§7.2仅是需求级覆盖合同。
- [x] AC count、多层、anti-cheat、skip/xfail、精确collection和counterexample门禁均已定义。
- [x] fixture、stand-in、clock、Git worktree和双技术栈数据可离线复现；真实credential仅用于protected L3。
- [x] 目录、固定工具版本、project-local命令、local/global安装态和teardown责任已确定。
- [x] Ground Truth独立，不调用Louke实现生成expected。
- [x] `interfaces.md`全部23个公开出口均有覆盖；所有跨模块接口都包含integration或专门CI contract integration。
- [x] FR-1701由installed wheel驱动1个success和13个逐阶段failure场景；Replay/Human入口、13阶段Project Status、wordcount真实build/local publish、隔离和teardown证据闭合。
- [x] 同一Project Status主成功旅程及代表性失败/返回/重试旅程有E2E，错误矩阵下沉unit/integration。
- [x] wheel/sdist及全部适用安装/运行/package readback纳入publish阻断门禁。
