# Public Repository Checklist

Use this checklist before making the GitHub repository public or sharing a source link with judges.

## Required For Public Source

- The repository is accessible without login.
- `README.md` explains the product, architecture, commands, and Gemma 4 implementation.
- `SUBMISSION.md` summarizes the competition story and judge-visible flows.
- `docs/gemma-4-implementation.md` maps Gemma 4 behavior to source files.
- `docs/judge-quickstart.md` gives a short validation path.
- `docs/validation-report.md` lists the required checks.

## Must Not Be Public

- `resources/private/demo-provider.json`
- `resources/private/demo-provider.json.txt`
- `.env` files with real values
- local SQLite databases
- model weights under `models/`
- packaged release output under `apps/desktop/release/`
- screenshots, captured frames, and activity artifacts
- local logs and cache directories
- personal scratch documents

## Secret Checks

Recommended local checks:

```powershell
git grep -n -I "GEMINI_API_KEY" -- .
git grep -n -I "Bearer <real-token>" -- .
git log --all --oneline -S "<real-provider-key-fragment>" -- .
```

Expected result:

- No real key values are found.
- `GEMINI_API_KEY` appears only in server-side examples or code that reads environment variables.

## History Cleanup

The previous local scratch Word document was removed from git history before publication because it contained local setup notes that did not belong in public source. Keep scratch notes out of commits.

## Public vs Demo Builds

Public build:

```powershell
npm.cmd run package:public
```

Private demo build:

```powershell
npm.cmd run package:demo
```

Only use `package:demo` when you intentionally want a local ignored demo credential file bundled into a private installer. Do not upload that installer as the public source artifact.
