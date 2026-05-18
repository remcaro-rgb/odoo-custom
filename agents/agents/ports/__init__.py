"""Port interfaces (Protocols / ABCs).

Agent core code depends on these and ONLY these. Adapters in
`agents.adapters` implement them; the bootstrap wires them at startup.

Port signatures are SemVer-stable across major versions. Breaking changes
require a major bump of the agents package.
"""

from .llm_provider import ChatResponse, LLMProvider, Message, Tool, Vector
from .repo import GitIdentity, PullRequest, Repo
from .issue_tracker import Comment, Issue, IssueTracker
from .notifier import Notifier, Severity
from .secret_store import SecretStore
from .artifact_store import ArtifactStore
from .compute_env import ComputeEnv, Deployment, Status
from .knowledge_base import KbChunk, KnowledgeBase
from .event_bus import Event, EventBus, Subscription
from .logger import Logger

__all__ = [
    # llm
    "LLMProvider", "Message", "ChatResponse", "Tool", "Vector",
    # repo
    "Repo", "PullRequest", "GitIdentity",
    # issues
    "IssueTracker", "Issue", "Comment",
    # notifier
    "Notifier", "Severity",
    # secrets
    "SecretStore",
    # artifacts
    "ArtifactStore",
    # compute
    "ComputeEnv", "Deployment", "Status",
    # kb
    "KnowledgeBase", "KbChunk",
    # events
    "EventBus", "Event", "Subscription",
    # logger
    "Logger",
]
