# STR-1406: 以先验契约测试和真实交付表面约束宿主项目实施

---

| Story ID | 创建时间                  | 分流建议         |
| :------- | :------------------------ | :--------------- |
| STR-1406 | 2026-07-25T09:49:47+09:00 | Go（Agent 建议） |

---

## 1. 原始输入

> 在实施阶段，发现几个重要的问题
> 1. devon 没有把实施与 http route 接线，导致 e2e/int 覆盖率为零
> 2. shield 写 e2e/int 时，也有两个问题，一是使用 stub 导致生产代码被 mask；二是只断言属性存在，未检测真实行为。
>
> 为了解决这个问题，我请 qwen 生成了005下的一个备忘录。

> 文件是.louke/project/specs/v0.14-005-atdd-process-improvement/process-improvement-005.md
>
> 注意区分：
>
> 1. 我们是在讨论未来的行为
> 2. Louke 是工具，将部署到宿主项目中，辅助宿主项目开发。Louke 使用 Python,宿主项目可能是任何语言
> 3. 时刻注意区分 Louke 空间与宿主项目空间

> 现在，请根据.louke/project/specs/v0.14-005-atdd-process-improvement/process-improvement-005.md 来创建一个 story

## 2. 用户意图

- 让 Louke 在未来为任意技术栈的宿主项目组织实施时，先建立可执行但不包含业务实现的接口声明和独立契约测试，再让 Devon 实现，避免实现完成后才发现公开交付入口没有接线。
- 消除 Shield 以 stub 替换宿主生产代码、只检查属性存在或由测试自己构造假入口所造成的 integration/e2e 假覆盖。
- 让 Human 在宿主项目工作流中看到可信证据：测试在实现前能因目标行为缺失或错误而有效失败，在真实实现和 production composition root 上通过，并能对故意错误行为保持区分力。
- 当测试、实现或合同不一致时，由 Louke 按锁定合同和独立审查证据路由回正确责任方，而不是靠 Devon、Shield 任一方单方面修改测试或实现来取得 GREEN。

## 3. 核心操作路径

### 3.1 从设计基线进入契约测试先行的实施

- **起点上下文**：这是一个流程变更。在旧流程中，Archer只负责 Architecture, Test Plan, Interfaces 设计（以及写入 int/e2e 接口等），但未生成接口桩，导致 Shiled 无法验证测试代码的语法正确性；未规定 Devon 和 Shield 的启动顺序，导致 TDD 没有落实彻底。Shield 在没有接口桩的情况下，自己造出第二套接口桩，导致假覆盖。
- **入口/触发**：Runtime 依据当前、已审查的设计基线启动本次实施，不再直接把只有 Issue 列表的任务派给 Devon。

1. Archer 面向宿主生产代码，在目标真实模块的同路径产出接口声明骨架；骨架只声明当前合同必需的公开或跨模块接口，不包含业务逻辑，也不产生可被误认为成功的行为。接口身份冻结后，Devon可在其上补全实现，但不能擅自改变声明合同。
2. Runtime 把锁定的需求、Acceptance、Architecture、Interfaces、Test Plan、接口声明骨架及宿主运行合同交给 Shield。Shield 在宿主测试空间编写 integration/e2e，通过宿主真实 public package、production composition root 或已声明的 CLI/API/UI/library 入口执行，而不以 test-owned stub 替换 SUT。
3. Shield 为新增或改变的合同行为提供可追溯反例，使测试能区分至少一种具体错误行为；Runtime确认测试资产可收集、可运行，且预期 RED 与目标 AC/接口对应。Prism在冻结前独立审查测试是否忠于合同、是否断言真实行为以及反例是否具有判别力。
4. Runtime冻结已审查的测试、反例和接口声明身份，再将完整设计包与这些资产交给 Devon。Devon只在宿主生产代码空间实现真实行为，并将其接入该宿主项目的 production composition root；不得修改冻结测试、以 stub 获得 GREEN，或只实现未被公开入口调用的孤立模块。
5. Runtime按照宿主项目声明的 integration/e2e 命令执行全部 required suites。只有真实生产实现、真实交付入口、验收锚定行为和必要的外部适配器边界均有通过证据，且没有未授权 skip/xfail、零收集或目标真实模块零执行，实施才可完成。
6. 在真实实现 GREEN 后，Runtime按宿主项目锁定的能力运行语义变异或等价判别检查，证明关键测试在真实实现被引入目标错误时会失败；随后恢复同一candidate并重新确认全量 GREEN。
7. Human在 Project Status/验证结果中看到本次candidate对应的合同、测试revision、真实交付表面、运行结果与判别证据，并可继续进入 M-VERIFY。

- **完成结果**：宿主项目的实现不只“存在代码或属性”，而是从声明的用户/调用者入口可达并产生合同结果；integration/e2e没有用SUT替身遮蔽生产代码，Louke持有同一candidate的先验测试、真实GREEN和表面接线证据。
- **继续/返回**：证据完整时继续M-VERIFY；测试/fixture缺陷返回Shield，实现或接线缺陷返回Devon，设计缺口返回M-DESIGN，产品合同缺口返回Sage/Human控制的需求路径。修复后沿同一责任路径重新审查并重跑，不通过skip或改写合同绕过。

### 3.2 合同争议与可恢复分流

- **起点上下文**：Devon实现后，冻结的integration/e2e未能GREEN，或Devon认为某项测试与锁定合同不一致。
- **入口/触发**：Runtime保留失败测试、candidate、runner和合同identity，并要求争议绑定具体测试、代码行为及合同条款。

1. 若测试断言与锁定合同一致而真实代码行为不同，Runtime将实现或production接线缺陷返回Devon。
2. 若测试断言与锁定合同不一致，Runtime将测试缺陷返回Shield；修订后的测试必须重新经过独立审查和冻结。
3. 若当前合同不足以判定目标行为，Runtime保持实施阻塞，将技术设计缺口交给Archer，或将会改变产品结果的需求缺口交给Sage/Human；任何一方都不能以“默认测试正确”补写合同未决定的产品行为。
4. Prism提供绑定当前合同、测试和代码revision的独立语义审查；Runtime根据审查及程序证据执行正式分流并使旧结论在revision变化后失效。

- **完成结果**：每次失败都有可核对的责任分类和返回位置，冻结测试既不能成为Devon随意绕过的障碍，也不能越过产品合同成为新的需求来源。
- **继续/返回**：责任方修复后从受影响检查重新开始；合同经正式修订时，相关测试、实现与旧审查一并标记stale，再按新baseline重走测试先行路径。

### 3.3 行为种子

#### BS-01 设计阶段产生同路径接口声明骨架

- EARS: `WHEN 当前宿主项目的M-DESIGN基线完成, THE系统 SHALL 由Archer在目标真实模块同路径产出只包含必要接口声明的源文件，并 SHALL NOT 在其中实现业务逻辑或提供可被当作成功结果的罐头行为`
- 来源: 3.1 / Human明确澄清
- 说明: integration可以导入真实宿主模块，同时实现责任仍清晰留给Devon；接口声明不是GREEN或验收证据。

#### BS-02 Shield先于Devon形成可判别契约测试

- EARS: `WHEN 接口声明和设计合同已锁定, THE Runtime SHALL 先派发Shield编写宿主项目integration/e2e，并仅在测试通过真实public package或交付入口执行、对新增或改变行为产生可追溯RED且能识别具体错误反例后冻结测试`
- 来源: 3.1 / 005备忘录
- 说明: 防止测试在实现之后迎合代码，也防止stub或属性存在断言产生假覆盖。

#### BS-03 Devon必须完成真实production接线

- EARS: `WHEN Devon接收冻结测试和完整设计包, THE Devon SHALL 在宿主生产代码空间补全真实实现并接入production composition root；THE Runtime SHALL NOT 仅因内部模块存在、属性存在或绕过公开入口的测试通过而接受实施完成`
- 来源: 3.1 / v0.14-004实施复盘
- 说明: 直接保护“模块已写但HTTP route或其他交付入口未接线”的失败模式，并适用于API、CLI、UI或library等不同宿主表面。

#### BS-04 宿主required suites必须在真实实现上全绿

- EARS: `WHEN Devon请求完成实施, THE Runtime SHALL 按宿主项目锁定的integration/e2e运行合同执行required suites，并仅在非零收集、无未授权skip/xfail、真实目标模块被执行且验收锚定行为全部GREEN时允许继续`
- 来源: 3.1 / 约束
- 说明: Louke负责统一证据和门禁，但不假设宿主项目使用Python、pytest或Web框架。

#### BS-05 测试判别力必须有独立证据

- EARS: `WHEN 新增或改变的契约测试准备冻结或真实实现已GREEN, THE系统 SHALL 证明该测试面对与目标合同绑定的错误行为时会失败，并 SHALL NOT 将collection、import、fixture、启动或其他无关错误计为有效判别证据`
- 来源: 3.1 / 005备忘录 / 成熟mutation testing惯例
- 说明: “测试是红的”或“变异进程非零退出”本身不足以证明测试检查了真实行为。

#### BS-06 合同和独立审查决定缺陷去向

- EARS: `IF 冻结测试与真实实现发生争议, THE Runtime SHALL 依据当前合同和Prism独立审查将问题路由至Shield、Devon、M-DESIGN或Human控制的需求路径；IF 合同未决定该产品行为, THE系统 SHALL 保持阻塞而 SHALL NOT 默认任一方正确`
- 来源: 3.2 / 既有Runtime authority合同
- 说明: 防止测试越权发明需求，也防止实现者以主观理由跳过测试。

#### BS-07 Louke与宿主项目空间保持可辨

- EARS: `WHERE Louke为任意语言宿主项目执行本流程, THE系统 SHALL 将Louke runtime/prompt能力、宿主项目内Louke合同与证据、宿主生产源码及宿主测试资产分别归属和授权，并 SHALL 按宿主声明的工具链执行而不假设宿主使用Python或Web`
- 来源: Human明确约束 / 3.1
- 说明: Louke自身用Python实现不应泄漏为宿主项目的语言、框架或目录要求。

## 4. 范围、约束与例外

### 4.1 必须保持的产品约束

- 本Story描述005计划实现的未来行为，不把当前仓库中尚不存在的命令、门禁或多语言适配能力伪报为已交付事实。
- Louke内部实现可以使用Python；宿主项目语言、测试框架、公开交付表面和CI工具由宿主事实及锁定设计决定，Louke不得把Python/pytest/HTTP作为通用宿主前提。
- 必须区分Louke工具空间、宿主项目内`.louke`合同/证据空间、宿主生产源码空间和宿主测试/CI空间；各Agent只能在Runtime授权的对应空间写入。
- Archer产出的接口声明骨架位于目标真实模块同路径，只声明当前合同所需接口，不作具体业务实现；Devon在其上完成实现。声明身份可冻结，但实现区域必须在Devon任务中可写。
- Integration可以并通常需要导入宿主真实生产模块或composition root；禁止的是以测试拥有的stub、mock app、替换模块或罐头结果遮蔽SUT。E2E必须从宿主声明的最终用户/调用者入口执行。
- 测试必须断言可观察行为及必要结果/readback，属性或字段存在检查只能作为补充，不能单独证明AC完成。
- Devon必须收到当前完整设计包和冻结测试身份；Issue只作为追踪句柄，不能替代权威合同。
- 失败测试不得由Devon直接修改、skip或xfail；测试修订返回Shield并重新审查，合同修订返回对应上游并使旧证据stale。
- Louke管理的实施退出和CI门禁必须运行宿主required suites；不得要求正常pre-commit阶段为了尚未实现的行为先GREEN，也不得无故移除宿主项目自身已有且不冲突的hook政策。

### 4.2 非常规要求

- Archer在M-DESIGN阶段向宿主生产源码同路径写入“仅声明、无实现”的接口骨架，扩大了设计工件与宿主源码的交界。该例外由Human明确要求，必须通过精确write scope、声明/实现边界、review和最终残留检查限制，不能扩张为Archer编写业务实现。
- Shield在Devon实现前编写并冻结integration/e2e，且新增或改变的契约测试需要错误反例证据。这有意改变当前先完成M-IMPL、再在M-TEST生成integration/e2e的顺序，后续Spec必须同步修订Runtime阶段内状态、lease和返回合同。

### 4.3 Out-of-Scope

- 不在Story中决定Python、TypeScript、Go、Rust或其他宿主语言的AST解析器、模块替换机制、mutation工具、测试报告格式或具体CLI参数。
- 不要求所有宿主项目都是Web应用，也不把HTTP route当作唯一交付入口；页面、API、CLI、public library或其他已声明表面适用同一真实性原则。
- 不用本流程替代宿主项目已有unit测试、Devon的实现级RGR或语言原生静态检查；本Story聚焦integration/e2e真实性、接线与流程责任。
- 不在005中重新定义宿主业务功能，也不把测试或反例中出现但合同未决定的行为自动提升为产品需求。
- v0.14-004现有实现缺陷的即时修复仍属于004稳定工作；本Story定义其后可复用的未来流程，不能以005规划代替004修复。

## 5. 重要推导与证据

### D-01 接口声明骨架属于宿主生产空间，但不是业务实现

- **结论**：Archer面向宿主生产代码产出同路径接口声明是Human明确选择；该源文件用于让integration依赖真实模块合同，不得包含能够让验收变绿的实现。
- **依据**：Human明确修正为“Archer应该产出与真实模块同路径的源文件，但只声明必要的接口，不作具体实现”；现有Archer设计职责本就面向宿主生产结构。
- **影响**：后续Spec必须调整Archer manifest/write scope，并区分可冻结的声明区域与Devon可写的实现区域，否则同一文件既冻结又替换会产生权限冲突。

### D-02 真实表面随宿主项目而变化

- **结论**：HTTP route是触发005复盘的实例，不是流程唯一对象；真实表面由当前宿主声明，可包括UI、API、CLI或public library。
- **依据**：Human强调宿主项目可能是任意语言；备忘录中的Aaron批注明确要求不要假设宿主一定是Web应用。
- **影响**：Sage/Archer应定义语言无关的“交付表面已接线并被required test执行”结果，而把框架和运行器细节留给项目设计。

### D-03 先验反例与post-GREEN mutation证明不同结果

- **结论**：实现前的错误反例证明测试意图具有判别方向；真实实现GREEN后的语义变异证明冻结测试确实能保护candidate。二者都不能替代真实生产表面上的GREEN。
- **依据**：005备忘录明确区分pre-Devon负样本和post-GREEN真实代码mutation；成熟测试惯例要求mutant因目标断言而被kill，不能只检查进程非零。
- **影响**：后续设计可选择宿主适配机制，但证据必须区分有效RED、真实GREEN和mutation kill，避免always-fail测试被误判为高质量测试。

### D-04 “合同是裁判”不等于测试能补写合同

- **结论**：当合同已经决定行为且冻结测试经独立审查后，Devon若无法引用相反条款就不能主观绕过；当合同本身没有决定该行为时，必须返回上游，不能默认测试正确。
- **依据**：备忘录裁定表将未约定行为归为合同缺陷；既有Runtime流程把设计缺口和需求缺口分别返回Archer与Human控制路径。
- **影响**：化解备忘录“合同缺陷”与“默认测试正确”的表面冲突，保持Human对产品结果的决定权。

### D-05 覆盖率非零只是最低安全网

- **结论**：目标真实模块integration覆盖率为零必须阻断，但非零覆盖不能单独证明交付入口接线或业务行为正确。
- **依据**：004中route未接线导致目标覆盖为零；同时Shield的属性存在断言说明即使代码被加载，也可能没有验证真实结果。
- **影响**：流程必须同时保留AC/接口追溯、production surface执行、行为断言和必要readback，而不能以单个覆盖率百分比替代验收。

### D-06 Prism审查与Runtime流程authority保持分离

- **结论**：Prism对合同、测试和实现提供独立语义分类；Runtime负责绑定revision、执行程序门禁和正式路由，Prism不自行推进workflow或伪造最终状态。
- **依据**：现有v0.14-003工作流将Agent限制为语义审查或coding，把状态、证据和返回路径交给Runtime；005的目标是增加独立裁判而不是形成第二套状态authority。
- **影响**：争议可以得到可信解释，同时测试或review变化都会通过Runtime使旧结论stale。

## 6. 开放产品决定

- 无。宿主语言对应的声明形式、有效RED解析、反例隔离和mutation工具属于后续技术设计，不要求Human选择。

## 7. 必要性、风险与分流建议

- **既有能力**：v0.14-003已有M-IMPL/M-TEST/M-VERIFY、Archer/Devon/Shield/Prism职责、project-local integration/e2e运行合同、测试patch review、候选冻结与缺陷分流；005可在这些合同上调整测试生成时序并补充真实表面与判别证据。
- **冲突**：当前流程在implementation tasks完成后才派发Shield，当前Shield prompt还允许Mode B stub/activation skip；005明确要求Shield先于Devon并禁止SUT替换。Archer向宿主真实模块同路径写接口声明也需要新的manifest/write-scope合同。这些是005必须显式取代的流程规则，不能只靠Prompt文字叠加。
- **重要风险**：若接口声明包含罐头成功行为，会重现SUT被mask；若反例只造成import/启动错误，会把空洞测试伪装为有效；若Louke猜测任意宿主语言工具链，会侵入宿主约定。后续设计必须使用宿主声明的运行合同、精确scope和分层证据缓解。
- **分流建议**：Go — 004已经暴露真实接线遗漏和测试假覆盖，问题会直接破坏Human对Louke自动实施结果的信任；Human已明确未来行为、跨语言边界和接口声明职责，剩余事项均可由Sage/Archer在Spec与Design阶段展开。

## 8. 可追溯信息

- **Story ID**：`STR-1406`
- **创建时间**：`2026-07-25T09:49:47+09:00`
- **锁定时间**：`2026-07-25T11:25:00+09:00`
- **关联 Spec/Issue**：`v0.14-005-atdd-process-improvement`；来源备忘录`process-improvement-005.md`；Issue待后续流程建立
- **Story SHA-256**：`2bf35f6117ddeb6f6f608bba5ac0ddae7a2daa01cb9203bab867e94c233959d5`
- **Spec SHA-256**：`0bd727b8e379d4dccb2a39b0227053f9ad2661fb39077a7b4a6b6d663c1c662a`
- **Acceptance SHA-256**：`5d8c6a9e3050233398ea330aa4a48f767c3431319861b9a78425140b0b7716c1`
- **Spec/Acceptance 状态**：已锁定（v0.14 bootstrap：由 Sage 在缺乏 runtime 字段时依据 story/SHA 与 review findings 完成；未伪造 PASS、gate 或阶段推进）
- **Sage peer review**：`Pending`（Scribe 不得填写通过结果）
