import { useMemo, useState } from "react";

import type { SettingsState } from "@genie/contracts";

import { api } from "../lib/api";

type Mode = "demo" | "local" | "custom";

const MODEL_PRESETS = ["gemma-4-26b-a4b-it", "gemma-4-31b-it", "gemma-3-*"];

interface SetupWizardProps {
  settings: SettingsState;
  onComplete(): Promise<void>;
  onOpenLogs(): void;
}

export function SetupWizard({ onComplete, onOpenLogs, settings }: SetupWizardProps) {
  const [mode, setMode] = useState<Mode>(settings.active_profile_id ?? "demo");
  const [localEndpoint, setLocalEndpoint] = useState(settings.local_endpoint ?? "");
  const [customEndpoint, setCustomEndpoint] = useState(settings.custom_endpoint ?? "");
  const [localToken, setLocalToken] = useState("");
  const [customToken, setCustomToken] = useState("");
  const [localModel, setLocalModel] = useState(settings.local_model ?? "gemma-4-26b-a4b-it");
  const [customModel, setCustomModel] = useState(settings.custom_model ?? "gemma-4-26b-a4b-it");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const modelSuggestions = useMemo(() => MODEL_PRESETS, []);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      if (mode === "demo") {
        await api.updateSettings({ active_profile_id: "demo", onboarding_complete: true });
      }
      if (mode === "local") {
        if (localToken) {
          await api.saveCredentials("local", localToken);
        }
        await api.updateSettings({
          active_profile_id: "local",
          local_endpoint: localEndpoint,
          local_model: localModel,
          onboarding_complete: true,
        });
      }
      if (mode === "custom") {
        if (customEndpoint || customToken) {
          await api.saveCredentials("custom", customToken, customEndpoint);
        }
        await api.updateSettings({
          active_profile_id: "custom",
          custom_endpoint: customEndpoint,
          custom_model: customModel,
          onboarding_complete: true,
        });
      }
      await onComplete();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Setup failed.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="tab-section">
      <div className="section-header">
        <div>
          <h3>Welcome to Genie</h3>
          <p>Pick a mode to get started. You can change this later in Settings.</p>
        </div>
        <div className="inline-actions">
          <button type="button" onClick={onOpenLogs}>
            Open Logs Folder
          </button>
        </div>
      </div>

      {error ? <p className="warning-banner">{error}</p> : null}

      <div className="profile-list">
        <label className={`profile-card ${mode === "demo" ? "active" : ""}`}>
          <input checked={mode === "demo"} type="radio" name="setup-mode" onChange={() => setMode("demo")} />
          <div>
            <strong>Demo</strong>
            <p>Works out of the box. Uses bundled/remote demo config when present, otherwise offline fallback.</p>
          </div>
        </label>
        <label className={`profile-card ${mode === "local" ? "active" : ""}`}>
          <input checked={mode === "local"} type="radio" name="setup-mode" onChange={() => setMode("local")} />
          <div>
            <strong>Local</strong>
            <p>Connect to a local model endpoint you control. Optional token and model selection.</p>
          </div>
        </label>
        <label className={`profile-card ${mode === "custom" ? "active" : ""}`}>
          <input checked={mode === "custom"} type="radio" name="setup-mode" onChange={() => setMode("custom")} />
          <div>
            <strong>Custom</strong>
            <p>Connect to any compatible endpoint. Provide endpoint + optional token and model name.</p>
          </div>
        </label>
      </div>

      {mode === "local" ? (
        <div className="settings-grid">
          <label className="field">
            <span>Local endpoint</span>
            <input value={localEndpoint} onChange={(e) => setLocalEndpoint(e.target.value)} placeholder="http://127.0.0.1:11434/v1" />
          </label>
          <label className="field">
            <span>Local token (optional)</span>
            <input type="password" value={localToken} onChange={(e) => setLocalToken(e.target.value)} placeholder="Optional bearer token" />
          </label>
          <label className="field">
            <span>Model</span>
            <input list="model-presets" value={localModel} onChange={(e) => setLocalModel(e.target.value)} placeholder="gemma-4-26b-a4b-it" />
          </label>
        </div>
      ) : null}

      {mode === "custom" ? (
        <div className="settings-grid">
          <label className="field">
            <span>Custom endpoint</span>
            <input value={customEndpoint} onChange={(e) => setCustomEndpoint(e.target.value)} placeholder="https://your-endpoint.example/v1" />
          </label>
          <label className="field">
            <span>Custom token (optional)</span>
            <input type="password" value={customToken} onChange={(e) => setCustomToken(e.target.value)} placeholder="Optional bearer token" />
          </label>
          <label className="field">
            <span>Model</span>
            <input list="model-presets" value={customModel} onChange={(e) => setCustomModel(e.target.value)} placeholder="gemma-4-26b-a4b-it" />
          </label>
        </div>
      ) : null}

      <datalist id="model-presets">
        {modelSuggestions.map((model) => (
          <option key={model} value={model} />
        ))}
      </datalist>

      <div className="inline-actions">
        <button type="button" className="primary-button" disabled={saving} onClick={() => void save()}>
          {saving ? "Saving..." : "Continue"}
        </button>
      </div>
    </section>
  );
}

