# DIAG-02 uploader instrumentation

DIAG-02 is temporary, diagnostic-only stdout logging for locating the DWG upload and ingestion boundary. It does not change upload, conversion, ingestion, analysis, or UI behavior.

Implemented markers:

- `UPLOADER_NONE` when Streamlit returns no uploaded file.
- `UPLOADER_OBJECT` when an upload object exists; logs only filename, declared size, extension, and optional MIME type.
- `PRE_INGEST_DWG_REACHED` immediately before a DWG is passed to `ingest_file_bytes`.
- `INGEST_ENTRY` after `ingest_file_bytes` determines the extension; logs only filename and extension.

The diagnostics never log raw file bytes, file contents, or a full-file hash. Remove all DIAG-02 instrumentation after the failure boundary has been identified.
