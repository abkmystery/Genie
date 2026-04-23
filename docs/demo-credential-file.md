# Demo Credential File (Phase 1)

Genie "Demo" mode can optionally use a single dedicated credential/config file to enable real model calls without any user setup.

This mechanism is **obscurity only, not security**. The file may be recoverable by inspecting the packaged app resources. Genie will not display the raw key in the UI, Settings, logs, or the debug panel.

## Credential Source Order (Demo Mode)

Genie resolves demo credentials/config in this order:

1. **Bundled local file** inside the packaged app resources
2. **Optional remote single-file URL** (if configured)
3. **Offline/mock fallback** (always available)

## Bundled Local File (Primary)

Expected path inside packaged resources:

- `resources/private/demo-provider.json`

During development, you can place it at:

- `resources/private/demo-provider.json` (repo root)

This file is **gitignored by default**.

## File Format

### Preferred: JSON

```json
{
  "provider_type": "google_gemini_openai_compatible",
  "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
  "api_key": "PUT_KEY_HERE",
  "model": "gemma-4-26b-a4b-it",
  "timeout_ms": 60000,
  "supports_images": true,
  "supports_audio_input": false,
  "notes": "demo mode provider config"
}
```

Optional light obfuscation is supported:

- `api_key_b64`: base64-encoded key
- or `api_key` starting with `b64:` followed by base64 data

### Optional: Plain Text

If the file is plain text (not valid JSON), its contents are treated as the API key only.

Defaults in that case:

- `base_url`: `https://generativelanguage.googleapis.com/v1beta/openai/`
- `model`: `gemma-4-26b-a4b-it`

## Optional Remote Single-File Source (Secondary)

The demo profile config can optionally include a remote URL:

- `remote_demo_file_url`
- `remote_demo_file_format` (`json` or `text`)

If `remote_demo_file_url` is blank, remote fetching is skipped.
If fetching fails, Genie continues the fallback chain.

## Build Behavior

Genie supports two build flavors:

1. **Public build**: does not require a real `demo-provider.json`; Demo mode falls back to offline/mock if missing.
2. **Demo build**: if `resources/private/demo-provider.json` exists locally at build time, it is bundled into the packaged resources and used automatically.

The example template lives at:

- `resources/private/demo-provider.example.json`

