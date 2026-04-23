import type { ProviderConfig, SettingsState } from "@genie/contracts";

import type { HealthPayload } from "../lib/api";

interface SettingsPanelProps {
  profiles: ProviderConfig[];
  settings: SettingsState | null;
  health: HealthPayload | null;
  customToken: string;
  customEndpoint: string;
  customModel: string;
  localToken: string;
  localEndpoint: string;
  localModel: string;
  localModelPath: string;
  onSetProfile(profileId: string): Promise<void>;
  onSaveCustom(endpoint: string, token: string, model: string): Promise<void>;
  onSaveLocal(endpoint: string, token: string, model: string): Promise<void>;
  onToggleTts(enabled: boolean): Promise<void>;
  onToggleScreenShare(enabled: boolean): Promise<void>;
  onToggleActivityRecording(enabled: boolean): Promise<void>;
  onToggleGuidedTask(enabled: boolean): Promise<void>;
  onGuidedOverlayStyleChange(value: "arrow_only" | "highlight_only" | "arrow_pulse"): Promise<void>;
  onGuidedAutoAdvanceSensitivityChange(value: number): Promise<void>;
  onGuidedCompletionModeChange(value: "conservative" | "balanced"): Promise<void>;
  onGuidedMaxPlanningStepsChange(value: number): Promise<void>;
  onToggleGuidedDebugLabels(enabled: boolean): Promise<void>;
  onActivitySamplingRateChange(value: number): Promise<void>;
  onActivityMaxDurationChange(value: number): Promise<void>;
  onClearCredentials(providerId: string): Promise<void>;
  onCustomTokenChange(value: string): void;
  onCustomEndpointChange(value: string): void;
  onCustomModelChange(value: string): void;
  onLocalTokenChange(value: string): void;
  onLocalEndpointChange(value: string): void;
  onLocalModelChange(value: string): void;
  onLocalModelPathChange(value: string): void;
  onOpenLogsFolder(): Promise<void>;
  onRunDiagnostics(): Promise<void>;
  diagnostics: Record<string, unknown> | null;
}

export function SettingsPanel({
  profiles,
  settings,
  health,
  customToken,
  customEndpoint,
  customModel,
  localToken,
  localEndpoint,
  localModel,
  localModelPath,
  onSetProfile,
  onSaveCustom,
  onSaveLocal,
  onToggleTts,
  onToggleScreenShare,
  onToggleActivityRecording,
  onToggleGuidedTask,
  onGuidedOverlayStyleChange,
  onGuidedAutoAdvanceSensitivityChange,
  onGuidedCompletionModeChange,
  onGuidedMaxPlanningStepsChange,
  onToggleGuidedDebugLabels,
  onActivitySamplingRateChange,
  onActivityMaxDurationChange,
  onClearCredentials,
  onCustomTokenChange,
  onCustomEndpointChange,
  onCustomModelChange,
  onLocalTokenChange,
  onLocalEndpointChange,
  onLocalModelChange,
  onLocalModelPathChange,
  onOpenLogsFolder,
  onRunDiagnostics,
  diagnostics,
}: SettingsPanelProps) {
  const activeProfile = settings?.active_profile_id ?? "demo";

  return (
    <section className="tab-section">
      <div className="section-header">
        <div>
          <h3>Settings</h3>
          <p>Switch profiles without editing source code and store credentials behind the secure store abstraction.</p>
        </div>
        <div className="inline-actions">
          <button type="button" onClick={() => void onOpenLogsFolder()}>
            Open Logs Folder
          </button>
        </div>
      </div>

      {settings?.secure_storage_warning ? <p className="warning-banner">{settings.secure_storage_warning}</p> : null}

      <div className="profile-list">
        {profiles.map((profile) => (
          <label key={profile.id} className={`profile-card ${activeProfile === profile.id ? "active" : ""}`}>
            <input
              checked={activeProfile === profile.id}
              type="radio"
              name="profile"
              onChange={() => onSetProfile(profile.id)}
            />
            <div>
              <strong>{profile.display_name}</strong>
              <p>{profile.description}</p>
              <small>
                transport={profile.transport} · model={profile.model_name} · screen=
                {String(profile.capabilities.supports_screen_input)}
              </small>
            </div>
          </label>
        ))}
      </div>

      <div className="settings-grid">
        <label className="field">
          <span>Local endpoint</span>
          <input
            value={localEndpoint}
            onChange={(event) => onLocalEndpointChange(event.target.value)}
            placeholder="http://127.0.0.1:8766/v1"
          />
        </label>
        <label className="field">
          <span>Local profile token</span>
          <input
            type="password"
            value={localToken}
            onChange={(event) => onLocalTokenChange(event.target.value)}
            placeholder="Optional token for your local model endpoint"
          />
        </label>
        <label className="field">
          <span>Local model</span>
          <input
            value={localModel}
            onChange={(event) => onLocalModelChange(event.target.value)}
            placeholder="google/gemma-4-E4B-it"
            list="model-presets"
          />
        </label>
        <label className="field">
          <span>Local model folder</span>
          <input
            value={localModelPath}
            onChange={(event) => onLocalModelPathChange(event.target.value)}
            placeholder="C:\\Users\\you\\Downloads\\Genie\\models\\gemma-4-E4B-it"
          />
        </label>
        <div className="inline-actions">
          <button type="button" onClick={() => onSaveLocal(localEndpoint, localToken, localModel)}>
            Save Local Credential
          </button>
          <button type="button" onClick={() => onClearCredentials("local")}>
            Clear Local Credential
          </button>
        </div>
        <label className="field">
          <span>Custom endpoint</span>
          <input
            value={customEndpoint}
            onChange={(event) => onCustomEndpointChange(event.target.value)}
            placeholder="https://your-endpoint.example/v1"
          />
        </label>
        <label className="field">
          <span>Custom token</span>
          <input
            type="password"
            value={customToken}
            onChange={(event) => onCustomTokenChange(event.target.value)}
            placeholder="Optional bearer token"
          />
        </label>
        <label className="field">
          <span>Custom model</span>
          <input
            value={customModel}
            onChange={(event) => onCustomModelChange(event.target.value)}
            placeholder="gemma-4-26b-a4b-it"
            list="model-presets"
          />
        </label>
        <div className="inline-actions">
          <button
            type="button"
            onClick={() => {
              onSaveCustom(customEndpoint, customToken, customModel);
            }}
          >
            Save Custom Profile
          </button>
          <button type="button" onClick={() => onClearCredentials("custom")}>
            Clear Custom Credentials
          </button>
        </div>
      </div>

      <datalist id="model-presets">
        <option value="google/gemma-4-E4B-it" />
        <option value="google/gemma-4-E2B-it" />
        <option value="gemma-4-26b-a4b-it" />
        <option value="gemma-4-31b-it" />
        <option value="gemma-3-*" />
      </datalist>

      <label className="toggle-row">
        <input checked={settings?.tts_enabled ?? false} type="checkbox" onChange={(event) => onToggleTts(event.target.checked)} />
        <span>Speak answers when TTS is enabled</span>
      </label>

      <label className="toggle-row">
        <input
          checked={settings?.screen_share_enabled ?? true}
          type="checkbox"
          onChange={(event) => onToggleScreenShare(event.target.checked)}
        />
        <span>Attach current screen to chat automatically</span>
      </label>

      <label className="toggle-row">
        <input
          checked={settings?.activity_recording_enabled ?? true}
          type="checkbox"
          onChange={(event) => onToggleActivityRecording(event.target.checked)}
        />
        <span>Enable explicit activity recording sessions</span>
      </label>

      <label className="toggle-row">
        <input
          checked={settings?.guided_task_enabled ?? true}
          type="checkbox"
          onChange={(event) => void onToggleGuidedTask(event.target.checked)}
        />
        <span>Enable Guided Task mode with on-screen arrows and step cards</span>
      </label>

      <div className="settings-grid">
        <label className="field">
          <span>Activity sampling rate (fps)</span>
          <input
            type="number"
            min="0.25"
            max="2"
            step="0.25"
            value={settings?.activity_sampling_hz ?? 1}
            onChange={(event) => void onActivitySamplingRateChange(Number(event.target.value || "1"))}
          />
        </label>
        <label className="field">
          <span>Max recording duration (seconds)</span>
          <input
            type="number"
            min="15"
            max="300"
            step="15"
            value={settings?.activity_max_duration_seconds ?? 60}
            onChange={(event) => void onActivityMaxDurationChange(Number(event.target.value || "60"))}
          />
        </label>
      </div>

      <div className="settings-grid">
        <label className="field">
          <span>Guidance overlay style</span>
          <select
            value={settings?.guided_overlay_style ?? "arrow_pulse"}
            onChange={(event) => void onGuidedOverlayStyleChange(event.target.value as "arrow_only" | "highlight_only" | "arrow_pulse")}
          >
            <option value="arrow_only">Arrow only</option>
            <option value="highlight_only">Highlight only</option>
            <option value="arrow_pulse">Arrow + pulse</option>
          </select>
        </label>
        <label className="field">
          <span>Guidance completion mode</span>
          <select
            value={settings?.guided_completion_mode ?? "conservative"}
            onChange={(event) => void onGuidedCompletionModeChange(event.target.value as "conservative" | "balanced")}
          >
            <option value="conservative">Conservative</option>
            <option value="balanced">Balanced</option>
          </select>
        </label>
        <label className="field">
          <span>Auto-advance sensitivity</span>
          <input
            type="number"
            min="0.5"
            max="0.99"
            step="0.05"
            value={settings?.guided_auto_advance_sensitivity ?? 0.85}
            onChange={(event) => void onGuidedAutoAdvanceSensitivityChange(Number(event.target.value || "0.85"))}
          />
        </label>
        <label className="field">
          <span>Max planning steps</span>
          <input
            type="number"
            min="2"
            max="12"
            step="1"
            value={settings?.guided_max_planning_steps ?? 6}
            onChange={(event) => void onGuidedMaxPlanningStepsChange(Number(event.target.value || "6"))}
          />
        </label>
      </div>

      <label className="toggle-row">
        <input
          checked={settings?.guided_show_debug_labels ?? false}
          type="checkbox"
          onChange={(event) => void onToggleGuidedDebugLabels(event.target.checked)}
        />
        <span>Show guidance confidence and debug labels</span>
      </label>

      {health ? (
        <div className="diagnostics-card">
          <strong>Diagnostics</strong>
          <p>Profile: {health.profile.display_name}</p>
          <p>Credential storage: {health.storage_mode}</p>
          {health.demo_status ? (
            <p>
              Demo provider: source={health.demo_status.source} · model={health.demo_status.model} · configured=
              {String(health.demo_status.api_key_present)}
            </p>
          ) : null}
          <div className="inline-actions">
            <button type="button" onClick={() => void onRunDiagnostics()}>
              Run Diagnostics
            </button>
          </div>
          {diagnostics ? (
            <pre className="diagnostics-output">{JSON.stringify(diagnostics, null, 2)}</pre>
          ) : null}
          {health.warnings.map((warning) => (
            <p key={warning} className="warning-inline">
              {warning}
            </p>
          ))}
        </div>
      ) : null}
    </section>
  );
}
