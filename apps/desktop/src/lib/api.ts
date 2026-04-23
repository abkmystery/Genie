import type {
  ActivityStatusResponse,
  ChatRequest,
  ChatResponse,
  AttachmentRecord,
  GuidedTaskActionRequest,
  GuidedTaskStatus,
  ProviderConfig,
  RegionSelection,
  SettingsState,
  StartGuidedTaskResponse,
  StopGuidedTaskResponse,
  StartActivityRecordingResponse,
  StopActivityRecordingResponse,
  SourceRecord,
  TraceEvent,
} from "@genie/contracts";

export interface ScreenContext {
  capture: {
    id: string;
    path: string;
    width: number;
    height: number;
    mode: "native" | "simulated";
    ocr_text?: string | null;
    summary?: string | null;
  };
  text: string;
  summary: string;
}

export interface RegionContext extends ScreenContext {
  selection: RegionSelection;
}

export interface HealthPayload {
  ok: boolean;
  profile: ProviderConfig;
  storage_mode: string;
  warnings: string[];
  demo_status?: {
    source: "bundled_file" | "remote_file" | "offline_mock";
    provider_type: string;
    base_url: string;
    model: string;
    timeout_ms: number;
    supports_images: boolean;
    supports_audio_input: boolean;
    api_key_present: boolean;
  } | null;
}

const API_BASE = import.meta.env.VITE_LOCAL_API_BASE_URL ?? "http://127.0.0.1:8765";

export function captureImageUrl(captureId: string): string {
  const normalized = captureId.endsWith(".png") ? captureId : `${captureId}`;
  return `${API_BASE}/captures/${encodeURIComponent(normalized)}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<HealthPayload>("/health"),
  listProfiles: () => request<ProviderConfig[]>("/profiles"),
  resolveStartupProfile: (profileId: string | null) =>
    request<ProviderConfig>("/profiles/resolve-startup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile_id: profileId }),
    }),
  setActiveProfile: (profileId: string) =>
    request<ProviderConfig>("/profiles/active", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile_id: profileId }),
    }),
  getSettings: () => request<SettingsState>("/settings"),
  updateSettings: (payload: Partial<SettingsState>) =>
    request<SettingsState>("/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        active_profile_id: payload.active_profile_id,
        tts_enabled: payload.tts_enabled,
        screen_share_enabled: payload.screen_share_enabled,
        activity_recording_enabled: payload.activity_recording_enabled,
        activity_sampling_hz: payload.activity_sampling_hz,
        activity_max_duration_seconds: payload.activity_max_duration_seconds,
        guided_task_enabled: payload.guided_task_enabled,
        guided_overlay_style: payload.guided_overlay_style,
        guided_auto_advance_sensitivity: payload.guided_auto_advance_sensitivity,
        guided_completion_mode: payload.guided_completion_mode,
        guided_max_planning_steps: payload.guided_max_planning_steps,
        guided_show_debug_labels: payload.guided_show_debug_labels,
        custom_endpoint: payload.custom_endpoint,
        local_endpoint: payload.local_endpoint,
        local_model: payload.local_model,
        local_model_path: payload.local_model_path,
        custom_model: payload.custom_model,
        demo_model: payload.demo_model,
        onboarding_complete: payload.onboarding_complete,
      }),
    }),
  saveCredentials: (providerId: "local" | "custom", token: string, endpoint?: string) =>
    request<{ ok: boolean; mode: string }>("/settings/credentials", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider_id: providerId, token, endpoint }),
    }),
  clearCredentials: (providerId: string) =>
    request<{ ok: boolean }>(`/settings/credentials/${providerId}`, { method: "DELETE" }),
  listSources: () => request<SourceRecord[]>("/sources"),
  addSources: async (files: File[]) => {
    const body = new FormData();
    files.forEach((file) => body.append("files", file));
    return request<SourceRecord[]>("/sources", { method: "POST", body });
  },
  reindexSource: (sourceId: string) => request<SourceRecord>(`/sources/${sourceId}/reindex`, { method: "POST" }),
  removeSource: (sourceId: string) => request<{ ok: boolean }>(`/sources/${sourceId}`, { method: "DELETE" }),
  listAttachments: (conversationId: string) => request<AttachmentRecord[]>(`/sessions/${conversationId}/attachments`),
  addAttachments: async (conversationId: string, files: File[]) => {
    const body = new FormData();
    files.forEach((file) => body.append("files", file));
    return request<AttachmentRecord[]>(`/sessions/${conversationId}/attachments`, { method: "POST", body });
  },
  removeAttachment: (conversationId: string, attachmentId: string) =>
    request<{ ok: boolean }>(`/sessions/${conversationId}/attachments/${attachmentId}`, { method: "DELETE" }),
  captureScreen: () => request<ScreenContext>("/screen/capture", { method: "POST" }),
  captureRegion: (selection: RegionSelection) =>
    request<RegionContext>("/screen/region", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: "capture region", region_selection: selection }),
    }),
  transcribe: (payload?: { transcriptHint?: string; audioBase64?: string; audioFormat?: string }) =>
    request<{ text: string }>("/audio/transcribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        transcript_hint: payload?.transcriptHint ?? null,
        audio_base64: payload?.audioBase64 ?? null,
        audio_format: payload?.audioFormat ?? null,
      }),
    }),
  speak: (text: string) =>
    request<{ spoken: boolean; mode: string; message: string; preview: string }>("/audio/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }),
  stopSpeech: () =>
    request<{ stopped: boolean; mode: string; message: string }>("/audio/stop", {
      method: "POST",
    }),
  startActivityRecording: (payload: { durationSeconds?: number; samplingHz?: number }) =>
    request<StartActivityRecordingResponse>("/activity/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        duration_seconds: payload.durationSeconds,
        sampling_hz: payload.samplingHz,
      }),
    }),
  stopActivityRecording: (sessionId?: string) =>
    request<StopActivityRecordingResponse>("/activity/stop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId ?? null }),
    }),
  currentActivity: () => request<ActivityStatusResponse>("/activity/current"),
  lastActivity: () => request<ActivityStatusResponse>("/activity/last"),
  summarizeActivity: (sessionId?: string) =>
    request<StopActivityRecordingResponse>("/activity/summarize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId ?? null }),
    }),
  startGuidedTask: (payload: { prompt: string; conversationId?: string; sourceIds?: string[]; regionSelection?: RegionSelection | null }) =>
    request<StartGuidedTaskResponse>("/guided/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt: payload.prompt,
        conversation_id: payload.conversationId ?? null,
        source_ids: payload.sourceIds ?? [],
        region_selection: payload.regionSelection ?? null,
      }),
    }),
  currentGuidedTask: () => request<GuidedTaskStatus>("/guided/current"),
  observeGuidedTask: () =>
    request<GuidedTaskStatus>("/guided/observe", {
      method: "POST",
    }),
  actOnGuidedTask: (payload: GuidedTaskActionRequest) =>
    request<GuidedTaskStatus>("/guided/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  stopGuidedTask: (sessionId?: string) =>
    request<StopGuidedTaskResponse>("/guided/stop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId ?? null }),
    }),
  chat: (payload: ChatRequest) =>
    request<ChatResponse>("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getTrace: (traceId: string) => request<TraceEvent[]>(`/traces/${traceId}`),
  runDiagnostics: () => request<Record<string, unknown>>("/diagnostics/run", { method: "POST" }),
};
