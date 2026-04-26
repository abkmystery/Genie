export type ProviderProfileId = "demo" | "local" | "custom";

export interface ProviderCapabilities {
  supports_screen_input: boolean;
  supports_stt: boolean;
  supports_tts: boolean;
}

export interface ProviderProfile {
  id: ProviderProfileId;
  display_name: string;
  description: string;
  transport: "gateway" | "http" | "mock";
  api_style?: "genie_gateway" | "openai_compatible";
  backend_base_url: string;
  model_name: string;
  timeout_ms: number;
  capabilities: ProviderCapabilities;
  credentials_required: boolean;
  credentials_stored_locally: boolean;
  provider_mode?: "demo" | "local" | "custom";
  demo_source_order?: Array<"bundled_file" | "remote_file" | "offline_mock">;
  remote_demo_file_url?: string;
  remote_demo_file_format?: "json" | "text";
  default_model?: string;
}

export interface ProviderConfig extends ProviderProfile {
  endpoint_override?: string | null;
  token_present?: boolean;
}

export type ProviderRuntimeStatus =
  | "live_gemma"
  | "fallback_mock"
  | "local_not_ready"
  | "endpoint_error"
  | "unknown";

export interface ProviderDiagnostics {
  provider_status: ProviderRuntimeStatus;
  provider_source?: string | null;
  live_model_name?: string | null;
  fallback_reason?: string | null;
  last_model_error?: string | null;
  latency_ms?: number | null;
}

export interface SourceRecord {
  id: string;
  filename: string;
  content_type: string;
  path: string;
  status: "indexed" | "failed" | "processing";
  size_bytes: number;
  chunk_count: number;
  error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface SourceChunk {
  id: string;
  source_id: string;
  ordinal: number;
  text: string;
  locator?: string | null;
  metadata: Record<string, string | number | boolean | null>;
}

export interface AttachmentRecord {
  id: string;
  conversation_id: string;
  filename: string;
  content_type: string;
  status: "indexed" | "failed";
  chunk_count: number;
  error?: string | null;
  created_at: string;
}

export interface EvidenceItem {
  id: string;
  label: string;
  kind: "source" | "screen" | "region";
  quote?: string | null;
  locator?: string | null;
  score?: number | null;
}

export interface ScreenCaptureRef {
  id: string;
  path: string;
  width: number;
  height: number;
  mode: "native" | "simulated";
  captured_at: string;
  ocr_text?: string | null;
  summary?: string | null;
}

export interface RegionSelection {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface TraceEvent {
  id: string;
  trace_id: string;
  type:
    | "REQUEST_RECEIVED"
    | "PROFILE_RESOLVED"
    | "SOURCE_PARSED"
    | "SOURCE_INDEXED"
    | "SCREEN_CAPTURED"
    | "REGION_CAPTURED"
    | "CONTEXT_BUILT"
    | "RETRIEVAL_COMPLETED"
    | "MODEL_CALLED"
    | "RESPONSE_RENDERED"
    | "RECORDING_STARTED"
    | "RECORDING_FRAME_CAPTURED"
    | "RECORDING_STOPPED"
    | "SUMMARY_GENERATED"
    | "GUIDED_TASK_STARTED"
    | "TASK_PLAN_CREATED"
    | "STEP_GROUNDED"
    | "STEP_GROUNDING_FAILED"
    | "OVERLAY_RENDERED"
    | "STEP_COMPLETION_DETECTED"
    | "STEP_CONFIRMED_BY_USER"
    | "STEP_ADVANCED"
    | "GUIDED_TASK_STOPPED"
    | "GUIDED_TASK_ERROR"
    | "ERROR_RAISED";
  message: string;
  metadata: Record<string, unknown>;
  created_at: string;
  duration_ms?: number | null;
}

export interface ErrorEnvelope {
  code: string;
  message: string;
  trace_id?: string | null;
  details?: Record<string, unknown> | null;
}

export interface SettingsState {
  active_profile_id: ProviderProfileId;
  tts_enabled: boolean;
  screen_share_enabled?: boolean;
  activity_recording_enabled?: boolean;
  activity_sampling_hz?: number;
  activity_max_duration_seconds?: number;
  guided_task_enabled?: boolean;
  guided_overlay_style?: "arrow_only" | "highlight_only" | "arrow_pulse";
  guided_auto_advance_sensitivity?: number;
  guided_completion_mode?: "conservative" | "balanced";
  guided_max_planning_steps?: number;
  guided_show_debug_labels?: boolean;
  secure_storage_warning?: string | null;
  custom_endpoint?: string | null;
  custom_token_present?: boolean;
  local_endpoint?: string | null;
  local_token_present?: boolean;
  local_model?: string | null;
  local_model_path?: string | null;
  custom_model?: string | null;
  demo_model?: string | null;
  onboarding_complete?: boolean;
}

export interface ScreenContext {
  capture: ScreenCaptureRef;
  text: string;
  summary: string;
}

export interface RegionContext {
  capture: ScreenCaptureRef;
  selection: RegionSelection;
  text: string;
  summary: string;
}

export interface ChatRequest {
  prompt: string;
  use_current_screen?: boolean;
  use_region?: boolean;
  region_selection?: RegionSelection | null;
  source_ids?: string[];
  conversation_id?: string | null;
}

export interface ChatResponse {
  answer: string;
  provider_used: string;
  provider_diagnostics?: ProviderDiagnostics | null;
  trace_id: string;
  evidence: EvidenceItem[];
  debug_steps: TraceEvent[];
  conversation_id: string;
  warnings: string[];
  guided_task_status?: GuidedTaskStatus | null;
}

export interface ActivityFrameRef {
  id: string;
  capture: ScreenCaptureRef;
  timestamp: string;
  summary?: string | null;
  ocr_text?: string | null;
  window_title?: string | null;
  dedupe_key?: string | null;
}

export interface ActivityEvent {
  id: string;
  timestamp: string;
  type: "recording_started" | "recording_stopped" | "window_changed" | "frame_sampled" | "summary_generated" | "error";
  description: string;
  window_title?: string | null;
  metadata: Record<string, unknown>;
}

export interface ActivityTimeline {
  session_id: string;
  started_at: string;
  ended_at?: string | null;
  representative_frames: ActivityFrameRef[];
  events: ActivityEvent[];
  total_frames: number;
  window_titles: string[];
}

export interface ActivitySummary {
  session_id: string;
  started_at: string;
  ended_at: string;
  summary_text: string;
  steps: string[];
  uncertain: boolean;
  provider_used: string;
  warnings: string[];
}

export interface ActivitySessionRecord {
  id: string;
  status: "idle" | "active" | "completed" | "stopped" | "failed";
  started_at: string;
  requested_duration_seconds: number;
  sampling_hz: number;
  ends_at?: string | null;
  ended_at?: string | null;
  frames_captured: number;
  last_window_title?: string | null;
  last_error?: string | null;
  summary_available: boolean;
}

export interface StartActivityRecordingRequest {
  duration_seconds?: number;
  sampling_hz?: number | null;
}

export interface StartActivityRecordingResponse {
  ok: boolean;
  session?: ActivitySessionRecord | null;
  message: string;
}

export interface StopActivityRecordingRequest {
  session_id?: string | null;
}

export interface StopActivityRecordingResponse {
  ok: boolean;
  session?: ActivitySessionRecord | null;
  summary?: ActivitySummary | null;
  message: string;
}

export interface ActivityStatusResponse {
  current?: ActivitySessionRecord | null;
  last?: ActivitySessionRecord | null;
  summary?: ActivitySummary | null;
}

export interface GuidedTaskStep {
  step_id: string;
  order_index: number;
  instruction_text: string;
  target_description: string;
  completion_hint: string;
  grounding_required: boolean;
}

export interface GuidedTaskPlan {
  title: string;
  goal: string;
  estimated_steps: number;
  steps: GuidedTaskStep[];
}

export interface OverlayTarget {
  x: number;
  y: number;
  width: number;
  height: number;
  capture_width?: number | null;
  capture_height?: number | null;
  target_label: string;
  annotation?: string | null;
  render_style: "arrow_only" | "highlight_only" | "arrow_pulse";
}

export interface GroundingRequest {
  session_id: string;
  step_id: string;
  screen_summary: string;
  screen_text?: string | null;
}

export interface GroundingResult {
  success: boolean;
  confidence: number;
  bbox?: OverlayTarget | null;
  target_label?: string | null;
  reason: string;
  fallback_suggestion?: string | null;
  target_bbox_source?: "heuristic" | "ocr" | "model" | "fallback" | null;
}

export interface StepProgressState {
  state: "waiting" | "completed" | "uncertain" | "needs_confirmation";
  confidence: number;
  reason: string;
  auto_advanced: boolean;
}

export interface GuidedTaskSession {
  id: string;
  conversation_id?: string | null;
  title: string;
  goal: string;
  status: "active" | "paused" | "completed" | "stopped" | "needs_attention" | "failed";
  created_at: string;
  updated_at: string;
  current_step_index: number;
  trace_id: string;
  last_error?: string | null;
}

export interface GuidedTaskStatus {
  session?: GuidedTaskSession | null;
  plan?: GuidedTaskPlan | null;
  current_step?: GuidedTaskStep | null;
  latest_grounding?: GroundingResult | null;
  overlay_target?: OverlayTarget | null;
  progress_state?: StepProgressState | null;
  recovery_options: string[];
  telemetry?: GuidanceTelemetry | null;
}

export interface GuidanceTelemetry {
  capture_signature?: string | null;
  screen_relevance?: "relevant" | "unrelated" | "changed" | "same" | "uncertain" | "unknown";
  grounding_confidence?: number | null;
  target_bbox_source?: "heuristic" | "ocr" | "model" | "fallback" | null;
  step_decision?: string | null;
  replan_reason?: string | null;
  latency_breakdown?: Record<string, number>;
}

export interface StartGuidedTaskRequest {
  prompt: string;
  conversation_id?: string | null;
  source_ids?: string[];
  region_selection?: RegionSelection | null;
}

export interface StartGuidedTaskResponse {
  ok: boolean;
  status?: GuidedTaskStatus | null;
  message: string;
}

export interface GuidedTaskActionRequest {
  session_id?: string | null;
  action: "mark_done" | "next_step" | "pause" | "resume" | "rescan" | "cant_find_it";
  region_selection?: RegionSelection | null;
}

export interface StopGuidedTaskRequest {
  session_id?: string | null;
}

export interface StopGuidedTaskResponse {
  ok: boolean;
  status?: GuidedTaskStatus | null;
  message: string;
}
