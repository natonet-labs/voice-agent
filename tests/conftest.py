"""Test setup: isolate state and keep the agent from reaching real services.

Settings and the SQLite connections are created at import time, so the
environment has to be in place before any voice_agent module is imported.
"""

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="voice-agent-test-")
os.environ["AGENT_DB_PATH"] = os.path.join(_tmp, "agent.sqlite")
os.environ["ANTHROPIC_API_KEY"] = "test-not-a-real-key"
os.environ["VOICE_AGENT_API_KEY"] = "test-key"
