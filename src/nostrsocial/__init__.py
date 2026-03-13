"""NostrSocial — Social graph manager for OpenClaw AI agents."""

from .types import (
    BehaviorRules,
    CapacityError,
    Contact,
    DriftEvent,
    IdentityState,
    ListType,
    LIST_CAPACITY,
    NetworkShape,
    Tier,
    TIER_CAPACITY,
    TIER_ORDER,
    DEFAULT_DRIFT_THRESHOLDS,
    DEFAULT_LIST_CAPACITY,
    DEFAULT_TIER_CAPACITY,
)
from .behavior import (
    NEUTRAL_BEHAVIOR,
    get_behavior,
)
from .contacts import ContactList
from .enclave import SocialEnclave
from .evaluate import Action, ConversationSignals, Evaluation, evaluate
from .proxy import derive_proxy_npub
from .resonance import LinkResult, Recognition
from .storage import FileStorage, MemoryStorage
from .verify import Challenge

__version__ = "0.1.0"

__all__ = [
    # Core types
    "BehaviorRules",
    "CapacityError",
    "Contact",
    "DriftEvent",
    "IdentityState",
    "ListType",
    "NetworkShape",
    "Tier",
    "TIER_ORDER",
    # Evaluation types
    "Action",
    "ConversationSignals",
    "Evaluation",
    # Constants
    "LIST_CAPACITY",
    "TIER_CAPACITY",
    "DEFAULT_DRIFT_THRESHOLDS",
    "DEFAULT_LIST_CAPACITY",
    "DEFAULT_TIER_CAPACITY",
    "NEUTRAL_BEHAVIOR",
    # Classes
    "ContactList",
    "SocialEnclave",
    "Challenge",
    # Storage
    "FileStorage",
    "MemoryStorage",
    # Resonance
    "LinkResult",
    "Recognition",
    # Functions
    "derive_proxy_npub",
    "evaluate",
    "get_behavior",
]
