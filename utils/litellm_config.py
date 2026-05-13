"""Process-wide LiteLLM defaults."""

from __future__ import annotations

import os


def configure_litellm_environment() -> None:
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
