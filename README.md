# ZURU BIM Analyzer

ZURU is an evidence-bound DXF analysis app built with Streamlit and `ezdxf`.

## Current capability

- Upload DXF files.
- Extract deterministic DXF source facts: entity type, layer, handle, block name and text where available.
- Show entity and layer statistics.
- Preview and export normalized evidence as JSON.
- Run bounded room-label heuristics from TEXT/MTEXT labels such as `БАНЯ-123` and `КУХНЯ-123`.
- Optionally run Gemini as a separate inference layer when `GEMINI_API_KEY` is configured.

## Evidence model

ZURU intentionally separates:

1. **DXF source facts** — directly observed from the file.
2. **Heuristics** — naming/geometry signals that may help interpretation but are not treated as proven BIM semantics.
3. **AI inference** — optional and clearly separated from deterministic parsing.

The normalized evidence schema is implemented in `dxf_evidence.py`; deterministic analysis lives in `zuru_core.py`.

## Run locally

```bash
pip install -r requirements.txt
streamlit run zuru_simple.py
```

Optional Gemini support:

```bash
set GEMINI_API_KEY=your_key_here
```

On macOS/Linux:

```bash
export GEMINI_API_KEY=your_key_here
```

## Tests

```bash
python -m unittest discover -v
```

The suite includes normalized-entity tests, synthetic architectural DXF ground truth and a non-BIM negative case. GitHub Actions runs the suite on branches and pull requests.

## File support

Current verified ingestion: **DXF**.

DWG is not advertised as supported until a real conversion/ingestion path is implemented and tested.

## Real DWG acceptance fixture

`Sana fasadi.dwg` is intentionally present in the repository as the authorized real-file acceptance fixture for MACHINE Issue #12. Its presence does not by itself establish DWG support. DWG may be advertised as verified only after the required real-file chain succeeds: DWG → real converter → DXF → canonical parser → ZURU normalized evidence.

## Development direction

The next architectural layer is evidence-bound element classification built on top of normalized DXF facts. ZURU should not infer `door`, `wall`, `room`, or other BIM semantics from generic DXF primitives without explicit evidence and validation rules.
