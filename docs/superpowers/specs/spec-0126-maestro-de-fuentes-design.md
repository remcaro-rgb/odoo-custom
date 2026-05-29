**Possible duplicates:**
- open issue: [Maestro de Fuentes](GoliattCo/odoo-custom#126) _(similarity 1.00)_
- spec: [`club_events` — add a `maintainers` field to the manifest](docs/superpowers/specs/2026-05-23-club-events-maintainers-tier7-fix.md) _(similarity 0.69)_
- spec: [`club_news` — add a `website` field to the manifest (Tier-3 canary)](docs/superpowers/specs/2026-05-23-club-news-website-tier3-fix.md) _(similarity 0.69)_

## Specification Complete

| Item | Value |
|------|-------|
| **`SPECIFY_FEATURE_DIRECTORY`** | `specs/005-maestro-fuentes` |
| **`SPEC_FILE`** | `specs/005-maestro-fuentes/spec.md` |
| **Checklist** | All 16 items pass |

**Summary**: CRUD master data page for "fuentes" (financial sources) with 4 fields: Code (required, unique per tenant), Name (required), Description (optional), and Movimiento Externo (Yes/No). Four user stories cover create, modify, delete, and browse/search flows. No [NEEDS CLARIFICATION] markers — the feature is well-scoped and unambiguous.

Ready for `/speckit-clarify` or `/speckit-plan`.