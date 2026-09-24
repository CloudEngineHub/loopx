import {useEffect, useRef, useState} from "react";
import {FileText, RefreshCw} from "lucide-react";
import {
  fetchManagedGoalResults, readManagedGoalResult,
  type ManagedGoalResultPage, type ManagedGoalResultRow, type ManagedGoalResultRead,
} from "../../data/chat";
import {TeamArtifactReport} from "./team-artifact-content";

/** Goal-scoped local reports; an inventory row never stands in for exact acceptance readback. */
export function GoalManagedResults({goalId, zh}: {goalId: string; zh: boolean}) {
  const [page, setPage] = useState<ManagedGoalResultPage | null>(null);
  const [selected, setSelected] = useState<{row: ManagedGoalResultRow; read: ManagedGoalResultRead} | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const generation = useRef(0);
  const chosen = useRef<{todoId: string; sha256: string} | null>(null);
  const reader = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chosen.current = null;
    void load();
    return () => {generation.current++;};
  }, [goalId]);

  async function read(row: ManagedGoalResultRow, current: number, focus = false) {
    const result = await readManagedGoalResult(goalId, row.todo_id);
    if (current !== generation.current) return;
    if (result.todo_id !== row.todo_id || result.goal_id !== goalId ||
        result.result.sha256 !== row.sha256 || result.result.producer_agent_id !== row.producer_agent_id) {
      throw new Error(zh ? "报告版本或验收已变化" : "Report version or acceptance changed");
    }
    chosen.current = {todoId: row.todo_id, sha256: row.sha256};
    setSelected({row, read: result});
    if (focus) window.requestAnimationFrame(() => reader.current?.focus());
  }

  async function load(cursor?: string) {
    const current = ++generation.current;
    if (cursor) chosen.current = null;
    setBusy(true); setError(""); setSelected(null);
    try {
      const next = await fetchManagedGoalResults(goalId, cursor);
      if (current !== generation.current) return;
      setPage(next);
      const previous = chosen.current;
      const row = previous
        ? next.items.find(item => item.todo_id === previous.todoId && item.sha256 === previous.sha256)
        : next.items[0];
      if (previous && !row) {
        setError(zh ? "上次报告已不在当前验收结果中。" : "The previous report is no longer in current accepted results.");
      } else if (row) {
        await read(row, current);
      }
    } catch (failure) {
      if (current === generation.current) setError(`${zh ? "无法核验报告；旧内容已清除。" : "Cannot verify report; previous content was cleared."} ${String(failure)}`);
    } finally {
      if (current === generation.current) setBusy(false);
    }
  }

  async function select(row: ManagedGoalResultRow) {
    const current = ++generation.current;
    chosen.current = {todoId: row.todo_id, sha256: row.sha256};
    setBusy(true); setError(""); setSelected(null);
    try {await read(row, current, true);}
    catch (failure) {
      if (current === generation.current) setError(`${zh ? "报告或验收已变化；旧内容已清除。" : "Report or acceptance changed; previous content was cleared."} ${String(failure)}`);
    } finally {if (current === generation.current) setBusy(false);}
  }

  const artifact = selected ? {
    ref: selected.row.content_type === "text/markdown" ? "accepted-report.md" :
      selected.row.content_type === "application/json" ? "accepted-report.json" : "accepted-report.txt",
    sha256: selected.row.sha256,
    text: selected.read.text,
  } : null;
  return <section className="goal-team-results goal-managed-results" aria-label={zh ? "已验收的团队报告" : "Accepted team reports"} aria-busy={busy}>
    <header><div><h3>{zh ? "团队报告" : "Team reports"}</h3>
      <p>{zh ? "只有仍能通过当前验收的报告会出现在这里。" : "Only reports that still pass current acceptance appear here."}</p></div>
      <button type="button" disabled={busy} onClick={() => void load()}><RefreshCw size={14} aria-hidden="true"/>{zh ? "刷新" : "Refresh"}</button></header>
    {busy ? <p role="status">{zh ? "正在核验报告…" : "Verifying reports…"}</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    {page && !busy && !page.items.length ? <p>{zh ? "暂无可核验的团队报告。" : "No verifiable team reports yet."}</p> : null}
    {page && page.items.length > 0 ? <div className="goal-team-results-layout">
      <nav className="goal-team-result-list" aria-label={zh ? "选择团队报告" : "Choose a team report"}>
        {page.items.map(row => <button type="button" key={row.todo_id} disabled={busy}
          aria-pressed={selected?.row.todo_id === row.todo_id} onClick={() => void select(row)}>
          <FileText size={16} aria-hidden="true"/><span><strong>{row.title}</strong><small>{row.producer_agent_id}</small></span>
        </button>)}
        {page.next_cursor ? <button type="button" disabled={busy} onClick={() => void load(page.next_cursor!)}>
          {zh ? "下一页" : "Next page"}
        </button> : null}
      </nav>
      {artifact && selected ? <div ref={reader} tabIndex={-1} className="goal-team-result-reader">
        <TeamArtifactReport key={`${selected.row.todo_id}:${artifact.sha256}`} artifact={artifact}
          zh={zh} heading={selected.row.title}/>
        <p>{zh ? "验收任务" : "Accepted Todo"}: <code>{selected.row.todo_id}</code></p>
      </div> : null}
    </div> : null}
  </section>;
}
