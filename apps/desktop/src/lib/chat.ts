import type { ActivityStatusResponse, GuidedTaskStatus } from "@genie/contracts";

interface BasicMessage {
  role: "user" | "assistant";
  text: string;
}

export function buildContextLabel({
  screenShareEnabled,
  hasRegion,
  attachmentCount,
}: {
  screenShareEnabled: boolean;
  hasRegion: boolean;
  attachmentCount: number;
}) {
  const labels = [];
  labels.push(screenShareEnabled ? "screen on" : "screen off");
  if (hasRegion) labels.push("region attached");
  if (attachmentCount) labels.push(`${attachmentCount} attachment${attachmentCount === 1 ? "" : "s"}`);
  return labels.join(" · ");
}

export function isGuidancePrompt(value: string): boolean {
  const lowered = value.trim().toLowerCase();
  return [
    "guide me through",
    "show me where to click",
    "help me do this step by step",
    "point to the next step",
    "walk me through this",
    "tell me exactly where to click",
    "guide me",
  ].some((phrase) => lowered.includes(phrase));
}

export function resolveGuidanceGoal(goal: string, messages: BasicMessage[]) {
  const trimmed = goal.trim();
  const genericPrompts = new Set(["guide me", "walk me through this", "show me where to click", "help me do this step by step"]);
  if (!genericPrompts.has(trimmed.toLowerCase())) {
    return trimmed;
  }
  const priorUserMessage = [...messages]
    .reverse()
    .find((message) => message.role === "user" && message.text.trim().toLowerCase() !== trimmed.toLowerCase());
  if (!priorUserMessage) {
    return trimmed;
  }
  return `Guide me through this goal: ${priorUserMessage.text.trim()}`;
}

export function formatGuidedTaskMessage(status: GuidedTaskStatus | null): string {
  if (!status?.session || !status.plan || !status.current_step) {
    return "Guided Task mode started, but I could not build the first grounded step yet.";
  }
  const lines = [
    `Guided Task: ${status.plan.title}`,
    `Step ${status.current_step.order_index + 1} of ${status.plan.estimated_steps}: ${status.current_step.instruction_text}`,
  ];
  if (status.latest_grounding?.success && status.latest_grounding.target_label) {
    lines.push(`I am pointing to: ${status.latest_grounding.target_label}.`);
  } else if (status.latest_grounding?.reason) {
    lines.push(status.latest_grounding.reason);
  }
  if (status.recovery_options.length > 0) {
    lines.push("Use Re-scan, Mark Done, or I can't find it if the target needs another pass.");
  }
  return lines.join("\n");
}

export function formatGuidedTaskCompletion(status: GuidedTaskStatus | null): string {
  if (!status?.session || !status.plan) {
    return "Guided task completed.";
  }
  return [
    `Completed: ${status.plan.title}`,
    `Finished ${status.plan.estimated_steps} step${status.plan.estimated_steps === 1 ? "" : "s"}.`,
    "You can start another guided task whenever you want.",
  ].join("\n");
}

export function formatActivitySummary(summary: NonNullable<ActivityStatusResponse["summary"]>) {
  const lines = [summary.summary_text.trim()];
  if (summary.steps.length > 0) {
    lines.push("");
    lines.push(
      ...summary.steps.map((step, index) => {
        const cleaned = step.replace(/^\s*(?:[-*]|\d+[.)]|step\s*\d+:?)\s*/i, "").trim();
        return `Step ${index + 1}: ${cleaned}`;
      }),
    );
  }
  return lines.join("\n").trim();
}
