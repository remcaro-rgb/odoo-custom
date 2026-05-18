"""Adapter implementations.

One file per (port, vendor). Vendor SDKs are imported only in their respective
adapter file — agent core never sees them.

This package intentionally has very little in __init__.py. Adapters are
imported lazily by bootstrap.py so unused adapters don't require their SDKs.

Naming convention:
    {port}_{vendor}.py
e.g.:
    llm_claude.py       — Claude direct
    llm_litellm.py      — LiteLLM gateway
    repo_github.py
    issues_github.py
    notifier_slack.py
    compute_fly.py
"""
