# RFC: Small Kernel and Runtime Composition (v0)

- **RFC status:** Accepted, design acceptance takes effect on merge
- **Supersedes / closes:** none
- **Delivery maturity:** Proposal
- **Authors / owners:** LoopX maintainers
- **Created:** 2026-10-29
- **Last normative revision:** 2026-10-29
- **Implementation baseline:** `9cae3b28939f72fa4aadab5cfe49e19bcbdab372`
- **Related contracts:** [Distribution split](monorepo-distribution-split-v0.md), [Unified controller/executor contract](controller-executor-unified-contract-v0.md), [Session execution modes](agent-session-execution-modes-v0.md), [Overall roadmap](loopx-overall-roadmap-v0.md), [Extensions](../../reference/extensions.md)
- **Language mirror:** [中文版](small-kernel-runtime-composition-v0.zh-CN.md)

## Document map and maintenance contract

Sections 1–11 define the design and acceptance contract; section 4 records the
named implementation baseline. Section 12 records unresolved decisions, whose
recommendations are not approval. The appendix contains source evidence.
English and Chinese are semantic mirrors. Merge accepts a design basis; it
does not establish implementation, performance, host qualification or a new
default. Dated delivery evidence belongs in the [RFC ledger](ledger/README.md).

## 1. Decision summary

LoopX should have one small governance kernel, composed into **minimal** and
**standard** presets. A research configuration freezes a composition and its
experimental changes; it does not create a third governance implementation.

The kernel owns durable work admission and settlement: Goal requirements,
work identity, claims/leases, budget, stop rules, effect identity, receipts and
recovery. Hosts own model/tool execution. Capabilities supply task strategies
and domain behavior. Frontends display and submit through these same owners.

Smallness has four independent meanings: installed dependencies, loaded code,
activated services, and model-visible context. Installing standard must not
make every command load or start every capability. Minimal must still perform
a real governed Turn and recover it after interruption.

This RFC refines runtime composition under the existing distribution split
and unified work contract. It neither renames their packages nor adds another
plugin system, session protocol or roadmap. Existing defaults, mandatory work
obligations and authority remain in force until a qualified migration changes
them explicitly. No benchmark, device operation or host promotion is approved
by accepting this design.

## 2. Problem and motivation

A short CLI read should not initialize a research stack or an IM service. An
embedded managed task should not need an App session. A standard product user
still needs understandable progress, intervention, recovery and delivery back
to the original request. A benchmark needs to measure that same implementation
without importing unrelated product services or changing the native evaluator.

Package splitting alone cannot meet these needs: an installed dependency can
still be eagerly imported, an unused service can still poll, and a small
binary can still send excessive context on every model call. Conversely, a
loader alone cannot provide LoopX's durable governance semantics.

The design must support these observable journeys:

| Journey | Required outcome | Composition implication |
| --- | --- | --- |
| Bounded managed task | Start without an interactive App, execute, settle and read back the result | Minimal includes one qualified host path and durable authority |
| Long-horizon research | Produce a useful first result, then evidence-backed revisions or new outcomes as work continues | Optional planning, research and memory strategies; progress is more than elapsed time or repeated summaries |
| Two or three cooperating peers | Return evidence to the coordinator, record adoption, recover ownership after interruption | Reuse shared work/lease authority; peer lifetime and result adoption are distinct |
| App or IM request | Pause, correct, resume and receive the accepted result at the original destination | Frontends and delivery providers compose around the same work identity |
| Hardware or external operations | Execute several steps, reconcile uncertain effects, and verify stopping at the relevant boundary | An explicitly activated operation provider owns readback, interlocks and safe retry |
| Reproducible benchmark | Compare qualified product compositions with native controls and complete costs | Freeze experiment inputs; keep native runner, verifier and scoring ownership |

These are shared product requirements, not a commitment to ship every journey
or every combination at once. Content, office and engineering capabilities
use the same boundaries without becoming mandatory startup dependencies.

### Invariants

- I1. Each state transition and effect has one authority; presets cannot fork it.
- I2. Omitting an optional component causes no initialization, timer, network
  call, hook or model instruction from that component.
- I3. A missing execution prerequisite fails with actionable context before
  dispatch; it never falls back to an ungoverned execution path.
- I4. Required context remains complete and fresh; smaller prompts do not
  authorize dropping requirements, required reads or stop conditions.
- I5. Replay reconciles durable identity and external evidence before retry;
  completion, settlement and result delivery remain distinguishable.
- I6. Performance and outcome claims name the measured composition, baseline,
  environment and scope. Faster help is not evidence of better task outcomes.

## 3. Scope and non-goals

In scope: runtime ownership, explicit composition, demand loading, context
boundaries, benchmark fidelity and staged qualification for product journeys.

Non-goals: a new model loop, capability catalog, scheduler, memory database,
benchmark-native runner, storage migration, device abstraction framework or
microservice split. This proposal adds no CLI flag, package or persisted schema.
It removes no stored field. Actual configuration syntax is an implementation
decision under the existing extension and distribution contracts.

## 4. Current-system contract

On the named baseline, [entrypoint.py](../../../loopx/entrypoint.py) has a small
version route and selected native scheduler follow-ups;
[cli_runtime.py](../../../loopx/cli_runtime.py) dispatches selected commands and
retains the full-parser path for other commands. `performance-diagnosis` is
registry-optional but is not in the selected-command set. This supplies a
bounded first loading seam; it is not evidence that all startup is already lazy.

Typed domain authority is being consolidated under
[control_plane](../../../loopx/control_plane/) according to the
[TypeScript migration](typescript-control-plane-migration-v0.md). Python still
owns adapters and some existing paths. New composition work must use the
existing owner and characterize legacy behavior before moving it; it must not
silently recreate rules in a second language.

The distribution RFC owns `loopx-core`, `loopx-workspace` and optional packages.
The [three-layer protocol](../../reference/protocols/multi-agent-three-layer-minimality-v0.md)
uses “kernel” for a broader reusable layer including runner/presentation
facilities. Here, **governance kernel** means the authority boundary, while
**boot closure** means code required by a selected entrypoint. A reusable
facility can remain in that broader layer without belonging to every boot closure.

The unified controller/executor RFC owns the governed work contract. Session
modes own `managed_runtime` versus `attached_host`. The
[DSH/Pi selection RFC](harness-selection-dsh-pi-v0.md) owns host qualification;
a bounded headless adapter and a session-owning runtime have different duties.
[Benchmark toolkit](../../../loopx/capabilities/benchmark_toolkit/README.md)
owns reusable permission, concurrency and integrity support, while
[benchmark policy](../../../benchmark/README.md) keeps native execution and
evaluation with the benchmark. This RFC does not restore a second launcher.

## 5. Proposed architecture

### 5.1 Ownership and placement

| Boundary | Owner and responsibility | Excluded responsibility |
| --- | --- | --- |
| Bootstrap | Existing entrypoint/CLI route; resolve command and installed composition metadata | Goal decisions, provider activation during discovery |
| Governance kernel | Existing typed Goal, work, quota, runtime and coordination owners; admission, transition, effect, settlement and recovery rules | LLM/tool loop, task strategy, UI, transport, benchmark scoring |
| Host execution | Admitted managed or attached host provider; model calls, tools, session lifecycle and execution observations | A second work ledger or independent permission authority |
| Capability strategy | Nearest outcome capability; planning, context selection, research, recall, review | Overriding required transitions, leases, stop or budget |
| Extension lifecycle | Existing manifest, registry, compatibility and activation machinery | Another generic plugin/container framework |
| Product surface | Workspace, CLI, IM or delivery provider consumes public-safe projections and submits commands | Inferring canonical state from private source files or display text |

Placement rationale: no new capability id or provider id is introduced here.
Core governance belongs to `control_plane`; loading/lifecycle mechanics belong
to existing entrypoints and `extensions`; benchmark support stays with
`benchmark_toolkit`. A later optional host/device integration uses an existing
outcome owner when sufficient, with its independently distributed provider in
`packages/<package-id>/`. A new capability requires a real provider-neutral
caller contract, not merely an installable bundle.

Governance is a logical boundary, not a request to move every rule into one
file. Keep cohesive typed domains. A planner may recommend work or a stride;
only the owning transition decides admission and obligations. Replacing a
strategy must not turn a machine-enforced `must_attempt_work` rule into prose
guidance. Changing such a default requires its own disclosed contract change.

### 5.2 Presets and independent axes

| Composition | Required content | Explicit optional content |
| --- | --- | --- |
| Minimal | Bootstrap, existing governance implementation, one supported authority provider, one qualified execution path, compact status/result readback and recovery | Task capabilities, persistent recall, observers, connectors, workspace UI |
| Standard | The same kernel and compatible product composition for ordinary use | Activate capabilities, host integration, UI/IM services and external connectors only for the chosen workflow |
| Research configuration | A pinned minimal or standard composition plus a declared experiment overlay | Instrumentation or ablations explicitly named in the experimental design |

Minimal is a supported end-to-end composition, not a disabling flag on a
fully initialized standard runtime. A kernel library may be used for read-only
embedding without a host, but that does not qualify the executable minimal preset.
Standard is a convenience composition; installation alone grants no activation
or permission. Existing installation behavior remains until the distribution
RFC's migration gates are met.

Keep these axes independent: composition; managed/attached mode; host provider;
one/two model sessions; storage provider; benchmark arm. In particular, minimal
does not mean “attached,” standard does not require two model sessions, and
research does not mean “ungoverned.” Publish only tested combinations. Preserve
the session-mode RFC's defaults and explicit mode admission; do not silently
change a binding's execution owner when changing composition.

### 5.3 Resolve, load, activate, provide context

1. **Resolve:** read local versioned metadata generated at build/install or
   explicit extension registration. Top-level help, command listing and unknown
   command rejection must not scan repositories, import every provider or use
   the network. Duplicate registrations and stale/incompatible metadata are
   reported; precedence is explicit, never import-order dependent.
2. **Load:** import the selected command and its dependency closure. Detailed
   command help may load its own parser, but not activate execution services.
   Optional imports stay behind their owning route, including fallback paths.
3. **Activate:** validate installed/enabled/ready state and scoped permissions,
   then start required services through their existing lifecycle owner. Missing
   optional code reports how to install/enable it. Missing required authority
   or runtime fails closed. Kernel import/help must not require Node; effectful
   commands retain the distribution RFC's typed `node_unavailable` boundary.
4. **Provide context:** render the existing governed work contract for the
   selected work and executor. Reuse full-first, differential continuation and
   recovery semantics from the unified controller/executor design. Required
   reads and source completeness remain binding.

Context reuse must be invalidated by relevant source/requirement revisions,
session generation changes, compaction or lost acknowledgements. A smaller
packet cannot be treated as proof the executor has the prior context. Recover
through the owning contract when continuity is unknown. Capability instructions
are supplied when applicable; authority is never inferred from prompt text.

Optional observers consume committed events or bounded projections. Their
latency must not enter admission/settlement transactions unless the existing
contract explicitly requires their receipt. Batch best-effort telemetry only;
do not defer authoritative receipt persistence, weaken fsync/transaction
guarantees or cache stale permission/lease decisions to meet a timing target.

### 5.4 Durable lifecycle and external effects

Use existing Goal/Agent/work/Turn identities, revisions, leases, effect ids and
receipts through the unified work contract. Resolve composition, verify
requirements and authority, admit work, execute through the bound host, validate
and persist evidence, settle once, then deliver/read back through the owning
channel. Each step uses its existing legal transitions and replay rules;
this description adds no competing status enum or transaction coordinator.

An executor crash, a lost effect acknowledgement and a lost result-delivery
acknowledgement are different recovery cases. An operation provider must expose
whether an effect can be reconciled and retried safely. Unknown external state
holds further dependent effects for readback or intervention; “not observed”
does not mean “not executed.” Device idempotency, physical interlocks and
compensation remain provider responsibilities, not invented kernel guarantees.

Model cancellation, process termination and confirmed device stop are separate
facts. A stopped model must not produce a “device stopped” claim without device
evidence. Providers needing persistent supervision cannot be unloaded while
effects are unresolved. Result acceptance, transport delivery and the user's
readback must also retain their existing distinct evidence.

### 5.5 Benchmark uses the product implementation

Follow the [long-horizon research program](long-horizon-harness-benchmark-research-program-v0.md):
native/plain controls, passive observation, governed execution and ablations
have explicit identities. A native control receives no LoopX instructions or
hooks. Passive observation must qualify non-interference. Governed arms use
the same qualified composition and transitions as product tasks; an ablation
that changes governance is a named experimental variant, never a product default.

Freeze product/host versions, resolved composition, model and sampling settings,
skills/tools, initial state, budget, checkpoint/recovery policy, dataset and
verifier versions. Scope memory by run/arm and prohibit cross-arm contamination.
Report controller, executor, compaction, retry, recovery and human-intervention
costs as well as task outcomes. Native runners/verifiers retain task semantics
and scoring. Performance work cannot bypass toolkit permission/integrity checks
or publish raw tasks, trajectories or verifier logs as public product evidence.

Long-horizon product qualification additionally needs evidence that later work
improves an already useful initial result or changes a decision. Deliberately
weakening the initial result, adding more text or running longer is not progress.

## 6. Alternatives and design choices

| Alternative | Decision and trade-off |
| --- | --- |
| Only split packages or add lazy imports | Useful first slices; insufficient to define activation, authority and context boundaries |
| Separate minimal and standard engines | Rejected: duplicates transitions and invalidates product/benchmark parity |
| Make every rule a plugin | Rejected: budget, stop, lease and settlement could disappear with a preset |
| Adopt an upstream agent runtime as the LoopX kernel | Rejected: upstream model execution can be a provider, but does not replace LoopX work authority |
| One mandatory daemon or remote service | Not required: adds lifecycle and deployment cost to bounded local use; any daemon remains under its existing RFC |

Pi demonstrates a small agent core with tool/event execution and explicit
context transformation separate from the coding product. DSH demonstrates
shared runtime composition through multiple presets and a self-contained
minimal SDK bundle. At the pinned revision, DSH web minimal and standard use
the same agent-preset package with different plugin lists; minimal includes
persistent shell, image reading and compaction. Its SDK minimal also supplies
working-directory state and persistence with optional configured MCP resources.
These are composition examples, not evidence that DSH has exactly two engines
or that LoopX's headless adapter and DSH plugin correspond to those presets.
Borrow the explicit boundaries, without adopting Cordis, upstream permission
defaults or a new LoopX model loop. Pinned sources are in Appendix A.

## 7. Safety, privacy, and compatibility

No existing permission or mandatory gate becomes optional through composition.
Host availability, extension installation and runtime capability declarations
are observations, not grants. Keep Goal, Agent, workspace and delivery scopes
through every provider call; resolve secrets through the existing provider
boundary. Public projections exclude private source content and local artifacts.

No schema/field removal is proposed. Preserve known readers/writers and external
imports for their documented compatibility windows. Unmigrated CLI routes keep
the existing fallback until command parity qualifies their replacement. Reject
unsupported version/provider combinations before dispatch; never run two writers
against one binding to make mixed-version rollout appear available.

## 8. Migration and rollback

First characterize CLI parsing, output, errors, required reads and effect
behavior. Move one cohesive route and update active callers; remove an internal
bridge only after its real callers migrate. Do not migrate storage or weaken
durability as a side effect of loading work.

Introduce executable minimal as opt-in with an explicit resolved composition
readback. Before switching an active binding, check compatibility, quiesce its
owner and reconcile outstanding effects. Validate the new owner/readback before
resuming; never hot-swap across an active lease. Roll back to the previous
qualified composition after the same reconciliation. Keep durable state intact.
Any later irreversible data change needs a separate migration/export gate.

Standard adoption requires the product journey gates below. Retire the full
parser fallback only after all supported commands have migrated and global
options, help, errors and exit codes preserve compatibility. Default changes
require release notes and an explicit owner decision; this RFC makes none.

## 9. Validation and acceptance

These rows are proposed acceptance criteria, not claims of passing evidence.
Deterministic fixtures cover semantics independently of observed implementation
output. Live, performance and promotion evidence are reported separately.

| Id / claim | Test or evidence | Required result | Boundary |
| --- | --- | --- | --- |
| A1 / demand loading | Import/process/network tracing for import, help, listing, unknown command and a selected route, under both presets | Only declared dependency closure; no optional activation | Does not prove execution performance |
| A2 / authority parity | Characterization and negative tests for requirements, stale claims, stop, budget, replay and settlement | Identical legal/illegal transitions in both presets, exactly one settlement | No authority bypass in minimal |
| A3 / CLI compatibility | Differential supported-command corpus, including fallback and missing Node/provider cases | Stable parsing, output contract, exit codes and actionable failures | Unmigrated routes are explicitly listed |
| A4 / managed minimal | One real managed task, injected interruption, restart, evidence validation and result readback | Same identity, reconciled effect, no duplicate work or charge; accepted result reachable | One qualified host is enough initially; mock-only execution is insufficient |
| A5 / context continuity | Initial context, unchanged continuation, source revision, compaction and lost-ACK cases | Complete required context or explicit recovery; stale context rejected | Token reduction measured separately |
| A6 / standard journey | Original App/IM request, correction/pause, resume, completion and return | One execution owner; visible accepted result and costs; no silent destination change | Each frontend/provider qualifies separately |
| A7 / research and peers | Useful initial result followed by evidence-backed improvement; peer result return and adoption after owner recovery | New outcome or justified decision revision with attributable evidence | More time, peers or prose alone cannot pass |
| A8 / benchmark fidelity | Frozen matched runs, native/passive/governed boundaries, memory isolation and full cost ledger | Native semantics intact; C0–C4 evidence follows the research/diagnostics owners | No score or causal benefit is claimed by this RFC |
| A9 / physical effects | Simulator/fault injection, then explicitly authorized provider-specific live qualification | Lost ACK reconciled, duplicate actuation prevented where guaranteed, device stop independently confirmed | No universal exactly-once or emergency-stop guarantee |
| A10 / overhead | Repeated paired cold-process and warm-path measurements on a named environment | Report median/p95, RSS, modules, file I/O, Node startup/IPC, bytes and model tokens; no durability regression | M0 sets numeric budgets; no paid task run required for CLI baselines |

Candidate local-development targets are import below 50 ms, top-level help below
100 ms and selected command help below 200 ms at p95. They are D3 proposals,
not verified results or portable CI thresholds. Define interpreter startup and
cache conditions, sample count and machine/runtime versions before adopting
them. Measure real status/admission/settlement latency separately on
representative small and large state, including SQLite contention/recovery;
do not apply a CLI-help target to those operations or subtract their required I/O.

## 10. Operational contract

Readback should explain the resolved composition and versions, selected host
and session mode, required versus optional providers, activation/readiness and
the reason a component was loaded. Reuse current diagnostics/projection owners;
do not introduce another status database. Missing prerequisites, incompatible
metadata, stale authority and uncertain effects must remain distinguishable.

Record startup and Turn overhead separately. Optional observer failure is
visible without rewriting committed execution results; mandatory delivery or
evidence receipt failure remains governed by its owner. Capacity limits and
backpressure belong to the existing work/host/provider contracts. Operator
recovery reconciles persisted receipts and provider readback before resuming.

## 11. Normative delivery plan

These slices fit the existing roadmap's runtime, distribution and product
streams; they do not establish a parallel program or require a repository-wide
rewrite before a local performance improvement can ship.

| Milestone | Shipped behavior | Entry gate | Exit evidence | Rollback |
| --- | --- | --- | --- | --- |
| M0 / one loading seam | Selected `performance-diagnosis` route and measured loading boundary | Current-route characterization; owner/dependency map; D3 measurement decision | A1/A3 for this route, A10 baseline, no unrelated imports or behavior change | Revert route extraction |
| M1 / executable minimal | One qualified managed governed task with durable restart/result readback | D1 composition contents and D2 host/provider choice; existing authority contracts | A1–A5 and A10 for this supported combination | Explicit return to previous qualified composition |
| M2 / standard journey | Standard resolves the same kernel and activates only a chosen product workflow | M1; existing session/frontend admission | A2/A5/A6/A10 including cold install and feature-off parity | Disable the opt-in composition and retain state |
| M3 / research qualification | Matched product-path experiment and one long-horizon/peer journey | M1 or M2 for the selected surface; frozen design and separate run authorization | A7/A8, complete cost and privacy review, existing C0–C4 gates | Retire experimental overlay; retain bounded evidence |
| M4 / external operation provider | One real caller with provider-specific effect reconciliation and stop evidence | D4; named device/operation owner and explicit operation authorization | A9 plus inherited governance gates | Quiesce/reconcile provider before disabling |

M0 does not qualify the kernel. M3 and M4 are optional qualification branches;
they need not block a qualified CLI or managed task. No unused provider,
configuration field, framework or generic test matrix is added ahead of its
first real caller. Each PR records the bounded refactor considered, applied
or deferred and its compatibility evidence.

## 12. Open decisions

| Id / owner | Options and recommendation | Evidence needed / decision point |
| --- | --- | --- |
| D1 / distribution and runtime maintainers | Map presets to the accepted distribution scheme; recommend opt-in minimal and standard as the eventual compatibility composition, without choosing a new default now | Exact installed/load/activation closures and upgrade/readback contract before M1 packaging |
| D2 / host and authority maintainers | Select the first managed host and supported storage combination from existing providers; recommend the smallest already qualifying path, with DSH/Pi judged by the existing selection RFC | A4 host/session continuity and authority recovery evidence before M1 exit; no universal host claim |
| D3 / performance maintainers | Adopt machine-specific p95 budgets or relative regression limits; recommend the candidate budgets plus explicit measurement conditions | Reproducible baseline before M0 exit; real Turn budget derived independently |
| D4 / operation-provider owner | Choose one concrete external-operation caller, or defer physical qualification; recommend no generic device framework before a caller exists | Scope, idempotency/readback/stop contract and authorization before M4 |

Approval must be recorded through the corresponding reviewed decision; a
recommendation, implementation progress or silence cannot close a decision.

## Appendix A: Source evidence (non-normative)

| Evidence | Pinned source | Supported claim and limit |
| --- | --- | --- |
| E1 / LoopX | Implementation baseline above; linked entrypoint, CLI and owning contracts in section 4 | Existing seams and ownership only; no new performance measurement |
| E2 / DSH | [`minimal.patch.yml`](https://github.com/deepseek-ai/deepseek-harness/blob/f3803c96974ad4a94195fb97e5c637e9c2a3afe3/packages/bundle/web-app/presets/minimal.patch.yml), [`standard.patch.yml`](https://github.com/deepseek-ai/deepseek-harness/blob/f3803c96974ad4a94195fb97e5c637e9c2a3afe3/packages/bundle/web-app/presets/standard.patch.yml), [`sdk-minimal`](https://github.com/deepseek-ai/deepseek-harness/blob/f3803c96974ad4a94195fb97e5c637e9c2a3afe3/packages/bundle/sdk-minimal/README.md) | Shared preset composition and a self-contained SDK bundle; not a LoopX host qualification or permission recommendation |
| E3 / Pi | [`agent` core](https://github.com/badlogic/pi-mono/blob/f14813e96510a7cf7562a120e809c6a134af073d/packages/agent/README.md) | Agent/tool/event core with `transformContext`, `convertToLlm`, `prepareRequest` and `finishTurn` seams; no LoopX authority or performance claim |

No live benchmark or hardware operation was performed for this proposal.
