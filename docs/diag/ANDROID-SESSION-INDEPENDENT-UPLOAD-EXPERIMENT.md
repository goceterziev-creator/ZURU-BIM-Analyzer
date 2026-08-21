# Android session-independent upload experiment

Status: bounded experiment; not deployed and not production-approved.

## Boundary and data flow

This experiment changes only transport before `UploadedFile` materialization.
The ordinary Streamlit uploader remains available.

1. A same-origin iframe bootstraps an HttpOnly browser-owner cookie and a
   double-submit XSRF token.
2. Explicit file selection creates a 10-minute, owner-bound upload intent.
3. The browser streams the bytes with an HTTP `PUT` that is independent of the
   Streamlit WebSocket/session.
4. A process-local registry stages the bytes in a private temporary directory.
5. A recovered Streamlit page discovers only ready metadata owned by the same
   browser cookie.
6. The user must press **Confirm and analyze**. That action creates a
   high-entropy, single-use claim capability. The component keeps it only in
   tab-scoped browser session storage and sends it through Streamlit component
   state over the recovered WebSocket.
7. `zuru_simple.py` consumes the claim once, acknowledges it through a new
   component generation, deletes it from browser session storage, deletes the
   temporary file, and adapts the bytes to the same fields used from
   Streamlit's `UploadedFile`.
8. The existing `ingest_file_bytes(filename, file_bytes)` call remains the only
   ingestion entry. DWG conversion, DXF analysis, and reports are unchanged.

The experiment ASGI entry point is `zuru_app.py`. An isolated preview must use:

```text
streamlit run zuru_app.py
```

Changing a production start command is not part of this experiment.

## Security, ownership, and bounds

- The browser owner is a random 256-bit token in an HttpOnly, Secure (under
  HTTPS), SameSite=Strict cookie. It is independent of Streamlit session state.
- Mutation requests require an exact same-origin `Origin` and a 256-bit
  double-submit XSRF token. Existing Streamlit XSRF settings are untouched.
- Upload and claim identifiers are random 256-bit capabilities. Registry
  lookups also enforce the browser owner before bytes may be stored or a claim
  may be created.
- Another browser cannot list an owner's metadata or use its upload identifier.
  Claim capabilities are never placed in a URL, query string, browser history,
  referrer, or ordinary HTTP request log. They are returned in a protected
  same-origin response body, held in tab-scoped session storage only until
  acknowledgement, and transported to Python as Streamlit component state.
- Only basename-normalized `.dxf` and `.dwg` filenames are accepted.
- Both declared and observed sizes must match and be from 1 byte through
  200 MiB. Content streams larger than the declaration are rejected.
- The process permits at most 32 intents and 400 MiB of reserved staged data.
- Temporary files use a private directory and generated filenames; client
  filenames are never used as paths.
- No raw bytes or file contents are logged.

## Lifetime and cleanup

Every intent expires 10 minutes after creation. Expired entries and their files
are removed on every registry operation and by a 30-second ASGI cleanup loop.
Rejected/aborted writes delete their partial temporary file immediately.
Successful claim consumption reads once and deletes immediately. Application
shutdown cancels cleanup and removes all registry-owned files.

The staged adapter is popped from Streamlit session state before analysis, so a
later rerun cannot automatically replay it. The registry rejects a consumed
claim even if stale browser state attempts to send it again. There is no
automatic analysis after reconnect and no retry against an expired Streamlit
session.

## Preview acceptance protocol

Use an isolated branch preview only; do not change production.

### Android Chrome

1. Open a fresh preview URL in Chrome on Android.
2. Expand the Android experiment and select `Sana fasadi.dwg`.
3. Allow the normal Android picker/session replacement to occur.
4. Confirm that the recovered page shows the received filename and size.
5. Confirm that analysis has **not** started.
6. Press **Confirm and analyze** exactly once.
7. Require `UPLOADER_OBJECT`, `PRE_INGEST_DWG_REACHED`, `INGEST_ENTRY`, and a
   completed analysis. Require exactly one analysis.

Repeat independently in Firefox for Android with a fresh browser owner.

### Desktop regression controls

1. Standard Streamlit uploader: a known DXF must complete analysis.
2. Standard Streamlit uploader: `Sana fasadi.dwg` must reach the existing
   converter and complete analysis.
3. Invalid extension and files larger than 200 MiB must remain rejected.

## Rejection and rollback

Reject the experiment if ownership crosses browsers, upload or ingestion is
duplicated, analysis starts without confirmation, expired/consumed claims work,
temporary data exceeds its lifetime, security/limits weaken, or either desktop
control regresses.

Rollback is deletion of the experiment modules/component assets, the small
integration block in `zuru_simple.py`, and experiment-only tests/documentation,
followed by launching the unchanged `zuru_simple.py` entry point. No converter,
analyzer, ingestion, dependency, or production data migration is involved.
