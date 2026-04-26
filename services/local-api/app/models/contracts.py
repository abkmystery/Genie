from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic import ConfigDict


class ProviderCapabilities(BaseModel):
    supports_screen_input: bool = True
    supports_stt: bool = True
    supports_tts: bool = True


class ProviderProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: Literal["demo", "local", "custom"]
    display_name: str
    description: str
    transport: Literal["gateway", "http", "mock"]
    api_style: Literal["genie_gateway", "openai_compatible"] | None = None
    backend_base_url: str
    model_name: str
    timeout_ms: int = 30000
    capabilities: ProviderCapabilities
    credentials_required: bool = False
    credentials_stored_locally: bool = False
    provider_mode: Literal["demo", "local", "custom"] | None = None
    demo_source_order: list[Literal["bundled_file", "remote_file", "offline_mock"]] | None = None
    remote_demo_file_url: str | None = None
    remote_demo_file_format: Literal["json", "text"] | None = None
    default_model: str | None = None


class ProviderConfig(ProviderProfile):
    endpoint_override: str | None = None
    token_present: bool = False


class ProviderDiagnostics(BaseModel):
    provider_status: Literal["live_gemma", "fallback_mock", "local_not_ready", "endpoint_error", "unknown"] = "unknown"
    provider_source: str | None = None
    live_model_name: str | None = None
    fallback_reason: str | None = None
    last_model_error: str | None = None
    latency_ms: float | None = None


class SourceRecord(BaseModel):
    id: str
    filename: str
    content_type: str
    path: str
    status: Literal["indexed", "failed", "processing"]
    size_bytes: int
    chunk_count: int
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class SourceChunk(BaseModel):
    id: str
    source_id: str
    ordinal: int
    text: str
    locator: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceItem(BaseModel):
    id: str
    label: str
    kind: Literal["source", "screen", "region"]
    quote: str | None = None
    locator: str | None = None
    score: float | None = None


class ScreenCaptureRef(BaseModel):
    id: str
    path: str
    width: int
    height: int
    mode: Literal["native", "simulated"]
    captured_at: datetime
    ocr_text: str | None = None
    summary: str | None = None


class RegionSelection(BaseModel):
    x: int
    y: int
    width: int
    height: int


class ScreenContext(BaseModel):
    capture: ScreenCaptureRef
    text: str
    summary: str


class RegionContext(BaseModel):
    capture: ScreenCaptureRef
    selection: RegionSelection
    text: str
    summary: str


class TraceEvent(BaseModel):
    id: str
    trace_id: str
    type: Literal[
        "REQUEST_RECEIVED",
        "PROFILE_RESOLVED",
        "SOURCE_PARSED",
        "SOURCE_INDEXED",
        "SCREEN_CAPTURED",
        "REGION_CAPTURED",
        "CONTEXT_BUILT",
        "RETRIEVAL_COMPLETED",
        "MODEL_CALLED",
        "RESPONSE_RENDERED",
        "RECORDING_STARTED",
        "RECORDING_FRAME_CAPTURED",
        "RECORDING_STOPPED",
        "SUMMARY_GENERATED",
        "GUIDED_TASK_STARTED",
        "TASK_PLAN_CREATED",
        "STEP_GROUNDED",
        "STEP_GROUNDING_FAILED",
        "OVERLAY_RENDERED",
        "STEP_COMPLETION_DETECTED",
        "STEP_CONFIRMED_BY_USER",
        "STEP_ADVANCED",
        "GUIDED_TASK_STOPPED",
        "GUIDED_TASK_ERROR",
        "ERROR_RAISED",
    ]
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    duration_ms: float | None = None


class SettingsState(BaseModel):
    active_profile_id: Literal["demo", "local", "custom"]
    tts_enabled: bool = False
    screen_share_enabled: bool = True
    activity_recording_enabled: bool = True
    activity_sampling_hz: float = 1.0
    activity_max_duration_seconds: int = 60
    guided_task_enabled: bool = True
    guided_overlay_style: Literal["arrow_only", "highlight_only", "arrow_pulse"] = "arrow_pulse"
    guided_auto_advance_sensitivity: float = 0.85
    guided_completion_mode: Literal["conservative", "balanced"] = "conservative"
    guided_max_planning_steps: int = 6
    guided_show_debug_labels: bool = False
    secure_storage_warning: str | None = None
    custom_endpoint: str | None = None
    custom_token_present: bool = False
    local_endpoint: str | None = None
    local_token_present: bool = False
    local_model: str | None = None
    local_model_path: str | None = None
    custom_model: str | None = None
    demo_model: str | None = None
    onboarding_complete: bool = False


class ChatRequest(BaseModel):
    prompt: str
    use_current_screen: bool = False
    use_region: bool = False
    region_selection: RegionSelection | None = None
    source_ids: list[str] = Field(default_factory=list)
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    provider_used: str
    provider_diagnostics: ProviderDiagnostics | None = None
    trace_id: str
    evidence: list[EvidenceItem]
    debug_steps: list[TraceEvent]
    conversation_id: str
    warnings: list[str] = Field(default_factory=list)
    guided_task_status: GuidedTaskStatus | None = None


class ActivityFrameRef(BaseModel):
    id: str
    capture: ScreenCaptureRef
    timestamp: datetime
    summary: str | None = None
    ocr_text: str | None = None
    window_title: str | None = None
    dedupe_key: str | None = None


class ActivityEvent(BaseModel):
    id: str
    timestamp: datetime
    type: Literal["recording_started", "recording_stopped", "window_changed", "frame_sampled", "summary_generated", "error"]
    description: str
    window_title: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActivityTimeline(BaseModel):
    session_id: str
    started_at: datetime
    ended_at: datetime | None = None
    representative_frames: list[ActivityFrameRef] = Field(default_factory=list)
    events: list[ActivityEvent] = Field(default_factory=list)
    total_frames: int = 0
    window_titles: list[str] = Field(default_factory=list)


class ActivitySummary(BaseModel):
    session_id: str
    started_at: datetime
    ended_at: datetime
    summary_text: str
    steps: list[str] = Field(default_factory=list)
    uncertain: bool = False
    provider_used: str = "activity:timeline"
    warnings: list[str] = Field(default_factory=list)


class ActivitySessionRecord(BaseModel):
    id: str
    status: Literal["idle", "active", "completed", "stopped", "failed"]
    started_at: datetime
    requested_duration_seconds: int
    sampling_hz: float
    ends_at: datetime | None = None
    ended_at: datetime | None = None
    frames_captured: int = 0
    last_window_title: str | None = None
    last_error: str | None = None
    summary_available: bool = False


class StartActivityRecordingRequest(BaseModel):
    duration_seconds: int = 60
    sampling_hz: float | None = None


class StartActivityRecordingResponse(BaseModel):
    ok: bool
    session: ActivitySessionRecord | None = None
    message: str


class StopActivityRecordingRequest(BaseModel):
    session_id: str | None = None


class StopActivityRecordingResponse(BaseModel):
    ok: bool
    session: ActivitySessionRecord | None = None
    summary: ActivitySummary | None = None
    message: str


class ActivityStatusResponse(BaseModel):
    current: ActivitySessionRecord | None = None
    last: ActivitySessionRecord | None = None
    summary: ActivitySummary | None = None


class GuidedTaskStep(BaseModel):
    step_id: str
    order_index: int
    instruction_text: str
    target_description: str
    completion_hint: str
    grounding_required: bool = True


class GuidedTaskPlan(BaseModel):
    title: str
    goal: str
    estimated_steps: int
    steps: list[GuidedTaskStep] = Field(default_factory=list)


class OverlayTarget(BaseModel):
    x: int
    y: int
    width: int
    height: int
    capture_width: int | None = None
    capture_height: int | None = None
    target_label: str
    annotation: str | None = None
    render_style: Literal["arrow_only", "highlight_only", "arrow_pulse"] = "arrow_pulse"


class GroundingRequest(BaseModel):
    session_id: str
    step_id: str
    screen_summary: str
    screen_text: str | None = None


class GroundingResult(BaseModel):
    success: bool
    confidence: float
    bbox: OverlayTarget | None = None
    target_label: str | None = None
    reason: str
    fallback_suggestion: str | None = None
    target_bbox_source: Literal["heuristic", "ocr", "model", "fallback"] | None = None


class StepProgressState(BaseModel):
    state: Literal["waiting", "completed", "uncertain", "needs_confirmation"]
    confidence: float = 0.0
    reason: str = ""
    auto_advanced: bool = False


class GuidedTaskSession(BaseModel):
    id: str
    conversation_id: str | None = None
    title: str
    goal: str
    status: Literal["active", "paused", "completed", "stopped", "needs_attention", "failed"]
    created_at: datetime
    updated_at: datetime
    current_step_index: int = 0
    trace_id: str
    last_error: str | None = None


class GuidanceTelemetry(BaseModel):
    capture_signature: str | None = None
    screen_relevance: Literal["relevant", "unrelated", "changed", "same", "uncertain", "unknown"] = "unknown"
    grounding_confidence: float | None = None
    target_bbox_source: Literal["heuristic", "ocr", "model", "fallback"] | None = None
    step_decision: str | None = None
    replan_reason: str | None = None
    latency_breakdown: dict[str, float] = Field(default_factory=dict)


class GuidedTaskStatus(BaseModel):
    session: GuidedTaskSession | None = None
    plan: GuidedTaskPlan | None = None
    current_step: GuidedTaskStep | None = None
    latest_grounding: GroundingResult | None = None
    overlay_target: OverlayTarget | None = None
    progress_state: StepProgressState | None = None
    recovery_options: list[str] = Field(default_factory=list)
    telemetry: GuidanceTelemetry | None = None


class StartGuidedTaskRequest(BaseModel):
    prompt: str
    conversation_id: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    region_selection: RegionSelection | None = None


class StartGuidedTaskResponse(BaseModel):
    ok: bool
    status: GuidedTaskStatus | None = None
    message: str


class GuidedTaskActionRequest(BaseModel):
    session_id: str | None = None
    action: Literal["mark_done", "next_step", "pause", "resume", "rescan", "cant_find_it"]
    region_selection: RegionSelection | None = None


class StopGuidedTaskRequest(BaseModel):
    session_id: str | None = None


class StopGuidedTaskResponse(BaseModel):
    ok: bool
    status: GuidedTaskStatus | None = None
    message: str


class StartupProfileRequest(BaseModel):
    profile_id: Literal["demo", "local", "custom"] | None = None


class SetProfileRequest(BaseModel):
    profile_id: Literal["demo", "local", "custom"]


class UpdateSettingsRequest(BaseModel):
    active_profile_id: Literal["demo", "local", "custom"] | None = None
    tts_enabled: bool | None = None
    screen_share_enabled: bool | None = None
    activity_recording_enabled: bool | None = None
    activity_sampling_hz: float | None = None
    activity_max_duration_seconds: int | None = None
    guided_task_enabled: bool | None = None
    guided_overlay_style: Literal["arrow_only", "highlight_only", "arrow_pulse"] | None = None
    guided_auto_advance_sensitivity: float | None = None
    guided_completion_mode: Literal["conservative", "balanced"] | None = None
    guided_max_planning_steps: int | None = None
    guided_show_debug_labels: bool | None = None
    custom_endpoint: str | None = None
    local_endpoint: str | None = None
    local_model: str | None = None
    local_model_path: str | None = None
    custom_model: str | None = None
    demo_model: str | None = None
    onboarding_complete: bool | None = None


class CredentialPayload(BaseModel):
    provider_id: Literal["local", "custom"]
    token: str | None = None
    endpoint: str | None = None


class SpeechToTextRequest(BaseModel):
    transcript_hint: str | None = None
    audio_base64: str | None = None
    audio_format: str | None = None


class AttachmentRecord(BaseModel):
    id: str
    conversation_id: str
    filename: str
    content_type: str
    status: Literal["indexed", "failed"]
    chunk_count: int
    error: str | None = None
    created_at: datetime


class TextToSpeechRequest(BaseModel):
    text: str


class DemoProviderStatus(BaseModel):
    source: Literal["bundled_file", "remote_file", "offline_mock"]
    provider_type: str
    base_url: str
    model: str
    timeout_ms: int
    supports_images: bool
    supports_audio_input: bool
    api_key_present: bool = False


class HealthStatus(BaseModel):
    ok: bool
    profile: ProviderConfig
    storage_mode: str
    warnings: list[str] = Field(default_factory=list)
    demo_status: DemoProviderStatus | None = None
    provider_diagnostics: ProviderDiagnostics | None = None


class GatewayChatRequest(BaseModel):
    prompt: str
    profile_id: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    screen_summary: str | None = None
    region_summary: str | None = None
    screen_image_data_url: str | None = None
    region_image_data_url: str | None = None
    audio_base64: str | None = None
    audio_format: str | None = None


class GatewayChatResponse(BaseModel):
    answer: str
    provider_used: str
    provider_diagnostics: ProviderDiagnostics | None = None
