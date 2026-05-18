"""odoo-saas-agents — portable AI-agent runtime.

Six agents on a hexagonal architecture. Agent core depends only on the port
ABCs in `agents.ports`; concrete adapters in `agents.adapters` bind those
ports to specific vendors (Claude, GitHub, Slack, Fly, pgvector, ...).

See docs/superpowers/specs/2026-05-16-portable-agent-runtime-design.md
"""

__version__ = "0.1.0"
