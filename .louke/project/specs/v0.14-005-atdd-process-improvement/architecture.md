# 契约测试先行与真实交付表面验证 — Architecture

- **Spec ID**：`v0.14-005-atdd-process-improvement`
- **设计日期**：2026-07-25
- **Story identity**：`sha256:254eb9c753a424275233af446721ca7d18851e1851de392c738858b2b2879a70`
- **Spec identity**：`sha256:f1e29c404775240b820b767df1a450962a291d2c9a0ee2644e067663baccd05d`
- **Acceptance identity**：`sha256:cff523caa12f2d587adabe8a9b2afda260fb8b62ab58c81beb59b6b95ddf9a4d`
- **Bootstrap qualification**：当前完整 Runtime/active schema registry 未部署；本文及关联 machine contract/prompt bundle 是 `candidate`，不表示 program validation、Prism verdict、implementation baseline 或阶段已通过。

## 1. 范围、继承合同与宿主事实

本设计改变 `M-IMPL` 内的责任顺序，不增加顶级阶段：`M-DESIGN` 同时锁定人类可读设计、同路径接口声明和宿主 adapter；`M-IMPL` 先由 Shield 形成可判别的 integration/e2e，再由 Devon 实现；`M-TEST` 在真实 candidate 上完成 required suites、语义判别、恢复后 GREEN 与覆盖闭包；随后才可进入 `M-VERIFY`。

已核对的事实与继承身份如下：

1. Louke 是 MIT License 的 Python 包，`pyproject.toml` 要求 Python `>=3.11`，版本源是 `pyproject.toml:[project].version=0.14.0`，构建后端是 `setuptools.build_meta`；公开 CLI 为 `lk`，Web 入口为 `lk serve` / `python -m louke serve`，Web 使用 Starlette。
2. 直接运行依赖来自 `pyproject.toml`；本设计不新增运行时第三方库。现有 `.venv` 可核对 `pytest 9.1.1`、`pytest-cov 7.1.0`、`pytest-asyncio 1.4.0`、`build 1.5.0`、`jsonschema 4.26.0`、`packaging 26.2`、`pre-commit 4.6.1`。浏览器资产继续使用 `tests/e2e/playwright-requirements.txt` 固定的 Playwright `1.54.0`。
3. `tests/e2e/run-project-venv` 与 `tests/e2e/run_e2e.py` 是宿主项目现有 runner。后者当前只发现到 v0.14-004，且没有 RED/判别/evidence 子命令；Devon必须按本文扩展同一 runner，不建立平行 runner。
4. `.louke/project/project.toml` 当前candidate已锁定 `meta.test_framework="pytest"`、integration/e2e命令及005 asset paths；runner discovery的代码实现仍由Devon完成。该metadata是运行合同，不等于runner已支持005。
5. `.github/workflows/louke-ci.yml` 是唯一 Louke 托管 workflow，稳定 check 是 `Louke CI / required`。当前 workflow仍使用 floating action major、未固定完整测试依赖、未运行005 trace/判别，且声明的 `real-smoke` 命令当前 runner不支持；这些属于本轮必须按第11节收敛的实现差距，不能静默继承为已满足。
6. `.pre-commit-config.yaml` 已固定 `pre-commit-hooks v6.0.0`、`ruff v0.15.20`、`mypy v2.1.0`，并保留 Louke 自有快速 hook。它不运行 required integration/e2e，符合合法RED边界；Devon只扩展现有 Louke hook 的增量声明/trace静态校验，不新增执行RED套件的hook。
7. v0.14-004 的 Project Status 设计是本轮唯一呈现基线：`architecture.md sha256:32c88eb2062eb0173738086202eddf87122204ee99d32133c1ea30a6c39335cc`、`interfaces.md sha256:ce4e83ae0d0f614a43a1912e317859105f84f08ba53fc3e8b1cc150dd108e37f`。本轮扩展其 `GET /api/projects/{project_id}/status` 与同一 Workbench surface，不创建结果页；当前源码尚无该精确route，因此本设计交付注册到production `create_app()`的接口桩。
8. `louke/schemas/registry.json` 当前是 `activation_state=candidate`，且其v1 schema把002 identity写成常量，不能作为005 exact active schema。`.louke/project/contracts/`此前不存在。Human已允许bootstrap阶段生成缺失schema；因此本轮在project-local路径产生program-owned registry/schema/instance candidates，但Runtime在原子激活前必须返回`SCHEMA_NOT_ACTIVE`并拒绝正式baseline。
9. `louke/agents/{Archer,Shield,Devon,Prism}.md`是打包canonical prompt source；`.opencode/agents/**`是当前开发部署输出，两者字节identity已经漂移。005明确影响四个角色，所以闭合集合恰为这四个source；本轮不写`.opencode/agents/**`，不改变active deployment。

## 2. 模块边界

| 模块 | 职责 | 不拥有的职责 | 公开观察边界 |
|---|---|---|---|
| `Design Declaration` | 生成/描述同路径声明清单，冻结path、signature、route、token和Devon行为体write scope | 不实现业务、不设置FR-0101专用validator或baseline前自证门禁、不把桩当GREEN | `InterfaceDeclarationManifest`、源码readback、Shield collection/RED绑定 |
| `ATDD Checkpoint` | 在同一`M-IMPL` attempt内按current evidence开放Shield或Devon任务，冻结测试identity并控制cooldown | 不运行Agent provider、不持久化review verdict、不增加顶级stage | checkpoint projection、task readback、command result |
| `Task Package` | 生成绑定同一baseline的Shield/Devon task manifest及精确write/forbidden scopes | 不以Issue替代权威输入、不让Agent自行扩scope | task manifest/readback |
| `Host Required-Test Adapter` | 读取project-local runner contract，执行collection/RED/GREEN，规范化节点、AC层、skip、surface和目标模块动态执行证据 | 不硬编码pytest/Web为任意宿主默认，不替换SUT | host runner command、`HostTestEvidence` |
| `Semantic Discrimination Adapter` | 在隔离Git worktree中应用已审查的最小生产源码patch，构建/安装变异artifact，运行目标测试，恢复并复核原candidate | 不在当前worktree原地改SUT，不接受基础设施错误为kill | adapter CLI、counterexample manifest、discrimination evidence |
| `Test Asset Review` | 绑定Shield patch、反例、RED、runner和baseline，形成Prism独立审查输入 | 不让Prism冻结/推进，不复用stale review | review task/readback identity |
| `Failure Routing` | 依据锁定合同、程序证据和适用的Prism诊断给出classification、owner、return target | 不把测试默认为需求，不让Agent自行改变状态 | failure decision、discussion/return readback |
| `Runtime Facts` | append-only保存baseline、task、declaration、test、runner、review、candidate、mutation、coverage和route evidence | 不把provider/session metadata作为workflow事实，不覆盖历史 | evidence envelope、artifact URL、audit event |
| `Runtime Projection` | 将Runtime facts投影到继承的Project Status，显示checkpoint、current/stale、owner、owning link与合法动作 | 不从文件存在、聊天或客户端猜测状态 | Project Status API、checkpoint detail API |
| `Workbench Presentation` | 在同一Project Status active card和attempt detail呈现ATDD进度、证据、attention、继续/返回 | 不dispatch、不生成第二状态权威 | 浏览器URL、可访问名称、动作可用性、可见反馈 |
| `Prompt/Capability Packaging` | 对四个canonical source做确定性transform、staging render、readback、reviewer binding和原子候选激活设计 | 不让candidate Prism审自己，不直接覆盖active deployment | prompt bundle/readback/supersession manifest |
| `CI/Traceability` | 检查AC层闭包、声明、prompt、machine contract、required suites、真实build/artifact及判别证据，聚合稳定required check | 不把pre-commit或单个selector当full gate | CI jobs、JUnit/JSON/coverage/browser evidence |
| `External Stand-ins` | 对Git/进程/clock/provider等SUT外依赖提供协议一致、无真实credential的可控边界 | 不实现Runtime、projection、route、业务判断或production composition | invocation ledger、redacted request/response、teardown report |
| `Replay Agent Adapter` | 按closed fixture manifest把Runtime真实dispatch精确映射到一次性预录Agent结果，并记录dispatch/result ledger | 不直接写workflow事实、不跳过Agent output schema、不调用真实LLM provider、不接受未知或乱序fixture | `--opencode-backend replay`、replay manifest、session/result readback |
| `Full Lifecycle Harness` | 在系统临时目录创建独立wordcount宿主、安装verified Louke wheel、通过production Runtime/Workbench驱动13阶段成功与逐阶段失败场景并清理 | 不把fixture状态直接写入Runtime、不在Louke仓库生成wordcount代码、不验证Agent语义质量 | lifecycle scenario/evidence、Project Status snapshots、临时宿主与publish sink清理报告 |

## 3. 依赖方向与authority

```text
M-DESIGN artifacts -> Design Declaration -> baseline readback -> ATDD Checkpoint -> Task Package -> Shield collection/RED
Host project.toml -> Host Required-Test Adapter ---------> Runtime Facts
Shield test/negative patch -> Test Asset Review -> trusted active Prism result
Runtime Facts + current review -> ATDD Checkpoint -> Task Package -> Devon
Devon production candidate -> production composition root
                            -> Host Required-Test Adapter
                            -> Semantic Discrimination Adapter
                            -> Runtime Facts -> Failure Routing
Runtime Facts -> Runtime Projection -> Workbench Presentation -> Human
canonical prompt sources -> Prompt/Capability Packaging -> staging only
verified Louke wheel + lifecycle fixtures -> Full Lifecycle Harness
Runtime dispatch -> Replay Agent Adapter -> schema-valid prerecorded result -> Runtime Facts
Full Lifecycle Harness -> production Runtime/Web/CLI -> Runtime Projection -> Workbench Presentation
all executable gates -> CI/Traceability -> Louke CI / required
```

1. Runtime/program是dispatch、current revision、冻结、lease、证据持久化、stale传播、正式路由和阶段推进的唯一authority。Agent只返回task schema允许的产物或诊断。
2. `Shield preparation`、`RED/review/freeze`、`Devon implementation`是`M-IMPL` checkpoint，不是新的`M-TEST`阶段。`M-TEST`只消费真实candidate做最终GREEN、semantic discrimination、restore后GREEN与AC/surface/coverage闭包。
3. 接口声明的**公开合同区**由path、signature、route和token identity冻结；同文件的**行为体区域**是Devon明确write scope。Runtime沿用task write-scope/revision gate拒绝行为体区域之外的直接修改；FR-0101不新增独立声明validator、CLI或pre-baseline程序证据。Shield通过真实production import/collection及绑定token的RED暴露错误声明，Prism审查同一声明与测试revision。
4. Shield测试资产、负样本patch和manifest冻结后，Devon scope显式排除它们。声明或上游合同identity变化会停止旧Devon任务、将冻结测试置`cooldown`并使RED/review/GREEN等依赖证据stale；Runtime建立新baseline后重新走Shield collection、有效RED和Prism审查。
5. 测试可替换外部adapter，但不得替换Louke production package、Runtime service、Starlette `create_app()`、route table、projection或目标源码。所有默认CI fixture使用临时HOME/workspace/SQLite/provider namespace和合成credential；不读取真实HOME/生产secret。

## 4. 声明骨架与ATDD checkpoint设计

### 4.1 同路径声明

本轮新增接口声明位于真实Louke模块：

- `louke/runtime/atdd_checkpoint.py`
- `louke/runtime/host_required_tests.py`
- `louke/runtime/semantic_discrimination.py`
- `louke/runtime/atdd_failure_routing.py`
- `louke/runtime/atdd_projection.py`
- `louke/opencode/replay.py`
- `louke/web/api/project_status.py`
- `louke/web/app.py`中的三个production route注册（仅接线声明）

新文件只包含完整public signature、type annotation、docstring及`raise NotImplementedError("IF-…")`。`app.py`只增加import和Route声明，不写handler逻辑。Devon必须原地替换raise行为并保持path/signature/route/token映射；不需要保留`NotImplementedError`。已废弃的`louke/runtime/interface_declarations.py`不属于closed声明集合且已从candidate源码删除；Devon与Shield必须保持该路径不存在，不得恢复、import或把它用作测试出口。

FR-0101明确不引入独立声明validator、`interface_stubs` CLI、`declaration_validation` checkpoint或baseline前formal validator evidence。Archer交付声明、closed manifest和源码readback；Shield测试必须从manifest列出的真实production path import/collect，并把签名、route或token错误分类为无效测试资产/不可归因RED，不能据此冻结；Devon遇到不可达声明走FR-0201 revision return；Prism审查同一声明、测试和RED revision。Archer的bootstrap AST/import检查仅用于避免交付明显破损文件，始终是`bootstrap_manual/unvalidated`，不形成Runtime gate。

FR-0201的冻结保护由既有task write-scope/revision合同承担：baseline记录公开声明元数据及允许替换的`implementation_region`，Devon只能修改行为体和设计明确列出的composition接线；公开signature、route、token或文件位置变化必须形成新design identity。该write-scope检查不是FR-0101声明质量validator，也不在Shield前替代真实collection。

### 4.2 checkpoint顺序

`ATDDCheckpointProjection.phase`固定使用下列语义值，不形成stage identity：

1. `shield_test_preparation`
2. `pre_implementation_red`
3. `prism_test_review`
4. `test_freeze`
5. `devon_implementation`
6. `required_green`
7. `semantic_discrimination`
8. `restored_green`
9. `m_test_closure`

每一项都只有`pending|running|passed|failed|attention|cooldown|stale`可见状态。`passed`要求current formal evidence；bootstrap/manual和`unvalidated`只能显示attention，不能解锁正式Shield/Devon派发。Shield dispatch要求包含声明manifest/readback的current M-DESIGN baseline及其它适用program schema/capability gate；不要求FR-0101专用validator。Devon dispatch的必要条件是production collection、有效RED、可执行反例、同revision Prism review及冻结结果全部current。

### 4.3 有效RED与测试分类

- `behavior_class=new_or_changed`来自当前baseline相对上一有效baseline的AC/interface/surface delta；本Spec的39个AC均为新增流程合同。继承v0.14-004的13 stage catalog和普通Project Status导航可保持GREEN，但FR-1701要求新增真实全阶段组合旅程，不得把既有局部stage测试冒充完整生命周期。
- 初始RED必须精确收集expected node ids，无skip/xfail/setup/service error。目标测试只能因测试断言失败，或因已声明桩抛出与目标接口一致的`NotImplementedError("IF-…")`而RED；后者在HTTP层可以表现为production route的5xx，但runner必须从同一请求的受控server event核对token。任意import/compile/fixture/permission/zero collection不是有效RED。
- 每个新增/改变required test至少绑定一个counterexample。当前Louke宿主的Git/build/临时venv能力可安全执行所有005默认CI目标，因此本设计**不允许描述性退化**；`unsupported`只适用于未来宿主且必须由active machine contract在M-DESIGN预先列出具体不支持原因。

## 5. Runner、负样本、动态表面与恢复

### 5.1 Host runner扩展

继续使用`tests/e2e/run-project-venv`。Devon扩展`tests/e2e/run_e2e.py`：

```text
tests/e2e/run-project-venv integration
tests/e2e/run-project-venv e2e --profile all --runtime both -m "not v014_005_full_lifecycle"
tests/e2e/run-project-venv atdd --phase pre-red --spec v0.14-005-atdd-process-improvement --bundle <path> --evidence <path>
tests/e2e/run-project-venv atdd --phase post-green --spec v0.14-005-atdd-process-improvement --bundle <path> --evidence <path>
```

前两条保持现有兼容；integration discovery增加`tests/integration/v014_atdd_process_improvement`，`v014/all` e2e增加`tests/e2e/v014_atdd_process_improvement`。Devon必须在项目pytest配置注册`v014_005_full_lifecycle` marker；通用`all`命令发现005常规旅程但显式deselect该专用矩阵，只有`full-lifecycle` job可以选择它。`atdd`是本设计要求Devon实现的确定入口，不是当前已交付命令。

Runner必须生成IF-EVIDENCE-01 envelope，精确记录command/cwd、source/test/runner/environment identity、expected/collected/executed node ids、每个AC-layer结果、skip/xfail、suite lifecycle、loaded production module path+digest、surface invocation、coverage target和退出原因。Python宿主用coverage.py/pytest-cov动态证据；Node fixture用Node `--test`和`NODE_V8_COVERAGE`。不同宿主的raw报告由project-local adapter规范化，不改变通用evidence字段。

### 5.2 Project-local semantic adapter

选用自有`tools/louke_atdd_adapter.py`（Devon按IF-DISCRIM-01实现），不引入`mutmut`。原因：005需要稳定绑定AC/IF的语义错误，而通用mutation operator的编号和等价mutant不稳定，且难以证明目标表面仍启动。adapter只使用Python stdlib、Git、现有build/runner：

1. 核对original source SHA、clean candidate、test revision、patch digest和allowed production paths；
2. 在系统临时目录创建detached Git worktree，HOME/XDG/credential/provider完全隔离；
3. 应用Shield资产中的最小unified patch；patch只可改manifest允许的production path，禁止tests、`.louke`合同、workflow、runner和credential；
4. 构建变异wheel，安装到新的product venv，通过同一production composition root执行manifest中精确node ids；
5. 只有目标test完成收集并因绑定AC/IF assertion失败、其它required setup正常时记`killed`；PASS为`survived`，build/import/setup/service/无关失败为`invalid`；
6. 无论结果如何删除sandbox/worktree；验证原checkout SHA、tracked diff、candidate artifact digest未变；
7. 用原candidate artifact重跑受影响required suites，再全量重跑integration/e2e；两次均GREEN才产生`restored_green`。

Shield提交：`tests/fixtures/v014_atdd_process_improvement/counterexamples/*.patch`与`counterexamples.manifest.json`。patch是隔离执行输入，不进入正常pytest discovery，不被import或monkeypatch到正常SUT。pre-Devon self-check允许patch基于声明骨架提供一个错误但可运行的行为；post-GREEN patch基于current candidate重新生成/复核identity后才执行，测试revision保持冻结。

### 5.3 两技术栈fixture

NFR-0001由两个L2 fixture证明：

- Python/Starlette Louke自身：setuptools wheel，HTTP+Workbench surface，pytest/Playwright/coverage；
- `tests/fixtures/v014_atdd_process_improvement/hosts/node-cli`：Node `22.17.1`、npm `10.9.2`、无第三方package、`node --test`、public CLI stdout/readback、V8 coverage。

Node fixture由Shield作为测试数据实现，Runtime必须完全读取其project-local contract，不因`.js`后缀猜adapter。CI integration job使用`actions/setup-node` commit `49933ea5288caeca8642d1e84afbd3f7d6820020`固定Node。Node fixture只证明通用流程中立性，不把Node加入Louke运行时依赖或发布artifact。

### 5.4 FR-1701全阶段生命周期Harness

FR-1701复用production Runtime、`lk serve`、Workbench和现有`run-project-venv`，不新增测试专用workflow或直接写Runtime facts。Shield资产固定为：

```text
tests/e2e/v014_atdd_process_improvement/test_full_lifecycle.py
tests/fixtures/v014_atdd_process_improvement/full_lifecycle/scenario.manifest.json
tests/fixtures/v014_atdd_process_improvement/full_lifecycle/agent-results/*.json
tests/fixtures/v014_atdd_process_improvement/full_lifecycle/failures/*.json
tests/fixtures/v014_atdd_process_improvement/full_lifecycle/wordcount-seed/**
```

执行入口复用现有e2e parser，并由Devon增加可选verified artifact输入；不增加平行runner：

```text
tests/e2e/run-project-venv e2e --profile v014 --runtime local \
  --wheel <verified-wheel> \
  tests/e2e/v014_atdd_process_improvement/test_full_lifecycle.py \
  -m v014_005_full_lifecycle --maxfail=1
```

本地未给`--wheel`时runner仍按现有合同从当前source构建一次并验证版本；CI的`full-lifecycle` job必须下载`build-artifacts`产生且经`artifact-verify`核对的同digest wheel并显式传入，禁止另行build Louke。`--profile all`必须包含005目录，但`project.toml [e2e].run`以`-m "not v014_005_full_lifecycle"`排除本专用矩阵；通用`e2e-standin`不运行其success或failpoint场景，完整1+13矩阵只由专用命令产生一次evidence。

成功场景按以下方式运行：

1. runner在系统临时目录创建彼此分离的`host/`、`control/`、`publish-sink/`、`home/`和独立venv；wordcount seed只进入`host/`且仅含宿主初始化输入及project-local build/test/publish合同，不含Louke源码、Louke测试代码或预计算workflow状态；closed scenario/replay bundle复制到只读`control/`；随后安装verified Louke wheel并在`host/`初始化独立Git仓库。
2. production server使用`lk serve --project-root <host> --opencode-backend replay --opencode-replay-manifest <control>/scenario.manifest.json`。CLI改动锁定到`louke/serve.py`（`replay`choice、manifest参数、regular-file/digest检查及显式环境传递）和`louke/opencode/dispatch.py`（显式`replay`解析；不回退mock/real）；所有production Agent task service沿用application-composed`adapter_factory`，不得在测试侧注入替代Runtime。`louke.opencode.replay.load_replay_adapter(...)`实现现有`OpenCodeAdapter`协议：`create`把exact `dispatch_correlation_id/role`绑定到scenario `session_key`，`send_message`核对session、turn和UTF-8 request digest后才accepted，`reconcile_session`随后exact-once返回schema-valid`ProviderResult`；`list/list_messages/stream_events/stop`投影同一调用ledger。结果语义键为`{workflow_run_id,stage_id,role,task_contract_digest,turn_ordinal}`；unknown、乱序、重复消费、schema/prompt/request/result digest不符或fixture余项均失败。Adapter只返回Agent result，不写artifact、stage或Project Status。
3. Runtime真实消费Scribe、Sage、Lex、Archer、Shield、Devon、Prism的schema-valid预录result，形成Story、Spec、Acceptance、设计、声明、测试、实现和review artifacts；本测试只断言identity、路由和传递，不评价文本语义质量。
4. Human动作通过production Workbench的可见action或其同源公开API提交，携带session、CSRF、`Idempotency-Key`和current revision。M-START确认、需求Go/批准及publish批准不得由fixture直接写状态。
5. 同一Project、WorkflowRun和attempt必须依次进入且仅进入一次：`M-START → M-STORY → M-SPEC → M-ACC → M-REQ-APPROVAL → M-DESIGN → M-IMPL → M-TEST → M-VERIFY → M-SECURITY → M-RELEASE → M-PUBLISH → M-MILESTONE`。每个transition记录ordinal、precondition refs、输入/输出artifact refs、evidence refs、Project Status snapshot和next capability。
6. 成功配置固定`security_audit="disabled"`；M-SECURITY仍产生`kind=stage-disabled`、`execution=disabled`、`result=passed` evidence并占一个ordinal，然后自动继续。M-RELEASE对wordcount执行真实project-local build；M-PUBLISH只把同digest artifact写入临时local publish sink，禁止GitHub/PyPI secret或公网；M-MILESTONE消费该publish evidence。
7. 完成后核对Louke模块从临时venv的installed wheel加载、wordcount源码/构建物只位于临时host、scenario/replay资产只位于独立control、Louke仓库tracked bytes/refs未变、无真实provider调用，并在`finally`停止server/子进程、删除venv/host/control/publish sink/HOME。清理无法确认时结果为attention且CI失败。

失败合同使用同一scenario schema的13个`fail_before_completion`变体，每个变体只在一个canonical stage的公开边界返回确定失败（Agent result、Human action、host command、enabled security stand-in、release build、local publish sink或milestone adapter），并从Project Status断言：current stage未越过、后续stage没有artifact/evidence、owner和合法recovery可达、同一WorkflowRun未产生平行run。pytest collection顺序锁定为`success`第一，其后依次为`fail-M-START`、`fail-M-STORY`、`fail-M-SPEC`、`fail-M-ACC`、`fail-M-REQ-APPROVAL`、`fail-M-DESIGN`、`fail-M-IMPL`、`fail-M-TEST`、`fail-M-VERIFY`、`fail-M-SECURITY`、`fail-M-RELEASE`、`fail-M-PUBLISH`、`fail-M-MILESTONE`；命令使用`--maxfail=1`，任一意外断言、setup或teardown失败立即停止并保留已产evidence。成功旅程使用Playwright覆盖Human主路径；13项失败矩阵可通过同一production HTTP/API脚本执行，但必须启动installed product并读取public Project Status，不能调用内部状态推进函数。

选择预录Replay Adapter而非修改现有echo mock：echo不能提供各角色output schema或任务identity，易把错误fixture误当Agent成功；选择本地publish sink而非真实GitHub/PyPI：它能证明artifact identity和stage接线，同时满足默认CI无secret/无公网。主要风险是fixture与prompt/schema漂移；scenario绑定Agent I/O schema、prompt bundle、task contract和result digest，任一变化使fixture stale并要求Shield重审。

## 6. Evidence、归因与持久化

每份RED/review/freeze/GREEN/surface/discrimination/coverage/closure evidence都使用`IF-EVIDENCE-01`最小identity envelope。JSON canonical digest采用UTF-8、sorted-key、compact separators；文件本身先写临时路径、fsync并原子rename。正式Runtime将摘要与artifact location append到现有SQLite workflow facts；大JUnit/coverage/trace保存在candidate evidence目录，Project Status只投影摘要和owning link。

最低identity：`schema_version,evidence_id,kind,qualification,validation_state,workspace_id,project_id,run_id,attempt_id,baseline_identity,candidate_identity,source_revision,test_revision,runner_identity,environment_identity,command,started_at,finished_at,result,reason,artifact_refs,evidence_digest`。`qualification=bootstrap_manual`或`validation_state=unvalidated`不得用于成功门禁。

失败归因顺序：

1. identity/collection/lifecycle/permission/污染不成立：`infrastructure_or_test_asset`，owner=Shield或Runtime owning adapter；
2. 测试断言可由current合同决定且真实代码不同：`implementation_or_composition`，owner=Devon；
3. 测试与current合同不同：`test_contract_mismatch`，owner=Shield，测试改动后重新审查冻结；
4. Architecture/Interfaces/adapter不足以决定或执行：`design_gap`，return=`M-DESIGN`；
5. Spec/Acceptance未决定产品结果：`requirement_gap`，return=`M-SPEC|M-ACC`；
6. 污染、恢复不确定、身份不一致：`safety_attention`，Runtime保持attention并阻止M-VERIFY。

需要语义判断时，Prism只返回绑定同一合同/test/candidate/runner的诊断；Runtime应用和持久化classification。Devon缺少合同锚点的争议不会自动改变状态，但合同未决定行为时同样不能默认Shield正确。

## 7. Project Status与人机交互

复用004的`/workbench?activity=projects&project=<id>`和`GET /api/projects/{project_id}/status`。`ProjectStatus.active`在M-IMPL/M-TEST时增加`atdd`投影：current checkpoint、九项checkpoint摘要、baseline/test/candidate/runner identity、最近evidence、owner、owning URL、合法primary action与`m_verify_allowed`。

- running：显示阶段仍为M-IMPL或M-TEST，同时以非颜色文本显示checkpoint、owner、attempt ordinal和elapsed；重复动作禁用。
- passed：显示current evidence identity及“完成”文本；仅全部闭合时出现`Continue to M-VERIFY`。
- failed/attention/cooldown：显示classification、影响、owner、return target与唯一恢复入口；不会跳到孤立页。
- stale/conflict：旧evidence明确标`stale/superseded`并只读；revision conflict显示current readback链接，不可重试旧action。
- disconnected：一次读取失败即显示stale；最后成功readback超过15秒同样禁用mutation。重连按current revision刷新，保留所选checkpoint/attempt；若已失效则显示原因而不静默切换Project。
- permission：无权限或历史Project保持只读，证据导航可见，mutation/action隐藏或disabled并有文本原因。
- dirty：Project Status本身无编辑字段，故用户dirty状态`N/A`；打开discussion/repair surface后的未提交输入由该既有surface负责，返回URL保留Project/attempt/checkpoint。
- 键盘：checkpoint条目是可聚焦button/link，Enter/Space打开详情，方向键/Home/End遍历，状态包含可访问文本/icon而非只用颜色；焦点在poll更新后保持。

前端不得从文件、Guide消息、Issue或URL猜`passed`；直接访问后续URL仍由Runtime current capability复核。详情/证据打开后使用same-origin `return_url`回到同一Project、attempt和checkpoint。

FR-1701不增加新页面：同一Project Status stage timeline显示13项canonical stage、同一WorkflowRun identity、transition ordinal和每项artifact/evidence摘要。当前stage action只在projection声明capability时可见/启用；失败显示owner与recovery且后续stage保持未进入。`M-SECURITY`禁用时必须以文本“Disabled / passed-through”及`stage-disabled` evidence呈现，不能隐藏该stage或只用颜色；到达`M-MILESTONE`后显示13/13及最终local publish artifact identity。浏览器重连、历史只读、stale/conflict和焦点保持沿用上述合同。

## 8. Prompt/capability candidate

闭合集合精确为：

```text
louke/agents/Archer.md
louke/agents/Shield.md
louke/agents/Devon.md
louke/agents/Prism.md
```

本轮source candidate要取代：Shield-after-implementation/`M-TEST`准备顺序、Shield/Devon自行commit/push、test-owned模块替换/罐头负样本、Devon“合同未写即默认测试正确”、Prism作为终局状态authority，以及hard-coded 7-kind registry对扩展kind的拒绝。保留已接受的Runtime authority、完整M-DESIGN bundle、最小权限、真实surface和CI合同。

确定性transformer继续使用现有`louke.board.cmd_opencode`所调用的`parse_frontmatter`、`_render_passthrough_block`和`_rewrite_agent_skill_references`规则；输入是canonical source bytes+role model binding，输出是`.opencode/agents/<lower-role>.md`等价bytes，但本轮只写入Spec-local staging record，不写active路径。四角色task/result使用program-owned candidate `schemas/agent-io-v014-005.schema.candidate.json`中的八个closed bindings，避免把旧002 Archer/Prism schema或machine-contract instance误当作005 Agent I/O schema；未激活时不得dispatch。现有`louke/_tools/prompt_bundle.py`validator/readback闭合集合仍只有Archer/Prism；Devon必须将其扩为上述四项，并保持拒绝任何第五项。candidate Prism source由先前trusted active Prism bundle审查，不能自审。source/transformer/model/schema/digest任一变化使render/review/readback stale。Runtime只有在Agent I/O schema、四项staging digest、独立review、wheel package readback及active pointer CAS全部current时原子激活；失败保持旧active bundle不变。

## 9. 技术选型与关键取舍

| 选择 | 解决的问题 | 放弃的替代 | 主要风险与缓解 |
|---|---|---|---|
| Python `>=3.11`、现有Starlette/SQLite | 继承真实Runtime/Web和安装态surface | 新服务、Node前端、第二数据库 | 现有模块历史包袱；以明确application边界、append-only evidence和integration约束 |
| 现有`run-project-venv`单runner | 保持宿主真实命令、wheel安装态和local/global矩阵 | 新`louke mutation`全局CLI、测试专用runner | runner变复杂；子命令闭合、evidence schema和兼容回归 |
| project-local Git worktree+patch semantic adapter | 稳定绑定AC/IF、隔离真实production mutation | `mutmut`随机operator、`sys.modules`替换、monkeypatch | patch可能stale；绑定source SHA/path/digest，应用失败为invalid且不能算kill |
| pytest `9.1.1`/pytest-cov `7.1.0`/Playwright `1.54.0` | 继承现有Python测试生态并固定当前可核对版本 | 切换unittest/Cypress | 仓库无lock；Devon实现完全解析的`tests/requirements-ci.txt`并让cache包含digest |
| Node `22.17.1`无依赖fixture | 证明语言/表面中立而不引入应用依赖 | 只用两个Python fixture、引入大型JS框架 | CI增加工具链；setup-node固定SHA且fixture无network install |
| production `OpenCodeAdapter`协议上的Replay Adapter | 无真实LLM仍让Runtime消费各角色schema-valid result并保留session/task identity | echo mock、测试直接写artifact/facts、真实provider | fixture易漂移；closed manifest绑定role/stage/task/schema/prompt/result digest且exact-once消费 |
| 临时Python wordcount宿主+local publish sink | 用低依赖无关业务证明13阶段、真实build/publish identity与空间隔离 | 在Louke仓库内生成示例、真实GitHub/PyPI、只回放状态 | 全旅程耗时；verified wheel复用、成功一次+逐stage fail-fast、90分钟专用job |
| JSON schema candidate registry v2 | 解除002 schema硬编码并给ATDD adapter program-owned schema | 从prompt/instance自证、继续使用002 const schema | 当前无active registry；全部candidate fail-closed，Runtime实现/独立review/readback后才原子激活 |
| Project Status内嵌checkpoint | 用户在同一Project/attempt看到可信证据 | 独立ATDD dashboard/后台only | 信息密度；active card摘要、详情按需、继承004导航和freshness |

不新增运行时第三方依赖。测试/CI直接工具固定：pytest`9.1.1`、pytest-cov`7.1.0`、pytest-asyncio`1.4.0`、Playwright`1.54.0`、build`1.5.0`、jsonschema`4.26.0`、packaging`26.2`、pre-commit`4.6.1`；hook环境继续由现有rev固定。Devon创建`tests/requirements-ci.in`和带hash的完全解析`tests/requirements-ci.txt`，其direct pins必须与本表一致；解析漂移需更新本设计而非临场升级。

## 10. 发布版本与artifact同步

本Spec不引入新的Human release version、tag语义或artifact种类；canonical package identity继续是`0.14.0`，外部表示继续是`releases/0.14.0`/`v0.14.0`。但005实现会进入Louke wheel/sdist和canonical prompt package，故CI仍必须验证真实artifact：

| Artifact | 权威版本/提取 | 安装/运行出口 |
|---|---|---|
| wheel `dist/louke-0.14.0-py3-none-any.whl` | `pyproject.toml`；wheel `.dist-info/METADATA: Version` | clean venv `lk --version`、`importlib.metadata.version("louke")`；四prompt和schema readback |
| sdist `dist/louke-0.14.0.tar.gz` | top-level `PKG-INFO: Version` | 从sdist构建wheel后同上 |

继续使用宿主已有`tools/louke_python_release_adapter.py`；Devon按004锁定合同补齐`prepare/verify-dist/verify-installed`，不得另选adapter。顺序固定为identity/source校验→真实build→逐artifact提取→compare 0.14.0→wheel/sdist安装态出口→prompt/schema package readback。缺失、多个artifact、版本不匹配、命令不支持、readback不确定均阻断publish。设计方案、source prepared、artifacts built、artifact versions verified四类evidence保持可辨；只有最后一类允许publish。

## 11. GitHub Actions CI合同

### 11.1 触发、runner、依赖与权限

Devon原地更新`.github/workflows/louke-ci.yml`，workflow名仍为`Louke CI`，不得新增同名required check。触发PR到`main`/`releases/**`、这些分支push、`v*` tag及manual。主job使用`ubuntu-22.04/Python 3.12/Node 22.17.1`；unit矩阵Python`3.11,3.12,3.13,3.14`；install矩阵保留Ubuntu/macOS/Windows与现有3.11—3.13。

默认`contents: read`，fork PR无secret且禁止`pull_request_target`。真实外部smoke仅tag/manual protected `release-smoke` environment；publish仅`release` environment并最小提升`contents:write`/PyPI token。005默认required jobs只使用stand-ins和合成credential。

所有action改为完整SHA：checkout`11d5960a326750d5838078e36cf38b85af677262`、setup-python`a26af69be951a213d495a4c3e4e4022e16d87065`、setup-node`49933ea5288caeca8642d1e84afbd3f7d6820020`、upload-artifact`ea165f8d65b6e75b540449e92b4886f43607fa02`、download-artifact`d3f86a106a0bac45b974a628896c90dbdf5c8093`、cache`0057852bfaa89a56745cba8c7296529d2fc39830`、action-gh-release`3bb12739c298aeb8a4eeaf626c5b8d85266b0e65`；YAML旁保留版本注释。cache key包含OS/Python/Node、`tests/requirements-ci.txt`、`pyproject.toml`和Playwright requirements digest；不缓存evidence、workspace facts或credential。

### 11.2 Job DAG与确定命令

```text
quality ──────────────────────────────────────────┐
design-contract ──────────────────────────────────┤
ac-trace ─────────────────────────────────────────┤
build-artifacts -> artifact-verify ───────────────┤
                -> unit matrix ───────────────────┤
                -> host-compat ───────────────────┤
                -> integration ───────────────────┤
                -> e2e-standin ───────────────────┤
artifact-verify -> full-lifecycle ────────────────┤
integration + e2e-standin -> atdd-discrimination ┤
build-artifacts -> install-matrix ────────────────┤
                                                   -> required
required + artifact-verify -> real-smoke -> publish  (tag/manual protected)
```

| Job | 必须执行的宿主入口 | 失败语义与证据 |
|---|---|---|
| `quality` | constraints安装；`pre-commit run --all-files` | 任一hook失败阻断；不运行合法RED required suites |
| `design-contract` | registry/instance validator、prompt closed-set/render parity validator；不增加FR-0101 declaration validator | missing/extra prompt、schema inactive冒充active、registry/instance/prompt digest未知均失败；声明质量由production collection/RED/review证明；JSON evidence 30天 |
| `ac-trace` | 现有`tools/check_ac_traceability.py`对001、004、005分别运行；005带`--expected-count 39`；另运行candidate `tools/check_atdd_assets.py` | 39/39 AC层绑定、每个required test反例、禁止skip/xfail/SUT替换；零测试或未知token失败 |
| `build-artifacts` | constraints安装；release场景先adapter prepare；`python -m build --wheel --sdist` | 恰好1 wheel+1 sdist；source SHA/version/digest evidence |
| `artifact-verify` | adapter `verify-dist`/`verify-installed`及wheel/sdist四prompt/schema/route package readback | 任一artifact/公开版本/prompt/schema/route缺失或不匹配失败 |
| `unit` | clean verified wheel；`python -m pytest -q tests/unit --cov=louke.runtime --cov-report=xml --cov-report=term-missing --cov-fail-under=95` | 全矩阵GREEN；JUnit/coverage；零收集失败 |
| `host-compat` | 运行005 integration中的Python Web host与Node CLI host profiles | 两套各自build/runner/surface/coverage/evidence均成功；使用错误默认adapter必须失败 |
| `integration` | `tests/e2e/run-project-venv integration` | 包含005路径，非零、全GREEN、无skip/xfail、production module+composition root动态证据；JUnit/JSON |
| `e2e-standin` | `tests/e2e/run-project-venv e2e --profile all --runtime both -m "not v014_005_full_lifecycle"` | wheel安装态+真实Chromium+production `create_app()`；显式排除full-lifecycle专用矩阵；失败trace/screenshot/server ledger |
| `full-lifecycle` | 下载verified wheel；执行§5.4专用命令，`success`后按13 stage顺序运行failpoint并使用`--maxfail=1` | 同一run严格13阶段、artifact/evidence传递、replay无真实provider、Human公开动作、disabled security、临时host/publish sink隔离与finally清理；lifecycle JSON、Project Status snapshots、browser trace |
| `atdd-discrimination` | `tests/e2e/run-project-venv atdd --phase post-green --spec v0.14-005-atdd-process-improvement --bundle tests/fixtures/v014_atdd_process_improvement/counterexamples.manifest.json --evidence atdd-discrimination.json` | 每个required changed behavior的目标断言kill、sandbox teardown、original digest不变、恢复后受影响及全量GREEN；survived/invalid/unknown失败 |
| `install-matrix` | 只安装同run verified wheel，复用`install.sh`/`install.ps1` | local/global `lk --version`及package/prompt/schema readback一致 |
| `required` | `if: always()`聚合以上全部mandatory needs | job名`required`，稳定check`Louke CI / required`；failure/cancel/timeout/skipped/missing/unknown任何一个都非成功 |
| `real-smoke` | **仅在Devon实现runner对应子命令后**使用`tests/e2e/run-project-venv real-smoke --profile v014 --runtime local` | 真实OpenCode/GitHub sandbox且teardown；命令未实现即release path失败，不得保留假合同 |
| `publish` | 只消费build-artifacts产生且artifact-verify验证的同digest wheel/sdist | 不重新build；required/smoke/identity/prompt/schema readback任一非current阻断 |

Timeout：quality/ac-trace/design 15分钟；build/artifact/unit 20分钟；host-compat/integration 25分钟；e2e/install 35分钟；discrimination 45分钟；full-lifecycle 90分钟；real-smoke 60分钟；required 5分钟。required测试不自动rerun；Runtime显式重试产生新attempt/evidence，旧结果保留。

## 12. Machine-contract、候选激活与实现交接

project-local candidates位于`.louke/project/contracts/v0.14-005-atdd-process-improvement/`。program-owned registry candidate必须包含通用v2 machine-contract envelope、本轮16个required kinds，以及独立的四角色Agent I/O schema及八个role/direction bindings；FR-1701由`e2e-test`、`host-required-test`和`atdd-fixture`实例闭合，不新增无上游授权的kind。machine instance只引用v2 schema identity/version/digest，不内嵌schema。当前状态始终是`candidate-not-installed`，bootstrap/manual validation只可记录`unvalidated`或`candidate-check`，不能写PASS。

激活前置：Devon实现registry resolver/validator、runner/semantic adapter、Replay Agent Adapter、prompt transformer和CI入口；不要求已从FR-0101移除的声明validator。schema meta-validation与正/负fixture均符合；39/39 AC和全部interface闭包；真实wheel/sdist package/readback；full-lifecycle success+13 failpoint evidence；先前trusted active Prism独立审查完整candidate；Runtime原子安装project instances、prompt和registry pointer并readback。任一partial/stale/unknown保持旧active不变并返回`SCHEMA_NOT_ACTIVE`，不得建立正式implementation baseline或派发Shield。

在bootstrap语义层，技术选择、签名、route、runner、fixture、adapter、evidence、测试层和CI均已确定，Shield与Devon无需再选择产品行为或工具；但正式Runtime dispatch仍因active schema/validator尚未部署而fail closed。这一区分不是设计缺口，也不构成gate通过声明。
