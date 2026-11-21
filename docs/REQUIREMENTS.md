# Requirement traceability

Every requirement from the assignment PDF, where it is implemented and how it is verified.
Tests are under `backend/tests/` and `frontend/src/test/` unless noted.

| # | Requirement (PDF section) | Implementation | Verification |
| --- | --- | --- | --- |
| 1 | Multi-turn chat UI (§2) | `frontend/src/App.tsx`, `hooks/useChat.ts` | `App.test.tsx`; browser run |
| 2 | Per-reply metadata: source, model, latency, input/output tokens (§2, §5) | `components/MessageMeta.tsx` | `App.test.tsx` checks each test id's exact text |
| 3 | Optional system prompt (§2, §3) | `SettingsPanel.tsx`; `sessions.system_prompt` | `test_custom_system_prompt_applies_to_session_but_not_history` |
| 4 | History stored per session; bot remembers (§2) | `repository.py`, `chat_service._build_messages` | `test_multi_turn_sends_full_history_with_system_prompt` |
| 5 | ≥ 2 keys, failover on 429 / quota / 5xx (§2) | `llm/gateway.py` | `test_first_key_error_fails_over_to_second_key[429/500/503]`; real Gemini 401 failover seen in Docker logs |
| 6 | LiteLLM built-in cache, LLM_CACHE / LIVE_INFERENCE (§2) | `configure_litellm` (`Cache(type="local")`) | `test_cache.py` (real LiteLLM cache) |
| 7 | Per-request token usage (§2, §3) | `gateway._usage` | `test_token_usage_is_per_request_and_matches_provider` |
| 8 | SQLite only, under a volume, `DATABASE_URL`, auto schema (§2) | `db.py`, `docker-compose.yml` (`chat-data:/data`) | `test_history_is_persisted_in_sqlite_and_survives_restart`; container restart check |
| 9 | Data model `messages(id, session_id, role, content, metadata, created_at)` (§2) | `db.Message` (+ `sessions` table, index, FK) | SQL query in the persistence test |
| 10 | `GET /health` → status, keys_configured, cache_enabled (§3) | `api/routes.health` | `test_health_*` |
| 11 | `POST /chat` request rules: session_id 1–128, message 1–4000 after trim (§3) | `schemas.ChatRequest` | `test_invalid_chat_requests_return_422...` (10 cases), 4000-char boundary |
| 12 | `/chat` response fields and types (§3) | `schemas.ChatResponse` | `test_first_chat_returns_full_contract` |
| 13 | `GET /sessions/{id}/messages`, oldest first, no system prompt, 404 (§3) | `routes.session_messages` | `test_history_endpoint_*`, `test_unknown_session_history_returns_404` |
| 14 | JSON errors only, never stack traces; 422 / 503 / 404 bodies (§3) | FastAPI defaults + `main.unhandled_exception` | `test_malformed_json_returns_422`, `test_unexpected_server_error_is_clean_json...` |
| 15 | Failed requests (422 / 503) are not stored (§3) | write happens only after success, in one transaction | 422 tests, `test_all_keys_failing...`, `test_failed_turn_does_not_corrupt_existing_history` |
| 16 | Cache key = model + full message list; same first message → LLM_CACHE; different → never cached (§3) | LiteLLM key (model+messages), `max_messages=None` | `test_same_first_message...`, `test_different_message...`, `test_cache_key_includes_history/system_prompt` |
| 17 | Cache hit: identical reply, stored tokens, key_id null, 0 fallbacks, faster (§3) | `gateway.complete` | `test_same_first_message_in_new_session_is_served_from_cache` |
| 18 | Equal-length first messages → about equal input tokens (§3) | provider usage | `test_equal_length_first_messages_report_same_input_tokens` |
| 19 | `X-Simulate-Failure`: format, `*`, statuses 429/500/502/503, single request only (§4) | `llm/simulation.py`, gateway | `test_failover.py` simulation tests, `test_units.py` |
| 20 | Honoured only when `ENABLE_FAILURE_SIMULATION=true` (§4) | `routes._failure_plan` | `test_header_is_ignored_when_simulation_is_disabled` |
| 21 | `key_1=429` / `key_1=500` → 200 key_2; `*=429` → 503, nothing stored (§4) | gateway | parametrised simulation tests |
| 22 | Simulated request returns a real answer (§4) | real key called after simulated failures | `test_simulated_first_key_failure_fails_over` asserts real reply + real key_2 call |
| 23 | data-testids: chat-input (empty after send), send-button, assistant-message, meta-* (§5) | `Composer.tsx`, `Messages.tsx`, `MessageMeta.tsx` | `App.test.tsx`; Playwright run |
| 24 | `system-prompt-input` (§5) | `SettingsPanel.tsx` | `App.test.tsx` |
| 25 | New session on each page load (§5) | `useChat` creates a session id on mount | `App.test.tsx` (New chat → new id) |
| 26 | 422 / 503 shown as readable messages (§5) | `api/client.ts`, `ErrorMessage` | `App.test.tsx` (503, 422, network) |
| 27 | Backend allows the frontend origin (§5) | `CORSMiddleware` from `ALLOWED_ORIGINS` | `test_cors_*` |
| 28 | `make up`: backend :8000, frontend :3000 (§6) | `Makefile`, `docker-compose.yml` | compose stack run and health-checked |
| 29 | Multi-stage Dockerfiles, small runtime images (§6) | `backend/Dockerfile`, `frontend/Dockerfile` | both built |
| 30 | Named volume at `/data` (§6) | `chat-data:/data` | restart persistence check |
| 31 | All config via env vars; `.env.example`; no secrets in repo (§6, §7) | `config.py`, `.env.example`, `.gitignore` | `git check-ignore .env` |
| 32 | Repository structure (§7) | root layout | n/a |
| 33 | Backend tests (§7) | `backend/tests` (69 tests) | `make test` |
| 34 | README with the six headings (§7) | `README.md` | n/a |
| 35 | Live deployment of both tiers (§2, §7) | `render.yaml` | **pending: needs the owner's Render account and API keys** |
| 36 | 2–3 min demo video (§7) | n/a | **pending: recorded by the candidate** |
