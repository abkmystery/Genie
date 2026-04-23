import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";

import type {
  ActivityStatusResponse,
  ChatResponse,
  AttachmentRecord,
  GuidedTaskStatus,
  ProviderConfig,
  SettingsState,
  SourceRecord,
  TraceEvent,
} from "@genie/contracts";

import { DebugPanel } from "./components/DebugPanel";
import { GuidedTaskCard } from "./components/GuidedTaskCard";
import { Launcher } from "./components/Launcher";
import { MessageList } from "./components/MessageList";
import { SetupWizard } from "./components/SetupWizard";
import { SettingsPanel } from "./components/SettingsPanel";
import { SourceManager } from "./components/SourceManager";
import {
  formatActivityTimer,
  formatSeconds,
  looksLikeBase64Audio,
  sanitizeSpeechText,
  startBrowserSpeechRecognition,
  startWavRecording,
} from "./lib/audio";
import { api, type HealthPayload, type RegionContext, type ScreenContext } from "./lib/api";
import {
  buildContextLabel,
  formatActivitySummary,
  formatGuidedTaskCompletion,
  formatGuidedTaskMessage,
  isGuidancePrompt,
  resolveGuidanceGoal,
} from "./lib/chat";

type TabKey = "chat" | "sources" | "settings" | "debug";

interface MessageItem {
  id: string;
  role: "user" | "assistant";
  text: string;
  response?: ChatResponse;
}

const TABS: TabKey[] = ["chat", "sources", "settings", "debug"];
const TAB_LABELS: Record<TabKey, string> = {
  chat: "Chat",
  sources: "Sources",
  settings: "Settings",
  debug: "Debug",
};

export default function App() {
  const [isOpen, setIsOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<TabKey>("chat");
  const [prompt, setPrompt] = useState("");
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [conversationId, setConversationId] = useState<string>(() => crypto.randomUUID());
  const [sources, setSources] = useState<SourceRecord[]>([]);
  const [attachments, setAttachments] = useState<AttachmentRecord[]>([]);
  const [profiles, setProfiles] = useState<ProviderConfig[]>([]);
  const [settings, setSettings] = useState<SettingsState | null>(null);
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [diagnostics, setDiagnostics] = useState<Record<string, unknown> | null>(null);
  const [screenContext, setScreenContext] = useState<ScreenContext | null>(null);
  const [regionContext, setRegionContext] = useState<RegionContext | null>(null);
  const [traceEvents, setTraceEvents] = useState<TraceEvent[]>([]);
  const [lastResponse, setLastResponse] = useState<ChatResponse | null>(null);
  const [customToken, setCustomToken] = useState("");
  const [customEndpoint, setCustomEndpoint] = useState("");
  const [customModel, setCustomModel] = useState("");
  const [localToken, setLocalToken] = useState("");
  const [localEndpoint, setLocalEndpoint] = useState("");
  const [localModel, setLocalModel] = useState("");
  const [localModelPath, setLocalModelPath] = useState("");
  const [activityStatus, setActivityStatus] = useState<ActivityStatusResponse | null>(null);
  const [guidedStatus, setGuidedStatus] = useState<GuidedTaskStatus | null>(null);
  const surfacedActivitySummaryRef = useRef<string | null>(null);
  const surfacedGuidedCompletionRef = useRef<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [pendingCapture, setPendingCapture] = useState<ScreenContext | null>(null);
  const [pendingGuidedRescan, setPendingGuidedRescan] = useState(false);
  const [micStatus, setMicStatus] = useState<"idle" | "recording" | "transcribing">("idle");
  const [micElapsed, setMicElapsed] = useState(0);
  const micControllerRef = useRef<{ stop(): void } | null>(null);
  const attachmentPickerRef = useRef<HTMLInputElement | null>(null);
  const [backendReady, setBackendReady] = useState(false);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const panelRef = useRef<HTMLElement | null>(null);
  const resizeStateRef = useRef<{ startX: number; startY: number; startWidth: number; startHeight: number } | null>(null);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const guidanceObserveInFlightRef = useRef(false);

  const contextLabel = useMemo(() => {
    return buildContextLabel({
      screenShareEnabled: settings?.screen_share_enabled !== false,
      hasRegion: Boolean(regionContext),
      attachmentCount: attachments.length,
    });
  }, [attachments.length, regionContext, settings?.screen_share_enabled]);

  useEffect(() => {
    const bootstrap = async () => {
      try {
        setBackendError(null);
        if (window.genieShell?.ensureBackend) {
          try {
            await window.genieShell.ensureBackend();
            setBackendReady(true);
          } catch (cause) {
            setBackendReady(false);
            setBackendError(cause instanceof Error ? cause.message : "Backend failed to start.");
            return;
          }
        } else {
          setBackendReady(true);
        }
        const cliProfile = (await window.genieShell?.getLaunchProfile?.()) ?? null;
        await api.resolveStartupProfile(cliProfile);
        const [profileList, currentSettings, sourceList, currentHealth] = await Promise.all([
          api.listProfiles(),
          api.getSettings(),
          api.listSources(),
          api.health(),
        ]);
        const attachmentList = await api.listAttachments(conversationId);
        const currentActivity = await api.currentActivity();
        const currentGuided = await api.currentGuidedTask();
        setProfiles(profileList);
        setSettings(currentSettings);
        setCustomEndpoint(currentSettings.custom_endpoint ?? "");
        setLocalEndpoint(currentSettings.local_endpoint ?? "");
        setLocalModel(currentSettings.local_model ?? "");
        setLocalModelPath(currentSettings.local_model_path ?? "");
        setCustomModel(currentSettings.custom_model ?? "");
        setSources(sourceList);
        setAttachments(attachmentList);
        setHealth(currentHealth);
        setActivityStatus(currentActivity);
        setGuidedStatus(currentGuided);
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "Failed to bootstrap Genie.");
      }
    };
    void bootstrap();
  }, []);

  useEffect(() => {
    if (!backendReady || !settings?.onboarding_complete) {
      return;
    }
    let cancelled = false;
    const run = async () => {
      try {
        const status = await api.currentActivity();
        if (cancelled) return;
        setActivityStatus(status);
        const completedSummary = status.summary ?? null;
        if (completedSummary && surfacedActivitySummaryRef.current !== completedSummary.session_id) {
          surfacedActivitySummaryRef.current = completedSummary.session_id;
          setMessages((previous) => [
            ...previous,
            {
              id: crypto.randomUUID(),
              role: "assistant",
              text: formatActivitySummary(completedSummary),
            },
          ]);
        }
      } catch {
        // Ignore polling errors and keep the last known activity status.
      }
    };
    void run();
    const timer = window.setInterval(() => {
      void run();
    }, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [backendReady, settings?.onboarding_complete]);

  useEffect(() => {
    if (!window.genieShell?.onRegionSelection) {
      return;
    }
    const unsubscribe = window.genieShell.onRegionSelection((selection) => {
      if (!pendingCapture && !pendingGuidedRescan) {
        return;
      }
      void (async () => {
        try {
          if (!selection) {
            setPendingCapture(null);
            setPendingGuidedRescan(false);
            return;
          }
          if (pendingGuidedRescan) {
            const status = await api.actOnGuidedTask({
              action: "rescan",
              session_id: guidedStatus?.session?.id ?? null,
              region_selection: selection,
            });
            setGuidedStatus(status);
            setPendingGuidedRescan(false);
            return;
          }
          const context = await api.captureRegion(selection);
          setRegionContext(context);
          setScreenContext(pendingCapture);
        } catch (cause) {
          setError(cause instanceof Error ? cause.message : "Region capture failed.");
        } finally {
          setPendingCapture(null);
          setPendingGuidedRescan(false);
        }
      })();
    });
    return unsubscribe;
  }, [guidedStatus?.session?.id, pendingCapture, pendingGuidedRescan]);

  useEffect(() => () => {
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
  }, []);

  useEffect(() => {
    if (!backendReady || !settings?.onboarding_complete || !guidedStatus?.session || guidedStatus.session.status === "paused") {
      return;
    }
    let cancelled = false;
    const tick = async () => {
      if (guidanceObserveInFlightRef.current) {
        return;
      }
      guidanceObserveInFlightRef.current = true;
      try {
        const next = await api.observeGuidedTask();
        if (!cancelled) {
          setGuidedStatus(next);
        }
      } catch {
        // Keep last known guidance state.
      } finally {
        guidanceObserveInFlightRef.current = false;
      }
    };
    const timer = window.setInterval(() => {
      void tick();
    }, 600);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [backendReady, guidedStatus?.session?.id, guidedStatus?.session?.status, settings?.onboarding_complete]);

  useEffect(() => {
    if (!guidedStatus?.session?.trace_id) {
      return;
    }
    void (async () => {
      try {
        setTraceEvents(await api.getTrace(guidedStatus.session!.trace_id));
      } catch {
        // Keep last known trace output.
      }
    })();
  }, [guidedStatus?.progress_state?.state, guidedStatus?.session?.trace_id, guidedStatus?.session?.updated_at]);

  useEffect(() => {
    if (!guidedStatus?.session || guidedStatus.session.status !== "completed") {
      return;
    }
    if (surfacedGuidedCompletionRef.current === guidedStatus.session.id) {
      return;
    }
    surfacedGuidedCompletionRef.current = guidedStatus.session.id;
    setMessages((previous) => [
      ...previous,
      {
        id: crypto.randomUUID(),
        role: "assistant",
        text: formatGuidedTaskCompletion(guidedStatus),
      },
    ]);
  }, [guidedStatus]);

  useEffect(() => {
    if (
      !guidedStatus?.session ||
      !["active", "needs_attention"].includes(guidedStatus.session.status) ||
      !guidedStatus.overlay_target
    ) {
      void window.genieShell?.setGuidanceOverlay?.(null);
      return;
    }
    void window.genieShell?.setGuidanceOverlay?.({
      target: guidedStatus.overlay_target,
      title: guidedStatus.plan?.title ?? guidedStatus.session.title,
      stepLabel: `Step ${(guidedStatus.current_step?.order_index ?? 0) + 1} of ${guidedStatus.plan?.estimated_steps ?? 0}`,
      statusLabel: guidedStatus.latest_grounding?.success ? "Grounded" : guidedStatus.session.status,
      showDebugLabels: settings?.guided_show_debug_labels ?? false,
    });
  }, [guidedStatus, settings?.guided_show_debug_labels]);

  const refreshSettings = async () => {
    const [currentSettings, currentHealth, profileList] = await Promise.all([api.getSettings(), api.health(), api.listProfiles()]);
    setSettings(currentSettings);
    setCustomEndpoint(currentSettings.custom_endpoint ?? "");
    setLocalEndpoint(currentSettings.local_endpoint ?? "");
    setLocalModel(currentSettings.local_model ?? "");
    setLocalModelPath(currentSettings.local_model_path ?? "");
    setCustomModel(currentSettings.custom_model ?? "");
    setHealth(currentHealth);
    setProfiles(profileList);
  };

  const refreshSources = async () => {
    setSources(await api.listSources());
  };

  const refreshAttachments = async () => {
    setAttachments(await api.listAttachments(conversationId));
  };

  const handleResizeStart = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (!panelRef.current) {
      return;
    }
    resizeStateRef.current = {
      startX: event.clientX,
      startY: event.clientY,
      startWidth: panelRef.current.offsetWidth,
      startHeight: panelRef.current.offsetHeight,
    };

    const handlePointerMove = (moveEvent: MouseEvent) => {
      const state = resizeStateRef.current;
      if (!state) {
        return;
      }
      const nextWidth = Math.max(360, Math.min(760, state.startWidth + (moveEvent.clientX - state.startX)));
      const nextHeight = Math.max(520, Math.min(980, state.startHeight + (moveEvent.clientY - state.startY)));
      void window.genieShell?.resizePanel?.({ width: nextWidth, height: nextHeight });
    };

    const handlePointerUp = () => {
      resizeStateRef.current = null;
      window.removeEventListener("mousemove", handlePointerMove);
      window.removeEventListener("mouseup", handlePointerUp);
    };

    window.addEventListener("mousemove", handlePointerMove);
    window.addEventListener("mouseup", handlePointerUp);
  };

  const toggleOpen = async () => {
    const next = !isOpen;
    setIsOpen(next);
    await window.genieShell?.setPanelOpen?.(next);
  };

  const stopSpeaking = async () => {
    utteranceRef.current = null;
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    try {
      await api.stopSpeech();
    } catch {
      // Ignore fallback stop errors when no backend speech is active.
    } finally {
      setIsSpeaking(false);
    }
  };

  const speakResponse = async (text: string) => {
    const cleaned = sanitizeSpeechText(text);
    if (!cleaned) {
      return;
    }

    if (window.speechSynthesis) {
      const speech = window.speechSynthesis;
      speech.cancel();
      const utterance = new SpeechSynthesisUtterance(cleaned);
      utteranceRef.current = utterance;
      utterance.onend = () => {
        if (utteranceRef.current === utterance) {
          utteranceRef.current = null;
          setIsSpeaking(false);
        }
      };
      utterance.onerror = () => {
        if (utteranceRef.current === utterance) {
          utteranceRef.current = null;
          setIsSpeaking(false);
        }
      };
      setIsSpeaking(true);
      speech.speak(utterance);
      return;
    }

    setIsSpeaking(true);
    try {
      await api.speak(cleaned);
    } finally {
      setIsSpeaking(false);
    }
  };

  const startGuidance = async (goal: string) => {
    const resolvedGoal = resolveGuidanceGoal(goal, messages);
    setLoading(true);
    setError(null);
    setPrompt("");
    const userMessage: MessageItem = { id: crypto.randomUUID(), role: "user", text: goal.trim() };
    setMessages((previous) => [...previous, userMessage]);
    try {
      const payload = await withScreenCaptureHidden(() =>
        api.startGuidedTask({
          prompt: resolvedGoal,
          conversationId: conversationId,
          sourceIds: sources.map((source) => source.id),
          regionSelection: regionContext?.selection ?? null,
        }),
      );
      if (!payload.ok || !payload.status) {
        throw new Error(payload.message || "Guidance could not start.");
      }
      const nextGuidedStatus = payload.status;
      setGuidedStatus(nextGuidedStatus);
      setMessages((previous) => [
        ...previous,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: formatGuidedTaskMessage(nextGuidedStatus),
        },
      ]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Guidance could not start.");
    } finally {
      setLoading(false);
      setActiveTab("chat");
    }
  };

  const startActivityRecording = async () => {
    try {
      const started = await api.startActivityRecording({
        durationSeconds: settings?.activity_max_duration_seconds ?? 60,
        samplingHz: settings?.activity_sampling_hz ?? 1,
      });
      if (!started.ok) {
        setError(started.message);
        return;
      }
      setActivityStatus((previous) => ({ ...previous, current: started.session ?? null }));
      setMessages((previous) => [
        ...previous,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: `I started recording your activity for ${started.session?.requested_duration_seconds ?? settings?.activity_max_duration_seconds ?? 60} seconds. I'll send the full step-by-step summary here when it finishes.`,
        },
      ]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Activity recording could not start.");
    }
  };

  const stopActivityRecording = async () => {
    try {
      const stopped = await api.stopActivityRecording(activityStatus?.current?.id);
      setActivityStatus((previous) => ({
        current: null,
        last: stopped.session ?? previous?.last ?? null,
        summary: stopped.summary ?? previous?.summary ?? null,
      }));
      const completedSummary = stopped.summary ?? null;
      if (completedSummary) {
        surfacedActivitySummaryRef.current = completedSummary.session_id;
        setMessages((previous) => [
          ...previous,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            text: formatActivitySummary(completedSummary),
          },
        ]);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Activity recording could not stop.");
    }
  };

  const startRegionSelection = async () => {
    try {
      const context = await withScreenCaptureHidden(() => api.captureScreen());
      setPendingCapture(context);
      await window.genieShell?.openRegionOverlay?.({
        captureId: context.capture.id,
        width: context.capture.width,
        height: context.capture.height,
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Region selection could not start.");
    }
  };

  const handleMicClick = async () => {
    if (micStatus === "recording") {
      micControllerRef.current?.stop();
      return;
    }
    if (micStatus !== "idle") {
      return;
    }
    setError(null);
    setMicElapsed(0);
    setMicStatus("recording");

    try {
      const speechRecognition = startBrowserSpeechRecognition({
        maxSeconds: 30,
        onProgress: (seconds) => setMicElapsed(seconds),
      });
      let capturedValue = "";
      if (speechRecognition) {
        micControllerRef.current = speechRecognition;
        try {
          capturedValue = await speechRecognition.result;
        } catch {
          capturedValue = "";
        }
      }

      if (!capturedValue.trim()) {
        const recorder = startWavRecording({
          maxSeconds: 30,
          onProgress: (seconds) => setMicElapsed(seconds),
        });
        micControllerRef.current = recorder;
        capturedValue = await recorder.result;
      }

      micControllerRef.current = null;
      setMicStatus("transcribing");
      const next =
        speechRecognition && !looksLikeBase64Audio(capturedValue)
          ? String(capturedValue).trim()
          : (await api.transcribe({ audioBase64: String(capturedValue), audioFormat: "wav" })).text.trim();
      if (next) {
        setPrompt(next);
      } else {
        setError("No speech detected. Try again in a quieter environment.");
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Mic transcription failed.");
    } finally {
      micControllerRef.current = null;
      setMicStatus("idle");
      setMicElapsed(0);
    }
  };

  const clearGuidanceOverlay = async () => {
    await window.genieShell?.setGuidanceOverlay?.(null);
    setGuidedStatus((current) => {
      if (!current?.overlay_target) {
        return current;
      }
      return { ...current, overlay_target: null };
    });
  };

  const withScreenCaptureHidden = async <T,>(work: () => Promise<T>): Promise<T> => {
    if (!window.genieShell?.beginScreenCapture || !window.genieShell?.endScreenCapture) {
      return work();
    }
    await window.genieShell.beginScreenCapture();
    try {
      return await work();
    } finally {
      await window.genieShell.endScreenCapture();
    }
  };

  const runGuidedAction = async (
    action: "mark_done" | "next_step" | "pause" | "resume" | "rescan" | "cant_find_it",
  ) => {
    await clearGuidanceOverlay();
    const capturesScreen = action === "mark_done" || action === "next_step" || action === "rescan";
    const status = capturesScreen
      ? await withScreenCaptureHidden(() => api.actOnGuidedTask({ action, session_id: guidedStatus?.session?.id ?? null }))
      : await api.actOnGuidedTask({ action, session_id: guidedStatus?.session?.id ?? null });
    setGuidedStatus(status);
  };

  const handleSend = async () => {
    if (!prompt.trim()) {
      return;
    }
    const outgoingPrompt = prompt.trim();
    if (isGuidancePrompt(outgoingPrompt)) {
      await startGuidance(outgoingPrompt);
      return;
    }
    setLoading(true);
    setError(null);
    setPrompt("");
    const userMessage: MessageItem = { id: crypto.randomUUID(), role: "user", text: outgoingPrompt };
    setMessages((previous) => [...previous, userMessage]);

    try {
      const payload = await withScreenCaptureHidden(() =>
        api.chat({
          prompt: outgoingPrompt,
          use_current_screen: settings?.screen_share_enabled !== false,
          use_region: Boolean(regionContext),
          region_selection: regionContext?.selection ?? null,
          source_ids: sources.map((source) => source.id),
          conversation_id: conversationId,
        }),
      );
      const assistantMessage: MessageItem = {
        id: crypto.randomUUID(),
        role: "assistant",
        text: payload.answer,
        response: payload,
      };
      setMessages((previous) => [...previous, assistantMessage]);
      setLastResponse(payload);
      setConversationId(payload.conversation_id);
      setTraceEvents(payload.debug_steps);
      setGuidedStatus(payload.guided_task_status ?? null);

      if (settings?.tts_enabled) {
        void speakResponse(payload.answer);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Chat request failed.");
    } finally {
      setLoading(false);
      setActiveTab("chat");
    }
  };

  return (
    <div className={`shell ${isOpen ? "open" : "closed"}`}>
      {!isOpen ? (
        <Launcher open={isOpen} onToggle={() => void toggleOpen()} />
      ) : (
        <section ref={panelRef} className="panel">
          <header className="panel-header">
            <div>
              <span className="eyebrow">Genie</span>
              <h1>Genie</h1>
            </div>
            <div className="inline-actions">
              <button type="button" onClick={() => void toggleOpen()}>
                Collapse
              </button>
            </div>
          </header>

          {!backendReady ? (
            <section className="tab-section">
              <div className="section-header">
                <div>
                  <h3>Starting Genie</h3>
                  <p>{backendError ? "The local backend failed to start." : "Launching the local backend in the background..."}</p>
                </div>
                <div className="inline-actions">
                  <button
                    type="button"
                    onClick={async () => {
                      setBackendError(null);
                      try {
                        await window.genieShell?.ensureBackend?.();
                        setBackendReady(true);
                        await refreshSettings();
                      } catch (cause) {
                        setBackendReady(false);
                        setBackendError(cause instanceof Error ? cause.message : "Backend failed to start.");
                      }
                    }}
                  >
                    Retry
                  </button>
                  <button type="button" onClick={() => void window.genieShell?.openLogsFolder?.()}>
                    Open Logs Folder
                  </button>
                </div>
              </div>
              {backendError ? <p className="warning-banner">{backendError}</p> : <p className="empty-copy">Waiting for http://127.0.0.1:8765/health</p>}
            </section>
          ) : settings && !settings.onboarding_complete ? (
            <SetupWizard
              settings={settings}
              onComplete={async () => {
                await refreshSettings();
              }}
              onOpenLogs={() => void window.genieShell?.openLogsFolder?.()}
            />
          ) : (
          <nav className="tab-bar">
            {TABS.map((tab) => (
              <button
                key={tab}
                className={activeTab === tab ? "active" : ""}
                type="button"
                onClick={() => setActiveTab(tab)}
              >
                {TAB_LABELS[tab]}
              </button>
            ))}
          </nav>
          )}

          {backendReady && settings?.onboarding_complete && activeTab === "chat" ? (
            <section className="tab-section chat-tab">
              <div className="chat-toolbar sticky-toolbar">
                <button
                  type="button"
                  onClick={() => void startActivityRecording()}
                  disabled={activityStatus?.current?.status === "active"}
                >
                  {activityStatus?.current?.status === "active"
                    ? `Recording ${formatActivityTimer(activityStatus.current)}`
                    : "Track Screen"}
                </button>
                {activityStatus?.current?.status === "active" ? (
                  <button
                    type="button"
                    onClick={() => void stopActivityRecording()}
                  >
                    Stop Tracking
                  </button>
                ) : null}
                <button
                  type="button"
                  onClick={() => void startRegionSelection()}
                >
                  Draw Region
                </button>
                <button
                  type="button"
                  onClick={() => void handleMicClick()}
                >
                  {micStatus === "recording"
                    ? `Stop (${formatSeconds(micElapsed)} / 0:30)`
                    : micStatus === "transcribing"
                      ? "Transcribing..."
                      : "Mic"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    attachmentPickerRef.current?.click();
                  }}
                >
                  Attach Files
                </button>
                <input
                  ref={attachmentPickerRef}
                  type="file"
                  multiple
                  className="visually-hidden"
                  accept=".txt,.md,.pdf,.docx,.csv,.xlsx,.png,.jpg,.jpeg,.webp"
                  onChange={async (event) => {
                    const files = Array.from(event.target.files ?? []);
                    event.target.value = "";
                    if (!files.length) return;
                    try {
                      await api.addAttachments(conversationId, files);
                      await refreshAttachments();
                    } catch (cause) {
                      setError(cause instanceof Error ? cause.message : "Attachment upload failed.");
                    }
                  }}
                />
              </div>

              <GuidedTaskCard
                status={guidedStatus}
                showDebugLabels={settings?.guided_show_debug_labels ?? false}
                onMarkDone={async () => {
                  await runGuidedAction("mark_done");
                }}
                onNextStep={async () => {
                  await runGuidedAction("next_step");
                }}
                onRescan={async () => {
                  await runGuidedAction("rescan");
                }}
                onCantFind={async () => {
                  await clearGuidanceOverlay();
                  const waiting = await api.actOnGuidedTask({ action: "cant_find_it", session_id: guidedStatus?.session?.id ?? null });
                  setGuidedStatus(waiting);
                  setPendingGuidedRescan(true);
                  const context = await api.captureScreen();
                  setPendingCapture(context);
                  await window.genieShell?.openRegionOverlay?.({
                    captureId: context.capture.id,
                    width: context.capture.width,
                    height: context.capture.height,
                  });
                }}
                onPauseToggle={async () => {
                  const action = guidedStatus?.session?.status === "paused" ? "resume" : "pause";
                  await runGuidedAction(action);
                }}
                onStop={async () => {
                  await clearGuidanceOverlay();
                  const result = await api.stopGuidedTask(guidedStatus?.session?.id);
                  setGuidedStatus(result.status ?? null);
                  await clearGuidanceOverlay();
                }}
              />

              {activityStatus?.current?.status === "active" ? (
                <div className="diagnostics-card">
                  <strong>Recording active</strong>
                  <p>Timer: {formatActivityTimer(activityStatus.current)}</p>
                  <p>Frames captured: {activityStatus.current.frames_captured}</p>
                  <p>Sampling: {activityStatus.current.sampling_hz.toFixed(2)} fps</p>
                  <p>Last window: {activityStatus.current.last_window_title || "Unknown"}</p>
                </div>
              ) : null}

              {attachments.length ? (
                <div className="attachment-strip" aria-label="Session attachments">
                  {attachments.map((item) => (
                    <span key={item.id} className={`attachment-chip ${item.status === "failed" ? "failed" : ""}`}>
                      {item.filename}
                      <button
                        type="button"
                        title="Remove attachment"
                        onClick={async () => {
                          try {
                            await api.removeAttachment(conversationId, item.id);
                            await refreshAttachments();
                          } catch (cause) {
                            setError(cause instanceof Error ? cause.message : "Failed to remove attachment.");
                          }
                        }}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              ) : null}

              <div className="chat-scroll">
                <MessageList messages={messages} />
              </div>
              <div className="composer">
                <label className="field">
                  <span>Ask Genie</span>
                  <textarea
                    placeholder="Ask about your screen, a selected region, or your uploaded sources."
                    value={prompt}
                    onChange={(event) => setPrompt(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        if (!loading) {
                          void handleSend();
                        }
                      }
                    }}
                  />
                </label>
                <div className="composer-footer">
                  <span className="context-pill">{contextLabel || "no extra context attached"}</span>
                  <div className="inline-actions">
                    {isSpeaking ? (
                      <button type="button" onClick={() => void stopSpeaking()}>
                        Stop Voice
                      </button>
                    ) : null}
                    <button type="button" className="primary-button" disabled={loading} onClick={() => void handleSend()}>
                      {loading ? "Thinking..." : "Send"}
                    </button>
                  </div>
                </div>
              </div>
            </section>
          ) : null}

          {backendReady && settings?.onboarding_complete && activeTab === "sources" ? (
            <SourceManager
              sources={sources}
              onAdd={async (files) => {
                await api.addSources(files);
                await refreshSources();
              }}
              onReindex={async (sourceId) => {
                await api.reindexSource(sourceId);
                await refreshSources();
              }}
              onRemove={async (sourceId) => {
                await api.removeSource(sourceId);
                await refreshSources();
              }}
            />
          ) : null}

          {backendReady && settings?.onboarding_complete && activeTab === "settings" ? (
            <SettingsPanel
              customEndpoint={customEndpoint}
              customToken={customToken}
              customModel={customModel}
              health={health}
              localToken={localToken}
              localEndpoint={localEndpoint}
              localModel={localModel}
              localModelPath={localModelPath}
              onClearCredentials={async (providerId) => {
                await api.clearCredentials(providerId);
                setCustomToken("");
                setLocalToken("");
                await refreshSettings();
              }}
              onCustomEndpointChange={setCustomEndpoint}
              onCustomTokenChange={setCustomToken}
              onCustomModelChange={setCustomModel}
              onLocalTokenChange={setLocalToken}
              onLocalEndpointChange={setLocalEndpoint}
              onLocalModelChange={setLocalModel}
              onLocalModelPathChange={setLocalModelPath}
              onSaveCustom={async (endpoint, token, model) => {
                if (endpoint || token) {
                  await api.saveCredentials("custom", token, endpoint);
                }
                await api.updateSettings({ custom_endpoint: endpoint, custom_model: model, active_profile_id: "custom", onboarding_complete: true });
                await refreshSettings();
              }}
              onSaveLocal={async (endpoint, token, model) => {
                await api.saveCredentials("local", token);
                await api.updateSettings({ local_endpoint: endpoint, local_model: model, local_model_path: localModelPath, active_profile_id: "local", onboarding_complete: true });
                await refreshSettings();
              }}
              onSetProfile={async (profileId) => {
                await api.setActiveProfile(profileId);
                await refreshSettings();
              }}
              onToggleTts={async (enabled) => {
                await api.updateSettings({ tts_enabled: enabled });
                await refreshSettings();
              }}
              onToggleScreenShare={async (enabled) => {
                await api.updateSettings({ screen_share_enabled: enabled });
                await refreshSettings();
              }}
              onToggleActivityRecording={async (enabled) => {
                await api.updateSettings({ activity_recording_enabled: enabled });
                await refreshSettings();
              }}
              onToggleGuidedTask={async (enabled) => {
                await api.updateSettings({ guided_task_enabled: enabled });
                await refreshSettings();
              }}
              onGuidedOverlayStyleChange={async (value) => {
                await api.updateSettings({ guided_overlay_style: value });
                await refreshSettings();
              }}
              onGuidedAutoAdvanceSensitivityChange={async (value) => {
                await api.updateSettings({ guided_auto_advance_sensitivity: value });
                await refreshSettings();
              }}
              onGuidedCompletionModeChange={async (value) => {
                await api.updateSettings({ guided_completion_mode: value });
                await refreshSettings();
              }}
              onGuidedMaxPlanningStepsChange={async (value) => {
                await api.updateSettings({ guided_max_planning_steps: value });
                await refreshSettings();
              }}
              onToggleGuidedDebugLabels={async (enabled) => {
                await api.updateSettings({ guided_show_debug_labels: enabled });
                await refreshSettings();
              }}
              onActivitySamplingRateChange={async (value) => {
                await api.updateSettings({ activity_sampling_hz: value });
                await refreshSettings();
              }}
              onActivityMaxDurationChange={async (value) => {
                await api.updateSettings({ activity_max_duration_seconds: value });
                await refreshSettings();
              }}
              onOpenLogsFolder={async () => {
                await window.genieShell?.openLogsFolder?.();
              }}
              diagnostics={diagnostics}
              onRunDiagnostics={async () => {
                const result = await api.runDiagnostics();
                setDiagnostics(result);
              }}
              profiles={profiles}
              settings={settings}
            />
          ) : null}

          {backendReady && settings?.onboarding_complete && activeTab === "debug" ? (
            <DebugPanel error={error} response={lastResponse} traceEvents={traceEvents} guidedStatus={guidedStatus} />
          ) : null}

          <div className="window-resize-handle" onMouseDown={handleResizeStart} role="presentation" />
          {error ? <footer className="panel-footer warning-inline">{error}</footer> : null}
        </section>
      )}
    </div>
  );
}
