"""Moved to `agentseism.resolve` so it ships in the wheel. Re-exported here so
existing research code and tests keep importing the old path."""
from agentseism.resolve import *  # noqa: F401,F403
from agentseism.resolve import __dict__ as _d  # noqa: F401
globals().update({k: v for k, v in _d.items() if not k.startswith("__")})
