# Portable AI Agent Runtime — Design Spec

**Date:** 2026-05-16
**Author:** Manu (drafted with Claude)
**Status:** Draft
**Spec type:** design spec (follows §2.4 of `docs/2026-05-15-spec-driven-dev-plan.md`)
**Scope of work:** the runtime / packaging / abstraction layer that all six AI agents (spec-generator, implementation, code, security, optimization, support-triage) sit on top of. Replaces the implicit GitHub-Actions + Claude SDK assumption in v6.

---

## 1. Goal

Make every AI agent in this repo **runnable on any platform** with no agent-code changes — only a config swap.

Concretely:

- The LLM provider can be Claude, GPT-4o, Gemini, Mistral, or a local model (Ollama / vLLM) — chosen at deploy time.
- The CI runner can be GitHub Actions, GitLab CI, Argo Workflows, a Kubernetes Job, a Nomad task, or a local cron — same binary, same code.
- The source-control host can be GitHub, GitLab, Gitea, or Forgejo.
- The issue tracker can be GitHub Issues, GitLab Issues, Linear, or Jira.
- The notification channel can be Slack, Teams, Discord, email, or a generic webhook.
- The secret store can be GitHub Secrets, Vault, Kubernetes Secrets, Fly/Railway secrets, or just env vars.
- The vector store can be pgvector, Chroma, Pinecone, or Weaviate.

The default day-one bindings stay where v6 already lives: GitHub + GitHub Actions + Claude + Slack + Fly + pgvector. The architecture just makes "move off Anthropic" or "self-host the whole stack" a one-week migration instead of a rewrite.

---

## 2. Non-goals

- Abstracting the **Odoo deployment** itself. That's already cross-platform (Railway + Fly parity) and out of scope here.
- Abstracting the **human dev workflow**. Humans use GitHub PRs today — fine. The agents' adapters speak the host's API; humans use the host's UI.
- Building a **multi-provider load-balancer** that calls every LLM in parallel. One provider per agent run, selected by config.
- Replacing **LangChain / LangGraph / CrewAI** wholesale. We use thin abstractions and direct API calls; multi-agent orchestration frameworks are explicitly out of scope (too much lock-in to their patterns).
- A **plugin registry** for third-party adapters. Adapters live in this repo; external code is not loaded at runtime (security).

---

## 3. Architecture — hexagonal (ports & adapters)

```
                  ┌──────────────────────────────┐
                  │     Agent core logic         │
                  │  (pure Python; no I/O)       │
                  │                              │
                  │  spec_generator / impl /     │
                  │  code / security / opt /     │
                  │  support_triage              │
                  └─────────────┬────────────────┘
                                │
                                │ depends only on
                                │ Port interfaces
                                ▼
              ┌─────────────────────────────────────┐
              │              Ports (ABCs)            │
              ├─────────────────────────────────────┤
              │ LLMProvider · Repo · IssueTracker   │
              │ Notifier · SecretStore · Logger      │
              │ ArtifactStore · ComputeEnv          │
              │ KnowledgeBase · EventBus            │
              └─────────────────┬───────────────────┘
                                │
                                │ implemented by
                                │ pluggable Adapters
                                ▼
   ┌─────────────────────────────────────────────────────────┐
   │                       Adapters                          │
   ├─────────────────────────────────────────────────────────┤
   │ LLM:        Claude · OpenAI · Gemini · Ollama · LiteLLM │
   │ Repo:       GitHub · GitLab · Gitea · LocalGit          │
   │ Issues:     GitHubIssues · GitLabIssues · Linear · Jira │
   │ Notifier:   Slack · Teams · Discord · Email · Webhook   │
   │ Secrets:    GHA · Vault · K8sSecrets · Fly · Railway    │
   │ Artifacts:  S3 · GCS · LocalFS                          │
   │ Compute:    Fly · Railway · K8s · DockerLocal           │
   │ KB:         PgVector · Chroma · Pinecone · Weaviate     │
   │ EventBus:   GHWebhook · Redis · NATS · LocalCron        │
   │ Logger:     StdJSON · Loki · BetterStack · Datadog      │
   └─────────────────────────────────────────────────────────┘
```

Two design rules:

1. **Agent core has zero direct I/O.** No `requests.post`, no `subprocess`, no `boto3` in agent logic. Only port method calls.
2. **Adapters are leaves.** Adapters don't know about agents and don't call each other. They wrap a single external service.

Wiring happens once at startup in a `bootstrap.py` that reads config, instantiates adapters, and injects them into the agent.

---

## 4. Tenancy impact

None. This is engineering tooling; the agents act on the codebase and on tenant DBs through existing per-tenant boundaries already established in v6 (e.g. `saas_tenant_gate` HMAC for the support gateway, agentlab masking for the dev agents). The runtime layer doesn't change tenancy guarantees.

The Support Triage Agent's gateway (per its own design spec) uses ports from this runtime — `LLMProvider`, `KnowledgeBase`, `IssueTracker`, `Logger` — so its tenancy boundary is preserved regardless of which vendor sits behind each port.

---

## 5. Ports

Each port is a Python Protocol or ABC. Method signatures are stable; new methods are added only with a major version bump.

### 5.1 `LLMProvider`

```python
class LLMProvider(Protocol):
    def chat(self, messages: list[Message], *, model: str | None = None,
             max_tokens: int = 4096, temperature: float = 0.2,
             tools: list[Tool] | None = None) -> ChatResponse: ...

    def embed(self, texts: list[str], *, model: str | None = None) -> list[Vector]: ...

    @property
    def name(self) -> str: ...           # "claude-sonnet-4-6", "gpt-4o", ...
    @property
    def cost_per_1k_input(self) -> float: ...
    @property
    def cost_per_1k_output(self) -> float: ...
```

### 5.2 `Repo`

```python
class Repo(Protocol):
    def checkout(self, branch: str, *, base: str = "main") -> None: ...
    def commit(self, paths: list[str], message: str,
               author: GitIdentity) -> str: ...                     # returns SHA
    def push(self, branch: str) -> None: ...
    def open_pr(self, *, head: str, base: str = "main",
                title: str, body: str, labels: list[str] = ()) -> PullRequest: ...
    def add_labels(self, pr: PullRequest, labels: list[str]) -> None: ...
    def remove_labels(self, pr: PullRequest, labels: list[str]) -> None: ...
    def read(self, path: str, *, ref: str = "HEAD") -> bytes: ...
    def write(self, path: str, content: bytes) -> None: ...
    def list_changed_files(self, base: str, head: str) -> list[str]: ...
    def file_owners(self, path: str) -> list[str]: ...               # from CODEOWNERS
```

### 5.3 `IssueTracker`

```python
class IssueTracker(Protocol):
    def open_issue(self, *, title: str, body: str, labels: list[str]) -> Issue: ...
    def comment(self, issue: Issue, body: str) -> Comment: ...
    def edit_comment(self, comment: Comment, body: str) -> None: ...
    def add_label(self, issue: Issue, label: str) -> None: ...
    def remove_label(self, issue: Issue, label: str) -> None: ...
    def list_issues(self, *, labels: list[str] | None = None,
                    state: str = "open") -> list[Issue]: ...
    def search_similar(self, text: str, *, limit: int = 5) -> list[Issue]: ...
```

### 5.4 `Notifier`

```python
class Notifier(Protocol):
    def send(self, *, channel: str, summary: str,
             details: dict | None = None,
             severity: Literal["info", "warn", "page"] = "info") -> None: ...
```

### 5.5 `SecretStore`

```python
class SecretStore(Protocol):
    def get(self, name: str) -> str: ...
    def get_or_raise(self, name: str) -> str: ...
    def list(self) -> list[str]: ...                  # names only, never values
```

### 5.6 `ArtifactStore`

```python
class ArtifactStore(Protocol):
    def put(self, key: str, data: bytes, *, content_type: str) -> str: ...  # returns URL
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def signed_url(self, key: str, *, ttl_seconds: int = 3600) -> str: ...
```

### 5.7 `ComputeEnv`

```python
class ComputeEnv(Protocol):
    def spawn(self, *, name: str, image: str, env: dict[str, str],
              region: str | None = None, size: str = "small") -> Deployment: ...
    def destroy(self, deployment: Deployment) -> None: ...
    def status(self, deployment: Deployment) -> Status: ...
    def url(self, deployment: Deployment) -> str: ...
    def secrets_set(self, deployment: Deployment, kv: dict[str, str]) -> None: ...
```

Used by Implementation Agent (preview envs) and by the agentlab nightly restore.

### 5.8 `KnowledgeBase`

```python
class KnowledgeBase(Protocol):
    def upsert(self, chunks: list[KbChunk]) -> None: ...
    def search(self, query: str, *, k: int = 5,
               filter: dict | None = None) -> list[KbChunk]: ...
    def delete(self, ids: list[str]) -> None: ...
```

### 5.9 `EventBus`

```python
class EventBus(Protocol):
    def subscribe(self, event_type: str,
                  handler: Callable[[Event], None]) -> Subscription: ...
    def publish(self, event_type: str, payload: dict) -> None: ...
```

Used by Implementation Agent to react to `issue_comment.created`, and by Support Triage Agent's webhook back-sync.

### 5.10 `Logger`

```python
class Logger(Protocol):
    def info(self, msg: str, **fields) -> None: ...
    def warn(self, msg: str, **fields) -> None: ...
    def error(self, msg: str, **fields) -> None: ...
    @contextmanager
    def span(self, name: str, **fields) -> ContextManager: ...
```

Structured logging (JSON to stdout by default; the adapter routes to Loki, Better Stack, Datadog, etc.).

---

## 6. Adapter matrix

| Port | Default (v7) | First-party adapters | Notes |
|---|---|---|---|
| `LLMProvider` | `LiteLLMAdapter(claude-sonnet-4-6)` | LiteLLM (multi), Claude direct, OpenAI direct, Ollama, vLLM | LiteLLM gives 100+ providers from one interface |
| `Repo` | `GitHubAdapter` | GitHub, GitLab, Gitea, LocalGit | LocalGit useful for tests + air-gapped runs |
| `IssueTracker` | `GitHubIssuesAdapter` | GitHubIssues, GitLabIssues, Linear, Jira | |
| `Notifier` | `SlackAdapter` | Slack, Teams, Discord, Email (SMTP), Webhook | Webhook is the universal escape hatch |
| `SecretStore` | `EnvVarAdapter` | EnvVar, GitHubSecrets, Vault, K8sSecrets, FlySecrets, RailwaySecrets | EnvVar works everywhere if you inject secrets via the platform |
| `ArtifactStore` | `S3Adapter` (any S3-compatible) | S3, GCS, LocalFS | S3 adapter works with MinIO, Cloudflare R2, Backblaze B2 |
| `ComputeEnv` | `FlyAdapter` | Fly, Railway, Kubernetes, DockerLocal | DockerLocal lets devs run preview envs on their laptop |
| `KnowledgeBase` | `PgVectorAdapter` | PgVector, Chroma, Pinecone, Weaviate | pgvector is the cheapest and most portable |
| `EventBus` | `GitHubWebhookAdapter` | GitHubWebhook, Redis, NATS, LocalCron | LocalCron good for running improvement agents on a workstation |
| `Logger` | `StdJSONAdapter` (stdout) | StdJSON, Loki, BetterStack, Datadog | StdJSON + platform log capture is enough for most setups |

The adapters live in `agents/adapters/<port>_<name>.py` (one file per adapter, no internal sharing). The adapter file is the only place imports of vendor SDKs appear:

```
agents/adapters/llm_claude.py        # import anthropic
agents/adapters/llm_litellm.py       # import litellm
agents/adapters/llm_openai.py        # import openai
agents/adapters/repo_github.py       # import requests + github API
agents/adapters/repo_gitlab.py       # import gitlab
agents/adapters/notifier_slack.py    # import slack_sdk
agents/adapters/notifier_email.py    # import smtplib
...
```

If you don't use an adapter, the corresponding SDK is not installed (declared as an extra in `pyproject.toml`).

---

## 7. Configuration & binding

A single YAML file selects bindings:

```yaml
# agents/config.yml
runtime:
  log_level: info
  spend_cap_monthly_usd: 250

bindings:
  llm:           litellm
  repo:          github
  issues:        github
  notifier:      slack
  secrets:       envvar
  artifacts:     s3
  compute:       fly
  kb:            pgvector
  events:        github_webhook
  logger:        stdjson

litellm:
  model: claude-sonnet-4-6
  fallback_models: [gpt-4o, gemini-2.5-pro]    # used on rate-limit / outage
  base_url: https://api.anthropic.com
  api_key_secret: ANTHROPIC_API_KEY            # read via secrets adapter

github:
  org: remcaro-rgb
  repo: odoo-saas
  token_secret: GITHUB_TOKEN
  service_account: odoo-saas-agents-bot

slack:
  workspace_secret: SLACK_BOT_TOKEN
  default_channel: "#devops-agents"

fly:
  org: odoo-saas
  region_primary: iad

pgvector:
  dsn_secret: SUPPORT_GATEWAY_PG_DSN

s3:
  endpoint: https://r2.cloudflarestorage.com    # or AWS, MinIO, B2
  bucket: odoo-saas-artifacts
  access_key_secret: S3_ACCESS_KEY
  secret_key_secret: S3_SECRET_KEY
```

Per-environment overrides:

```
agents/config.yml              # base
agents/config.dev.yml          # overrides for local dev
agents/config.staging.yml      # overrides for staging
agents/config.prod.yml         # overrides for prod
```

Environment variables override anything: `AGENTS_BINDINGS_LLM=ollama agents run spec-generator …` flips LLM provider without touching files. Useful for one-off experiments.

**Validation.** A `agents config validate` command checks the config against the adapter registry and verifies required secrets are reachable. Runs in CI.

---

## 8. Packaging

### 8.1 OCI image

One image, all agents, all adapters:

```
ghcr.io/<org>/odoo-saas-agents:<version>
```

Built from `agents/Dockerfile`. Multi-stage: build wheels in stage 1, copy into a slim Python 3.12 image in stage 2. Final size target ≤ 250 MB.

Adapters' optional dependencies are all installed in the image (we don't ship a slimmer variant). If a 250 MB image is too big for some runner, a `*-minimal` image strips unused adapter SDKs at build time via build args.

### 8.2 CLI

```bash
agents run <agent-name> [--input <json>] [--config <path>]
agents iterate <agent-name> --pr <number>                 # for Implementation Agent
agents config validate
agents config show
agents test-adapter <port> <adapter-name>                 # smoke test
agents version
```

Each agent has the same shape — `python -m agents.cli run spec-generator …`. The CLI is implemented in `agents/cli.py` using `click` (one of the few dependencies; cheap, portable).

### 8.3 How CI platforms invoke it

GitHub Actions:
```yaml
- uses: docker://ghcr.io/<org>/odoo-saas-agents:v1
  with:
    args: run spec-generator --input '{"issue_id": ${{ github.event.issue.number }}}'
```

GitLab CI:
```yaml
script:
  - docker run --rm ghcr.io/<org>/odoo-saas-agents:v1 run spec-generator --input "$INPUT_JSON"
```

Kubernetes Job:
```yaml
spec:
  template:
    spec:
      containers:
      - name: agent
        image: ghcr.io/<org>/odoo-saas-agents:v1
        args: ["run", "spec-generator", "--input", "{...}"]
```

Local cron (a dev's machine):
```bash
0 */6 * * * docker run --env-file ~/.agents.env ghcr.io/<org>/odoo-saas-agents:v1 run code
```

Same image, same args. The platform-specific glue is in the platform's config files, not in agent code.

---

## 9. LLM provider strategy — LiteLLM as the default

We use **LiteLLM** as the default `LLMProvider` adapter:

- Single API call shape (`chat.completions`-style) maps onto Claude, OpenAI, Gemini, Mistral, Cohere, Ollama, vLLM, and ~100 others.
- Cost tracking is built in (`cost_per_1k_*` properties).
- Fallback chains: if Claude rate-limits, automatic retry on GPT-4o, then Gemini.
- Streaming, tool calls, JSON mode supported.
- Open-source, no vendor lock-in to LiteLLM itself (we depend on a thin protocol).

We **also** ship direct adapters (`llm_claude.py`, `llm_openai.py`) for the cases where LiteLLM's abstraction loses fidelity (e.g. Claude prompt caching, Claude Files API, beta features). The agent core code never imports them directly — it asks the runtime for an `LLMProvider`.

### 9.1 Provider selection heuristics

Per-agent default in config; per-task overrides allowed:

| Agent | Default | Why |
|---|---|---|
| Spec Generator | Claude Sonnet 4.6 | Best instruction-following for structured drafting |
| Implementation Agent | Claude Sonnet 4.6 | Strongest coding model in 2026 |
| Code Agent | Claude Sonnet 4.6 | Same |
| Security Agent | Claude Sonnet 4.6 | Same (with Bandit doing deterministic scanning first) |
| Optimization Agent | Claude Sonnet 4.6 | Same |
| Support Triage Agent | Claude Haiku 4.5 | Faster + cheaper for chat; escalate to Sonnet for hard cases |

All swappable via `config.yml`. A `--model` CLI flag overrides per-run.

### 9.2 Model deprecation policy

Models we depend on are pinned by exact ID in config. A separate workflow `model-availability.yml` runs weekly: pings each provider's `/models` endpoint, asserts the configured models still exist. Failure pages on-call.

### 9.3 Local-model option

The `Ollama` adapter is shipped so that paranoid setups (air-gapped, regulated, or just cost-sensitive) can run improvement agents (code, security, optimization) on a local model — typically Llama-3.1-70B or Qwen-2.5-Coder via Ollama. The customer-facing Spec Generator + Implementation Agent + Support Triage still benefit from a frontier model.

---

## 10. Default bindings (the concrete day-one stack)

To be clear about what changes from v6 and what doesn't:

| Layer | v6 (implicit) | v7 (explicit binding, same vendor) |
|---|---|---|
| LLM | Anthropic Claude direct | LiteLLM → Claude Sonnet 4.6 |
| Repo | GitHub | GitHub adapter |
| Issues | GitHub Issues | GitHub Issues adapter |
| Notifier | Slack | Slack adapter |
| Secrets | GHA Secrets | GHA Secrets adapter (mostly) + Fly secrets (gateway) |
| Artifacts | (not explicit) | S3-compatible (Cloudflare R2 recommended) |
| Compute | Fly (agentlab, preview) | Fly adapter |
| KB | (not explicit) | pgvector |
| EventBus | GitHub webhooks | GitHub webhook adapter |
| Logger | (not explicit) | StdJSON → Better Stack |

So **nothing operationally changes** for day-one users. The vendors stay where they are. What changes is that swapping any of them later is a 1–3 day adapter implementation, not a multi-week refactor.

---

## 11. Migration paths — worked examples

### 11.1 "We want to move off Anthropic"

1. Edit `agents/config.prod.yml`: set `litellm.model: gpt-4o`.
2. `agents config validate` confirms `OPENAI_API_KEY` is reachable.
3. Run `agents test-adapter llm litellm` — exercises the chat + embed paths.
4. Deploy.

Done. Agent code unchanged.

### 11.2 "We want to move off GitHub to self-hosted GitLab"

1. Implement `repo_gitlab.py` and `issues_gitlab.py` if not already (~2–3 days each).
2. Mirror the repo to the new GitLab instance.
3. Edit config: `bindings.repo: gitlab`, `bindings.issues: gitlab`. Set token secrets.
4. Re-wire CI: replace `.github/workflows/` with `.gitlab-ci.yml` files that invoke the same OCI image with the same args.
5. Migrate webhooks: replace GitHub webhooks with GitLab webhooks pointing at the gateway's same endpoint.

Estimated: 1 week including testing. The agent logic doesn't change.

### 11.3 "We want to self-host the LLM"

1. Stand up Ollama on a GPU host (or use vLLM on a Modal/Banana/Runpod setup).
2. Edit config: `bindings.llm: ollama` with model `qwen-2.5-coder:32b`.
3. Run the improvement agents (code, security, opt) against it for a quarter.
4. If quality holds, migrate Spec Generator + Implementation Agent too.

The Support Triage Agent stays on a frontier model (Haiku) since latency is critical and the customer ROI justifies it.

### 11.4 "We want to swap Slack for Discord"

1. Use the existing `Discord` adapter.
2. Edit config: `bindings.notifier: discord`. Set webhook URL.

Done in an hour.

---

## 12. Security model

Same guarantees as v6, but with three explicit additions:

- **Secrets never read by agent core.** Agent code receives a `SecretStore` and asks for named secrets by string. The adapter is responsible for the safe retrieval. Easier audit: grep for `secret_store.get(` to see every secret use.
- **Adapter-level allow-list.** A config-level switch limits which adapters can be activated per environment. Production config refuses to load any adapter not in `allowed_adapters: [...]` — prevents a misconfigured PR from quietly swapping a vendor.
- **No external code loaded.** Adapters are first-party Python in this repo. No plugin loading, no `pip install` at runtime, no dynamic imports.
- **OCI image signing.** Images are signed with `cosign`; the deploy step in any CI verifies the signature before pulling.
- **SBOM emitted at build.** `syft` produces an SBOM for every release; stored alongside the image; auditable.

---

## 13. Test plan

### 13.1 Contract tests

For every port, a contract test suite that any adapter must pass:

```
tests/contract/test_llm_provider.py
tests/contract/test_repo.py
tests/contract/test_issue_tracker.py
...
```

Each adapter is parameterised through the suite. Failing a contract test fails CI for that adapter.

Example contracts:

- `LLMProvider`: `chat()` returns a non-empty response; `embed()` returns vectors of expected dimension; cost properties are non-zero.
- `Repo`: `open_pr()` returns a `PullRequest` with a number; `list_changed_files(a, b)` is consistent with the underlying git.
- `IssueTracker`: `comment()` is idempotent under retries with the same idempotency key.

### 13.2 Integration tests

Per-adapter integration tests that hit real APIs (against test orgs / sandbox tenants):
- `tests/integration/test_repo_github.py` — runs against a throwaway test repo.
- `tests/integration/test_repo_gitlab.py` — runs against a GitLab sandbox.
- Skipped in PR CI; run nightly with secrets injected.

### 13.3 End-to-end smoke

The full Spec Generator flow exercised against:
- Default stack (GitHub + Claude + Slack).
- Alt stack (GitLab + GPT-4o + Discord) — runs weekly to keep the alternative path warm.

### 13.4 Adversarial

- Inject a malformed config — `agents config validate` must fail clean, not crash.
- Network partition between agent and one adapter — fallback chain on `LLMProvider` must kick in.
- Missing secret — must produce a clear error, not a stack trace.

---

## 14. Rollout plan

Slots in as **Phase 6** of the master roadmap, before any agent is written. Without the runtime, every agent built later would be tightly coupled to today's vendor choices and would need re-work.

### Phase 6 — Agent runtime + adapter library (weeks 9–10) *new*

Sub-tasks:
- Skeleton: `agents/` package, ports, default adapters, CLI, OCI Dockerfile.
- Default adapters: Claude (via LiteLLM), GitHub, GitHub Issues, Slack, S3, Fly, pgvector, EnvVar, GHWebhook, StdJSON.
- Contract test suite for every port.
- `agents config validate` + GHA workflow.
- One smoke agent (a trivial "hello" agent) running end-to-end on the new runtime.

Once green: every subsequent agent (was: Phases 6–9; now: Phases 7–10) is built on top.

### Phase 7 (was Phase 6) — Spec Generator

Built using the runtime. Same scope as v6 Phase 6.

### Phases 8–10 (were 7–9) — Implementation Agent, improvement agents, Support Triage Agent

Same scope as v6 Phases 7–9; renumbered.

### Phase 11 (deferred) — Alternative-stack validation

Optional. Pick one alternative stack (e.g. GitLab + GPT-4o + Teams) and stand up a "twin" of the staging pipeline on it. Run the weekly smoke. Proves portability is real, not aspirational.

---

## 15. Observability

The `Logger` port emits structured JSON. The default adapter writes to stdout; alternative adapters ship the same shape to Loki / Better Stack / Datadog / Cloudwatch / etc.

Every log line carries: `agent`, `run_id`, `port`, `adapter`, `tenant_hash?`, `issue?`, `pr?`, `latency_ms`, `cost_usd?`. End-to-end correlation across adapters works no matter which sink is used.

Per-agent dashboards (already in v6 §9 / §11) are sink-agnostic — they're built from the standard JSON fields.

---

## 16. Open questions

1. **LiteLLM vs roll-our-own?** LiteLLM has 100+ providers but is a 3rd-party dep; we could roll a tiny abstraction over 3 providers. Suggest: start with LiteLLM (faster), revisit if it becomes a bottleneck.
2. **Should adapters live in this repo or in a separate `odoo-saas-agents-adapters` repo?** Suggest: same repo for now (atomic releases). Split when external contributors arrive.
3. **Image variants** — do we ship `:slim` (only default adapters), `:full` (all adapters), `:gpu` (with vLLM)? Suggest: only `:full` to start; reconsider if size becomes a CI pain point.
4. **Adapter versioning policy** — semver on the agents package or per-adapter versioning? Suggest: monorepo semver. The image tag is the version of truth.
5. **Air-gapped install** — should the OCI image be self-contained (no network calls at startup)? Useful for regulated customers. Suggest: yes; bundle a minimal cache, allow `OFFLINE=1` mode.
6. **Tool ecosystem** — agents call MCP tools today via the Claude SDK. Should `LLMProvider` expose a generic tool-call interface so other providers (OpenAI function-calling, Gemini function-calling) work the same? Suggest: yes; the `tools` parameter on `chat()` already encodes this. Each adapter translates to its provider's tool-call format.
7. **Secrets at scale** — when secret count grows past ~30, EnvVar gets unwieldy. Suggest: ship Vault adapter early as the recommended production binding; EnvVar stays for local dev.
8. **Backwards-compatibility commitment** — what's our SemVer policy for the port interfaces? Suggest: ports are SemVer-stable across major versions; adapters can change at any time.
