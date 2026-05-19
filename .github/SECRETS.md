# GitHub Actions secrets

The `.github/workflows/ci.yml` cross-platform deploy gate needs these
repository secrets configured at **Settings → Secrets and variables →
Actions → Repository secrets**.

| Secret | Used by | Where to get it |
|---|---|---|
| `RAILWAY_TOKEN` | `ci.yml` deploy-railway | **Project token** from Project Settings → Tokens. Project tokens still work for `railway up` deploys but **fail every other `railway` command** in CLI v4.58+. |
| `RAILWAY_API_TOKEN` | `pgbackrest-backup.yml` backup-railway, `restore-drill.yml` drill-railway | **Account-level token** from https://railway.com/account/tokens (or a CLI session token from `~/.railway/config.json`'s `user.token` as a 30-day stopgap). Required by `railway ssh` and `railway whoami` in CLI v4.58+. Set via `gh secret set RAILWAY_API_TOKEN -R GoliattCo/odoo-custom --body "<token>"` — **always use `--body`** (the bare `-b -` form stores the literal value `-`; observed corrupting a `RAILWAY_TOKEN` secret to a 1-byte `-` during this incident's investigation). |
| `RAILWAY_SSH_PRIVATE_KEY` | `pgbackrest-backup.yml` backup-railway, `restore-drill.yml` drill-railway | **PEM-encoded private key** (full file contents including header/footer). CLI v4.58+ requires keys to be both present in `~/.ssh/` AND registered on the Railway account — auto-registration was removed. Generate a dedicated keypair with `ssh-keygen -t ed25519 -N "" -f ~/.ssh/gha_rw_ed25519 -C "gh-actions-pgbackrest@odoo-saas"`, register the public half via `railway ssh keys add --key ~/.ssh/gha_rw_ed25519.pub --name "gh-actions-pgbackrest"` (the `--key` flag still scans `~/.ssh/` for existence — keep the key under `~/.ssh/` even though `--key` is supplied), then set the secret via `gh secret set RAILWAY_SSH_PRIVATE_KEY -R GoliattCo/odoo-custom --body "$(cat ~/.ssh/gha_rw_ed25519)"`. Rotate by generating a new pair, registering it, swapping the secret, then `railway ssh keys remove gh-actions-pgbackrest` for the old. |
| `RAILWAY_ODOO_SERVICE_ID` | `ci.yml` deploy-railway | Railway dashboard → odoo service → Settings → service ID at the top of the page (`919deb8a-3ca5-4c48-8577-ea89f6c9cf90` for current pilot). |
| `RAILWAY_PROJECT_ID` | `pgbackrest-backup.yml` backup-railway | `465dcc94-8004-4b4c-ad19-039d1b9b90c8` for the `odoo-saas` project. `railway status` shows it. |
| `RAILWAY_ENVIRONMENT_ID` | `pgbackrest-backup.yml` backup-railway | `41fa1df4-6faa-4dae-beed-644fa6354180` for the `production` env. `railway variables --service postgres --kv` shows it. |
| `FLY_API_TOKEN` | `ci.yml` deploy-fly | `flyctl tokens create deploy --app odoo-saas-odoo --name "gh-deploy"` (deploy-only scope is fine; CI just runs `flyctl deploy`). |
| `FLY_SSH_TOKEN_POSTGRES` | `pgbackrest-backup.yml` backup-fly, `restore-drill.yml` drill-fly | `flyctl tokens create ssh --app odoo-saas-postgres --name "gh-actions-pgbackrest-ssh"`. **Must be ssh-scoped, NOT deploy** — deploy tokens can't run the GraphQL `appcompact` query that `flyctl ssh console` needs (observed: 401 "You must be authenticated to view this."). SSH tokens additionally include the org-wireguard scope. |

## Environments

The workflow uses two GitHub Environments to gate deploys:

- `staging-railway`
- `staging-fly`

Configure at **Settings → Environments**. For each, you can:

- Add reviewers if you want manual approval before each deploy.
- Set environment-specific secrets (overrides the repo-level ones).
- Set a wait timer (e.g., 5 minutes between merges and deploys).

For Phase 1 pilot, leave reviewers off — automatic deploys on merge to main.

## Why two environments instead of one?

Railway and Fly have separate failure modes, separate auth, separate
quotas. Splitting into two environments means a Fly token rotation
doesn't accidentally invalidate Railway deploys, and vice versa. The
`cross-platform-gate` job at the end of the workflow stitches them back
together to enforce parity.

## Rotating tokens

Quarterly:

```
# Railway — RAILWAY_TOKEN (deploy)
# Railway dashboard → Project → Tokens → revoke old token, create new one
# Update RAILWAY_TOKEN in GitHub repo secrets

# Railway — RAILWAY_API_TOKEN (ssh / non-deploy)
# Railway dashboard → Account → Tokens → create new account token
gh secret set RAILWAY_API_TOKEN -R GoliattCo/odoo-custom --body "<new-token>"
# Or pull a fresh CLI session token (~30-day expiry) if no account token is set:
SESS=$(jq -r '.user.token' < ~/.railway/config.json | tr -d '\r\n')
gh secret set RAILWAY_API_TOKEN -R GoliattCo/odoo-custom --body "$SESS"

# Railway — RAILWAY_SSH_PRIVATE_KEY
ssh-keygen -t ed25519 -N "" -f ~/.ssh/gha_rw_ed25519_new -C "gh-actions-pgbackrest@odoo-saas"
railway ssh keys add --key ~/.ssh/gha_rw_ed25519_new.pub --name "gh-actions-pgbackrest-$(date +%Y%m%d)"
gh secret set RAILWAY_SSH_PRIVATE_KEY -R GoliattCo/odoo-custom --body "$(cat ~/.ssh/gha_rw_ed25519_new)"
# Then remove the old registered key
railway ssh keys remove gh-actions-pgbackrest

# Fly
fly tokens create deploy --name "ci-rotated-YYYY-MM-DD"
gh secret set FLY_API_TOKEN -R GoliattCo/odoo-custom --body "<deploy-token>"
fly tokens create ssh --app odoo-saas-postgres --name "ssh-rotated-YYYY-MM-DD" --expiry 8760h
gh secret set FLY_SSH_TOKEN_POSTGRES -R GoliattCo/odoo-custom --body "<ssh-token>"
fly tokens revoke <old-token-id>
```

## Railway CLI v4.58+ behaviour notes

Hard-won lessons from the May 2026 pgBackRest backup workflow bring-up:

1. **`-b -` is a footgun.** `gh secret set NAME -b -` stores the literal
   value `-`, not stdin. Always use `--body "<value>"` or pipe to
   `gh secret set NAME` with no flag.
2. **Project tokens are deploy-only in v4.58+.** Anything other than
   `railway up` needs an account-level token via `RAILWAY_API_TOKEN`.
3. **SSH keys are no longer auto-registered.** Both halves of the
   keypair must exist: private key in `~/.ssh/`, public key registered
   on the account via `railway ssh keys add`.
4. **`--project` / `--environment` expect NAMES, not UUIDs.** The CLI
   reports UUID inputs as "not found in workspace" even when the
   project clearly exists.
5. **`railway ssh` needs a linked workdir** to find the project. Run
   `railway link --project NAME --environment NAME --service NAME` in
   the same shell and same cwd first; the link writes
   `~/.railway/config.json` keyed by `getcwd()`.
6. **`RAILWAY_PROJECT_ID` / `RAILWAY_ENVIRONMENT_ID` env vars override
   the linked state.** When they're set to UUIDs (as is conventional),
   `railway ssh` uses those UUIDs and bypasses the linked state — same
   "Project not found" as above. `unset` them after link before ssh.
7. **`~/.ssh/known_hosts` starts empty on CI runners.** Without
   `StrictHostKeyChecking accept-new` in `~/.ssh/config`, ssh rejects
   Railway's per-session proxy host fingerprint.

## Not yet in CI

- **Vercel deploy** for the control plane lives in the OTHER repo
  (`/Volumes/SATECHI2TB/userfolder/Odoo-control-plane/`). Vercel
  auto-deploys per PR from that repo; no GitHub Actions setup needed
  there beyond a typecheck workflow.
- **AWS credentials for `terraform apply`** are not in CI. Terraform
  applies are done locally by an operator. Adding `terraform plan`
  to PRs is a future enhancement.
- **Helm chart / GHCR signed image push** for the enterprise self-host
  artifact (Phase 4) — separate workflow when we get there.
