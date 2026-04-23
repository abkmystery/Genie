# Test Helpers

This folder is reserved for repo-level test helpers and future cross-service smoke assets.

Phase 1 keeps most executable tests beside each service, but the architecture also includes:

- mock credential stores
- in-memory repositories
- simulated screen artifacts
- lightweight profile loaders

The current Python mock/dev implementations live in `services/local-api/app/providers/dev_mocks.py`.
