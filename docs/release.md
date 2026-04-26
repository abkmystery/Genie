# Release

## Packaging Strategy

Phase 1 uses `electron-builder` from `apps/desktop` for desktop packaging.
In packaged builds, Electron starts the Python local backend automatically in the background (no terminal windows).

## Windows-Friendly Release Path

1. Install dependencies:

```powershell
npm.cmd install
py -3.11 -m pip install -r services/local-api/requirements.txt
```

2. Build a one-click backend executable:

```powershell
npm.cmd run build:backend
```

3. Build and package (public build):

```powershell
npm.cmd run package:public
```

This produces release artifacts under `apps/desktop/release/`.

Run the package audit before sharing a public artifact:

```powershell
npm.cmd run audit:package
```

## Demo Build With Bundled Demo Credential File

If you create `resources/private/demo-provider.json` locally (gitignored), `build:demo` will bundle it into the packaged app resources so Demo mode can use real AI out of the box.

```powershell
npm.cmd run package:demo
```

Details: see `docs/demo-credential-file.md`.

## Secret Safety

- Do not place real secrets in Electron env files.
- Do not bundle custom credential values into the app.
- Do not commit production gateway `.env` files.
- Public release bundles may include profile metadata and example configs only.
- Public release bundles must not include `demo-provider.json`, `.env` files, local databases, captures, model weights, or Python caches.

## Demo Mode

- Demo mode can resolve its provider config via:
  - a bundled demo credential file,
  - an optional remote single-file URL,
  - or an offline/mock fallback.

Genie does not show the raw demo key in UI/logs/debug; the file is still recoverable by inspection (obscurity-only).

## Optional Demo Gateway (Future/Private Hosting)

The repo still includes `services/demo-gateway` as an optional scaffold for future private hosting.
It is not required for one-click packaged demo builds.
