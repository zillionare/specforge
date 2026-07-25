# v0.14-005 流程改进备忘

> 来源：v0.14-004 实施复盘（Shield 测试质量 + Devon 路由未接线）
> 状态：待 004 稳定后实施
> 日期：2026-07-24（修订：2026-07-25）

---

## 0. 适用范围：Louke 内部 vs 宿主项目

Louke 是部署到宿主项目中辅助开发的工具。Louke 本身用 Python 开发，但宿主项目语言不定。本备忘中的机制需区分两层：

| 层 | 语言 | 内容 |
|---|---|---|
| **Louke 内部** | Python（固定） | runtime、web UI、agent prompt、`louke` CLI 子命令的实现 |
| **宿主项目侧** | 由宿主决定 | 接口桩、契约测试、负样本夹具、测试运行、变异检查、CI 配置 |

本文档中所有 `louke check stubs`、`louke check red`、`louke mutation check` 等命令均为 **Louke runtime 子命令**（Python 实现），由 runtime 感知宿主项目语言后执行对应操作。文中代码示例以 Python 为主，但概念和规则语言无关。

---

## 1. 端到端流程（修正版）

```
M-DESIGN baseline
  Archer 交付：architecture.md + interfaces.md + acceptance.md + 接口桩
  合同锁定（四方文档 + 接口桩冻结）
    │
    ▼
Runtime dispatch Shield
  输入：锁定合同 + 接口桩
    │
    ▼
Shield 编写 public-surface integration/e2e 契约测试
Shield 编写对应负样本夹具（每条测试至少一个）
    │
    ▼
Shield 自检：louke mutation check
  每条测试面对负样本必须 FAIL，否则重写
    │
    ▼
Runtime：louke check red（collection + valid RED 两层门禁）
  L1 基础设施：collection > 0、无 import/fixture error、无 skip/xfail
  L2 语义：断言失败在测试文件自身、消息含合同 token
    │
    ▼
Prism：测试忠实性 / 非空洞审查 / 负样本完备性
    │
    ▼
冻结测试 + 负样本（Devon 不可修改）
    │
    ▼
Runtime dispatch Devon
  输入：锁定合同 + 冻结测试 + 接口桩 + 设计包
    │
    ▼
Devon 替换接口桩为真实实现，接入 production composition root
    │
    ▼
Devon 退出门禁：
  按 project.toml 运行 integration/e2e
  全 GREEN、无 skip/xfail
  失败时：合同裁判 + 举证责任 → 必要时 Prism 裁定
    │
    ▼
post-GREEN 语义变异：
  对真实代码做 mutation testing（宿主语言对应工具或手写变异体）
  验证测试对真实实现的区分力
    │
    ▼
route/surface evidence：
  交付入口可达性证据（每个 FR 的交付入口有对应测试通过记录）
    │
    ▼
完整 candidate review / M-VERIFY
```

### 对原流程的修正说明

| 原流程 | 修正 | 理由 |
|--------|------|------|
| M-DESIGN baseline 未提接口桩 | Archer 交付物加接口桩 | 无桩则 Shield 测试无法 import，collection 即失败 |
| Shield 只写测试 | Shield 同时写负样本夹具 | 无负样本则无法证明测试区分力 |
| 无 Shield 自检步骤 | 加负样本自检（在 Runtime 门禁之前） | Shield 先自证，再交 Runtime 验证 |
| Prism 审查未含负样本 | 加负样本完备性审查 | 负样本缺失 = 测试质量未证明 |
| 冻结仅提测试 | 冻结测试 + 负样本 | Devon 不可修改负样本（否则可绕过变异检查） |
| Devon 失败无归因流程 | 加合同裁判 + 举证责任 + Prism 裁定 | 防止"测试不合理"成为逃避借口 |
| post-Green mutation 含义模糊 | 明确为对真实代码的 mutation testing | 区别于 pre-Devon 负样本（手写错误实现） |
| route/surface evidence 含义模糊 | 明确为交付入口可达性证据 | 每个 FR 的交付入口须有测试通过记录 |

---

## 2. 接口桩（Interface Stubs）

### 定义

接口桩是 interfaces.md 的可执行形态：与真实模块同名的源文件，定义完整的函数签名、类名、路由注册，但所有行为体只抛出"未实现"异常并附带合同 token。

### 谁写、何时写

Archer 在 M-DESIGN 阶段产出，与 architecture.md / interfaces.md / acceptance.md 同时交付、同时锁定。

### 要求

- 函数签名、类名、路由路径与 interfaces.md 完全一致；
- 所有行为体只抛"未实现"异常（附合同 token），不写任何逻辑；
- 路由必须注册到 app（handler 返回 501 或抛异常），否则测试客户端拿到 404 而非有意义的断言失败；
> **Aaron:** 这里需要抽象一点。宿主项目不一定是web 应用。
- 桩文件与真实模块同路径，Devon 实现时直接替换；
- 每个异常必须带合同 token（IF-XXX-XX），便于追溯。

### 各语言示例

**Python**：

```python
# src/setup_gate.py — Archer 产出的接口桩
"""IF-WEB-01: 设置门禁。本文件为接口桩，Devon 实现时替换。"""

class SetupGate:
    def check(self, path: str, *, authenticated: bool) -> GateDecision:
        raise NotImplementedError("IF-WEB-01")
```

**TypeScript**：

```typescript
// src/setup-gate.ts — Archer 产出的接口桩
/** IF-WEB-01: 设置门禁。本文件为接口桩，Devon 实现时替换。 */

export class SetupGate {
  check(path: string, authenticated: boolean): GateDecision {
    throw new Error("IF-WEB-01: not implemented");
  }
}
```

**Go**：

```go
// setup_gate.go — Archer 产出的接口桩
// IF-WEB-01: 设置门禁。本文件为接口桩，Devon 实现时替换。

type SetupGate struct{}

func (g *SetupGate) Check(path string, authenticated bool) GateDecision {
    panic("IF-WEB-01: not implemented")
}
```

**Rust**：

```rust
// src/setup_gate.rs — Archer 产出的接口桩
//! IF-WEB-01: 设置门禁。本文件为接口桩，Devon 实现时替换。

pub struct SetupGate;

impl SetupGate {
    pub fn check(&self, path: &str, authenticated: bool) -> GateDecision {
        todo!("IF-WEB-01")
    }
}
```

### CI 校验

`louke check stubs`：Louke runtime 子命令。读取 interfaces.md，按宿主语言解析桩文件，校验签名/路由/token 一致性，检查函数体仅含"未实现"异常（无逻辑代码）。

> **Aaron:** 实现技术难度？或者请 Agent 评审？

---

## 3. 有效 RED 判定标准（两层门禁）

测试失败本身没有证明力。只有"在正确的位置、因为正确的原因失败"才是有效 RED。

### 第一层：基础设施门禁（必须全绿）

Shield 提交测试后，`louke check red` 先跑"能不能跑"的检查：

- 测试 collection 数量 > 0，每个契约测试文件至少收集到 1 个 test；
- 无 import / module-not-found 错误（接口桩保证）；
- 无 fixture / setup 错误；
- 契约测试禁止 skip / xfail（或宿主语言等价标记）；
- 无缺失依赖（浏览器、服务端口等）。

任何一项不过 → 不是 RED，是测试坏了。Shield 必须修到基础设施全绿。

### 第二层：语义门禁（必须在断言处失败）

基础设施绿了之后，跑全量测试，对每个契约测试检查：

- 失败必须是断言失败（assertion failure），不能是连接错误、文件未找到、空指针等基础设施异常；
- 失败的 traceback 最后一帧必须在测试文件自身，不能在库代码、fixture、setup 里；
- 断言消息必须包含该测试声明的合同 token（`AC-FR0001-01` 或 `IF-WEB-01`）。

三项全满足 → 有效 RED。任何一项不满足 → 无效 RED，Shield 必须修。

### 断言锚定合同 token（硬规则）

各语言示例：

**Python**：

```python
def test_ac_fr0001_01_setup_redirect(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 303, (
        "AC-FR0001-01: 未登录访问 / 应 303 → /setup，"
        f"实际 {resp.status_code}"
    )
```

**TypeScript（Jest）**：

```typescript
test("AC-FR0001-01: 未登录访问 / 应 303 → /setup", async () => {
  const resp = await request(app).get("/").redirects(0);
  expect(resp.status).toBe(303); // AC-FR0001-01
});
```

**Go**：

```go
func TestACFR000101SetupRedirect(t *testing.T) {
    resp := httptest.Get(t, app, "/")
    // AC-FR0001-01: 未登录访问 / 应 303 → /setup
    assert.Equal(t, 303, resp.Code, "AC-FR0001-01")
}
```

断言消息无合同 token → `louke check red` 判无效。这同时排除"与目标合同无关的历史失败"。

### CI 实现

`louke check red`：Louke runtime 子命令。运行宿主项目测试（按 project.toml 声明的测试命令），解析测试输出（JUnit XML / TAP / go test JSON 等），对每个契约测试分类输出（有效 RED / 无效 RED + 原因 / GREEN），存在无效 RED → exit 1。

---

## 4. 负样本夹具：Shield 实现与自检指南

### 4.1 什么是负样本夹具

负样本夹具是一个**故意违背合同的实现**，用来证明对应测试具有区分能力。它不是测试框架的 fixture，不在正常测试运行中加载。

### 4.2 与"绝不 stub SUT"的关系

"绝不 stub SUT"的精确表述：**绝不 stub SUT 来换取 GREEN。** 负样本不是用来换 GREEN 的，是用来证明 RED 有效的。

| | Mode B（禁止） | 负样本夹具（要求） |
|---|---|---|
| 断言锚点 | stub 的罐头值 | 合同值 |
| 期望结果 | GREEN（假绿） | FAIL（证明区分力） |
| 运行进程 | 与正常测试同进程 | 独立进程（`louke mutation check`） |
| 被测对象 | 生产代码（被 stub 替换） | 测试本身（负样本是校准输入） |

负样本是校准砝码——用已知坏样本验证传感器能报警，测的是传感器，不是坏样本。

### 4.3 文件规范

位置：宿主项目测试目录下的 `fixtures/negative/{module}_wrong.{ext}`（ext 随宿主语言）。

每个负样本文件必须包含头部注释：

```
负样本：{IF/AC token} {模块名}
违背方式：{具体描述如何违背合同}
对应测试：{测试文件名}
```

**Python 示例**：

```python
# tests/fixtures/negative/setup_gate_wrong.py
"""
负样本：IF-WEB-01 设置门禁
违背方式：未登录访问 / 时返回 200 而非 303（缺少重定向）
对应测试：test_ac_fr0001_01.py
"""

class SetupGate:
    def check(self, path: str, *, authenticated: bool) -> GateDecision:
        # 故意错误：总是放行，不做重定向
        return GateDecision(allowed=True, redirect=None)
```

**TypeScript 示例**：

```typescript
// tests/fixtures/negative/setup-gate-wrong.ts
/**
 * 负样本：IF-WEB-01 设置门禁
 * 违背方式：未登录访问 / 时返回 200 而非 303（缺少重定向）
 * 对应测试：test-ac-fr0001-01.spec.ts
 */

export class SetupGate {
  check(path: string, authenticated: boolean): GateDecision {
    // 故意错误：总是放行，不做重定向
    return { allowed: true, redirect: null };
  }
}
```

### 4.4 编写规则

- 负样本必须与接口桩同签名（同函数名、同参数、同返回类型）；
- 违背方式必须具体、可追溯（引用合同 token + 说明违背了什么）；
- 每条契约测试至少一个负样本；
- 负样本只违背目标合同条款，其余行为与接口桩一致（避免无关失败）；
- 负样本不得包含任何"碰巧让测试通过"的逻辑。

### 4.5 Shield 自检命令

```bash
# 单条测试 + 对应负样本
louke mutation check \
  --test tests/integration/test_ac_fr0001_01.py \
  --negative tests/fixtures/negative/setup_gate_wrong.py \
  --expect fail

# 批量：所有契约测试 + 所有负样本
louke mutation check \
  --tests tests/integration/ \
  --negatives tests/fixtures/negative/ \
  --expect fail
```

`louke mutation check` 的工作方式（Louke runtime 子命令，Python 实现）：

1. 感知宿主项目语言，确定模块替换机制（Python: `sys.modules`；Node: `require.cache` / module alias；Go: build tag 替换；Rust: feature flag 替换）；
2. 在子进程/沙箱中，用负样本模块替换接口桩；
3. 运行目标测试（按 project.toml 声明的测试命令）；
4. 断言测试 FAIL（exit code != 0）；
5. 子进程退出，替换随之销毁；
6. 正常测试进程完全不受影响。

### 4.6 判定标准

- 目标测试 FAIL → 测试有效，负样本合格；
- 目标测试 PASS → 测试空洞（tautological），Shield 必须重写测试；
- 目标测试 ERROR（非断言失败）→ 负样本签名有误或测试基础设施问题，Shield 修复后重跑。

### 4.7 隔离保证（为什么不会挡住正常测试）

负样本与正常测试的隔离靠三层：

1. **文件隔离**：负样本在 `fixtures/negative/`，正常测试运行的 testpaths 不含此目录，collection 看不到；
2. **进程隔离**：`louke mutation check` 在子进程/沙箱中做模块替换，跑完即销毁，正常测试是独立进程；
3. **CI 流水线隔离**：`test` job 和 `mutation-check` job 是独立 job，各自独立环境，无共享状态。

与 Mode B 的本质区别：Mode B 的 stub 是测试框架的 autouse fixture，与正常测试同进程、同 collection，所以拦截了真实模块。负样本根本不在正常测试的进程里出现。

---

## 5. 合同作为裁判 + 举证责任规则

### 锁定合同

以下文档在 M-DESIGN 完成后锁定，作为 Shield 与 Devon 之间的中立裁判：

- `spec.md`（FR/NFR + 交付入口）
- `interfaces.md`（API 路由、请求/响应 schema、状态码）
- `acceptance.md`（AC 条目 + 可观测断言）
- 接口桩（interfaces.md 的可执行形态）

锁定后，任何一方不得单方面修改合同。合同缺陷走 Sage/Archer 修订流程。

### 裁定规则

当 Devon 的 int/e2e 测试失败时，按以下规则归因：

| 情形 | 判定 |
|------|------|
| 测试断言 X，合同写 X，代码做 Y | Devon 实现缺陷 → Devon 修 |
| 测试断言 X，合同写 Z（Z≠X） | Shield 测试缺陷 → Shield 修 |
| 合同对该行为无明确约定 | 合同缺陷 → 提交 Sage/Archer 补充 |

### 举证责任

- Devon 若认为某测试有误，必须**引用具体合同条款**（文件名 + 章节/条目编号）说明测试与合同不一致；
- 不得以"测试不合理""我觉得应该这样"等无合同依据的理由跳过或修改测试；
- 无法引用合同条款 = 默认测试正确，Devon 必须使代码满足测试。

---

## 6. Prism 裁定流程

### 6.1 测试阶段审查（Shield 提交后）

Prism 在测试冻结前审查：

- 测试忠实性：断言是否与合同条款一致；
- 非空洞性：测试是否真正验证了合同行为（非 hasattr / 非同义反复）；
- 负样本完备性：每条测试是否有对应负样本，负样本是否真正违背合同。

### 6.2 实现阶段争议裁定（Devon 测试失败时）

当 Shield 与 Devon 对测试归因产生争议且无法自行解决时：

1. Devon 提交争议：引用测试名 + 合同条款 + 代码行为，说明为何认为测试有误；
2. Prism 独立审阅锁定合同原文 + 测试代码 + 实现代码；
3. Prism 出具裁定：
   - 测试正确 → Devon 修复实现；
   - 测试有误 → Shield 修复测试（附修正理由）；
   - 合同模糊 → 标记为合同缺陷，转 Sage/Archer 补充后重新裁定；
4. 裁定为终局，双方执行。

Prism 角色定位：独立检查/审阅（非 Judge），此处行使的是合同解释权。

---

## 7. pre-commit 仅保留静态检查

从 pre-commit hook 中移除测试运行（已完成）。保留项为宿主语言对应的静态检查：

- 格式检查（Python: ruff/black；TS: prettier；Go: gofmt；Rust: rustfmt）
- 类型检查（Python: mypy/pyright；TS: tsc；Go: go vet；Rust: clippy）
- import 排序 / lint 规则

理由：测试运行移至 CI 和 Devon 退出门禁，pre-commit 不再承担"测试必须绿才能提交"的职责。这消除了 Mode B "green-before-code" 设计的原始动机。

---

## 8. 支撑原则（已达成共识）

### 8.1 绝不 stub 被测系统（SUT）

- 精确表述：**绝不 stub SUT 来换取 GREEN。**
- 只 stub 外部适配器：git、gh CLI、opencode、网络、时钟、文件系统 fixtures；
- 被测模块必须通过真实公共接口调用；
- HTTP 测试用测试客户端走真实路由；库函数直接 import 调用；CLI 用 subprocess；
- 负样本夹具不违反此原则（见 §4.2 辨析）。

### 8.2 真实表面验证（Real-Surface Exercise）

- 集成测试必须通过声明的交付入口（页面路由 / API endpoint / CLI 命令）进入系统；
- 不允许绕过路由直接调用内部函数来"模拟"用户路径。

### 8.3 覆盖率门禁

- 真实模块集成覆盖率 0% = CI 硬性失败；
- 覆盖率门禁 + 验收锚定断言（acceptance-anchored assertions）双重保障，缺一不可；
- 覆盖率工具随宿主语言（Python: coverage.py；TS: istanbul/c8；Go: go test -cover；Rust: tarpaulin）。

### 8.4 M-IMPL 派发携带设计包

- Devon 接收的任务输入必须包含完整设计包（architecture.md + interfaces.md + acceptance.md + 接口桩）作为权威输入；
- GitHub issues 仅作为任务句柄（handle），不作为实现规格的唯一来源；
- 修复 v0.14-004 中"Devon 只看 issue list、不知道接口设计"的输入断裂。

### 8.5 reconcile 范围扩展

- architecture.md §8 reconcile 从 3 个摘要（story/spec/acc）扩展为 4 个（+ interfaces.md）；
- 确保设计与接口文档的一致性检查完整。

---

## 9. 实施计划

1. 先稳定 v0.14-004（修复 D-001 CANONICAL_STAGES、补全路由接线、Shield 测试去 tautology）；
2. v0.14-005 启动时，将上述流程变更写入：
   - Archer agent prompt（接口桩交付要求）
   - Shield agent prompt（测试编写规范 + 负样本实现指南 + 自检命令）
   - Devon agent prompt（退出门禁 + 举证责任 + 接口桩替换规范）
   - CI workflow（valid-RED gate + mutation-check job + 覆盖率门禁 + stub 校验）
   - M-IMPL 派发逻辑（设计包 + 接口桩 + 冻结测试注入）
   - Prism agent prompt（测试阶段审查 + 实现阶段裁定）
   - Louke runtime 子命令实现：
     - `louke check stubs`（接口桩一致性校验，按宿主语言解析）
     - `louke check red`（有效 RED 判定，解析宿主测试输出）
     - `louke mutation check`（负样本校验，按宿主语言做模块替换）
3. 在 005 的第一个 story 上试运行完整流程，验证可行性。
