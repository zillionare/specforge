# 契约测试先行与真实交付表面验证 — Interfaces

- **Spec ID**：`v0.14-005-atdd-process-improvement`
- **Assertion basis**：本文件中的公开出口是`test-plan.md`唯一断言依据。
- **Bootstrap qualification**：标为candidate的命令/schema/manifest尚未激活；不存在或未激活时必须fail closed，不得把本文当作可执行PASS。

## 1. 通用identity、结果与错误合同

### IF-EVIDENCE-01 — ATDD evidence envelope

| 分类 | Surface / Schema | 合同 | modules |
|---|---|---|---|
| JSON envelope | RED、review、freeze、GREEN、surface、discrimination、coverage、closure及route evidence | 必填`{schema_version:"1.0.0-candidate",evidence_id,kind,qualification:formal|bootstrap_manual,validation_state:current|stale|superseded|unvalidated,workspace_id,project_id,run_id,attempt_id,baseline_identity,candidate_identity|null,source_revision,test_revision|null,runner_identity,environment_identity,command|null,started_at,finished_at,result,reason,artifact_refs:[ArtifactRef],evidence_digest}`；未知字段/缺字段/identity不一致fail closed | `Runtime Facts`, `Host Required-Test Adapter`, `Semantic Discrimination Adapter`, `Test Asset Review`, `Failure Routing`, `Runtime Projection`, `CI/Traceability` |
| `ArtifactRef` | evidence/readback | `{kind,path,identity,revision,digest,media_type,owning_url|null}`；digest为`sha256:<64 lowercase hex>`；path受workspace containment约束 | `Runtime Facts`, `Task Package`, `Runtime Projection`, `Workbench Presentation` |
| Digest | JSON evidence | `evidence_digest`是去除自身字段后对UTF-8 sorted-key compact JSON的SHA-256；artifact digest是原始bytes SHA-256。解析错误、缺失、duplicate key或结果不确定不得记success | `Runtime Facts`, `CI/Traceability` |
| Bootstrap | 任一candidate/manual结果 | `qualification=bootstrap_manual`或`validation_state=unvalidated`只能显示attention；不得解锁正式baseline、Shield/Devon派发、freeze、M-VERIFY或publish | `Runtime Facts`, `ATDD Checkpoint`, `Runtime Projection`, `Workbench Presentation` |
| Security | 所有body/log/artifact | 不含credential、session/provider token、真实HOME内容或provider/session transport metadata；命令参数和stand-in ledger按字段redact | `Runtime Facts`, `External Stand-ins`, `CI/Traceability`, `Workbench Presentation` |

### IF-ERROR-01 — 稳定错误与并发语义

| 分类 | HTTP/command结果 | 合同 | modules |
|---|---|---|---|
| HTTP error | JSON `application/json` | `{error_code,message,current_revision,recovery_url,details}`；`400 VALIDATION_FAILED`、`401 AUTH_REQUIRED`、`403 PERMISSION_DENIED|CSRF_INVALID|SCOPE_DENIED`、`404 NOT_FOUND`、`409 STALE_REVISION|IDENTITY_CONFLICT|COOLDOWN|OPERATION_UNCERTAIN`、`428 CONTRACT_NOT_ACTIVE` | `Workbench Presentation`, `Runtime Projection`, `ATDD Checkpoint`, `Task Package`, `Runtime Facts` |
| Human mutation | Project Status action | 有authenticated Human session、same-origin CSRF、`Idempotency-Key`和body `expected_run_revision`；同key同payload返回同operation，同key异payload或stale为409且无第二副作用 | `Workbench Presentation`, `ATDD Checkpoint`, `Runtime Facts` |
| Agent/program command | Python API/Runtime task | 必须绑定task identity、baseline、attempt、expected revision和allowed scope；provider/session metadata不能替代task identity | `ATDD Checkpoint`, `Task Package`, `Runtime Facts` |
| Fail closed | API/CLI/CI | missing、cancel、timeout、zero collection、skip、xfail、unknown、parse error、digest drift、teardown/restoration不确定均为非success | `Host Required-Test Adapter`, `Semantic Discrimination Adapter`, `CI/Traceability`, `Runtime Facts` |

## 2. M-DESIGN声明、schema与prompt候选

### IF-DECLARATION-01 — 同路径接口声明manifest与下游ATDD保证

| 分类 | Surface / Input | 成功/失败出口 | modules |
|---|---|---|---|
| Manifest | `.louke/project/contracts/v0.14-005-atdd-process-improvement/interface-declarations.candidate.json` | `{identity,revision,activation_state,baseline_identity,interfaces_identity,files:[{path,language,file_digest,entries:[{token,kind,symbol,signature,route|null,methods,implementation_region}]}],assurance}`；closed file/token set；`assurance.mode="downstream-atdd"`且明确不存在FR-0101专用validator/CLI | `Design Declaration`, `Runtime Facts`, `ATDD Checkpoint`, `Task Package` |
| M-DESIGN readback | manifest + listed production source bytes | 可核对每个声明位于manifest真实path，公开signature/type/route/token与本文件一致，既有文件只含授权声明/route patch；Archer bootstrap检查标记`bootstrap_manual/unvalidated`，不形成baseline gate或Shield前formal PASS | `Design Declaration`, `Runtime Facts`, `Task Package` |
| Shield collection/RED | `tests/e2e/run-project-venv integration`及test-bundle evidence | Shield从manifest真实production path import/collect并经production入口调用；signature/path/token不一致、未声明import错误或无法把失败绑定到目标IF时为`invalid_red|invalid_test_asset`，不得审查/冻结；匹配桩token或目标行为断言失败才可进入IF-VALID-RED-01 | `Design Declaration`, `Host Required-Test Adapter`, `Test Asset Review`, `ATDD Checkpoint`, `Runtime Facts` |
| Devon write/revision | IF-TASK-01 + declaration revision action | baseline冻结path/signature/route/token，只授权`implementation_region`及明确composition接线；Devon发现不可达/冲突或需改变公开声明时返回IF-ATDD-CHECKPOINT-01 declaration revision，新identity使旧测试/RED/review stale | `Design Declaration`, `Task Package`, `ATDD Checkpoint`, `Failure Routing`, `Runtime Facts` |

### IF-REGISTRY-01 — program-owned candidate registry与instances

| 分类 | Surface / Schema | 合同 | modules |
|---|---|---|---|
| Registry candidate | `.louke/project/contracts/v0.14-005-atdd-process-improvement/registry.candidate.json` | owner恰为`Runtime/program`、`activation_state=candidate`；列出exact schema identity/version/digest/path及required kinds；candidate不是active pointer | `Runtime Facts`, `CI/Traceability`, `ATDD Checkpoint` |
| Schema candidate | `schemas/machine-contract-v2.schema.candidate.json`、`schemas/agent-io-v014-005.schema.candidate.json` | Draft 2020-12；前者锁定通用machine identity envelope及16个kind payload，后者锁定Archer/Shield/Devon/Prism的八个task/result bindings；schema独立于instance/prompt，meta-validation错误/unknown keyword处理不确定失败 | `Runtime Facts`, `Prompt/Capability Packaging`, `CI/Traceability`, `Task Package` |
| Instance candidate | `instances/*.candidate.json` | 只以`schema_ref:{identity,version,digest,activation_state:"candidate"}`引用registry条目；`activation_state=candidate-not-installed`；绑定本Spec、project facts、artifact identities和fail-closed policy | `Runtime Facts`, `Host Required-Test Adapter`, `Semantic Discrimination Adapter`, `CI/Traceability` |
| Resolve | Runtime schema resolver | 原子激活前任何resolve返回`SCHEMA_NOT_ACTIVE`/HTTP 428；不得从instance、prompt或旧002 const schema推断active。partial install、digest drift或unknown维持旧active | `Runtime Facts`, `ATDD Checkpoint`, `CI/Traceability` |

### IF-PROMPT-01 — 四角色canonical source candidate与部署readback

| 分类 | Surface / Schema | 合同 | modules |
|---|---|---|---|
| Closed sources | `louke/agents/Archer.md`、`Shield.md`、`Devon.md`、`Prism.md` | 集合恰为四项；任何第五项、遗漏、大小写alias或`.opencode`文件作为source均`PROMPT_SCOPE_DENIED` | `Prompt/Capability Packaging`, `Runtime Facts`, `CI/Traceability` |
| Bundle | `prompt-bundle.candidate.json` | `{bundle_identity,revision,activation_state:candidate-not-deployed,closed_source_set,sources:[{role,path,digest,model_binding,input_schema_ref,output_schema_ref}],transformer,deployments,supersedes,accepted_semantics,bundle_digest}`；source/model/transformer/schema/render/digest全绑定 | `Prompt/Capability Packaging`, `Runtime Facts`, `CI/Traceability`, `Task Package` |
| Transformer | `louke.board.cmd_opencode`的现有确定性render规则 | 输入四source bytes+role model binding，使用`parse_frontmatter`、`_render_passthrough_block`、`_rewrite_agent_skill_references`，输出lowercase `.opencode/agents/<role>.md`等价bytes；本轮只产生Spec-local staging record，不写active路径 | `Prompt/Capability Packaging`, `CI/Traceability` |
| Validator/readback | `louke/_tools/prompt_bundle.py` candidate扩展 | 校验四source closed set、source/transformer/model/schema/render/bundle digest及active-unchanged；当前只支持两项，故四角色正式验证为`candidate-change-required`，缺实现不能激活 | `Prompt/Capability Packaging`, `Runtime Facts`, `CI/Traceability` |
| Staging | 本Spec`prompts/staging/*.render.candidate.json` | 包含source/render/model/transformer digest和rendered content digest；路径不得在`.opencode/agents` | `Prompt/Capability Packaging`, `Runtime Facts`, `CI/Traceability` |
| Reviewer binding | `reviewer-binding.candidate.json` | `reviewer_execution_bundle`必须是先前trusted active Prism且digest不同于`reviewed_candidate_bundle`；candidate Prism不能审自己 | `Prompt/Capability Packaging`, `Test Asset Review`, `Runtime Facts` |
| Deployment readback | `deployment-readback.candidate.json` | 明确`active_unchanged=true`、当前四个deployed digest、candidate目标digest和`qualification=staging_only`；不存在active pointer不得伪报激活 | `Prompt/Capability Packaging`, `Runtime Projection`, `CI/Traceability` |
| Supersession | bundle fields/readback | 新attempt不再接受Shield-after-implementation/`M-TEST`准备、Mode B/SUT替换、Agent commit/push、Prism推进状态；Runtime authority与既有兼容语义保留 | `Prompt/Capability Packaging`, `Task Package`, `ATDD Checkpoint`, `CI/Traceability` |

## 3. M-IMPL task、checkpoint与冻结合同

### IF-ATDD-CHECKPOINT-01 — M-IMPL checkpoint command/projection

| 分类 | Surface / Signature | 合同 | modules |
|---|---|---|---|
| Shield准备 | `louke.runtime.atdd_checkpoint.prepare_shield_task(*, project_root: Path, run_id: str, attempt_id: str, baseline_identity: str, expected_run_revision: int, output_path: Path) -> Mapping[str, object]` | current M-DESIGN baseline含声明manifest/source readback及完整设计/host contracts时生成IF-TASK-01 Shield task；FR-0101不要求专用validator evidence；其它适用schema/capability gate缺失时仍blocked、不dispatch | `ATDD Checkpoint`, `Task Package`, `Design Declaration`, `Runtime Facts` |
| Shield提交 | `record_shield_submission(*, project_root: Path, task_path: Path, bundle_path: Path, red_evidence_path: Path, expected_run_revision: int) -> Mapping[str, object]` | 绑定patch/反例/runner/RED identities；测试写scope、节点及AC层不完整或RED invalid拒绝 | `ATDD Checkpoint`, `Task Package`, `Host Required-Test Adapter`, `Runtime Facts` |
| 冻结 | `freeze_test_bundle(*, project_root: Path, submission_identity: str, prism_review_path: Path, expected_run_revision: int, evidence_path: Path) -> Mapping[str, object]` | 同test revision程序证据与trusted Prism review current才freeze；任何测试/反例变更使旧review失效 | `ATDD Checkpoint`, `Test Asset Review`, `Runtime Facts` |
| Devon派发 | `prepare_devon_task(*, project_root: Path, run_id: str, attempt_id: str, frozen_bundle_identity: str, expected_run_revision: int, output_path: Path) -> Mapping[str, object]` | 只消费同baseline current freeze；包含完整设计和write/forbidden scopes；Issue单独不足 | `ATDD Checkpoint`, `Task Package`, `Runtime Facts` |
| 声明修订 | `request_declaration_revision(*, project_root: Path, task_id: str, contract_anchor: str, reason: str, expected_run_revision: int, evidence_path: Path) -> Mapping[str, object]` | contract anchor必填；成功停止旧Devon任务，test bundle=`cooldown`，依赖证据stale，return target=`M-DESIGN` | `ATDD Checkpoint`, `Failure Routing`, `Task Package`, `Runtime Facts` |
| 实现结果 | `record_implementation_result(*, project_root: Path, task_id: str, candidate_identity: str, runner_evidence_paths: Sequence[Path], expected_run_revision: int, evidence_path: Path) -> Mapping[str, object]` | 只接受task write-scope内实现、冻结测试未改、冻结signature/route/token未被直接改变、required GREEN/surface动态证据current的candidate；公开合同冲突必须走declaration revision | `ATDD Checkpoint`, `Host Required-Test Adapter`, `Design Declaration`, `Runtime Facts` |
| M-TEST闭包 | `record_m_test_closure(*, project_root: Path, candidate_identity: str, discrimination_evidence_path: Path, restored_green_evidence_path: Path, closure_evidence_path: Path, expected_run_revision: int) -> Mapping[str, object]` | 每个required AC→IF→layer→test→surface→result→mutation适用映射闭合且恢复后全绿才`m_verify_allowed=true` | `ATDD Checkpoint`, `Semantic Discrimination Adapter`, `Runtime Facts`, `Runtime Projection` |
| Projection | `ATDDCheckpointProjection` | `{checkpoint_id,stage_id:M-IMPL|M-TEST,phase,display_state:pending|running|passed|failed|attention|cooldown|stale,owner,baseline_identity,declaration_identity,test_bundle_identity|null,candidate_identity|null,runner_identity,evidence_summary,reason,impact,owning_url,available_actions,m_verify_allowed}` | `ATDD Checkpoint`, `Runtime Projection`, `Workbench Presentation` |

### IF-TASK-01 — Shield/Devon完整task manifest

| 分类 | Schema / Outlet | 合同 | modules |
|---|---|---|---|
| Common | Runtime task readback | `{task_id,role,stage_id:"M-IMPL",checkpoint,project_id,run_id,attempt_id,baseline_identity,expected_run_revision,authoritative_inputs,host_contracts,production_surfaces,targets,allowed_write_set,forbidden_write_set,output_contract,freshness,bootstrap_qualification}`；每个input含path/identity/revision/digest | `Task Package`, `ATDD Checkpoint`, `Runtime Facts` |
| Shield task | `role=Shield/checkpoint=shield_test_preparation` | 必含Story/Spec/Acceptance/Test Plan/Architecture/Interfaces/declaration manifest+source/runner+adapter contracts、required AC-layer/IF/surface bindings；allowed仅`tests/integration/v014_atdd_process_improvement`、`tests/e2e/v014_atdd_process_improvement`、`tests/fixtures/v014_atdd_process_improvement`；禁止production/design/prompt/workflow | `Task Package`, `ATDD Checkpoint`, `Host Required-Test Adapter` |
| Devon task | `role=Devon/checkpoint=devon_implementation` | 在common基础上必含frozen test/negative/RED/Prism identities、Issues、CI合同；allowed为声明文件的implementation region及设计列出的Runtime/Web/tool/runner/workflow配置；禁止冻结tests、design、requirements、prompt candidates | `Task Package`, `ATDD Checkpoint`, `Design Declaration`, `CI/Traceability` |
| Freshness | task readback | baseline/declaration/test/review/runner/adapter/write-set/output-schema任一identity变化即旧task stale；Devon不能继续消费cooldown package | `Task Package`, `ATDD Checkpoint`, `Runtime Facts` |
| Missing/conflict | task generation/read | 任一权威input缺失、digest矛盾、scope交叠不安全、只有Issue或bootstrap unvalidated schema时blocked并列出`conflicting_inputs`；Agent不得临场补政策 | `Task Package`, `ATDD Checkpoint`, `Runtime Projection` |

### IF-TEST-BUNDLE-01 — Shield测试/反例bundle及freeze readback

| 分类 | Schema / Outlet | 合同 | modules |
|---|---|---|---|
| Bundle | `tests/fixtures/v014_atdd_process_improvement/test-bundle.manifest.json` | `{bundle_identity,revision,baseline_identity,declaration_identity,runner_contract_identity,adapter_contract_identity,tests:[{node_id,path,layer,ac_ids,interface_ids,production_surface,behavior_class,initial_expectation,counterexample_ids}],counterexamples,write_scope_digest}` | `Host Required-Test Adapter`, `Test Asset Review`, `ATDD Checkpoint`, `Runtime Facts` |
| Classification | each test binding | `behavior_class=new_or_changed|inherited_unchanged`来自baseline delta；前者`initial_expectation=red`，后者可green。mtime/创建时间不参与 | `Task Package`, `Host Required-Test Adapter`, `Test Asset Review` |
| Freeze | Runtime readback | `{freeze_identity,test_bundle_identity,test_revision,red_evidence_identity,counterexample_evidence_identities,prism_review_identity,frozen_paths,frozen_digest,state:frozen|cooldown|stale}`；只有同revision formal current证据可frozen | `ATDD Checkpoint`, `Test Asset Review`, `Runtime Facts`, `Runtime Projection` |
| Protection | Devon task/gates | 修改frozen path、skip/xfail或测试manifest后旧freeze失效并返回Shield；不得让Devon改测试换GREEN | `ATDD Checkpoint`, `Task Package`, `CI/Traceability`, `Failure Routing` |

## 4. 宿主runner、真实表面、RED/GREEN与判别

### IF-HOST-RUNNER-01 — project-local required suite执行

| 分类 | Surface / Signature | 成功/失败出口 | modules |
|---|---|---|---|
| Python API | `louke.runtime.host_required_tests.execute_host_tests(*, project_root: Path, contract_path: Path, bundle_path: Path, phase: str, candidate_identity: str, evidence_path: Path) -> Mapping[str, object]` | `phase=pre-red|required-green|restored-green|closure`；只执行contract命令并规范化IF-HOST-TEST-EVIDENCE-01；不从扩展名猜工具 | `Host Required-Test Adapter`, `ATDD Checkpoint`, `Runtime Facts`, `External Stand-ins` |
| Integration command | `tests/e2e/run-project-venv integration` | discovery包括历史路径和`tests/integration/v014_atdd_process_improvement`；非零精确collection、全GREEN、无skip/xfail、teardown成功才0 | `Host Required-Test Adapter`, `CI/Traceability`, `Runtime Facts` |
| E2E command | `tests/e2e/run-project-venv e2e --profile all --runtime both -m "not v014_005_full_lifecycle"` | discovery包括`tests/e2e/v014_atdd_process_improvement`常规旅程，但必须deselect `v014_005_full_lifecycle`专用矩阵；从verified wheel安装、真实Chromium、production server command，local/global均通过才0 | `Host Required-Test Adapter`, `Workbench Presentation`, `CI/Traceability`, `Runtime Facts` |
| ATDD command | `tests/e2e/run-project-venv atdd --phase pre-red|post-green --spec v0.14-005-atdd-process-improvement --bundle PATH --evidence PATH` | candidate-change-required；pre-red按IF-VALID-RED-01，post-green按IF-DISCRIM-01；缺命令/manifest/evidence非零 | `Host Required-Test Adapter`, `Semantic Discrimination Adapter`, `ATDD Checkpoint`, `CI/Traceability` |
| Host neutral | Python Web与Node CLI fixture | contract明确language/build/runner/surface/coverage adapter；同一通用evidence schema；非Python/Web不得加载pytest/Starlette默认 | `Host Required-Test Adapter`, `External Stand-ins`, `CI/Traceability` |

### IF-HOST-TEST-EVIDENCE-01 — collection、行为、surface与动态执行

| 分类 | Schema / Outlet | 合同 | modules |
|---|---|---|---|
| Runner payload | IF-EVIDENCE-01 extension | `{phase,expected_node_ids,collected_node_ids,executed_node_ids,ac_layers:[{ac_id,required_layers,node_ids,result}],suite_results,skip_count,xfail_count,assertion_failures,infrastructure_errors,production_modules:[{logical_id,path,digest,executed,coverage_percent}],surface_invocations:[{surface_id,kind,request_or_command,result,composition_root_identity}],service_lifecycle,teardown}` | `Host Required-Test Adapter`, `Runtime Facts`, `ATDD Checkpoint`, `CI/Traceability` |
| SUT ownership | production modules/surface | Python `louke.*`必须从candidate source或installed product venv加载，不能来自tests/negative path；HTTP必须由`louke.web.app.create_app()`真实route table处理；Node从fixture production package/CLI加载 | `Host Required-Test Adapter`, `Workbench Presentation`, `CI/Traceability` |
| Behavior | assertion results | 每个required test有公开刺激和IF结果/readback；shape/symbol存在只可辅助。expected不得调用同一SUT实现计算；`assert true`无效 | `Host Required-Test Adapter`, `Test Asset Review`, `CI/Traceability` |
| Coverage floor | target modules | 每个required target module`executed=true`且coverage可测行>0；0或报告missing失败。非零coverage不能替代behavior/surface evidence | `Host Required-Test Adapter`, `Runtime Facts`, `CI/Traceability` |

### IF-VALID-RED-01 — pre-implementation RED判定

| 分类 | Input/Result | 合同 | modules |
|---|---|---|---|
| Expected RED | test bundle + runner evidence | expected/collected/executed node ids精确相等；新增/改变目标因绑定assertion失败，或声明桩以匹配IF token的`NotImplementedError`失败；回归目标保持GREEN | `Host Required-Test Adapter`, `ATDD Checkpoint`, `Test Asset Review`, `Runtime Facts` |
| Invalid RED | runner evidence | zero/missing collection、无关import/compile、fixture/setup/service/permission、skip/xfail、错误token、无关test失败或结果unknown均`result=invalid_red`，不派发Devon | `Host Required-Test Adapter`, `ATDD Checkpoint`, `Runtime Projection` |
| Surface | target test | 即使RED也必须经过真实public package/cross-module/production route/CLI；测试自建app/route table、module replacement或罐头SUT为invalid | `Host Required-Test Adapter`, `Test Asset Review`, `CI/Traceability` |

### IF-DISCRIM-01 — executable counterexample与post-GREEN判别

| 分类 | Surface / Signature | 合同 | modules |
|---|---|---|---|
| Counterexample manifest | `tests/fixtures/v014_atdd_process_improvement/counterexamples.manifest.json` | `{identity,baseline_identity,test_revision,adapter_contract_identity,cases:[{case_id,ac_ids,interface_ids,target_node_ids,production_paths,original_source_digest,patch_path,patch_digest,expected_assertion_tokens,safe:true}]}`；当前005 required changed behavior无描述性fallback | `Semantic Discrimination Adapter`, `Host Required-Test Adapter`, `Test Asset Review`, `Runtime Facts` |
| Python API | `louke.runtime.semantic_discrimination.run_discrimination(*, project_root: Path, adapter_contract_path: Path, counterexample_manifest_path: Path, candidate_identity: str, phase: str, evidence_path: Path) -> Mapping[str, object]` | `phase=pre-implementation|post-green`；仅隔离worktree/venv，验证patch scope/build/surface；返回每case `killed|survived|invalid`及原因 | `Semantic Discrimination Adapter`, `Host Required-Test Adapter`, `Runtime Facts`, `External Stand-ins` |
| Restoration API | `verify_restored_candidate(*, project_root: Path, candidate_identity: str, original_artifact_digest: str, affected_bundle_path: Path, full_bundle_path: Path, evidence_path: Path) -> Mapping[str, object]` | 验证原checkout SHA/diff、artifact digest不变，先受影响再全required GREEN；任一不确定为attention | `Semantic Discrimination Adapter`, `Host Required-Test Adapter`, `ATDD Checkpoint`, `Runtime Facts` |
| Adapter CLI | `python tools/louke_atdd_adapter.py run --phase pre-implementation|post-green --contract PATH --manifest PATH --candidate ID --evidence PATH` | candidate-change-required；exit 0仅所有case killed、sandbox teardown、original未变，post-green还要求restored GREEN；build/import/setup/无关失败不算kill | `Semantic Discrimination Adapter`, `CI/Traceability`, `Runtime Facts` |
| Isolation | evidence | temp worktree/HOME/XDG/provider namespace；patch禁止tests/contracts/workflow/runner/credential；失败/中断/restart均清理或记录recovery-needed。无法确认恢复时`result=attention`并阻止M-VERIFY | `Semantic Discrimination Adapter`, `External Stand-ins`, `Runtime Facts`, `Runtime Projection` |

### IF-TEST-HARNESS-01 — authoritative fixture准备（测试基础设施）

| 分类 | Surface / Data | 合同 | modules |
|---|---|---|---|
| Runtime fixture importer | candidate `python -m louke._tools.atdd_fixture load --workspace PATH --manifest PATH --evidence PATH` | 仅测试环境；通过Runtime公开store/application port追加合法Project/Run/attempt/evidence facts并readback，不写旧`project-state.json`、不自建route/app、不返回业务结果；生产wheel默认不暴露无授权写入口 | `Host Required-Test Adapter`, `Runtime Facts`, `External Stand-ins`, `CI/Traceability` |
| Fixture manifests | `tests/fixtures/v014_atdd_process_improvement/scenarios/*.json` | synthetic identities/credential，固定clock和expected current facts；不含预计算UI HTML/route response。载入前后有digest及teardown | `External Stand-ins`, `Runtime Facts`, `Host Required-Test Adapter` |
| Invalid usage | tests/evidence | 直接写非权威状态文件、SQLite私表、test-owned route table或页面响应来制造状态，required result无效 | `Host Required-Test Adapter`, `Test Asset Review`, `CI/Traceability` |

## 5. 失败分流、修订与stale传播

### IF-FAILURE-ROUTE-01 — failure classification与return

| 分类 | Surface / Signature | 合同 | modules |
|---|---|---|---|
| Python API | `louke.runtime.atdd_failure_routing.classify_atdd_failure(*, project_root: Path, evidence_paths: Sequence[Path], contract_paths: Sequence[Path], prism_diagnostic_path: Path | None, output_path: Path) -> Mapping[str, object]` | 只读取同baseline/test/candidate/runner identity；返回`FailureDecision`并写IF-EVIDENCE-01；identity不足/合同未决定时fail closed | `Failure Routing`, `Runtime Facts`, `Test Asset Review`, `ATDD Checkpoint` |
| `FailureDecision` | Runtime/Project Status | `{decision_id,classification:infrastructure_or_test_asset|test_contract_mismatch|implementation_or_composition|design_gap|requirement_gap|safety_attention,owner:Shield|Devon|Archer|Runtime|HumanControlledRequirements,return_target:M-IMPL:Shield|M-IMPL:Devon|M-DESIGN|M-SPEC|M-ACC|ATTENTION,contract_anchors,test_identity,candidate_identity,runner_identity,prism_diagnostic_identity|null,current,reason,recovery_url}` | `Failure Routing`, `Runtime Facts`, `Runtime Projection`, `Workbench Presentation` |
| Devon争议 | IF-TASK-01 discussion/return | 必须引用具体contract anchor和observed code behavior；无锚点不允许skip/xfail/改冻结测试。若合同未决定则仍为requirement/design gap，不默认测试正确 | `Task Package`, `Failure Routing`, `Test Asset Review`, `Runtime Projection` |
| Prism diagnostic | review result readback | 只提供绑定identity的语义诊断；Runtime持久化正式decision。诊断或输入revision变化使旧decision stale | `Test Asset Review`, `Failure Routing`, `Runtime Facts` |

### IF-REVISION-01 — cooldown、stale、重试和历史

| 分类 | Outlet | 合同 | modules |
|---|---|---|---|
| Declaration change | checkpoint/evidence | 停止旧Devon task；freeze=`cooldown`；旧RED/review/freeze/implementation/GREEN/discrimination/closure=`stale`；新声明必须重新建立manifest/source readback、production collection、valid RED和review | `ATDD Checkpoint`, `Runtime Facts`, `Runtime Projection`, `Task Package` |
| Test change | checkpoint/evidence | 新test revision必须重过counterexample、valid RED、Prism和freeze；旧review不可解锁 | `ATDD Checkpoint`, `Test Asset Review`, `Runtime Facts` |
| Implementation change | checkpoint/evidence | 新candidate重跑受影响unit、全部required integration/e2e、discrimination、restore和closure | `ATDD Checkpoint`, `Host Required-Test Adapter`, `Semantic Discrimination Adapter`, `Runtime Facts` |
| Retry | Runtime action/readback | 新attempt/evidence引用`supersedes`和source attempt，只从FailureDecision合法target继续；旧结果保留。错误owner/stale URL无状态改变 | `ATDD Checkpoint`, `Failure Routing`, `Runtime Facts`, `Runtime Projection`, `Workbench Presentation` |

## 6. Project Status HTTP/UI交互合同

### IF-PROJECT-STATUS-01 — 同一Project Status的ATDD投影

| 分类 | Surface / Schema | 合同 | modules |
|---|---|---|---|
| API | `GET /api/projects/{project_id}/status`，支持`If-None-Match` | 继承004 `ProjectStatus`并增加`atdd:ATDDStatus|null`；未变304；unknown/forbidden/stale不解析到其它Project | `Runtime Projection`, `Runtime Facts`, `Workbench Presentation`, `ATDD Checkpoint` |
| `ATDDStatus` | ProjectStatus field | `{stage_id:M-IMPL|M-TEST,current_checkpoint_id,checkpoints:[ATDDCheckpointProjection],baseline_identity,declaration_identity,test_bundle_identity|null,candidate_identity|null,runner_identity,closure_summary,attention|null,m_verify_allowed,observed_at,fresh_until}` | `Runtime Projection`, `ATDD Checkpoint`, `Runtime Facts`, `Workbench Presentation` |
| Detail API | `GET /api/projects/{project_id}/status/checkpoints/{checkpoint_id}` | `{project_id,run_id,attempt_id,run_revision,checkpoint,evidence:[ArtifactRef],failure_decision|null,history,actions,owning_url,return_url}`；历史/stale仍可读且标识，不混成current | `Runtime Projection`, `Runtime Facts`, `Failure Routing`, `Workbench Presentation` |
| Action API | `POST /api/projects/{project_id}/status/checkpoints/{checkpoint_id}/actions/{action_id}` body `{expected_run_revision,return_url}` | 只接受projection current `available_actions`中的Runtime capability；`retry|open_return|continue_m_verify`语义；旧/伪造action 409/403且不改变状态 | `Workbench Presentation`, `Runtime Projection`, `ATDD Checkpoint`, `Runtime Facts` |
| Composition root | `louke.web.app.create_app()` | 上述三route在production route table注册，handler来自`louke.web.api.project_status`；TestClient/installed server请求不得404或落到test app | `Workbench Presentation`, `Runtime Projection`, `Host Required-Test Adapter` |

### IF-PROJECT-STATUS-UI-01 — Workbench可见状态、动作与可达性

| Surface/context | 用户动作与输入 | 可见结果与可用条件 | 状态/反馈/恢复 | modules |
|---|---|---|---|---|
| `/workbench?activity=projects&project=<id>` active card | 登录Human打开当前Project；无需创建新结果页 | stage仍显示M-IMPL/M-TEST；显示current checkpoint、owner、attempt、baseline/test/candidate/runner短identity、最近evidence及owning link | loading显示读取中；running有非颜色文本+进度；证据为空显示Unavailable而非成功 | `Workbench Presentation`, `Runtime Projection`, `Runtime Facts` |
| checkpoint列表/详情 | click或Enter/Space选择；方向键/Home/End遍历 | URL保留`project,selected_attempt,checkpoint`；详情显示current与历史差异、evidence identity、surface、result | 返回owning surface后同上下文；missing/forbidden/stale显示定位错误和same-project recovery，不跳其它Project | `Workbench Presentation`, `Runtime Projection`, `Failure Routing` |
| pre-Devon状态 | Human观察Shield准备/RED/review/freeze | 任一current evidence未成立时不显示/禁用Devon实施已开始或成功；bootstrap unvalidated显示attention | failed显示owner+return target；declaration revision时显示cooldown/stale及新baseline入口 | `Workbench Presentation`, `Runtime Projection`, `ATDD Checkpoint` |
| Devon/M-TEST状态 | Human观察implementation→required GREEN→discrimination→restored GREEN→closure | 每步有current identity；只有全部passed且`m_verify_allowed=true`显示`Continue to M-VERIFY` | survived/invalid/restore不确定显示attention并禁Continue；失败/取消保留Project/test identity | `Workbench Presentation`, `Runtime Projection`, `Semantic Discrimination Adapter`, `ATDD Checkpoint` |
| Action | Human选择projection提供的Retry/return/Continue并提交current revision | running时重复动作disabled；成功刷新同Project；permission/historical只读显示原因 | conflict/stale返回current readback；重连自动刷新，revision变化提示；直接访问后续URL仍复核capability | `Workbench Presentation`, `Runtime Projection`, `ATDD Checkpoint`, `Runtime Facts` |
| Accessibility | keyboard/screen reader/zoom | 所有checkpoint、状态、owner、失败和主要动作有可访问名称；状态用文本/icon不只颜色；poll不夺焦点 | 支持004锁定`1024x768@100%`、`1280x720@100%/200% text zoom`；断连仍保留只读导航 | `Workbench Presentation`, `Runtime Projection` |
| Dirty | 只读Status | `N/A`：Status无编辑字段 | discussion/repair surface自己保留未提交输入；return_url恢复Project/attempt/checkpoint | `Workbench Presentation`, `Task Package` |

## 7. project.toml、pre-commit、trace与CI

### IF-PROJECT-RUN-01 — 宿主integration/e2e运行合同

| Layer | project.toml公开合同 | 退出/evidence | modules |
|---|---|---|---|
| Integration | `[integration].run="tests/e2e/run-project-venv integration"`；paths含005 integration/fixtures及历史资产 | exit 0仅非零、required全绿、无skip/xfail、identity/teardown证据current；否则非零 | `Host Required-Test Adapter`, `CI/Traceability`, `Runtime Facts` |
| E2E | `[e2e].run="tests/e2e/run-project-venv e2e --profile all --runtime both -m \"not v014_005_full_lifecycle\""`；paths含005 e2e/fixtures及历史资产 | runner自行构建/安装/启动/ready/teardown；通用入口不收集full-lifecycle专用矩阵；exit 0仅local/global真实Chromium旅程及evidence全部成立 | `Host Required-Test Adapter`, `Workbench Presentation`, `CI/Traceability`, `Runtime Facts` |
| Missing/drift | Runtime/Shield/CI readback | missing key/path、runner command与design不同或discovery漏005均blocked；Shield不得发明替代命令 | `Task Package`, `Host Required-Test Adapter`, `CI/Traceability` |

### IF-LIFECYCLE-01 — FR-1701确定性13阶段wordcount旅程

| 分类 | Surface / Schema | 成功/失败出口 | modules |
|---|---|---|---|
| Dedicated e2e selection | `tests/e2e/run-project-venv e2e --profile v014 --runtime local --wheel <verified-wheel> tests/e2e/v014_atdd_process_improvement/test_full_lifecycle.py -m v014_005_full_lifecycle --maxfail=1` | `--wheel`可选且由Devon扩展现有runner；CI必须传入artifact-verify核对的同digest wheel。marker必须注册；执行顺序为`success`，然后按M-START→M-MILESTONE的canonical stage顺序运行13个`fail_before_completion`变体；任一意外失败立即停止。零收集、skip/xfail、另行build Louke、90分钟超时或结果unknown非零 | `Full Lifecycle Harness`, `Host Required-Test Adapter`, `CI/Traceability`, `Runtime Facts` |
| Scenario manifest | `tests/fixtures/v014_atdd_process_improvement/full_lifecycle/scenario.manifest.json` | `{schema_version,scenario_identity,louke_release_identity,prompt_bundle_ref,agent_io_schema_ref,task_contract_refs,canonical_stages:[13 exact stage IDs],host_seed:{path,digest},agent_results:[{workflow_stage,role,session_key,dispatch_correlation_id,task_contract_digest,turn_ordinal,request_digest,path,result_digest,expected_result_schema}],human_actions:[{stage_id,surface,action_id}],external_standins,success_expectations,failures:[13],teardown}`；closed/exact order，unknown或余项失败 | `Full Lifecycle Harness`, `Replay Agent Adapter`, `Task Package`, `Runtime Facts`, `External Stand-ins` |
| Replay public API | `louke.opencode.replay.load_replay_adapter(*, manifest_path: Path, project_root: Path) -> OpenCodeAdapter` | 返回现有production `OpenCodeAdapter`协议实现；`create`按next `session_key/dispatch_correlation_id/role`建立确定instance，`send_message`核对同session correlation、turn ordinal和UTF-8 request digest后accepted，`reconcile_session`才恰好返回一次schema-valid `ProviderResult`，`list/list_messages/stream_events/stop`与同一调用ledger一致。语义键仍为`workflow_run_id,stage_id,role,task_contract_digest,turn_ordinal`；missing/extra/乱序/重复、role/task/schema/prompt/request/result digest drift或真实provider fallback抛稳定错误且不写workflow事实 | `Replay Agent Adapter`, `Task Package`, `Runtime Facts`, `External Stand-ins` |
| Production server | `lk serve --project-root <temp-host> --opencode-backend replay --opencode-replay-manifest <temp-control>/scenario.manifest.json` | existing `--opencode-backend` choices扩为`mock|real|replay`；仅`replay`时manifest必填，realpath必须是runner复制到独立temp control的regular file且digest匹配scenario；manifest与其它backend组合、symlink/缺失/drift均非零。使用installed wheel和production app/Runtime，不回退`mock|real`、不读取真实provider credential | `Replay Agent Adapter`, `Full Lifecycle Harness`, `Workbench Presentation`, `Runtime Facts`, `External Stand-ins` |
| Lifecycle evidence | IF-EVIDENCE-01 extension | `{scenario_identity,host_root,publish_sink,installed_louke:{version,wheel_digest,module_paths},project_id,workflow_run_id,attempt_id,stages:[{stage_id,ordinal,entered_at,completed_at,state,execution:enabled|disabled,precondition_refs,artifact_refs,evidence_refs,projection_revision,owner,recovery_url|null}],agent_dispatches,human_actions,release_artifacts,published_artifacts,repo_before_after,provider_call_count,cleanup}`；success要求同一run恰好13项、ordinal 1..13、无跳跃/重复/平行run、artifact链闭合 | `Full Lifecycle Harness`, `Runtime Facts`, `Runtime Projection`, `Workbench Presentation`, `Replay Agent Adapter`, `External Stand-ins`, `CI/Traceability` |
| Disabled security | success scenario的`M-SECURITY` Project Status/evidence | `stage_id=M-SECURITY,state=passed,execution=disabled`，存在`kind=stage-disabled` evidence且随后进入M-RELEASE；UI以文本“Disabled / passed-through”表达，不能隐藏该stage或伪造审计结果 | `Full Lifecycle Harness`, `Runtime Projection`, `Workbench Presentation`, `Runtime Facts` |
| Human journey | `/workbench?activity=projects&project=<id>`及projection提供的current actions | Playwright或同源public API依次提交M-START确认、需求Go/批准和publish批准，带session/CSRF/idempotency/current revision；timeline显示同一run的current stage、artifact/evidence及13/13 M-MILESTONE结果。action隐藏/禁用、running、success、failed、stale、permission、reconnect及键盘合同继承IF-PROJECT-STATUS-UI-01 | `Full Lifecycle Harness`, `Workbench Presentation`, `Runtime Projection`, `Runtime Facts` |
| Fail-each-stage | manifest中13个单一`fail_before_completion`变体 | 每个变体只通过该stage公开依赖返回失败；Project Status停在该stage，显示owner/recovery，后续stage无entered/artifact/evidence，同一run无平行替代。失败注入不得直接写状态或调用内部推进函数 | `Full Lifecycle Harness`, `Replay Agent Adapter`, `Runtime Facts`, `Runtime Projection`, `Workbench Presentation`, `External Stand-ins` |
| Isolation/teardown | temp host/control/Git/venv/HOME/publish sink及finally ledger | wordcount源码/生成artifact只在temp host，scenario/replay资产只在独立temp control，Louke从temp venv installed wheel加载；真实HOME、Louke源码仓库、Git refs/bytes和外部资源before/after不变；server/child/worktree/host/control/sink全部清理。任一污染、真实provider调用或清理不确定为attention且命令非零 | `Full Lifecycle Harness`, `Host Required-Test Adapter`, `Runtime Facts`, `External Stand-ins`, `CI/Traceability` |

### IF-PRECOMMIT-01 — 合法RED边界

| 分类 | Surface / Command | 合同 | modules |
|---|---|---|---|
| Config | `.pre-commit-config.yaml` | 保留现有Louke hook、trailing whitespace、EOF、YAML/TOML、merge conflict、large file、ruff、ruff-format、mypy；不删除宿主快速策略 | `CI/Traceability`, `Design Declaration` |
| Normal commit | `pre-commit run --all-files`/staged hook | format/lint/type、manifest/token/AC metadata和scope静态检查；不得仅因新增required test合法RED而失败，不执行integration/e2e/mutation | `CI/Traceability`, `Design Declaration`, `Task Package` |
| Readback | hook evidence | `in_sync|drifted|missing|conflict`，列existing preserved hooks；pre-commit成功不能替代Runtime/CI required evidence | `CI/Traceability`, `Runtime Projection` |

### IF-TRACE-01 — AC/layer/反例闭包

| 分类 | Surface / Command | 合同 | modules |
|---|---|---|---|
| AC closure | `python tools/check_ac_traceability.py --acceptance .louke/project/specs/v0.14-005-atdd-process-improvement/acceptance.md --tests tests --expected-count 39` | 39/39声明AC至少被测试引用，Acceptance/Spec ID一致；零测试/缺失/unknown失败 | `CI/Traceability`, `Test Asset Review`, `Runtime Facts` |
| ATDD asset check | candidate `python tools/check_atdd_assets.py --interfaces ... --test-bundle ... --counterexamples ... --evidence ...` | 每个required AC层、跨模块IF、surface、test、initial expectation、counterexample闭合；扫描skip/xfail、SUT替换、test-owned app/route、tautology；无法判定失败 | `CI/Traceability`, `Test Asset Review`, `Host Required-Test Adapter` |

### IF-CI-01 — `Louke CI / required`

| Gate | 命令/依赖 | 可观察证据与失败语义 | modules |
|---|---|---|---|
| `quality` | constraints + `pre-commit run --all-files` | hook输出；任一失败阻断；不以合法RED为失败理由 | `CI/Traceability` |
| `design-contract` | IF-REGISTRY-01、IF-PROMPT-01 validators；IF-DECLARATION-01不设置专用validator | JSON evidence；registry/prompt extra/missing/drift/unknown/inactive冒充active失败；声明通过Shield production collection/RED/review闭合 | `CI/Traceability`, `Prompt/Capability Packaging`, `Runtime Facts` |
| `ac-trace` | IF-TRACE-01，005 expected 39 | AC/layer/counterexample/anti-cheat闭包；零/漏/unknown失败 | `CI/Traceability`, `Test Asset Review` |
| `build-artifacts`/`artifact-verify` | `python -m build --wheel --sdist`+IF-RELEASE-01 | source/artifact/install/prompt/schema/route readback；不确定失败 | `CI/Traceability`, `Runtime Facts`, `Prompt/Capability Packaging` |
| `unit` | pytest unit matrix+runtime coverage`>=95%` | JUnit/coverage，零收集非成功 | `CI/Traceability`, `Runtime Facts` |
| `host-compat` | Python Web+Node CLI fixture profiles | 两栈各自runner/build/surface/coverage合同；错误default adapter必须拒绝 | `CI/Traceability`, `Host Required-Test Adapter`, `External Stand-ins` |
| `integration`/`e2e-standin` | IF-PROJECT-RUN-01 | JUnit、IF-HOST-TEST-EVIDENCE-01、browser artifacts；真实SUT/surface必需 | `CI/Traceability`, `Host Required-Test Adapter`, `Workbench Presentation`, `Runtime Facts` |
| `full-lifecycle` | IF-LIFECYCLE-01，依赖artifact-verify同digest wheel；timeout 90分钟 | `success`先行、13 failpoint按canonical stage顺序且`--maxfail=1`；stage/artifact/evidence/Project Status/replay/provider/teardown JSON及browser trace；任一stage、隔离或cleanup不确定失败 | `CI/Traceability`, `Full Lifecycle Harness`, `Replay Agent Adapter`, `Runtime Facts`, `Runtime Projection`, `Workbench Presentation`, `External Stand-ins` |
| `atdd-discrimination` | IF-DISCRIM-01 post-green command | 全case killed、sandbox cleaned、original unchanged、restored full GREEN；survived/invalid/unknown失败 | `CI/Traceability`, `Semantic Discrimination Adapter`, `Runtime Facts` |
| `install-matrix` | verified wheel + existing installers | OS/Python/local/global public version及prompt/schema readback | `CI/Traceability`, `Prompt/Capability Packaging`, `Runtime Facts` |
| Required | workflow`Louke CI`、job`required`、check`Louke CI / required` | `if:always()`严格聚合全部mandatory needs；failed/cancelled/timed_out/skipped/missing/unknown任何一个均失败 | `CI/Traceability`, `Runtime Facts` |
| Release | protected real-smoke后publish | 只发布同source SHA/digest verified wheel/sdist；required/smoke/identity/readback任一不current阻断 | `CI/Traceability`, `Runtime Facts`, `Prompt/Capability Packaging` |

### IF-RELEASE-01 — 继承的0.14.0 artifact验证

| Surface | 输入 | 成功/失败出口 | modules |
|---|---|---|---|
| Version source | `pyproject.toml:[project].version` | canonical`0.14.0`；branch`releases/0.14.0`、tag`v0.14.0`；005不定义新release identity | `CI/Traceability`, `Runtime Facts` |
| Build | `python -m build --wheel --sdist` | 恰好一个0.14.0 wheel和sdist，记录SHA-256/source SHA；失败/多余/缺失阻断 | `CI/Traceability`, `Runtime Facts` |
| Adapter | `tools/louke_python_release_adapter.py prepare|verify-dist|verify-installed`（按004锁定补齐） | 每个artifact提取版本并与source/tag比较；clean install验证`lk --version`和metadata；命令缺失/不支持/不确定非零 | `CI/Traceability`, `Runtime Facts` |
| Package readback | wheel/sdist-built wheel | 四canonical prompts、candidate registry/schema package（激活后active readback）、三个Project Status routes可读；branch/tag不能替代artifact证据 | `Prompt/Capability Packaging`, `CI/Traceability`, `Workbench Presentation` |

## 8. 接口桩锁定清单

| Token | Source path | 锁定公开声明 | modules |
|---|---|---|---|
| `IF-ATDD-CHECKPOINT-01` | `louke/runtime/atdd_checkpoint.py` | `prepare_shield_task`、`record_shield_submission`、`freeze_test_bundle`、`prepare_devon_task`、`request_declaration_revision`、`record_implementation_result`、`record_m_test_closure` | `ATDD Checkpoint`, `Task Package`, `Runtime Facts` |
| `IF-HOST-RUNNER-01` | `louke/runtime/host_required_tests.py` | `execute_host_tests(...)` | `Host Required-Test Adapter`, `ATDD Checkpoint`, `Runtime Facts` |
| `IF-DISCRIM-01` | `louke/runtime/semantic_discrimination.py` | `run_discrimination(...)`、`verify_restored_candidate(...)` | `Semantic Discrimination Adapter`, `Host Required-Test Adapter`, `Runtime Facts` |
| `IF-FAILURE-ROUTE-01` | `louke/runtime/atdd_failure_routing.py` | `classify_atdd_failure(...)` | `Failure Routing`, `Runtime Facts`, `ATDD Checkpoint` |
| `IF-PROJECT-STATUS-01` | `louke/runtime/atdd_projection.py` | `project_atdd_status(*, project_root: Path, project_id: str, observed_at: datetime | None = None) -> Mapping[str, object]` | `Runtime Projection`, `Runtime Facts`, `Workbench Presentation` |
| `IF-PROJECT-STATUS-01` | `louke/web/api/project_status.py`、`louke/web/app.py` | `async project_status(request: Request) -> Response`、`async checkpoint_detail(request: Request) -> Response`、`async checkpoint_action(request: Request) -> Response`；三个exact production routes | `Workbench Presentation`, `Runtime Projection`, `ATDD Checkpoint` |
| `IF-LIFECYCLE-01` | `louke/opencode/replay.py` | `load_replay_adapter(*, manifest_path: Path, project_root: Path) -> OpenCodeAdapter` | `Replay Agent Adapter`, `Task Package`, `Runtime Facts`, `External Stand-ins` |

以上stub只证明import/route可达，不是GREEN evidence。Devon只能替换行为体；若signature/route不可实现，必须走IF-ATDD-CHECKPOINT-01 declaration revision而非私改。
