# DIAG-02 uploader instrumentation (diagnostic only)
# This file is intentionally minimal and documents diagnostics applied in branch diag/diag-02-upload-logging

This branch adds temporary, minimal logging around Streamlit's file_uploader to capture whether UploadedFile objects reach the server and whether ingest_file_bytes is invoked.

Remove the DIAG-01 and DIAG-02 logging lines after diagnosis.
