# Free deployment: GitHub + Oracle Always Free, each user brings their own OpenAI key

## Decisions
- **Users:** public. Each user adds their own OpenAI key, stored encrypted on the server, used only for their requests, and deletable at any time. The server holds no shared key.
- **Hosting:** one Oracle Cloud "Always Free" Ampere A1 VM.
  - It runs the existing `docker-compose.yml` (backend, plus the frontend served by nginx), with Caddy in front for free HTTPS.
  - The SQLite database, uploads and exports live on the VM's disk.
- **Code:** a private GitHub repository. GitHub Actions runs the tests on every change and deploys `main` to the VM.
- **Cost:** ₹0 for hosting, domain, certificates, backups, CI and monitoring. Users pay for their own OpenAI usage.

**Why not the other free hosts:**
- Render, Hugging Face, Cloud Run and Koyeb free tiers sleep when idle and/or lose files on restart. That would wipe the SQLite database and the uploads.
- Answers take 1–2 minutes, which some free proxies cut off.
- Vercel or Netlify for the frontend would put the app and API on different domains, which breaks the device cookie and needs new CORS work.
- One VM keeps everything on one origin and needs no database migration.

## Architecture
```
GitHub (private repo) ──CI on PR──▶ tests (offline, no key)
        │ push to main
        ▼ (Actions → SSH)
Oracle VM (Ubuntu 24.04 arm64, Mumbai or Hyderabad)
  Caddy :443  (Let's Encrypt, nyaysaathi.duckdns.org)
    └─▶ frontend (nginx: built React app, /api → backend)
          └─▶ backend (FastAPI/uvicorn)
                ├─ /srv/nyay/runtime  (SQLite, uploads, exports)   ← nightly backup → OCI Object Storage
                └─ /srv/nyay/.env     (secrets, 0600, never in git)
Browser ──WebRTC voice──▶ OpenAI Realtime (ephemeral secret minted with the user's own key)
```

## Phase 0: Put the code on GitHub (about 30 minutes)
1. **Check the history is clean.** Checked on 2026-11-09:
   - `.env`, `runtime/`, `*.sqlite*`, `uploads/` and `data/sources/originals/` are git-ignored and never committed;
   - the only key-shaped string in history is the fake test value in `backend/tests/test_devspace.py`.

   Run `gitleaks detect` once anyway before the first push.
2. **Create the repo.** Create a **private** repo (for example `nyay-saathi`), then:
   - `git remote add origin …`;
   - push `main` and `snapshot/2026-11-08-hardening-and-citations`;
   - open a PR from the snapshot branch into `main`.
3. **Protect `main`:** require the CI check and a PR, with no direct pushes. Enable secret scanning and push protection if your plan offers them; gitleaks in CI covers it either way.
4. **Decide about `docs/plans/`** (untracked): commit it, or add it to `.gitignore`.
5. **Don't commit** `runtime/nyay_saathi.sqlite3`. It holds your test conversations, encrypted with the dev master key. Production starts with a fresh database.

## Phase 1: Each user brings their own key (code, before going public)
Today one key (`settings.openai_api_key`) serves everyone. It's read in about 12 places: `model_calls.sdk`, `web_research.py`, `practice/engine.py`, `api/voice.py`, `routes.py` (transcribe and speech), `rag/discover.py`, `rag/retrieval.py` and `graph/workflow.py`. The `ai_configured` check is used across the app.

1. **Encrypted storage.**
   - A new table `owner_api_keys(owner_id PK, wrapped_key, key_hint, created_at, last_used_at)`.
   - The key is encrypted with the existing envelope cipher (`app/security/privacy.py` `EnvelopeCipher`, wrapped by `KMS_MASTER_KEY`).
   - Only the last 4 characters are ever shown.
   - Deleting a device's data also deletes its key.
2. **API** in a new `app/api/user_key.py`:
   - `GET /api/me/openai-key` returns `{configured, hint}`.
   - `PUT` validates the key with a no-cost call (`client.models.list()`) before saving, and is rate-limited.
   - `DELETE` removes the key.
   - Owner identity uses the existing `owner_context` device cookie.
3. **One request-scoped key.**
   - A new `app/security/user_key.py` holds a `ContextVar`, set by a dependency from the owner's stored key.
   - `api_key_for(settings)` and `key_available(settings)` replace every direct `settings.openai_api_key` / `ai_configured` use.
   - The turn task (`asyncio.create_task` in `routes.py`) inherits the context.
   - Thread pools (`web_research.py:430`) run tasks with `copy_context()`, as `research.py` already does.
   - Resuming an interrupted turn loads the owner's key by `owner_id`.
4. **Disable DevSpace and the server key.**
   - `DEVSPACE_ENABLED=false`, so the DevSpace endpoints return 404. The global models, limits and `.env` editing stay operator-only, done over SSH.
   - `OPENAI_API_KEY` is left empty on the server.
5. **Frontend.**
   - **Settings key card:** "Your OpenAI key" in Settings, reusing the DevSpace key card from `DevSpacePanel.tsx`: paste, show/hide, masked hint, and a remove action.
   - **Banner:** "Add your OpenAI key to start" replaces the "AI not configured" banner.
   - **Errors:** an OpenAI 401 or quota error shows "Your key was rejected or is out of credit".
   - **Privacy note:** "Stored encrypted on the server, used only for your requests, delete any time."
6. **Limits stay per device:** the hourly call and cost caps (`DEVICE_HOURLY_*`) protect each user's own credit. `REQUESTS_PER_MINUTE` protects the server.
7. **Tests** (offline, with fake clients):
   - two owners with different keys never share a client or key, including during streaming, research thread pools and resume;
   - no key gives a friendly 402/409 asking to add one;
   - the key never appears in responses, logs, exports, the escalation bundle or error text;
   - an invalid key is rejected on `PUT`;
   - DevSpace returns 404 when disabled;
   - deleting a device's data removes its key.

## Phase 2: Production configuration (code and config, in the repo)
1. **`docker-compose.prod.yml`** (an override):
   - adds a `caddy` service (ports 80/443, `Caddyfile`, a `caddy-data` volume for certificates);
   - binds `/srv/nyay/runtime` instead of a named volume, and reads `/srv/nyay/.env`;
   - sets `restart: unless-stopped`, and log rotation (`json-file`, 10 MB × 3);
   - removes the public `8000` and `5173` ports (only Caddy is exposed).
2. **`Caddyfile`:** `nyaysaathi.duckdns.org { reverse_proxy frontend:80 }`, plus security headers.
3. **`frontend/nginx.conf`:**
   - `proxy_read_timeout 300s` instead of 70s, since answers can take about 140 s;
   - keep `proxy_buffering off` so streaming works.
4. **Fail-fast startup guard** in `main.py`, when `COOKIE_SECURE=true` (meaning production). The app refuses to start if:
   - `KMS_MASTER_KEY` still has the dev default;
   - `CREDENTIAL_SIGNING_SECRET` is missing;
   - `ALLOW_LEGACY_UNSIGNED_COOKIE` is true;
   - `DEVSPACE_ENABLED` is true;
   - or `APP_ORIGIN` isn't `https://`.
5. **`.env.production.example`:**
   - `APP_ORIGIN=https://nyaysaathi.duckdns.org`
   - `COOKIE_SECURE=true`
   - `ALLOW_LEGACY_UNSIGNED_COOKIE=false`
   - `DEVSPACE_ENABLED=false`
   - `KMS_MASTER_KEY=<64 random chars>`
   - `CREDENTIAL_SIGNING_SECRET=<64 random chars>`
   - the storage paths under `/app/runtime`
   - no `OPENAI_API_KEY`
6. **ARM check:** build both images for `linux/arm64` once (`docker buildx build --platform linux/arm64`). That covers `python:3.12-slim`, tesseract, `uv`, `chromadb` and PyMuPDF wheels, `node:24-alpine` and `nginx`. Fix any missing wheel before Phase 4.

## Phase 3: The Oracle VM (about 1 hour, one time)
1. **Sign up** for Oracle Cloud Free Tier. The card is for identity only, and Always Free resources aren't charged.
   - Home region: **India South (Hyderabad)** or **India West (Mumbai)**. You can't change it later.
   - Optional but recommended: upgrade to "Pay As You Go" and set a ₹1 budget alert. It's still free within Always Free limits, and it stops Oracle reclaiming "idle" Always Free VMs.
2. **Create the instance:**
   - shape `VM.Standard.A1.Flex` with 2 OCPU and 12 GB RAM (half the free allowance, leaving room);
   - Ubuntu 24.04 (aarch64) with a 100 GB boot volume;
   - your SSH public key.
   - If it says "out of capacity", retry later or in another availability domain.
3. **Network:**
   - security list ingress 22 (your IP only, if practical), 80 and 443;
   - on the VM, `ufw allow 22,80,443/tcp`.
4. **Hardening:** a non-root `deploy` user, key-only SSH (`PasswordAuthentication no`), `unattended-upgrades` and `fail2ban`.
5. **Install:** Docker Engine with the compose plugin, `git`, `sqlite3` and `rclone`.
6. **Domain:** create `nyaysaathi.duckdns.org` on duckdns.org, pointing to the VM's public IP. Add a cron job to update it if the IP ever changes.

## Phase 4: First deployment
1. **Get the code onto the VM:**
   - add a **read-only deploy key** on GitHub (repo → Settings → Deploy keys) with the VM's key;
   - `git clone` into `/srv/nyay/app`.
2. **Set up secrets:**
   - create `/srv/nyay/.env` from `.env.production.example`, with `chmod 600`;
   - generate the secrets with `openssl rand -hex 32`;
   - **save `KMS_MASTER_KEY` and `CREDENTIAL_SIGNING_SECRET` in a password manager.** Losing the master key makes every encrypted conversation, and every backup, unreadable.
3. **Start:** `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`. Caddy gets the certificate automatically.
4. **Smoke test** at `https://nyaysaathi.duckdns.org`:
   - `/api/health` returns OK;
   - adding a key works;
   - a short English turn and a Hinglish turn work;
   - a document upload works;
   - the voice hold-to-talk works (it needs HTTPS);
   - the PDF and Word bundle downloads work;
   - DevSpace returns 404;
   - a second browser without a key sees "add your key".

## Phase 5: Automatic tests and deployment (GitHub Actions)
1. **`.github/workflows/ci.yml`**, on every PR and push:
   - backend: `uv sync --frozen`, `ruff check app`, `pytest` (offline, no key), and the offline release gates;
   - frontend: `npm ci`, `tsc --noEmit`, `vitest`, `npm run build`;
   - plus `gitleaks`.

   About 5 minutes a run, well inside the 2,000 free minutes a month for private repos. Playwright end-to-end tests run on demand only, to save minutes.
2. **`.github/workflows/deploy.yml`**, on push to `main` after CI passes:
   - SSH into the VM, using the secrets `DEPLOY_HOST`, `DEPLOY_USER` and `DEPLOY_SSH_KEY`;
   - run `git pull --ff-only && docker compose … up -d --build`;
   - wait for `https://…/api/health`;
   - on failure, check out the previous commit and rebuild.
3. **Releases:** tag each production deploy (`v2026.11.10-1`). Rolling back means re-running the deploy for the previous tag.

## Phase 6: Database backups and monitoring
1. **Nightly backup** at 02:30 IST, by a cron script `scripts/ops/backup.sh`:
   - `sqlite3 nyay_saathi.sqlite3 ".backup /tmp/…"` (a consistent copy while the app runs), the same for `checkpoints.sqlite3`, and a tar of `uploads/` and `exports/`;
   - `rclone` copies them to **OCI Object Storage** (Always Free 20 GB), keeping 14 daily and 8 weekly copies;
   - backups are already encrypted at rest by the app's field encryption, and stay private in the bucket.
2. **Monthly restore drill:** restore the latest backup into a scratch container and open one conversation.
3. **Uptime:** a free UptimeRobot check on `/api/health` every 5 minutes, with email alerts.
4. **Disk alert:** a cron job emails or logs when `/srv` passes 80%. The disk is 100 GB and uploads are capped at 10 MB each.
5. **Logs:** `docker compose logs`, with rotation from Phase 2. The app already avoids logging message text, keys and secrets; Phase 1 tests guard the key.

## Launch checklist
- Every CI check passes on `main`, and the startup guard passes with the production `.env`.
- DevSpace returns 404 publicly, and there's no `OPENAI_API_KEY` on the server.
- The master key and signing secret are in a password manager, and a backup has been restored once.
- HTTPS works, the voice mic works over HTTPS, and cookies are `Secure; SameSite=Lax`.
- Test with two different browsers and two different keys: each sees only its own conversations, and spend shows up on the right key in the OpenAI dashboard.
- The privacy note explains key storage and how to delete it.

## Order and effort
| Step | Who | Effort |
|---|---|---|
| 0. GitHub repo, branch protection, PR | you (click-through) and an agent | 30 min |
| 1. Each user brings their own key (code and tests) | an agent | about 1 day |
| 2. Production config, startup guard, ARM build check | an agent | 2–3 h |
| 3. Oracle sign-up, VM, DuckDNS | you (needs your card and login) | 1 h |
| 4. First deploy and smoke test | you, guided | 1 h |
| 5. CI/CD workflows | an agent | 1–2 h |
| 6. Backups and monitoring | an agent, then you add the cron and rclone credentials | 1 h |

Phases 0 and 3 need your accounts, so only you can do them. Everything else can be done and tested offline before the VM exists.
