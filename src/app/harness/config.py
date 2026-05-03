"""Harness configuration constants."""

# OpenAI TPM limit safety cap.
# 8 parallel at ~15-20K tokens each keeps sustained rate under 800K TPM.
MAX_PARALLEL_SCENARIOS: int = 8

# Pause between rounds to let the TPM window drain.
ROUND_COOLDOWN_SECONDS: int = 30

# Number of rounds the harness runs per invocation. Each round runs
# all scenarios and variants. Multiple rounds smooth stochastic LLM
# behavior and make pass-rates meaningful.
DEFAULT_NUM_ROUNDS: int = 5
