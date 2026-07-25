# 契约测试先行与真实交付表面验证 — 需求规格

- **规格 ID**：`v0.14-005-atdd-process-improvement`
- **关联 Story**：`STR-1406`
- **Story SHA-256**：`254eb9c753a424275233af446721ca7d18851e1851de392c738858b2b2879a70`
- **Spec SHA-256**：`f1e29c404775240b820b767df1a450962a291d2c9a0ee2644e067663baccd05d`
- **Acceptance SHA-256**：`cff523caa12f2d587adabe8a9b2afda260fb8b62ab58c81beb59b6b95ddf9a4d`
- **创建日期**：2026-07-25
- **锁定时间**：`2026-07-25T11:25:00+09:00`
- **状态**：已锁定（v0.14 bootstrap 的人工/Sage 锁定；未伪造 Runtime digest、PASS、commit、gate 或阶段推进）

> **职责边界**：本文只描述需求本身。用户目标、完整主路径与推导依据见`story.md`；可观察断言由后续`acceptance.md`定义。
>
> **产品集成位置**：本能力接入既有`M-DESIGN → M-IMPL → M-TEST → M-VERIFY`旅程和Project Status上下文，不新增平行工作流或孤立结果页。为保持v0.14 canonical stage identity，Shield的契约测试准备成为`M-IMPL`内、Devon实现前的受控checkpoint；`M-TEST`负责真实实现上的最终integration/e2e、判别与覆盖闭包。
>
> **v0.14 bootstrap说明**：当前Agent提示词可能已部分采用v0.14职责，但完整Runtime尚未激活。本草稿先锁定语义合同，不把尚未部署的schema、命令、程序校验或阶段状态写成现有事实。Human明确委托Agent临时代行的文档工作可以继续；缺少Runtime machine contract的程序结果只能标记为bootstrap/manual、未程序校验或未激活，不得伪造PASS、commit、gate或阶段推进。
>
> **锁定说明**：本轮锁定的spec.body 与lex r3评审结果一致，未修改行为种子或非常规要求；Story/Acceptance的SHA-256在locked frontmatter登记，可被Project Status和M-DESIGN readback引用。Runtime启用后，digest、activation、review verdict与阶段推进由Runtime自有程序合同重新接管。

## 功能需求

### FR-0001 接入现有实施与验证旅程

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- **来源**：`§3.1` / `BS-02` / `§4.2`
- **交付入口**：Project Status中当前Project的`M-IMPL`、`M-TEST`与`M-VERIFY`状态及其evidence/readback

Runtime必须在当前M-DESIGN baseline建立后，先完成接口声明、Shield契约测试准备、有效RED与独立审查，再允许Devon实施；真实实现通过最终integration/e2e和判别闭包后才可进入M-VERIFY。该顺序必须复用当前Project、WorkflowRun、attempt和canonical stage identity，不得建立第二套ATDD workflow、平行Project或孤立测试结果页。

---

### FR-0101 同路径接口声明骨架

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- **来源**：`BS-01` / `D-01` / Human明确澄清
- **交付入口**：M-DESIGN baseline中的接口声明清单、宿主项目目标真实模块路径及对应源码readback

Archer必须针对当前需求新增或改变、且integration需要导入或编译的宿主生产接口，在目标真实模块同路径产出符合宿主语言惯例的声明骨架。骨架只可包含当前Architecture/Interfaces所必需的signature、type、protocol、trait、公开入口声明或等价结构，不得包含业务逻辑、成功罐头值、绕过真实依赖的替身行为或足以把验收变为GREEN的实现。既有模块只增加必要声明，不得以重建文件覆盖无关宿主代码。

接口声明进入 M-DESIGN baseline 后，桩质量由下游流程验证：Shield 的契约测试必须 import 桩并经过真实 production 入口 collection，签名/路径/token 错误在 collection 或 RED 阶段即暴露；Devon 替换行为体时若签名不可达或与宿主 composition 冲突，必须通过 FR-0201 的 declaration revision 返回；争议由 Prism 对同一合同、桩和测试 revision 独立裁决。bootstrap 阶段可继续语义评审，但结果标记为未程序校验，不据此建立正式 implementation baseline。

---

### FR-0201 声明合同冻结与实现区域可写

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- **来源**：`BS-01` / `D-01`
- **交付入口**：同FR-0101；M-IMPL task manifest中的声明identity与Devon write scope readback

Runtime必须将接口声明的路径、合同锚点和设计revision纳入implementation baseline并阻止Devon擅自改变公开合同，同时向Devon明确授权在同一宿主模块补全实现。声明修订必须形成新的设计identity并使依赖旧声明的测试、review与实现证据stale；正常实现填充不得被误判为修改冻结测试或越权修改设计。

Devon在授权实施范围内若发现声明不可达、无法在宿主真实模块实现，或与宿主运行时/production composition冲突，必须通过绑定当前baseline和具体合同锚点的独立discussion/return发起声明修订请求，不得私改声明或冻结测试。Runtime收到请求后必须停止继续消费当前冻结包，使冻结测试进入cooldown，并把依赖当前声明的旧RED、测试审查与实现证据标记stale；只有声明新identity重新通过FR-0101检查，并依照FR-0701完成有效RED和Prism审查后，才可重新派发Devon。

---

### FR-0301 Shield先于Devon编写契约测试

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- **来源**：`BS-02` / `§3.1`
- **交付入口**：宿主项目design指定的integration/e2e测试路径及Project Status中的测试准备attempt

在任何依赖这些测试的Devon业务实现开始前，Runtime必须依据当前Test Plan和宿主project-local运行合同派发Shield。Shield只可在授权的宿主测试资产范围编写required integration/e2e，并为每个测试绑定AC/接口、目标公开表面、required layer和初始预期。分类必须以当前M-DESIGN baseline相对上一有效baseline的requirements/design delta为依据：绑定本baseline新增或发生语义变化的AC、接口或交付表面的测试属于新增/改变行为并可要求RED；只绑定本baseline明确继承且语义未变合同的测试属于回归行为并允许保持GREEN。测试文件创建时间本身不决定分类，也不得为制造全红而降低既有正确行为。

---

### FR-0401 真实生产入口与SUT不可替换

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- **来源**：`BS-03` / `§4.1` / `D-02`
- **交付入口**：同FR-0301；测试执行记录中的production surface identity

Integration必须导入、启动或调用宿主项目真实public package、production composition root或跨模块公开接口；e2e必须从当前Test Plan声明的最终用户/调用者表面执行。测试不得自行构造替代production route table、mock app、替换模块、自动失效stub或罐头SUT来满足验收。外部进程、服务、网络、时钟或存储适配器只有在Test Plan明确划出SUT边界并规定可控替身时才可替换，且替换不得绕过宿主应用与真实接线。

本需求适用于页面、HTTP/API、CLI、public library及宿主设计声明的其它表面；不得因为004问题发生在HTTP route而把Web框架变成所有宿主项目的前提。

---

### FR-0501 行为断言而非形状代验收

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- **来源**：`BS-02` / `§4.1` / v0.14-004实施复盘
- **交付入口**：同FR-0301；测试结果中的AC/接口锚定断言

每个required integration/e2e必须经公开刺激产生并断言合同规定的可观察结果，适用时还必须通过公开readback、持久状态、artifact、event或外部adapter ledger证明实际后果。属性、字段、类型、selector或symbol存在检查可作为schema/可达性补充，但不得单独作为行为AC的完成证据；测试通过调用同一实现计算expected与actual、`assert true`或等价同义反复也不得计入覆盖。

---

### FR-0601 有效RED与反例绑定

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- **来源**：`BS-02` / `BS-05` / `D-03`
- **交付入口**：Project Status中的pre-implementation test evidence及宿主runner的规范化结果

对初始预期为RED的测试，Runtime必须区分目标行为缺失与测试基础设施损坏。有效RED必须绑定当前AC/接口和预期失败类别，并由测试断言、精确缺失的已设计public symbol/interface、或宿主工具链可定位的等价合同差异产生；零收集、无关import/compile错误、fixture/setup失败、服务生命周期失败、缺失依赖、权限错误或未声明skip/xfail不得作为有效RED。

Shield还必须为每个新增或改变的required契约测试绑定至少一个具体、只偏离目标合同的反例。在当前M-DESIGN machine contract锁定的宿主mutation/负样本adapter和Test Plan支持安全替换或注入错误行为时，反例必须以可执行负样本存在；Shield须在提交前于隔离进程或等价沙箱运行目标测试，并证明测试完成收集后因绑定的目标断言而FAIL，不能以任意非零退出、基础设施ERROR或无关测试失败自证。只有该machine contract已明确判定当前目标无法安全执行负样本时，才可退化为描述性反例并由Prism审查；冻结证据必须引用该判定及其identity，而不能由Shield在测试准备时临时认定不支持。退化不得免除FR-1101在真实candidate GREEN后的mutation或等价判别闭包。实现前反例无论采用哪种形式，都不得代替真实SUT上的GREEN。

---

### FR-0701 冻结前独立测试审查

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- **来源**：`BS-02` / `BS-05` / `§3.1`
- **交付入口**：Project Status中的Shield test patch、RED evidence与Prism review readback

Runtime必须保存并绑定当前baseline的Shield测试patch、可执行负样本或描述性反例、适用的Shield自检结果、初始执行结果和宿主runner identity，再由Prism独立审查测试是否忠于Spec/Acceptance/Interfaces、使用正确required layer、经过真实生产入口、断言行为而非形状、且反例针对目标偏差。只有同一测试revision的程序证据和Prism审查均成立，Runtime才可冻结测试资产并派发Devon；采用描述性退化时，冻结记录还必须引用当前M-DESIGN machine contract中无法安全执行负样本的判定及其identity。接口声明升级必须使依赖旧声明的测试、旧RED和旧审查一并stale；新声明对应的测试必须重新经过有效RED检查和Prism审查。任何测试或负样本变化都必须产生新identity并使旧审查失效。

---

### FR-0801 Devon获得完整且一致的实施包

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- **来源**：`BS-03` / `§3.1` / `§4.1`
- **交付入口**：M-IMPL task readback与关联的权威输入清单

Runtime派发Devon时必须提供绑定同一baseline的Story、Spec、Acceptance、Test Plan、Architecture、Interfaces、接口声明、冻结测试与反例identity、宿主integration/e2e运行合同、目标AC/Issue、production surface和write/forbidden scopes。GitHub Issue只可作为追踪句柄，不得替代上述实施包；输入缺失、互相矛盾或revision不一致时不得要求Devon临场补设计或猜测产品政策。

---

### FR-0901 真实实现与production composition接线

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- **来源**：`BS-03` / `D-02` / v0.14-004实施复盘
- **交付入口**：宿主项目声明的页面/API/CLI/public library等生产交付表面

在满足FR-0401真实生产入口与SUT不可替换约束的前提下，Devon必须在授权宿主生产代码范围内补全接口声明对应的真实行为，并把该行为接入宿主项目实际production composition root和声明的最终交付表面。内部模块可导入、类或属性存在、直接调用内部函数通过、声明骨架可编译或测试专用app通过，均不能替代真实接线。接口声明中的未实现占位、501/todo/panic或语言等价物在最终candidate适用路径中不得作为成功行为残留。

本契约不取代Devon既有unit/contract RGR；unit RED/Green仍可在task内执行，但不能替代预先冻结的required integration/e2e责任。

---

### FR-1001 M-IMPL退出的宿主测试门禁

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- **来源**：`BS-04` / `§3.1`
- **交付入口**：Project Status中的M-IMPL完成检查和宿主`project.toml`运行合同对应结果

Devon实施完成后，Runtime必须按当前宿主项目已锁定的integration/e2e运行合同执行required suites，不得硬编码Python、pytest、Web或Louke仓库自身命令。只有required测试非零收集、全部GREEN、无未授权skip/xfail、运行环境与目标candidate一致，并且目标真实生产模块和交付表面具有动态执行证据时，M-IMPL的实现部分才可完成。单个局部selector、Agent自报或仅非零覆盖率不得替代该门禁。

---

### FR-1101 Post-GREEN语义判别与覆盖闭包

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- **来源**：`BS-05` / `D-03` / `D-05`
- **交付入口**：M-TEST evidence、宿主mutation/等价判别报告及production surface执行报告

M-DESIGN必须依据宿主项目事实，把宿主mutation/负样本adapter的选型、适用required行为、安全执行能力和不支持判据锁定为project-local machine contract；该合同的identity必须随Test Plan和运行合同交付，Shield不得在测试准备时自行选择、替换或宣布adapter不适用。合同缺失、未覆盖目标行为或判定不确定时，不得以描述性反例替代本可执行的负样本，也不得把缺少adapter本身视为宿主工具链不支持的证据。

真实candidate全量GREEN后，Runtime必须按上述M-DESIGN machine contract和当前宿主项目设计的能力，对每个required新增或改变行为执行与已绑定反例等价的语义mutation或其它可验证判别检查。只有目标测试从GREEN变为与该合同偏差对应的断言失败才算识别错误；collection、import、build、启动、fixture或无关测试失败不得计为kill。检查结束后必须恢复同一candidate并重新证明required suites全量GREEN。

M-TEST还必须闭合每个required AC到observable interface、required layer、测试、真实production surface、执行结果和适用mutation evidence的映射。目标真实模块没有动态执行证据或可测覆盖为0时必须失败；非零覆盖只能作为最低安全网，不能替代行为和表面接线证据。

---

### FR-1201 用户可见的完成、继续与返回

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- **来源**：`§3.1` / `§3.2` / `D-06`
- **交付入口**：Project Status当前attempt、测试/实现详情及M-VERIFY继续动作

Project Status必须让Human从同一Project上下文识别当前处于接口声明、Shield测试准备、RED/review、Devon实现、真实GREEN、M-TEST判别闭包或attention状态，并能查看绑定当前revision的关键证据和owning surface。M-DESIGN必须把这些evidence的用户可见projection、状态来源、所属对象、owning link以及继续/返回关系纳入既有Project Status接口设计；具体字段组织和布局由后续设计决定，但不得只保留后台记录而没有用户可达结果。全部合同闭合后，用户可从同一上下文继续M-VERIFY；失败或取消不得跳到孤立结果页，也不得丢失当前Project、测试identity或合法恢复位置。

---

### FR-1301 测试、实现与合同缺陷分流

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- **来源**：`BS-06` / `§3.2` / `D-04` / `D-06`
- **交付入口**：Project Status中的failure classification、owner与return target

当冻结测试未在真实实现上通过或Devon提出争议时，Runtime必须保留测试、candidate、runner和合同identity，并按以下语义分流：测试或fixture与当前合同不符返回Shield；测试符合合同而代码或production接线不同返回Devon；Architecture/Interfaces不足返回M-DESIGN；Spec/Acceptance未决定产品结果时返回Human控制的M-SPEC/M-ACC路径。需要语义判断时由Prism对同一合同、测试和代码revision提供独立审查，Runtime负责持久化和正式路由。

Devon若主张测试错误，必须引用具体合同条款；在合同已明确覆盖且测试已通过当前审查时，缺少相反依据不能成为skip或修改测试的理由。合同没有决定行为时则必须fail closed并返回上游，不得默认Shield测试成为新的产品需求。

---

### FR-1401 修订、重试与证据失效传播

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- **来源**：`§3.2` / `§4.1`
- **交付入口**：同FR-1301；Project Status历史attempt与current baseline readback

Shield修订测试必须重新经过有效RED/判别检查、Prism审查和冻结；Devon修订实现必须重跑受影响unit、integration/e2e及最终required闭包；设计或产品合同修订必须产生新baseline。声明、测试、实现、runner或上游合同identity变化时，依赖旧identity的review、GREEN、mutation、覆盖、candidate和继续动作必须标记stale/superseded，历史保留且不得被新结果静默覆盖。重试只能从对应责任方和合法恢复位置继续。

---

### FR-1501 Pre-commit与CI职责边界

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- **来源**：`§4.1` / `§4.3` / 005备忘录
- **交付入口**：宿主项目pre-commit readback、Louke托管required CI及Project Status gate evidence

Louke不得要求尚处于合法RED的新增integration/e2e在普通pre-commit阶段先GREEN。Louke管理的pre-commit增量应限于当前阶段适用的快速格式、lint、类型、trace或等价静态/合同检查，同时保留并合并宿主项目既有且不冲突的hook政策；不得无故移除宿主自有快速测试。真实integration/e2e、surface、mutation和覆盖闭包必须由Runtime实施门禁及Louke托管CI对同一candidate执行，pre-commit成功不得替代它们。

---

### FR-1601 Runtime、Agent Prompt与bootstrap迁移

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- **来源**：`BS-07` / `§4.2` / `D-06` / Human当前阶段说明
- **交付入口**：当前Project的active prompt/capability readback、Runtime dispatch evidence及bootstrap标识

005必须同步更新并对齐未来Runtime编排和受影响Agent职责：Archer可在精确授权下写宿主同路径声明骨架但不得实现业务；Shield在Devon前写并审查required integration/e2e且不得用SUT替身换GREEN；Devon补全实现和production接线但不得改冻结测试；Prism只返回绑定identity的独立语义审查；Runtime负责程序检查、冻结、执行、状态和路由。激活前，Runtime必须记录受影响canonical prompt/Agent contract的source identity、revision/digest、已经接受的v0.14语义及被取代规则，并通过对应supersession/readback明确取代Mode B stub/activation skip及Shield-after-implementation旧顺序；兼容修改必须保留，不得盲目覆盖为旧模板。

在完整Runtime启用前，Human明确要求的bootstrap代行只允许完成人类可读artifact或当前Agent权限明确允许的操作；结果必须与未来Runtime正式evidence区分。bootstrap期间缺少schema或validator不能阻止本Spec的语义评审，但不能据此宣告machine contract、gate或阶段已经通过。

---


### FR-1701 全阶段生命周期端到端验证

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- **来源**：v0.14 覆盖缺口分析 / Human 明确要求
- **交付入口**：临时目录中独立 wordcount 宿主项目上的完整 M-START → M-MILESTONE 工作流执行记录及 Project Status 投影

Louke 必须提供一个确定性端到端测试，在临时目录中创建一个与 Louke 自身功能无关的 wordcount 宿主项目，安装 Louke wheel，并以预录 Agent 输出驱动完整 13 阶段工作流（M-START → M-STORY → M-SPEC → M-ACC → M-REQ-APPROVAL → M-DESIGN → M-IMPL → M-TEST → M-VERIFY → M-SECURITY → M-RELEASE → M-PUBLISH → M-MILESTONE）。

测试验证阶段衔接、状态流转、artifact 绑定、证据传递和 Project Status 投影的正确性，不验证 Agent 语义输出质量。Agent 输出（Scribe story.md、Sage spec/acceptance、Lex 格式验收、Archer 设计三件套与接口桩、Shield 测试与反例、Devon 实现、Prism 审查）使用预录 fixture，不依赖真实 LLM provider。Human 交互（确认、Go 决策、批准、发布审批）通过浏览器或 API 脚本驱动。

wordcount 宿主项目位于系统临时目录，测试结束后清理；Louke 生产代码和测试代码不得混入 wordcount 项目。默认禁用的阶段（如 `security_audit = "disabled"` 时的 M-SECURITY）视为自动 pass-through，测试记录 disabled 证据后继续推进，仍计为经过该阶段。

---

## 非功能需求

### NFR-0001 宿主技术栈中立

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- **来源**：`BS-07` / `§4.1` / `D-02`

Louke内部Runtime、CLI和prompt实现可使用Python，但接口声明形式、测试框架、runner、build、coverage、mutation和交付表面必须来自当前宿主项目事实与M-DESIGN合同。Louke不得通过文件后缀猜测并强制选择宿主模块替换机制，也不得要求非Python或非Web宿主引入Python/pytest/Starlette语义来满足005。

---

### NFR-0101 Louke与宿主空间隔离及最小权限

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- **来源**：`BS-07` / `§4.1`

Louke工具实现与canonical prompts、宿主项目内`.louke`合同/证据、宿主生产源码、宿主测试资产和宿主CI配置必须具有可辨identity和独立write scope。Archer、Shield、Devon、Prism及bootstrap代行均不得借当前任务跨空间修改无关资产；测试fixture、mutation sandbox和外部stand-in不得读取或覆盖宿主真实credential、用户HOME或Louke仓库自身状态来制造结果。

---

### NFR-0201 证据完整性与可复现性

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- **来源**：`BS-04` / `BS-05` / `D-05` / `D-06`

RED、Prism review、冻结测试、GREEN、surface执行、mutation、coverage和最终candidate evidence必须绑定可核对的需求/design、宿主runner、源码/测试revision及执行环境identity。失败、取消、超时、零收集、缺失报告、解析不确定或identity不一致不得记为成功；相同输入的重试应保留旧attempt并产生可追溯的新结果，不得覆盖历史。

完整Runtime identity schema尚未部署时，M-DESIGN必须把本次流程所需的最小identity字段集合锁定并写入当前project-local `.louke/project/contracts/**`；由bootstrap/manual产生但尚未通过程序校验的identity和evidence必须明确标记为未程序校验，不得据此宣告machine contract、gate或阶段成功。

---

### NFR-0301 安全隔离与恢复

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- **来源**：`§3.1` / `§3.2` / `§4.1`

反例和post-GREEN mutation必须在可恢复的隔离环境中运行，不得污染当前candidate、release branch、宿主生产数据或外部真实资源。无论检查成功、失败、中断或Runtime重启，系统都必须能确认或恢复原candidate后再运行最终GREEN；结果不确定时保持attention并阻止M-VERIFY，不得将可能仍被变异的工作区作为候选。

---

## 澄清记录

- **2026-07-25 — Human**：005描述未来行为；Louke自身使用Python，但宿主项目语言不定，必须持续区分Louke空间与宿主项目空间。
- **2026-07-25 — Human**：Archer应在宿主真实模块同路径产出源文件，但只声明必要接口、不作具体实现；integration可以且通常需要导入真实生产代码。
- **2026-07-25 — Sage推导**：为保持v0.14已锁定的13个canonical stage identity，不新增ATDD顶级阶段；把Shield测试准备放入M-IMPL中Devon之前，把M-TEST保留为真实实现上的integration/e2e、mutation和覆盖闭包。
- **2026-07-25 — Sage推导**：备忘录“无法引用合同则默认测试正确”只适用于合同已明确覆盖且测试已通过当前独立审查的争议；合同未决定产品行为时必须返回上游，测试不能补写产品需求。
- **2026-07-25 — Human当前阶段说明**：完整Runtime尚未激活，可适度放宽未部署schema的程序校验，并允许Human明确要求的临时代行；本Spec据此区分bootstrap/manual结果与未来正式Runtime evidence，不生成流程PASS。
- **2026-07-25 — Review findings**：可执行负样本在宿主工具链可行时恢复为Shield提交前自检；不支持时才退化为描述性反例，并保留post-GREEN真实判别门禁。接口声明新增进入Shield前的程序化一致性检查；RED/GREEN初始分类绑定当前requirements/design delta而非测试文件时间；Project Status evidence projection明确成为后续M-DESIGN交付责任。
- **2026-07-25 — Review findings R2**：Devon主动发现声明不可达时通过独立discussion/return请求声明升级，旧RED、测试与审查进入cooldown/stale后重新闭环；可执行负样本的能力与adapter由M-DESIGN machine contract锁定，不再由Shield临时判定；production接线显式继承FR-0401；prompt supersession和bootstrap identity边界补充可追溯要求。
- **2026-07-25 — Sage推导（bootstrap路由）**：完整Runtime尚未启用时，FR-1301中的Prism合同缺口diagnostic由bootstrap代行转化为Sage/Human可达的M-SPEC/M-ACC入口，并把当前attempt标记为blocked/stale，直到上游合同修订完成；该说明不改变未来Runtime的永久合同。
