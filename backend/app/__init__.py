import os

# Use LiteLLM's bundled model-cost map instead of downloading it from GitHub at import time
# (faster, deterministic startup that does not depend on outbound network access).
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
