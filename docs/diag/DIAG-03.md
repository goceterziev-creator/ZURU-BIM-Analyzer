# DIAG-03 process/session boundary instrumentation

DIAG-03 is temporary, diagnostic-only stdout instrumentation for determining what changes when an Android upload produces a connection error.

Each Streamlit render logs:

- `process_start_id`: generated once per Python process;
- `pid`: operating-system process identifier;
- `session_id`: generated once per Streamlit session;
- `render_count`: incremented within the current session;
- `uploader_present`: whether the render received an uploaded file object.

Interpretation:

- changed `process_start_id` means the Python process restarted;
- stable `process_start_id` with changed `session_id` means the Streamlit session was replaced;
- stable process and session with a higher `render_count` means a normal rerun;
- `uploader_present=false` after file selection means the uploaded object did not survive to that render.

DIAG-03 does not log filenames, file sizes, MIME types, raw bytes, file contents, or hashes. It does not change upload, conversion, ingestion, analysis, or product behavior. Remove the instrumentation after the Android failure boundary has been confirmed.
