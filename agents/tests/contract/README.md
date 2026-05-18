# Contract tests

Every adapter must pass the contract tests for the port it implements.
Failing a contract test fails CI for that adapter.

## Layout

```
tests/contract/
├── test_llm_provider.py     # contract for LLMProvider
├── test_repo.py             # contract for Repo
├── test_issue_tracker.py    # contract for IssueTracker
├── ...                      # one per port
```

## How to add a new adapter

1. Implement the port in `agents/agents/adapters/<port>_<vendor>.py`.
2. Register it in `bootstrap.py`'s `_make_<port>()`.
3. Run the contract tests against it:

   ```bash
   ADAPTER=ollama pytest tests/contract/test_llm_provider.py
   ```

4. If green, the adapter is portable-runtime-compliant.

## Test design

- Use **mocked external calls** by default. Each contract test exercises the
  adapter's translation layer (port → vendor → port) with deterministic mocks.
- A separate `tests/integration/` directory holds **live-credential** tests
  that hit real APIs. These run nightly with secrets injected.
