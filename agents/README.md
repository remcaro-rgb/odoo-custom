# odoo-saas-agents

Portable AI-agent runtime for odoo-saas. Six agents (Spec Generator, Implementation,
Code, Security, Optimization, Support Triage) on a hexagonal architecture: agent
core depends only on **ports** (Python Protocols); concrete **adapters** bind
those ports to vendors (Claude, GitHub, Slack, Fly, pgvector, ...).

**Full design:** [`docs/superpowers/specs/2026-05-16-portable-agent-runtime-design.md`](../docs/superpowers/specs/2026-05-16-portable-agent-runtime-design.md)

## Quick start

```bash
# Install for development
pip install -e .[dev]

# Validate config
agents config validate

# Run an agent locally
AGENTS_BINDINGS_LLM=ollama agents run code

# In CI (one image, any platform)
docker run --env-file .env ghcr.io/<org>/odoo-saas-agents:v1 \
    run spec-generator --input '{"issue_id": 1500}'
```

## Layout

```
agents/                    # this repo subtree
├── pyproject.toml         # package metadata + optional dep extras
├── Dockerfile             # one image for every agent, every platform
├── README.md              # this file
├── config.example.yml     # template for agents/config.yml
└── agents/                # the Python package
    ├── cli.py             # `agents` CLI entry point
    ├── config.py          # config loader (yaml + env overrides)
    ├── bootstrap.py       # adapter wiring
    ├── ports/             # 10 port ABCs
    ├── adapters/          # adapter implementations (default bindings)
    └── implementation/    # (one of six agent packages)
        spec_generator/
        code/
        security/
        optimization/
        support_triage/
```

## Adding an adapter

1. Implement the port in `agents/adapters/<port>_<vendor>.py`.
2. Pass the contract test suite at `tests/contract/test_<port>.py`.
3. Register in `agents/adapters/__init__.py`.
4. Document in the relevant ADR if it changes the default binding.

## Ports

| Port | What it does |
|---|---|
| `LLMProvider` | chat + embed (LiteLLM by default) |
| `Repo` | clone, branch, commit, PR, file ops |
| `IssueTracker` | issues, comments, labels |
| `Notifier` | Slack / Teams / email / webhook |
| `SecretStore` | env vars / Vault / K8s / Fly |
| `ArtifactStore` | S3-compatible (R2 / MinIO / B2 / AWS) |
| `ComputeEnv` | spawn / deploy / destroy preview envs |
| `KnowledgeBase` | RAG: search + upsert |
| `EventBus` | webhook / cron / push events |
| `Logger` | structured JSON to stdout / Loki / Better Stack |

## Default bindings (day 1)

| Port | Default adapter |
|---|---|
| LLMProvider | LiteLLM → Claude Sonnet 4.6 |
| Repo | GitHub |
| IssueTracker | GitHub Issues |
| Notifier | Slack |
| SecretStore | EnvVar |
| ArtifactStore | S3-compatible (Cloudflare R2 recommended) |
| ComputeEnv | Fly |
| KnowledgeBase | pgvector |
| EventBus | GitHub webhook |
| Logger | StdJSON → Better Stack |

Vendor migration cost is documented in the main plan §14a.
