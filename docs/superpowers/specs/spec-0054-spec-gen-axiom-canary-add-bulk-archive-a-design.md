Specification created successfully.

## Summary

- **`SPECIFY_FEATURE_DIRECTORY`**: `specs/002-bulk-archive-partners`
- **`SPEC_FILE`**: `specs/002-bulk-archive-partners/spec.md`
- **Checklist**: All 16 items pass — no clarifications needed.

### Spec highlights:
- **3 user stories**: Bulk archive active partners (primary), handle already-archived in selection, permission-controlled access
- **9 functional requirements**: Confirmation dialog, atomic operation, skip already-archived, tenant isolation, error handling, "Select All" behavior
- **6 success criteria**: 5s for 50 records, handles 200+ records, 80% click reduction, no cross-tenant leakage
- **5 edge cases**: Large selections, partial failures, concurrent modifications, interrupted actions, view refresh

Ready for `/speckit-clarify` or `/speckit-plan`.