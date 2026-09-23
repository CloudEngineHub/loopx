import {useEffect, useState} from "react";
import {fetchChatSessions, fetchLoopXMode, fetchLoopXTeamWork, readLoopXTeamWork} from "../../data/chat";
import {TeamArtifactReport, isMarkdownArtifact, type TeamArtifact} from "./team-artifact-content";

type Readback = {kind: "waiting" | "unavailable" | "multiple"} | {
  kind: "adopted"; artifact: TeamArtifact; agentId: string;
};

/** A plan links to work through the Todo identities written by its apply receipt. */
async function readAdoptedResult(goalId: string, todoIds: Set<string>): Promise<Readback> {
  const listed = await fetchChatSessions({goalId, channelId: `goal.${goalId}`});
  // A Goal channel also contains ordinary conversations. Only a session with
  // a pinned coordinator identity can own delegation operations. Inspect every
  // session before applying the bounded work-read budget; an unreadable mode
  // still makes discovery incomplete rather than silently hiding work.
  const teamSessions: typeof listed.sessions = [];
  let incomplete = false;
  for (let offset = 0; offset < listed.sessions.length; offset += 8) {
    const batch = listed.sessions.slice(offset, offset + 8);
    const modes = await Promise.allSettled(batch.map(session => fetchLoopXMode(session.session_id)));
    modes.forEach((mode, index) => {
      if (mode.status === "rejected") incomplete = true;
      else if (mode.value.settings.agent_id) teamSessions.push(batch[index]);
    });
  }
  incomplete ||= teamSessions.length > 8;
  let unavailableAdoption = false;
  let remainingPages = 8;
  const adopted = new Map<string, Extract<Readback, {kind: "adopted"}>>();
  for (const session of teamSessions.slice(0, 8)) {
    let cursor: string | undefined;
    do {
      if (!remainingPages--) return {kind: "unavailable"};
      try {
        const page = await fetchLoopXTeamWork(session.session_id, cursor);
        incomplete ||= !page.page_readback_complete;
        for (const row of page.items) {
          if (!row.operation_id || !row.todo_id || !todoIds.has(row.todo_id) || row.status !== "accepted") continue;
          const source = await readLoopXTeamWork(session.session_id, row.operation_id);
          if (source.operation_id !== row.operation_id || source.todo_id !== row.todo_id
            || source.status !== "accepted" || source.recovery_required || source.error) {
            incomplete = true;
            continue;
          }
          for (const adoption of source.adoptions ?? []) {
            if (adoption.state !== "current") {
              unavailableAdoption = true;
              continue;
            }
            if (!adoption.source_artifacts.length || !adoption.source_artifacts.every(version =>
              source.artifacts?.some(item => item.ref === version.ref && item.sha256 === version.sha256))) {
              unavailableAdoption = true;
              continue;
            }
            let verified = false;
            try {
              const consumer = await readLoopXTeamWork(session.session_id, adoption.consumer_operation_id);
              const artifact = consumer.artifacts?.find(item =>
                adoption.consumer_artifacts.some(version => version.ref === item.ref && version.sha256 === item.sha256)
                && isMarkdownArtifact(item.ref))
                ?? consumer.artifacts?.find(item =>
                  adoption.consumer_artifacts.some(version => version.ref === item.ref && version.sha256 === item.sha256));
              if (consumer.operation_id === adoption.consumer_operation_id
                && consumer.request_id === adoption.consumer_request_id
                && consumer.agent_id === adoption.consumer_agent_id
                && consumer.todo_id === adoption.consumer_todo_id
                && consumer.status === "accepted" && !consumer.recovery_required && !consumer.error && artifact) {
                const key = `${session.session_id}:${consumer.operation_id}`;
                const earlier = adopted.get(key);
                if (!earlier || (!isMarkdownArtifact(earlier.artifact.ref) && isMarkdownArtifact(artifact.ref))) {
                  adopted.set(key, {kind: "adopted", artifact, agentId: adoption.consumer_agent_id});
                }
                verified = true;
              }
            } catch { /* The recorded adoption is not a readable conclusion. */ }
            if (!verified) unavailableAdoption = true;
          }
        }
        cursor = page.has_more ? page.next_cursor ?? undefined : undefined;
        if (page.has_more && !cursor) incomplete = true;
      } catch {
        incomplete = true;
        break;
      }
    } while (cursor);
  }
  if (incomplete || unavailableAdoption) return {kind: "unavailable"};
  if (adopted.size > 1) return {kind: "multiple"};
  return adopted.values().next().value ?? {kind: "waiting"};
}

/** Return only an accepted, currently adopted report to the manager conversation. */
export function ManagerTeamResult({goalId, todoIds, zh, onOpenGoalEvidence}: {
  goalId: string; todoIds: string[]; zh: boolean; onOpenGoalEvidence: (goalId: string) => void;
}) {
  const [result, setResult] = useState<{key: string; readback: Readback} | null>(null);
  const [revision, setRevision] = useState(0);
  const todoKey = [...todoIds].sort().join(",");
  // A new read must withdraw the previous accepted report immediately. The
  // request can be slow or fail after its source acceptance has changed.
  const key = `${goalId}:${todoKey}:${revision}`;
  useEffect(() => {
    if (!goalId || !todoKey) return;
    let cancelled = false;
    void readAdoptedResult(goalId, new Set(todoKey.split(",")))
      .then(value => {if (!cancelled) setResult({key, readback: value});})
      .catch(() => {if (!cancelled) setResult({key, readback: {kind: "unavailable"}});});
    return () => {cancelled = true;};
  }, [goalId, todoKey, key, revision]);
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!document.hidden) setRevision(value => value + 1);
    }, 30_000);
    return () => window.clearInterval(timer);
  }, []);
  const readback = result?.key === key ? result.readback : null;
  if (!goalId || !todoKey) return null;
  return <section className={`personal-manager-team-result is-${readback?.kind ?? "loading"}`} aria-label={zh ? "团队结果回到管家" : "Team result returned to manager"} aria-busy={!readback}>
    {!readback ? <p role="status">{zh ? "正在核验团队结果…" : "Verifying team result…"}</p> : readback.kind === "adopted" ? <>
      <header><strong>{zh ? "团队验收结果" : "Team result"}</strong><small>{goalId} · {readback.agentId}</small></header>
      <TeamArtifactReport artifact={readback.artifact} zh={zh} heading={zh ? "依据已采用 · 结果已验收" : "Source adopted · Result accepted"}/>
    </> : <p role="status">{readback.kind === "unavailable"
      ? (zh ? "团队结果或采用证据无法核验，请到 Goal 查看版本关系。" : "Team result or adoption evidence cannot be verified; inspect versions in the Goal.")
      : readback.kind === "multiple"
        ? (zh ? "有多个已验收的下游结果，请到 Goal 选择要采用的结论。" : "Multiple downstream results are accepted; choose the conclusion in the Goal.")
      : (zh ? "团队任务已分配，尚无可核验的已采用结果。" : "Team work is assigned; no verifiable adopted result yet.")}</p>}
    <div className="personal-manager-team-result-actions">
      <button type="button" onClick={() => onOpenGoalEvidence(goalId)}>{zh ? "查看证据与任务" : "Inspect evidence and tasks"}</button>
      <button type="button" disabled={!readback} onClick={() => setRevision(value => value + 1)}>{zh ? "刷新结果" : "Refresh result"}</button>
    </div>
  </section>;
}
