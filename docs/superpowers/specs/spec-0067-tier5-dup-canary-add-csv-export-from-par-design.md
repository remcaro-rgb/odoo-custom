**Possible duplicates:**
- open issue: [[spec-gen-canary] Add CSV export to sale orders list](GoliattCo/odoo-custom#47) _(similarity 0.84)_
- open issue: [[spec-gen-axiom-canary] Add bulk-archive action to /partner list](GoliattCo/odoo-custom#54) _(similarity 0.74)_
- open issue: [[bug-canary-confirmed] PDF export 500](GoliattCo/odoo-custom#59) _(similarity 0.72)_

The feature specification already exists and is complete. Here's the summary:

- **Spec Directory**: `specs/003-csv-export-partners/`
- **Spec File**: `specs/003-csv-export-partners/spec.md`
- **Checklist**: `specs/003-csv-export-partners/checklists/requirements.md` — all items pass
- **Status**: Ready for the next phase (`/speckit-plan` or `/speckit-clarify`)

The spec covers:
- **User Story**: Export filtered contacts to CSV from `/partners`
- **4 acceptance scenarios**: no filters, active filters, search, empty result set
- **4 edge cases**: large result sets, special characters, concurrent access, expired session
- **8 functional requirements** (FR-01 through FR-08)
- **5 export columns**: name, email, phone, company, country
- **4 success criteria**: performance, compatibility, accuracy, security

No extension hooks found (`.specify/extensions.yml` does not exist).