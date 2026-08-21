# Android resilient-upload experiment

This is a bounded, temporary experiment at the established boundary between
Android file selection and server-side `UploadedFile` materialization.

## Data-flow delta

The browser receives a random 192-bit owner token in the `zuru_upload_owner`
query parameter. The Python process keeps only this mapping:

`browser owner token -> current Streamlit diagnostic session id -> last seen`

When the same browser owner returns with a different Streamlit session id,
ZURU renders a new uploader owned by that new session and explicitly asks the
user to select the file again. The browser is never instructed to replay file
bytes against an expired session.

After an explicitly selected file becomes a normal Streamlit `UploadedFile`,
the existing application flow remains unchanged:

`UploadedFile -> getvalue() -> ingest_file_bytes(filename, file_bytes)`

## Security and cleanup

- No file bytes, filenames, MIME types, hashes, or file contents are retained
  by the recovery registry.
- The owner token is an opaque correlation value, not authentication and not
  authorization. It grants no access to a file or analysis result.
- Registry entries expire after 15 minutes and are pruned on every observation.
- The registry has a hard cap of 2,048 entries and deterministically evicts the
  oldest entry when the cap is exceeded.
- Streamlit remains responsible for upload validation, XSRF protection, upload
  size enforcement, and its session-specific upload URL.
- Supported extensions remain `dxf` and `dwg`.
- No second upload endpoint or analysis pipeline is introduced.

## Acceptance protocol

For Chrome for Android and Firefox for Android separately:

1. Open ZURU with mobile data enabled and Wi-Fi disabled.
2. Select `Sana fasadi.dwg` through the Android file picker.
3. If Streamlit replaces the session, verify that ZURU displays the recovery
   warning and does not claim that it retained or replayed the file.
4. Select the same file again in the recovered session.
5. Require `UPLOADER_OBJECT`, `PRE_INGEST_DWG_REACHED`, and `INGEST_ENTRY` in
   sequence, followed by a completed analysis.
6. Repeat once from a fresh tab to reject success caused only by stale state.

Desktop regression requires one DXF and `Sana fasadi.dwg` to complete through
the existing ingestion and analysis path without a recovery warning.

## Rejection and rollback

Reject the mechanism if the warning is not correlated with session replacement,
if explicit reselection still does not produce `UploadedFile`, if an upload is
duplicated, or if desktop DXF/DWG behavior regresses. Rollback is removal of
this experiment module, its import/owner observation/uploader key integration,
its tests, and this document; ingestion and conversion files are unchanged.
