# Odoo 18.0 Custom Setup — Design Spec

**Date:** 2026-03-11
**Author:** Manuel Caro
**Status:** Draft

---

## Goal

Set up a local, Dockerized Odoo 18.0 environment with the jorels-odoo-addons plugin installed, version-controlled in a private GitHub repository, ready for future custom module development.

---

## Repository

- **GitHub:** `remcaro-rgb/odoo-custom` (private, all-lowercase)
- **Local path:** `/Users/manuelcaro/Odoo`

---

## Repository Structure

```
odoo-custom/
├── odoo/                        # Odoo 18.0 source (git submodule, read-only)
├── addons/
│   └── jorels-odoo-addons/      # git submodule from GitLab (branch 18.0, public repo)
├── custom-addons/               # placeholder for future custom modules
│   └── .gitkeep
├── config/
│   └── odoo.conf
├── .env                         # Local dev credentials — git-ignored, NOT for production
├── docker-compose.yml
├── Dockerfile
├── .gitmodules
└── .gitignore
```

---

## Components

### 1. Git Submodules

| Submodule | Source | Branch | Auth |
|---|---|---|---|
| `odoo/` | `https://github.com/odoo/odoo` | `18.0` | public |
| `addons/jorels-odoo-addons/` | `https://gitlab.com/jorels-community/jorels-odoo-addons` | `18.0` | public |

**Pinning mechanism:** The commit SHA recorded by `git submodule add` in `.gitmodules` pins the exact revision. `--depth=1` is a bandwidth/storage optimization only — it does not pin the commit.

**Shallow clone caveat:** Do NOT set `shallow = true` in `.gitmodules` for `odoo/odoo`. A shallow clone with `depth=1` only fetches the branch tip; if the pinned SHA is not the current tip (almost always the case), collaborators will get `fatal: reference is not a tree`. The `odoo/` submodule must be cloned at full depth. Only `jorels-odoo-addons` (smaller repo) may safely use shallow cloning.

**Rationale for `odoo/` submodule:** Including Odoo source allows pinning to an exact commit for full reproducibility and building from source. The `odoo/` directory is treated as read-only — no core modifications are made.

### 2. Dockerfile

- **Base image:** `python:3.12-slim` (Debian Bookworm based)
  - Odoo 18.0 officially supports Python 3.10–3.12
  - All development runs inside the container; local Python version is irrelevant
- **System dependencies:**
  ```
  build-essential libpq-dev libxml2-dev libxslt1-dev libldap2-dev
  libsasl2-dev libjpeg-dev curl gnupg nodejs npm
  ```
- **less CSS compiler:** installed via `npm install -g less` (the `node-less` apt package is unavailable on Debian Bookworm)
- **wkhtmltopdf:** Odoo-compatible patched build from `github.com/odoo/wkhtmltopdf/releases` — NOT the distro package and NOT `nightly.odoo.com` (which hosts Odoo installers, not wkhtmltopdf). Pin to a specific release tag compatible with Debian Bookworm amd64.
- **Dockerfile RUN ordering:** All `apt-get install` calls must be in a single `RUN apt-get update && apt-get install -y ...` layer to avoid stale cache and broken package resolution.
- **Python deps:** installed from `odoo/requirements.txt`
- **Exposed port:** `8069`

### 3. docker-compose.yml

**Named volumes (top-level declaration):**
```yaml
volumes:
  odoo-db-data:
  odoo-filestore:
```

**`db` service** — `postgres:15-alpine`
- Environment from `.env` (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`)
- Volume: `odoo-db-data:/var/lib/postgresql/data`
- Healthcheck:
  ```yaml
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U odoo -h localhost"]
    interval: 5s
    retries: 5
  ```

**`odoo` service** — built from local Dockerfile
- `depends_on: db: condition: service_healthy` (waits for postgres to accept connections)
- Volume mounts (host → container):
  | Host path | Container path | Purpose |
  |---|---|---|
  | `./odoo` | `/odoo` | Odoo source |
  | `./addons/jorels-odoo-addons` | `/mnt/jorels-addons` | jorels addons |
  | `./custom-addons` | `/mnt/custom-addons` | custom modules |
  | `./config/odoo.conf` | `/etc/odoo/odoo.conf` | Odoo config |
  | `odoo-filestore` | `/var/lib/odoo` | Filestore persistence |
- Port: `8069:8069`

### 4. .env (git-ignored)

```env
POSTGRES_USER=odoo
POSTGRES_PASSWORD=odoo
POSTGRES_DB=odoo
```

> **Warning:** These credentials are for local development only. Change them before deploying to any shared or production environment.

### 5. odoo.conf

```ini
[options]
addons_path = /odoo/odoo/addons,/odoo/addons,/mnt/jorels-addons,/mnt/custom-addons
db_host = db
db_port = 5432
db_user = odoo
db_password = odoo
```

- `/odoo/odoo/addons` — Odoo core framework modules (`base`, `web`, `mail`, etc.)
- `/odoo/addons` — Odoo community addons
- Mount paths match the container-side mount points defined in `docker-compose.yml`.

---

## Data Flow

```
docker compose up
    ├── postgres:15-alpine starts
    │       └── healthcheck: pg_isready -U odoo -h localhost → passes
    └── odoo container starts (after db healthy)
            ├── reads /etc/odoo/odoo.conf
            ├── connects to db service on port 5432
            └── serves on localhost:8069
```

---

## GitHub Setup

1. `gh repo create remcaro-rgb/odoo-custom --private` (repo name is lowercase)
2. `git init` in `/Users/manuelcaro/Odoo`
3. `git submodule add --depth=1 https://github.com/odoo/odoo odoo && git -C odoo fetch --depth=1`
4. `git submodule add --depth=1 https://gitlab.com/jorels-community/jorels-odoo-addons addons/jorels-odoo-addons`
5. Set `shallow = true` in `.gitmodules` for both submodules
6. Initial commit + push to `main`

---

## Error Handling

- **DB readiness:** postgres healthcheck + `depends_on: condition: service_healthy` ensures Odoo does not start until postgres accepts connections
- **wkhtmltopdf:** pinned to Odoo-compatible patched build from `nightly.odoo.com`
- **less compiler:** installed via npm, not apt, to work on Debian Bookworm
- **Submodule size:** `shallow = true` in `.gitmodules` ensures collaborators also get shallow clones
- **`.gitignore` excludes:** `*.pyc`, `__pycache__/`, `.env`, `odoo-filestore/`, `*.log`

---

## Testing / Verification

1. `docker compose build` — completes without errors
2. `docker compose up` — both services start; `db` passes healthcheck; `odoo` is reachable
3. `http://localhost:8069` — Odoo setup wizard loads
4. After DB initialization: Settings → Activate Developer Mode → Apps → click **Update Apps List** → search "jorels" — modules appear (Developer Mode is required for the Update Apps List button to be visible)
5. `git submodule status` — both submodules show pinned SHA
6. `gh repo view remcaro-rgb/odoo-custom` — confirms private repo on GitHub

---

## Future Extensibility

- Add custom modules to `custom-addons/` — no other changes needed
- `odoo/` source is read-only; update via `git submodule update --remote` when needed
- Upgrade path: change submodule branch refs to future Odoo versions
