# 契约测试先行与真实交付表面验证 — Acceptance Criteria

- **Spec ID**：`v0.14-005-atdd-process-improvement`
- **关联 Story**：`STR-1406`
- **Story SHA-256**：`254eb9c753a424275233af446721ca7d18851e1851de392c738858b2b2879a70`
- **Spec SHA-256**：`f1e29c404775240b820b767df1a450962a291d2c9a0ee2644e067663baccd05d`
- **Acceptance SHA-256**：`cff523caa12f2d587adabe8a9b2afda260fb8b62ab58c81beb59b6b95ddf9a4d`
- **创建日期**：2026-07-25
- **锁定时间**：`2026-07-25T11:25:00+09:00`
- **状态**：已锁定（v0.14 bootstrap 的人工/Sage 锁定；Runtime启用后由Runtime重新接管digest与review verdict）

> 本文是当前`spec.md`中17项FR与4项NFR的验收注册表。每项验收通过Project Status、artifact/readback、Runtime持久状态、宿主runner结果或可核对的外部事实断言，不约束未被Spec决定的组件、精确文案、内部API schema或实现算法。
>
> 当前调用未提供Runtime计算的Story/Spec revision digest；本锁定以本地SHA-256作为可核验快照登记frontmatter，不据此伪造PASS、gate或阶段推进。完整Runtime启用前的结果仍受Spec中的bootstrap边界约束。

## FR-0001 接入现有实施与验证旅程

### AC-FR0001-01
- 从当前Project的Project Status进入`M-IMPL`时，同一WorkflowRun和attempt依次可核对当前M-DESIGN baseline、接口声明、Shield测试准备、有效RED和Prism审查；上述current evidence未全部成立前，Devon不会获得实施派发。
- Devon完成真实实现后，只有同一candidate通过required integration/e2e以及`M-TEST`判别和覆盖闭包，Project Status才提供进入`M-VERIFY`的继续动作。

### AC-FR0001-02
- 整个旅程继续使用既有`M-DESIGN → M-IMPL → M-TEST → M-VERIFY`canonical stage identity，不创建第二套ATDD WorkflowRun、平行Project或孤立测试结果页。
- 任一步失败、取消或证据失效时，用户仍停留在同一Project并能看到责任方、失败checkpoint和合法返回位置；系统不会跳过未闭合步骤进入`M-VERIFY`。

## FR-0101 同路径接口声明骨架

### AC-FR0101-01
- 对当前需求新增或改变且integration需要导入/编译的每个生产接口，M-DESIGN readback可核对声明骨架位于宿主目标真实模块路径，并与当前Architecture/Interfaces所需signature、type、protocol、trait、公开入口或语言等价结构一致。
- 检查声明patch时，既有无关宿主代码保持不变，声明区域不含业务逻辑、成功罐头值、绕过真实依赖的替身行为或足以使行为验收GREEN的实现。

### AC-FR0101-02
- 接口声明进入 baseline 后，Shield 测试 collection 可核对桩位于宿主目标真实模块路径、签名/路径/token 与 Interfaces 一致；签名不符、路径错误或 token 缺失时 collection 失败或 RED 不可归因，Shield 不会产出有效测试资产。
- Devon 实现时若签名不可达或与宿主 production composition 冲突，当前实施不能完成，必须通过绑定合同锚点的 declaration revision 返回；bootstrap 语义评审可以继续，但结果明确显示未程序校验。

## FR-0201 声明合同冻结与实现区域可写

### AC-FR0201-01
- M-IMPL task readback可核对冻结声明的路径、合同锚点、设计revision和Devon write scope；Devon可在同一宿主模块授权区域补全实现，而正常实现填充不会被报告为修改冻结测试或越权修改设计。
- Devon直接改变冻结公开声明或冻结测试时，当前实施不能完成；合法声明修订会产生新设计identity，并使依赖旧声明的测试、review和实现证据显示为stale。

### AC-FR0201-02
- Devon在实施中发现声明不可达、无法在真实模块实现或与宿主运行时/production composition冲突时，可从当前task以绑定baseline和合同锚点的独立discussion/return提出声明修订请求，而无需等待测试失败或私改合同。
- Runtime接受该请求后，当前冻结包不再可供Devon继续实施，冻结测试显示cooldown，旧RED、测试审查和实现证据显示stale；只有新声明identity通过FR-0101检查并重新取得有效RED和Prism审查后，Devon才会收到新的实施包。

## FR-0301 Shield先于Devon编写契约测试

### AC-FR0301-01
- Devon业务实现开始前，宿主design指定的测试路径中已有Shield提交的required integration/e2e；每个测试可核对绑定的AC/接口、目标公开表面、required layer和初始预期，且测试patch位于Shield授权范围。
- 缺少Test Plan、project-local运行合同、任一required绑定或授权测试路径时，Runtime不派发Devon，也不要求Shield或Devon临场补产品/设计政策。

### AC-FR0301-02
- 对当前M-DESIGN baseline相对上一有效baseline新增或语义变化的AC、接口或交付表面，测试分类显示为新增/改变行为并使用相应初始预期；对baseline明确继承且语义未变的合同，回归测试可保持GREEN。
- 仅改变测试文件创建时间不会改变分类；系统不会为了制造全红而把继承未变的正确行为降级或改写。

## FR-0401 真实生产入口与SUT不可替换

### AC-FR0401-01
- 每个required integration可从执行证据核对其导入、启动或调用宿主真实public package、production composition root或跨模块公开接口；每个required e2e从Test Plan声明的最终用户/调用者表面执行。
- 页面、HTTP/API、CLI、public library或其它宿主表面均按各自设计合同识别production surface，不以HTTP/Web框架作为非Web宿主的前提。

### AC-FR0401-02
- 使用测试自建production route table、mock app、替换模块、自动失效stub或罐头SUT获得GREEN时，该结果不会被接受为required integration/e2e证据。
- Test Plan明确划出SUT边界的外部进程、服务、网络、时钟或存储adapter可以受控替换；若替换绕过宿主应用或真实接线，同样不能通过本验收。

## FR-0501 行为断言而非形状代验收

### AC-FR0501-01
- 每个required integration/e2e都可追溯到公开刺激及合同规定的可观察结果；合同包含持久化、artifact、event或外部副作用时，测试还通过公开readback、持久状态、artifact、event或adapter ledger断言实际后果。
- 仅检查属性、字段、类型、selector或symbol存在的测试不能单独闭合行为AC；使用同一实现同时计算expected与actual、`assert true`或其它同义反复的测试不计入required覆盖。

## FR-0601 有效RED与反例绑定

### AC-FR0601-01
- 对初始预期为RED的required测试，pre-implementation evidence显示测试已完成收集，并因绑定AC/接口的目标断言、精确缺失的已设计public symbol/interface或宿主工具可定位的等价合同差异而失败；记录的失败类别与预期一致。
- 零收集、无关import/compile错误、fixture/setup或服务生命周期失败、缺失依赖、权限错误以及未声明skip/xfail均不能形成有效RED或解锁Devon派发。

### AC-FR0601-02
- 每个新增或改变的required测试都绑定至少一个只偏离目标合同的具体反例；当M-DESIGN machine contract声明当前行为支持安全adapter时，Shield提交前的隔离执行显示目标测试完成收集并因该合同断言而FAIL，而不是仅出现任意非零退出或基础设施ERROR。
- 只有current M-DESIGN machine contract明确记录当前目标无法安全执行负样本时，冻结记录才接受描述性反例，并可核对该判定及identity；Shield临时声称不支持、缺少adapter或无权威判定时不能退化。无论采用哪种反例，实现前证据都不会被当作真实SUT上的GREEN。

## FR-0701 冻结前独立测试审查

### AC-FR0701-01
- Project Status可查看绑定同一baseline和测试revision的Shield测试patch、反例、适用自检、初始执行结果、runner identity及Prism审查；审查覆盖合同忠实度、required layer、真实生产入口、行为断言和反例针对性。
- 只有同一测试revision的程序证据和Prism审查均current时，测试资产才显示冻结并可派发Devon；修改测试或反例后会产生新identity，旧审查不能继续解锁实施。

### AC-FR0701-02
- 使用描述性反例时，冻结记录引用current M-DESIGN machine contract中的不支持判定和identity；引用缺失、stale或不适用于目标行为时不能冻结。
- 接口声明升级后，依赖旧声明的测试、RED和审查均显示stale；新声明对应测试重新通过有效RED检查和Prism审查后，才形成新的current冻结记录。

## FR-0801 Devon获得完整且一致的实施包

### AC-FR0801-01
- Devon的M-IMPL task readback可核对同一baseline下的Story、Spec、Acceptance、Test Plan、Architecture、Interfaces、接口声明、冻结测试与反例identity、宿主运行合同、目标AC/Issue、production surface及write/forbidden scopes。
- 任一权威输入缺失、互相矛盾或revision不一致时，task保持阻塞并指出冲突输入；仅提供GitHub Issue句柄不会被视为完整实施包，Devon也不会被要求临场补设计或猜测产品政策。

## FR-0901 真实实现与production composition接线

### AC-FR0901-01
- 在满足FR-0401的真实SUT约束下，Devon完成后的candidate从宿主实际production composition root和声明的最终页面/API/CLI/public library或等价表面可观察到接口对应行为。
- 只证明内部模块可导入、类/属性存在、直接内部调用通过、声明可编译或测试专用app通过，不能完成该需求；最终candidate适用路径中仍有未实现占位、501/todo/panic或语言等价物时，required门禁不通过。

## FR-1001 M-IMPL退出的宿主测试门禁

### AC-FR1001-01
- Devon实施完成后，Runtime按当前宿主`project.toml`或等价project-local运行合同对同一candidate执行required suites；evidence显示非零收集、全部GREEN、无未授权skip/xfail、运行环境一致，并具有目标真实生产模块及交付表面的动态执行证据。
- 仅运行局部selector、只有Agent自报、只获得非零覆盖率、使用Louke仓库自身命令代替宿主合同，或任一required条件失败/不确定时，M-IMPL实现部分不会显示完成。

## FR-1101 Post-GREEN语义判别与覆盖闭包

### AC-FR1101-01
- M-DESIGN交付的project-local machine contract可核对宿主mutation/负样本adapter选型、适用required行为、安全执行能力、不支持判据及identity，并与Test Plan和运行合同属于同一baseline。
- Shield尝试自行选择、替换或宣布adapter不适用，或合同缺失、未覆盖目标行为、判定不确定时，描述性退化和后续判别闭包均不能通过；缺少adapter本身不会被显示为“不支持”的充分证据。

### AC-FR1101-02
- 真实candidate全量GREEN后，每个required新增或改变行为的mutation/等价检查都使目标测试从GREEN变为与绑定合同偏差对应的断言失败；collection、import、build、启动、fixture或无关测试失败不计为识别错误。
- 每次检查后可核对系统已恢复同一candidate并重新取得required suites全量GREEN；无法确认恢复或最终GREEN时不进入M-VERIFY。

### AC-FR1101-03
- M-TEST evidence对每个required AC闭合到observable interface、required layer、测试、真实production surface、执行结果及适用mutation evidence的映射。
- 任一required AC缺少映射、目标真实模块没有动态执行证据或可测覆盖为0时闭包失败；只有非零覆盖率而无行为/真实表面证据时同样不能通过。

## FR-1201 用户可见的完成、继续与返回

### AC-FR1201-01
- 用户从同一Project Status上下文可辨认当前处于接口声明、Shield测试准备、RED/review、Devon实现、真实GREEN、M-TEST判别闭包或attention状态，并能到达绑定current revision的关键证据、责任方和owning surface。
- 选择某项证据或修复入口再返回后，仍处于同一Project和可识别的attempt/revision；不存在只能从后台读取而用户无法到达的required结果。

### AC-FR1201-02
- 全部合同闭合后，同一Project Status提供继续`M-VERIFY`的合法动作；失败、取消、cooldown或stale状态显示受影响检查和合法恢复位置，不会跳到孤立结果页或丢失Project、测试identity。
- 用户不能通过旧页面、Guide文本或直接访问后续地址绕过Runtime current状态和未闭合门禁。

## FR-1301 测试、实现与合同缺陷分流

### AC-FR1301-01
- 对绑定同一合同、测试、candidate和runner identity的代表性失败，测试/fixture不符合同被路由Shield，代码或production接线不符合同被路由Devon，Architecture/Interfaces不足被路由M-DESIGN，Spec/Acceptance未决定产品结果被路由Human控制的M-SPEC/M-ACC。
- 需要语义判断时，Project Status显示Prism对同一revision的独立诊断以及Runtime持久化的failure classification、owner和return target；不会要求Human选择测试框架、实现方法或其它技术归因。

### AC-FR1301-02
- Devon提出测试争议时，return/discussion引用具体合同条款；在合同已明确且测试审查current而无相反依据时，Runtime拒绝skip、xfail或修改冻结测试作为解决方式。
- 合同未决定行为时，当前attempt保持阻塞并返回对应上游，Shield测试不会被默认为新产品需求；上游未形成current合同前，旧测试或实现不能继续推进。

## FR-1401 修订、重试与证据失效传播

### AC-FR1401-01
- Shield修订测试后可观察到新的有效RED/判别检查、Prism审查和冻结identity；Devon修订实现后可观察到受影响unit、integration/e2e及最终required闭包的新结果；设计或产品合同修订产生新baseline。
- 声明、测试、实现、runner或上游合同identity变化时，依赖旧identity的review、GREEN、mutation、覆盖、candidate和继续动作显示stale/superseded，历史结果仍可查看且不会被新结果覆盖。

### AC-FR1401-02
- 从Shield、Devon、M-DESIGN或M-SPEC/M-ACC的合法恢复位置重试时，新attempt只从对应受影响检查继续，并保留来源、旧attempt和新identity之间的可追溯关系。
- 从错误责任方、stale页面或不合法恢复位置发起重试不会改变current baseline，也不会复用旧证据宣告成功。

## FR-1501 Pre-commit与CI职责边界

### AC-FR1501-01
- 新增integration/e2e仍处于合法RED时，Louke管理的普通pre-commit不会仅因其未GREEN而拒绝提交；当前阶段适用的格式、lint、类型、trace或等价快速检查仍执行，宿主既有且不冲突的hooks和快速测试保留在readback中。
- 删除宿主既有快速测试、以pre-commit成功代替required integration/e2e，或以合法RED为由跳过当前适用的快速检查时，reconcile/gate不能通过。

### AC-FR1501-02
- Runtime实施门禁和Louke托管CI对同一candidate执行宿主合同声明的required integration/e2e、production surface、mutation和覆盖闭包，并分别提供可核对结果。
- pre-commit成功而任一required Runtime/CI证据缺失、失败、stale或指向其它candidate时，项目不能继续到依赖该闭包的阶段。

## FR-1601 Runtime、Agent Prompt与bootstrap迁移

### AC-FR1601-01
- active prompt/capability readback显示Archer仅可写同路径接口声明、Shield在Devon前准备并审查required integration/e2e、Devon补全实现与production接线且不能改冻结测试、Prism只返回绑定identity的审查、Runtime持有程序检查/冻结/执行/状态/路由责任。
- 激活记录包含每个受影响canonical prompt/Agent contract的source identity、revision/digest、已接受v0.14语义、被取代规则和supersession/readback；Mode B stub/activation skip及Shield-after-implementation旧顺序不再能驱动新attempt，同时兼容修改未被旧模板覆盖。

### AC-FR1601-02
- 完整Runtime启用前，Human明确委托的bootstrap代行只产生当前Agent权限允许的人类可读artifact或操作结果，并明确显示为bootstrap/manual、未程序校验或未激活；这些结果不能把machine contract、gate或阶段显示为通过。
- 缺少schema或validator时仍可进行Story/Spec/Acceptance语义工作；需要正式implementation baseline、Shield派发或阶段推进时保持阻塞，直到对应Runtime程序合同可用并产生current evidence。


## FR-1701 全阶段生命周期端到端验证

### AC-FR1701-01
- 在临时目录中创建的 wordcount 宿主项目可从 M-START 连续推进到 M-MILESTONE，13 个 canonical stage 全部按序经过，无跳跃、无重复、无平行 WorkflowRun。
- 每个阶段转移的前置条件、artifact 绑定和证据传递可核对；任一阶段失败时，工作流停留在该阶段并显示责任方和合法恢复位置，不跳到后续阶段。

### AC-FR1701-02
- Agent 输出使用预录 fixture，测试不调用真实 LLM provider；Human 交互通过脚本驱动（浏览器或 API）。
- wordcount 宿主项目位于系统临时目录，测试结束后清理；Louke 生产代码和测试代码不混入 wordcount 项目，wordcount 的生成代码也不混入 Louke 仓库。

## NFR-0001 宿主技术栈中立

### AC-NFR0001-01
- 至少两个使用不同语言/构建工具且包含不同交付表面的宿主fixture，均可依照各自M-DESIGN与project-local合同完成接口声明、测试准备、真实实现门禁和M-TEST闭包；证据使用各宿主自己的声明形式、runner、build、coverage和mutation能力。
- 非Python或非Web宿主的流程不会被要求引入Python、pytest、Starlette或基于文件后缀猜测的模块替换机制；能力不支持或合同缺失时返回定位到当前宿主adapter/contract的诊断，而不是静默套用Louke仓库默认值。

## NFR-0101 Louke与宿主空间隔离及最小权限

### AC-NFR0101-01
- task manifest/readback可区分Louke工具与canonical prompts、宿主`.louke`合同/证据、宿主生产源码、宿主测试资产和宿主CI配置的identity与write scope；Archer、Shield、Devon、Prism及bootstrap代行只能修改本任务授权空间。
- 对每个角色注入跨空间或无关文件修改时，结果被拒绝且原资产不被覆盖；允许的同路径声明、测试或实现修改仍能在其精确scope内完成。

### AC-NFR0101-02
- 在fixture、反例或mutation sandbox中使用可识别测试credential并监测用户HOME、Louke工具仓库、宿主真实数据和外部真实资源，执行前后均无未授权读取、写入或副作用；日志、evidence和可下载结果不暴露原始credential。
- 检测到越权、污染或结果无法确认时，当前检查失败或进入attention，不能用该结果制造RED、GREEN、mutation kill或阶段完成。

## NFR-0201 证据完整性与可复现性

### AC-NFR0201-01
- RED、Prism review、冻结测试、GREEN、surface执行、mutation、coverage和最终candidate evidence均可核对需求/design identity、宿主runner、源码revision、测试revision及执行环境identity，并指向同一适用baseline/candidate。
- 对失败、取消、超时、零收集、报告缺失、解析不确定或任一identity不一致的fixture，结果不会显示成功；相同输入的重试产生可追溯新结果并保留旧attempt，不覆盖历史。

### AC-NFR0201-02
- 完整Runtime identity schema未部署时，当前project-local `.louke/project/contracts/**`中存在由M-DESIGN锁定的最小identity字段集合，bootstrap/manual evidence可核对使用该集合并显示“未程序校验”。
- 缺少最小字段合同、evidence缺字段或未程序校验时，系统不据此宣告machine contract、gate或阶段成功；schema启用后的正式结果与旧manual结果保持可辨。

## NFR-0301 安全隔离与恢复

### AC-NFR0301-01
- 对可执行反例和post-GREEN mutation分别验证成功、目标未识别、基础设施失败、中断及Runtime重启，检查均在隔离环境内运行，current candidate、release branch、宿主生产数据和外部真实资源不被污染。
- 每次检查结束后，Runtime能确认或恢复原candidate，再执行最终required GREEN；恢复或candidate identity无法确认时Project Status保持attention并阻止`M-VERIFY`，可能仍被变异的工作区不会成为候选。
