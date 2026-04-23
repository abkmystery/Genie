import type { ChatResponse, GuidedTaskStatus, TraceEvent } from "@genie/contracts";

interface DebugPanelProps {
  response: ChatResponse | null;
  traceEvents: TraceEvent[];
  error: string | null;
  guidedStatus?: GuidedTaskStatus | null;
}

export function DebugPanel({ response, traceEvents, error, guidedStatus }: DebugPanelProps) {
  return (
    <section className="tab-section">
      <div className="section-header">
        <div>
          <h3>Debug Trace</h3>
          <p>Trace id, provider used, step timings, and surfaced errors for Phase 1 debugging.</p>
        </div>
      </div>
      {error ? <p className="warning-banner">{error}</p> : null}
      {response ? (
        <div className="diagnostics-card">
          <p>
            <strong>Trace:</strong> {response.trace_id}
          </p>
          <p>
            <strong>Provider:</strong> {response.provider_used}
          </p>
          <p>
            <strong>Warnings:</strong> {response.warnings.join(", ") || "None"}
          </p>
        </div>
      ) : (
        <p className="empty-copy">Run a request to populate the debug trace.</p>
      )}

      {guidedStatus?.session ? (
        <div className="diagnostics-card">
          <p>
            <strong>Guided task:</strong> {guidedStatus.session.title}
          </p>
          <p>
            <strong>Status:</strong> {guidedStatus.session.status}
          </p>
          <p>
            <strong>Current step:</strong> {guidedStatus.current_step?.instruction_text ?? "None"}
          </p>
          <p>
            <strong>Grounding:</strong> {guidedStatus.latest_grounding?.reason ?? "None"}
          </p>
          <p>
            <strong>Progress:</strong> {guidedStatus.progress_state?.reason ?? "No progress signal yet"}
          </p>
        </div>
      ) : null}

      <div className="trace-list">
        {traceEvents.map((event) => (
          <article key={event.id} className="trace-card">
            <strong>{event.type}</strong>
            <p>{event.message}</p>
            <small>{new Date(event.created_at).toLocaleTimeString()}</small>
          </article>
        ))}
      </div>
    </section>
  );
}
