# Security

## Principles

- No real provider secrets are committed to git.
- The desktop client talks only to the local API.
- Public profile config files contain metadata only.
- Local/custom secrets are stored via the `SecureCredentialStore` abstraction.
- Demo mode may optionally use a **single dedicated credential/config file** for out-of-the-box AI in packaged demo builds (obscurity-only).

## Safe To Ship Publicly

- `apps/desktop` source.
- `services/local-api` source.
- `services/demo-gateway` scaffold and `.env.example`.
- `config/profiles/*.json` public config files.
- `resources/private/demo-provider.example.json` template (no real key).
- Docs, contracts, and tests.

## Must Stay Private

- Any upstream provider credentials (API keys/tokens) unless you intentionally bundle them into a demo build via the dedicated demo file.
- Any custom/local user credential values.
- Hosted provider account credentials.
- Production deployment environment files.

## Credential Handling

- Genie uses a `SecureCredentialStore` abstraction.
- Preferred path: OS keyring via Python `keyring`.
- Fallback path: dev-only local file storage with a warning.
- The fallback exists only so local development does not block product progress.

## Demo Credential File (Obscurity Only)

For demo builds, Genie can optionally read a single file at:

- `resources/private/demo-provider.json` (bundled into packaged app resources when present at build time)

Genie will not display the raw key in the UI, Settings, logs, or the debug panel.
If someone extracts the packaged file later, that is acceptable for this demo.

Details: see `docs/demo-credential-file.md`.

## Public Repository Notes

The public source repository must not contain private demo installers, model weights, databases, captures, logs, or local scratch files. The previous scratch Word document was removed from git history before publication because it contained local setup notes. Keep future demo credentials in ignored files only.

See `docs/public-repository-checklist.md` for the publication checklist.
