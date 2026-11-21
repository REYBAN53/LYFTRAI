# Lyftr Chat: an LLM chatbot with key failover and response caching

A full-stack chat app. **React + TypeScript** frontend, **FastAPI** backend, **LiteLLM** as the
model gateway (key-pool failover plus LiteLLM's built-in response cache) and **SQLite** for
session history. Every assistant reply shows where it came from (`LIVE_INFERENCE` or
`LLM_CACHE`), the model, the latency, per-request input/output tokens, and which API key
answered after how many failovers.

```
 Browser (React)            FastAPI backend                                    Model provider
┌───────────────┐  POST   ┌───────────────────────────────────────────────┐  (e.g. Gemini)
│ chat UI       │ /chat   │ routes ─► ChatService ─► LLMGateway            │
│ metadata chips├────────►│             │   │          │ for key in pool:  │   key_1 ──► 429 ✗
│ settings      │◄────────┤             │   │          │  litellm          │   key_2 ──► 200 ✓
└───────────────┘  JSON   │             │   │          │  .acompletion() ──┼─►
                          │             │   │          │   └ LiteLLM cache │
                          │             ▼   └─ save turn (one transaction) │
                          │        ChatRepository ──► SQLite /data/app.db  │
                          └───────────────────────────────────────────────┘
```

---

## 1. Live URLs

| Tier | URL |
| --- | --- |
| Frontend | _Pending deployment_ |
| Backend | _Pending deployment_ (`/health`, `/chat`, `/sessions/{id}/messages`) |
| Demo video | _Pending_ |

Deployment steps are in [Deploying](#deploying-render) below. Both tiers are public and need no login.

---

## 2. Run locally: with Docker and without

### Prerequisites: API keys

The backend needs **at least two** LLM API keys. The default model is
`gemini/gemini-flash-lite-latest`, which has a free tier:

1. Open <https://aistudio.google.com/apikey> and create a key.
2. Create a **second key in a different Google Cloud project**. Free-tier quota is per project,
   so two keys in one project share one quota and failover between them would not help.
3. Put both in `.env` (never in source code):

```bash
cp .env.example .env
# edit .env:  LLM_API_KEYS=AIza...first,AIza...second
```

Any LiteLLM-supported provider works. Set `LLM_MODEL` (e.g. `groq/openai/gpt-oss-20b`) and use
keys for that provider.

### With Docker (recommended)

```bash
make up     # builds both images, starts backend on :8000 and frontend on :3000
make down   # stops the stack; history stays in the named volume `chat-data`
```

- Frontend: <http://localhost:3000>
- Backend: <http://localhost:8000/health> (interactive docs at <http://localhost:8000/docs>)

Other targets: `make logs`, `make ps`, `make test` (backend + frontend tests in Docker),
`make clean` (stop **and delete** the SQLite volume).

### Without Docker

Backend (Python 3.12+):

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.asgi:app --reload --port 8000    # reads ../.env; SQLite at backend/data/app.db
pytest                                       # 69 backend tests
```

Frontend (Node 22+), in a second terminal:

```bash
cd frontend
npm ci
npm run dev        # http://localhost:3000, calls http://localhost:8000 by default
npm test           # component tests
```

### Configuration

All configuration is through environment variables. `.env.example` lists every one.

| Variable | Default | Meaning |
| --- | --- | --- |
| `LLM_API_KEYS` | (none) | Comma-separated key pool, ≥ 2. Ids are `key_1`, `key_2`, … in order |
| `DATABASE_URL` | `sqlite:///./data/app.db` | SQLite location (`sqlite:////data/app.db` in Docker) |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated CORS origins |
| `ENABLE_FAILURE_SIMULATION` | `false` (`true` in compose) | Enables the `X-Simulate-Failure` header |
| `LLM_MODEL` | `gemini/gemini-flash-lite-latest` | Any LiteLLM model string |
| `LLM_TIMEOUT_SECONDS` | `30` | Per-key request timeout |
| `LLM_MAX_TOKENS` | `1024` | Max completion tokens |
| `LLM_CACHE_TTL_SECONDS` | `86400` | Lifetime of a cached response |
| `DEFAULT_SYSTEM_PROMPT` | helpful-assistant prompt | Used when a session sets none |
| `LOG_LEVEL` | `INFO` | Backend log level |
| `API_BASE_URL` | `http://localhost:8000` | **Frontend container**: backend URL, injected at container start |
| `VITE_API_BASE_URL` | (none) | **Frontend static build** (Render/Vercel/Netlify): backend URL baked in at build time |

---

## 3. Design decisions: key fallback, caching, SQLite session storage

### Backend layout

```
backend/app/
  api/routes.py      HTTP only: the 3 endpoints, header parsing, status codes
  chat_service.py    orchestration: load history → build messages → gateway → persist
  llm/gateway.py     LiteLLM calls, ordered key failover, cache configuration
  llm/keys.py        key pool (key_1, key_2, …); secrets hidden from repr/logs
  llm/simulation.py  X-Simulate-Failure parser (a per-request value object)
  repository.py      all SQL (SQLAlchemy), atomic turn persistence
  db.py, schemas.py, config.py, main.py (app factory, CORS, JSON error handler)
```

Each layer has one job. Routes never touch SQL, the service never touches HTTP, and the gateway
knows nothing about sessions. `create_app(settings)` is a factory, so tests build isolated apps
with their own database and key pool.

### Key fallback

The gateway walks the pool **in order** and calls `litellm.acompletion(..., api_key=<key>, num_retries=0)`:

```
for key in [key_1, key_2, ...]:
    simulated failure for this key?  → record, try next key (the provider is never called)
    call LiteLLM with this key
      success → return reply + key_id + fallback_attempts = number of keys that failed first
      error   → record (status, error type), try next key
all failed → HTTP 503 {"detail": "all providers unavailable"}
```

- **What triggers failover:** any provider-side error, which covers 429 / quota exhaustion, 5xx,
  timeouts, connection errors and auth errors (a revoked key should not take the app down).
  LiteLLM normalises every provider's errors into typed exceptions with a `status_code`, so this
  works for any vendor. An empty completion (e.g. blocked by a safety filter) also counts as a
  failed attempt.
- **Why an explicit loop instead of `litellm.Router`:** the contract needs the *exact* key that
  answered and the number of keys that failed first. The simulation hook must also fail
  specific keys *for one request only*. The Router's deployment cooldowns would turn a simulated
  429 into shared state that changes how later, unrelated requests are routed. A ten-line ordered
  loop keeps this deterministic, testable and easy to explain. LiteLLM still does what it is good
  at: one API for every provider, error normalisation, token usage and caching.
- `num_retries=0` because retrying the *same* rate-limited key only adds latency. Failover to the
  next key is the retry.
- **Never leaking keys:** keys are only ever referenced by id. `ApiKey.secret` is excluded from
  `repr`, and provider error text is redacted before it is logged. A test asserts that no secret
  appears in responses or logs during failover.

### X-Simulate-Failure

`key_1=429`, `key_1=429,key_2=500`, `*=503`, … (statuses 429/500/502/503; an explicit key entry
beats `*`). The header is parsed into an immutable `FailurePlan` that lives only for that request,
so it cannot leak into other requests or mark a real key unhealthy. It is honoured only when
`ENABLE_FAILURE_SIMULATION=true`, and ignored otherwise. A malformed header returns 422 with an
explanation.

While a simulation is active, the request **skips the cache read** (`cache={"no-cache": True}`).
Otherwise a previously cached answer would hide the outage, and `key_1=429` would answer from
cache with `key_id: null` instead of demonstrating `key_2`. The result is still written to the
cache. A simulated request always returns a real model answer from a real key, never an error
wrapped in a 200.

### Caching (LiteLLM built-in)

`litellm.cache = Cache(type="local", ttl=LLM_CACHE_TTL_SECONDS, max_messages=None)`. This is
LiteLLM's own in-memory cache, not a hand-written dictionary. I verified several behaviours
against the installed LiteLLM source rather than assuming them:

| Finding | Consequence / what I did |
| --- | --- |
| LiteLLM's cache key is built from `model`, `messages` and sampling params. **The API key is not part of it.** | Exactly the contract: model + the full message list (system prompt + history + new message). One cache entry serves every key in the pool, so a cache hit happens before any key is used → `key_id: null`, `fallback_attempts: 0`. |
| By default LiteLLM **skips caching for requests with more than 4 messages** (`max_messages=4`). | Set `max_messages=None`, otherwise any conversation past its second turn would never be cached. Covered by a test. |
| In LiteLLM 1.110.2 the cache-read path imports modules needing `orjson` and `soundfile`, which the base package does not declare. Without them **every cache lookup silently missed**. | Pinned both in `requirements.txt` with a comment. The cache tests fail if this regresses. |
| The disk cache type was removed in this LiteLLM version. | Used the in-memory cache (the assignment allows either). |
| LiteLLM imports its cache-hit code lazily (~150 ms on the first hit). | Pre-imported at startup so the first cache hit is also fast. |
| A cached response keeps its original `usage` and sets `_hidden_params["cache_hit"]`. | Cache hits report the stored token counts and `resolution_source: LLM_CACHE`. |

Consequences: an identical first message in a new session returns `LLM_CACHE` with an identical
reply. Any difference in system prompt, history or message is a different key and runs live
inference. The cache lives in process memory, so it is cleared on restart and the backend runs a
single worker on purpose. Sharing it across replicas would need an external store such as Redis,
which the assignment rules out.

### SQLite session storage

- **Schema** (created automatically on startup by `Base.metadata.create_all`): the required
  `messages` table, unchanged in shape (`id, session_id, role, content, metadata JSON, created_at
  ISO-8601`), plus:
  - a `sessions` table (`id, system_prompt, created_at, updated_at`). It stores the session's
    system-prompt override, so the prompt applies to the whole session but is **never** returned
    by the history endpoint. It also gives a cheap "does this session exist" check for the 404.
  - a composite index `(session_id, id)` so loading one session's history in order is an index
    range scan.
  - a foreign key from `messages.session_id` to `sessions.id`, with `PRAGMA foreign_keys=ON`.
- **Atomic turns:** the user message and the assistant reply are written in **one transaction
  after** the model has answered. A request that fails (422, 503 or anything else) writes nothing,
  so history can never contain an unanswered question or half a turn.
- **Ordering:** history is ordered by the autoincrement `id` (oldest first). That is exact even
  when two rows share a `created_at` millisecond.
- **Concurrency:** WAL journal mode (readers never block the writer), plus a per-session
  `asyncio.Lock` so two concurrent requests in the *same* session cannot interleave their history.
  Different sessions run fully in parallel.
- **Location:** `DATABASE_URL=sqlite:////data/app.db` on the named Docker volume `chat-data`, so
  history survives `make down` / `make up` and container restarts. I verified this by restarting
  the backend container and reading the history back.

### Tokens and latency

`input_tokens` / `output_tokens` are the provider-reported `usage` of **this** request: the full
prompt (system + history + new message) and this reply. They are never a running total. On a
cache hit they are the usage stored with the cached response. `latency_ms` is measured on the
server, from receiving the request to having the reply (history load + cache lookup or inference).

### Frontend

- `api/client.ts`: a typed fetch wrapper that turns every failure (422 details, 503, network
  error, timeout) into a readable `ApiError`. The UI never shows a blank screen.
- `hooks/useChat.ts`: conversation state. The session id is generated client-side on each page
  load and on "New chat". A failed message is marked "Not sent" and can be retried; because the
  server stored nothing, a retry cannot create duplicates.
- Components are small and presentational (`MessageMeta`, `Composer`, `Messages`, `SettingsPanel`,
  …). All contract `data-testid`s contain exactly the contract value, with labels and icons kept
  outside those elements.
- The Docker image is static files on unprivileged nginx. The backend URL is injected **at
  container start** (`API_BASE_URL` → `/env-config.js`), so one image works against any backend.
  Static hosts use `VITE_API_BASE_URL` at build time instead.

### Infrastructure

- Backend Dockerfile: `builder` (virtualenv with pinned deps) → `test` (optional target that runs
  pytest) → `runtime` (`python:3.12-slim` + the virtualenv only, non-root user, health check).
  LiteLLM and its dependency tree are most of the image size.
- Frontend Dockerfile: `node:22-alpine` installs, **runs the tests** and builds →
  `nginx-unprivileged:alpine` serves `dist/` (~80 MB image).
- `docker-compose.yml`: both services, the named volume `chat-data` at `/data`, `.env` loaded if
  present.

---

## 4. Verification: how to see failover, cache hits and per-message token usage

### Automated tests

```bash
make test          # or: cd backend && pytest   /   cd frontend && npm test
```

The backend suite (69 tests) replaces only the network hop to the model vendor, using a
**LiteLLM custom provider** rather than patching `litellm.acompletion`. Every test request
therefore goes through the real LiteLLM pipeline **including its real cache**.

| Area | Tests |
| --- | --- |
| Health | `/health` shape; 503 when no keys |
| Errors | unexpected server error → clean JSON 500, no stack trace, nothing stored; unknown route is JSON |
| Validation (422) | missing/empty/blank/oversize `session_id`; missing/empty/whitespace-only message; 4001 chars rejected; exactly 4000 after trimming accepted; wrong types; malformed JSON; nothing persisted |
| Chat | full response contract; per-request token accounting; equal-length first messages report equal input tokens |
| Multi-turn | the provider receives system + full history + new message, in order |
| Sessions | isolation between sessions; system prompt override persists per session and never appears in history |
| History | oldest first; assistant metadata stored as JSON; 404 for unknown sessions |
| Persistence | rows checked directly in the SQLite file; history survives an app restart |
| Cache | same first message in a new session → `LLM_CACHE`, identical reply and tokens, `key_id` null, 0 fallbacks, faster, provider called once; different message, history or system prompt → miss; conversations longer than 4 messages are cached; cache hit even when key_1 is down |
| Failover (real errors) | key_1 429/500/503 → key_2 with `fallback_attempts: 1`; all keys down → 503; failed turn leaves history intact; keys never appear in responses or logs |
| X-Simulate-Failure | `key_1=429/500/502/503` → key_2; `*=429`, `key_1=429,key_2=500` → 503 with nothing stored; applies to one request only; bypasses the cache; 3 keys → key_3 with 2 fallbacks; ignored when disabled; malformed header → 422 |

The frontend tests check: Enter sends and clears the input; every metadata `data-testid` holds
exactly its contract value; the send button is disabled while loading and for empty input; 503,
422 and network errors render as readable messages with Retry; the system prompt and simulation
header are sent; "New chat" uses a new session id.

### Manual verification with curl

Set the backend URL once (local or deployed):

```bash
export API=http://localhost:8000
```

**Health**

```bash
curl -s $API/health
# {"status":"ok","keys_configured":2,"cache_enabled":true,"model":"gemini/gemini-flash-lite-latest","failure_simulation_enabled":true}
```

**Normal chat** (look at `metadata`: `LIVE_INFERENCE`, `key_1`, tokens, latency)

```bash
curl -s -X POST $API/chat -H 'Content-Type: application/json' \
  -d '{"session_id":"demo-1","message":"What is the capital of France?"}'
```

**Multi-turn** (same session; the bot remembers the earlier message)

```bash
curl -s -X POST $API/chat -H 'Content-Type: application/json' \
  -d '{"session_id":"demo-mt","message":"My name is Ada and I love chess."}'
curl -s -X POST $API/chat -H 'Content-Type: application/json' \
  -d '{"session_id":"demo-mt","message":"What is my name and what do I love?"}'
```

**History** (oldest first, metadata per assistant message, no system prompt)

```bash
curl -s $API/sessions/demo-mt/messages
curl -s $API/sessions/does-not-exist/messages        # 404 {"detail":"session not found"}
```

**Cache hit** (same first message in a *new* session → `LLM_CACHE`, identical reply, same
tokens, `key_id: null`, much lower `latency_ms`)

```bash
curl -s -X POST $API/chat -H 'Content-Type: application/json' \
  -d '{"session_id":"cache-a","message":"Name three primary colors."}'
curl -s -X POST $API/chat -H 'Content-Type: application/json' \
  -d '{"session_id":"cache-b","message":"Name three primary colors."}'
```

**Failover: first key fails** (needs `ENABLE_FAILURE_SIMULATION=true`; expect 200, `key_id:
"key_2"`, `fallback_attempts: 1`, a real answer)

```bash
curl -s -X POST $API/chat -H 'Content-Type: application/json' \
  -H 'X-Simulate-Failure: key_1=429' \
  -d '{"session_id":"fo-1","message":"Say hello in French."}'
curl -s -X POST $API/chat -H 'Content-Type: application/json' \
  -H 'X-Simulate-Failure: key_1=500' \
  -d '{"session_id":"fo-2","message":"Say hello in Spanish."}'
```

**All keys fail** (expect 503 `{"detail":"all providers unavailable"}` and nothing stored)

```bash
curl -s -w '\nHTTP %{http_code}\n' -X POST $API/chat -H 'Content-Type: application/json' \
  -H 'X-Simulate-Failure: *=429' \
  -d '{"session_id":"fo-down","message":"Anyone there?"}'
curl -s $API/sessions/fo-down/messages               # 404: the failed turn was not stored
```

**Validation** (each returns 422 with a `detail`)

```bash
curl -s -X POST $API/chat -H 'Content-Type: application/json' -d '{"session_id":"v","message":"   "}'
curl -s -X POST $API/chat -H 'Content-Type: application/json' -d '{"message":"no session"}'
curl -s -X POST $API/chat -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"v\",\"message\":\"$(printf 'x%.0s' {1..4001})\"}"
curl -s -X POST $API/chat -H 'Content-Type: application/json' -d '{"session_id":'
```

The backend logs each turn without secrets, for example:

```
WARNING app.llm.gateway: key key_1 failed (simulated HTTP 429); failing over
INFO    app.chat_service: chat session=fo-1 source=LIVE_INFERENCE key=key_2 fallbacks=1 tokens=31/9 latency=640ms
```

### In the UI

1. Send a message: the reply shows `LIVE_INFERENCE`, the model, `… ms`, `in N`, `out M` and `key_1`.
2. Click **New chat** and send the same first message: the badge turns green `LLM_CACHE`, the
   latency drops to a few ms, the tokens match and no key chip is shown.
3. **Settings → Failover simulation → `key_1=429`**, then send a message: the key chip shows
   `key_2 · 1 failover`.
4. Choose `*=429`: a readable "All model providers are unavailable" card appears with **Retry**.
   The message is marked "Not sent" and is not stored.

Token usage is shown **per reply** (`in` / `out` chips), never as a conversation total.

### Deploying (Render)

`render.yaml` is a Render Blueprint for both tiers (free plans):

1. Push this repo to GitHub (public). In Render: **New → Blueprint** → select the repo.
2. When prompted, set the secrets in the Render dashboard (never in the repo):
   - backend `LLM_API_KEYS` = `key1,key2`
   - backend `ALLOWED_ORIGINS` = the frontend URL, e.g. `https://lyftr-chat-frontend.onrender.com`
   - frontend `VITE_API_BASE_URL` = the backend URL, e.g. `https://lyftr-chat-backend.onrender.com`
3. After the first deploy, check `ALLOWED_ORIGINS` and `VITE_API_BASE_URL` against the actual
   URLs. If you change `VITE_API_BASE_URL`, redeploy the frontend, because it is baked in at build
   time.
4. Verify with the curl commands above against the live backend URL.

Notes: Render's free web services sleep after inactivity (the first request can take ~1 min), and
their filesystem is ephemeral. Locally, history persists on the Docker volume. For durable history
on Render, attach a persistent disk at `/data` (paid plan) or use Railway / Fly.io volumes. The
same Docker image works unchanged; it honours `$PORT`.

---

## 5. Setup Used

- **Editor:** _fill in (e.g. VS Code)_
- **AI tools:** Claude Code (Anthropic) for architecture, implementation, tests and
  verification. Every behaviour claimed above was checked by running the tests or the stack.
- **Runtime:** Python 3.12 (Docker) / 3.13 (local), Node 22, Docker Compose v2.

---

## 6. Bonus features (if any)

| Feature | Why |
| --- | --- |
| Optional **system prompt** per session (`system-prompt-input`), persisted server-side and never shown in history | Part of the brief's optional scope. Stored on the session so it applies to every turn without the client resending it |
| **Failover simulation picker** in the UI (sends `X-Simulate-Failure`) | Failover can be demonstrated from the browser, not only with curl |
| **Retry** on failed messages; failed messages marked "Not sent" | Pairs with "failed turns are never stored", so retrying cannot duplicate history |
| **Key / failover chip** (`key_2 · 1 failover`) next to the required metadata | Makes resilience visible per reply |
| **Markdown rendering** (GFM tables, code blocks, lists; raw HTML disabled) and **copy** button | LLM output is mostly Markdown; raw HTML stays disabled for XSS safety |
| **Health badge** (model, key count) from `/health` | Shows immediately whether the frontend can reach the backend |
| Empty state with suggestions; Enter / Shift+Enter; auto-growing input; character counter near 4000; auto-scroll with "jump to latest"; light/dark themes; mobile layout; reduced-motion support; accessible labels | Polish and accessibility without extra dependencies |
| Per-session lock, WAL mode, composite index, FK | Correct under concurrent requests; fast history reads |
| `make test` runs both test suites in Docker; the frontend image build runs its tests | A broken build cannot ship |
| Runtime-configurable frontend image (`API_BASE_URL`) | One image for every environment |
