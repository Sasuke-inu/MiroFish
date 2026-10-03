"""Verify installed telemetry opt-outs without making telemetry requests."""
import json
import os
from importlib.util import find_spec
from unittest.mock import patch

from huggingface_hub import constants
from huggingface_hub.utils import _telemetry
from camel.utils.langfuse import is_langfuse_available, get_langfuse_status
from graphiti_core.telemetry import telemetry as graphiti_telemetry


expected = {
    "DO_NOT_TRACK": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "ANONYMIZED_TELEMETRY": "False",
    "OTEL_SDK_DISABLED": "true",
    "SCARF_NO_ANALYTICS": "true",
    "LANGFUSE_ENABLED": "false",
    "LANGFUSE_TRACING_ENABLED": "false",
    "GRAPHITI_TELEMETRY_ENABLED": "false",
}
for name, value in expected.items():
    assert os.environ.get(name) == value, f"Privacy setting missing: {name}"

assert constants.HF_HUB_DISABLE_TELEMETRY
with patch.object(_telemetry, "_start_telemetry_thread") as start_thread:
    _telemetry.send_telemetry("mirofish-installation-check")
    start_thread.assert_not_called()

assert find_spec("unstructured") is None, "Unused analytics-capable dependency was reinstalled"

assert not is_langfuse_available()
assert not get_langfuse_status()["env_enabled"]
assert not graphiti_telemetry.is_telemetry_enabled()
with patch.object(graphiti_telemetry, "initialize_posthog") as initialize:
    graphiti_telemetry.capture_event("mirofish-local-check")
    initialize.assert_not_called()
print(json.dumps({
    "environment_opt_outs": True,
    "huggingface_telemetry_thread_started": False,
    "unstructured_installed": False,
    "camel_langfuse_enabled": False,
    "graphiti_telemetry_enabled": False,
    "graphiti_posthog_initialized": False,
}, indent=2))
