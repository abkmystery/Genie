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
          <p>Trace id, provider used, step timings, and surfaced errors for development debugging.</p>
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
          {response.provider_diagnostics ? (
            <>
              <p>
                <strong>Provider status:</strong> {response.provider_diagnostics.provider_status}
              </p>
              <p>
                <strong>Live model:</strong> {response.provider_diagnostics.live_model_name ?? "Unknown"}
              </p>
              {response.provider_diagnostics.fallback_reason ? (
                <p>
                  <strong>Fallback:</strong> {response.provider_diagnostics.fallback_reason}
                </p>
              ) : null}
              {response.provider_diagnostics.last_model_error ? (
                <p>
                  <strong>Last model error:</strong> {response.provider_diagnostics.last_model_error}
                </p>
              ) : null}
            </>
          ) : null}
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
          {guidedStatus.telemetry ? (
            <>
              <p>
                <strong>Screen relevance:</strong> {guidedStatus.telemetry.screen_relevance ?? "unknown"}
              </p>
              <p>
                <strong>Decision:</strong> {guidedStatus.telemetry.step_decision ?? "unknown"}
              </p>
              <p>
                <strong>Bbox source:</strong> {guidedStatus.telemetry.target_bbox_source ?? "unknown"}
              </p>
            </>
          ) : null}
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
