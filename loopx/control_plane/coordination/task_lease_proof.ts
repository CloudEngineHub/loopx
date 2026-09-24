/** Current nonterminal mutation proof. Admission stays in the lifecycle owner;
 * this boundary never acquires, renews, releases or transfers a lease. */
import type {JsonObject} from "../effect_program.ts";
import {requireJsonObject} from "../runtime_decode.ts";
import {EffectRuntimeRequestError} from "../effect_runtime_errors.ts";
import {parseIsoTimestamp} from "../runtime_timestamp.ts";
import {leaseEpoch} from "../work_items/task_lease_acquire.ts";
import {evaluateCoordinationTerminalFence, COORDINATION_TERMINAL_FENCE_REQUEST_SCHEMA} from "./todo_lifecycle_decision.ts";

export interface TaskLeaseProof {
  idempotency_key: string;
  expected_version: number;
}

export function decodeTaskLeaseProof(value: unknown): TaskLeaseProof | null {
  if (value == null) return null;
  const proof = requireJsonObject(value, "lease_proof");
  if (Object.keys(proof).some(key => key !== "idempotency_key" && key !== "expected_version")) {
    throw new EffectRuntimeRequestError("lease_proof accepts only idempotency_key and expected_version");
  }
  if (typeof proof.idempotency_key !== "string" || !proof.idempotency_key.trim() ||
      proof.idempotency_key !== proof.idempotency_key.trim() ||
      typeof proof.expected_version !== "number" || !Number.isSafeInteger(proof.expected_version) || proof.expected_version < 1) {
    throw new EffectRuntimeRequestError("lease_proof requires an unpadded execution key and positive safe-integer version");
  }
  return {idempotency_key: proof.idempotency_key, expected_version: proof.expected_version};
}

export function evaluateCanonicalTaskLeaseProof(input: {
  todo: JsonObject; lease: JsonObject | undefined; handoff_mode: string;
  actor_agent_id: string | null; registered_agents: readonly string[];
  lease_idempotency_key: string | null; lease_expected_version: number | null; now: Date;
}) {
  const {lease} = input;
  if (!(input.now instanceof Date) || !Number.isFinite(input.now.valueOf())) {
    throw new EffectRuntimeRequestError("lease proof requires a valid transaction clock");
  }
  const expires = lease === undefined ? null :
    typeof lease.expires_at === "string" ? parseIsoTimestamp(lease.expires_at) : null;
  if (lease?.status === "active" && expires === null) {
    throw new EffectRuntimeRequestError("active lease expiry is invalid");
  }
  const decision = evaluateCoordinationTerminalFence({
    schema_version: COORDINATION_TERMINAL_FENCE_REQUEST_SCHEMA,
    todo: input.todo, registered_agents: input.registered_agents,
    actor_agent_id: input.actor_agent_id,
    // Retained execution lineage must not become an unfenced metadata edit.
    handoff_mode: lease !== undefined ? "hard_lease" : input.handoff_mode,
    lease: lease === undefined ? null : {...lease, present: true,
      active: lease.status === "active" && expires !== null && expires > input.now,
      lease_epoch: leaseEpoch(lease)},
    lease_idempotency_key: input.lease_idempotency_key,
    lease_expected_version: input.lease_expected_version,
    allow_user_gate_auto_acquire: false, delegated_authority: false,
    require_active_when_fence_supplied: true,
  });
  // Strip the terminal owner's release proposal: callers receive only a
  // decision, so an observation cannot accidentally apply terminal effects.
  return {outcome: decision.outcome, code: decision.code};
}
