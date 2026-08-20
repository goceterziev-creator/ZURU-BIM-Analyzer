"""Temporary process-scoped identity for DIAG-03 runtime diagnostics."""

import os
import uuid


# This module is imported once per Python process and remains cached across
# normal Streamlit script reruns. A new value therefore indicates a new process.
PROCESS_START_ID = uuid.uuid4().hex
PROCESS_PID = os.getpid()
