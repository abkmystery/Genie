import type { GuidedTaskStatus } from "@genie/contracts";

interface GuidedTaskCardProps {
  status: GuidedTaskStatus | null;
  showDebugLabels: boolean;
  onMarkDone(): Promise<void>;
  onNextStep(): Promise<void>;
  onRescan(): Promise<void>;
  onCantFind(): Promise<void>;
  onPauseToggle(): Promise<void>;
  onStop(): Promise<void>;
}

export function GuidedTaskCard({
  status,
  showDebugLabels,
  onMarkDone,
  onNextStep,
  onRescan,
  onCantFind,
  onPauseToggle,
  onStop,
}: GuidedTaskCardProps) {
  if (!status?.session || !status.plan || !status.current_step || ["completed", "stopped"].includes(status.session.status)) {
    return null;
  }

  const stepNumber = status.current_step.order_index + 1;
  const totalSteps = status.plan.estimated_steps;
  const paused = status.session.status === "paused";
  const needsAttention = status.session.status === "needs_attention";

  return (
    <section className={`guidance-card ${needsAttention ? "warning" : ""}`}>
      <div className="guidance-header">
        <div>
          <strong>{status.plan.title}</strong>
          <p>
            Step {stepNumber} of {totalSteps}
          </p>
        </div>
        <span className="context-pill">{paused ? "Paused" : status.session.status.replace("_", " ")}</span>
      </div>

      <p className="guidance-instruction">{status.current_step.instruction_text}</p>
      <p className="guidance-target">
        <strong>Target:</strong> {status.current_step.target_description}
      </p>
      {status.latest_grounding ? (
        <p className="guidance-reason">
          {status.latest_grounding.reason}
          {showDebugLabels ? ` (${Math.round(status.latest_grounding.confidence * 100)}%)` : ""}
        </p>
      ) : null}
      {showDebugLabels && status.progress_state ? (
        <p className="guidance-reason">
          Progress: {status.progress_state.state}
          {` (${Math.round(status.progress_state.confidence * 100)}%)`}
          {status.progress_state.reason ? ` - ${status.progress_state.reason}` : ""}
        </p>
      ) : null}
      {status.recovery_options.length ? (
        <div className="guidance-recovery">
          {status.recovery_options.map((option) => (
            <p key={option}>{option}</p>
          ))}
        </div>
      ) : null}

      <div className="inline-actions">
        <button type="button" onClick={() => void onMarkDone()}>
          Mark Done
        </button>
        <button type="button" onClick={() => void onNextStep()}>
          Next Step
        </button>
        <button type="button" onClick={() => void onRescan()}>
          Re-scan
        </button>
        <button type="button" onClick={() => void onCantFind()}>
          I can&apos;t find it
        </button>
        <button type="button" onClick={() => void onPauseToggle()}>
          {paused ? "Resume" : "Pause"}
        </button>
        <button type="button" className="danger-button" onClick={() => void onStop()}>
          Stop Guidance
        </button>
      </div>
    </section>
  );
}
