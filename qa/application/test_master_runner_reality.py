"""Include additive Master QA runner-reality regressions in existing coordinator CI.

This runs DEVELOPMENT contract tests only. Actual VM/host real output remains
a separate mandatory signed stage; these fixtures are NOT native VM PASS.
"""
import sys
from pathlib import Path

MASTER = Path(__file__).resolve().parents[1] / "master"
sys.path.insert(0, str(MASTER))
from test_runner_reality_gate import RunnerContractTests  # noqa: F401
