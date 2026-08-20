import json
import os

import google.generativeai as genai
import pandas as pd
import streamlit as st

from zuru_ingest import ingest_file_bytes, DwgConverterUnavailableError, is_converter_configured
from report_builder import build_reports

st.set_page_config(layout="wide", page_title="ZURU BIM Analyzer PRO v2.4")
st.title("🏗️ ZURU Tech BIM Analyzer PRO")
st.markdown("**Evidence-bound DXF analyzer · deterministic source facts + bounded heuristics**")


def get_gemini_key():
    try:
        return st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
    except Exception:
        return os.getenv("GEMINI_API_KEY")


gemini_key = get_gemini_key()
model = None
if gemini_key:
    genai.configure(api_key=gemini_key)
    model = genai.GenerativeModel("gemini-pro")
    st.success("✅ Gemini AI е наличен като допълнителен inference слой.")
else:
    st.info("ℹ️ Gemini AI не е конфигуриран. Детерминистичният DXF анализ работи независимо.")


def classify_rooms_gemini(room_texts):
    if model is None:
        return None
    try:
        response = model.generate_content(f"Класифицирай стаи по тези DXF надписи: {room_texts[:20]}")
        return response.text.strip()
    except Exception as exc:
        return json.dumps({"error": "Gemini unavailable", "detail": str(exc)}, ensure_ascii=False)


uploaded_file = st.file_uploader("📁 Качи DXF/DWG файл (до 200MB)", type=["dxf", "dwg"])
st.caption("При анализ от телефон остави този екран отворен, докато статусът стане „Анализът е готов“.")

# DIAG-02 TEMPORARY: server-side upload-boundary instrumentation.
if uploaded_file is None:
    print("DIAG-02 | UPLOADER_NONE", flush=True)
else:
    uploaded_extension = uploaded_file.name.lower().rsplit(".", 1)[-1] if "." in uploaded_file.name else ""
    print(
        f"DIAG-02 | UPLOADER_OBJECT | filename={uploaded_file.name!r} | "
        f"declared_size={uploaded_file.size} | extension={uploaded_extension!r} | "
        f"mime_type={getattr(uploaded_file, 'type', None)!r}",
        flush=True,
    )

if uploaded_file is not None:
    filename = uploaded_file.name
    file_size = uploaded_file.size / (1024 * 1024)
    st.info(f"📄 {filename} | {file_size:.1f} MB")
    analysis_status = st.status(
        "⏳ Файлът е получен. Подготвям анализа…",
        expanded=True,
        state="running",
    )

    try:
        ext = filename.lower().rsplit('.', 1)[-1]
        if ext == "dwg" and not is_converter_configured():
            analysis_status.update(
                label="❌ DWG конверторът не е наличен.",
                expanded=True,
                state="error",
            )
            st.error("DWG converter is not configured or available. Enable DWG_CONVERTER_IMPL or inject a converter.")
            st.stop()

        analysis_status.write("✅ Файлът достигна до ZURU.")
        file_bytes = uploaded_file.getvalue()
        if ext == "dwg":
            analysis_status.update(
                label="🔄 DWG се конвертира и анализира…",
                expanded=True,
                state="running",
            )
            analysis_status.write("Тази стъпка може да отнеме повече време при първия анализ.")
            print(
                f"DIAG-02 | PRE_INGEST_DWG_REACHED | filename={filename!r} | extension={ext!r}",
                flush=True,
            )
        else:
            analysis_status.update(
                label="🔎 DXF evidence се анализира…",
                expanded=True,
                state="running",
            )
        analysis = ingest_file_bytes(filename, file_bytes)
        analysis_status.update(
            label="✅ Анализът е готов.",
            expanded=False,
            state="complete",
        )
    except DwgConverterUnavailableError as exc:
        analysis_status.update(
            label="❌ DWG конвертирането не може да стартира.",
            expanded=True,
            state="error",
        )
        st.error(f"DWG conversion unavailable: {exc}")
        st.stop()
    except Exception as exc:
        analysis_status.update(
            label="❌ Анализът беше прекъснат.",
            expanded=True,
            state="error",
        )
        st.error(f"Файлът не можа да бъде прочетен/анализиран: {exc}")
        st.stop()

    entity_stats = analysis["entity_stats"]
    layer_stats = analysis["layer_stats"]
    room_texts = analysis["room_texts"]
    room_stats = analysis["room_label_stats"]
    evidence_records = analysis["evidence_records"]

    col1, col2, col3 = st.columns(3)
    col1.metric("📊 DXF entities", f"{sum(entity_stats.values()):,}")
    col2.metric("🧾 Evidence records", f"{len(evidence_records):,}")
    col3.metric("📝 TEXT/MTEXT labels", len(room_texts))

    st.caption(
        "Evidence records са директно извлечени от DXF. Архитектурно значение не се предполага автоматично."
    )

    st.subheader("📈 Source entity types")
    st.bar_chart(entity_stats.most_common(10))

    st.subheader("🔍 Source layers")
    st.bar_chart(layer_stats.most_common(15))

    st.subheader("🧭 Архитектурни source signals")
    st.caption("Това са наблюдавани DXF сигнали, не потвърдена BIM класификация.")
    source_signals = analysis["source_signals"]
    st.dataframe(
        pd.DataFrame(list(source_signals.items()), columns=["DXF signal", "Count"]),
        use_container_width=True,
        hide_index=True,
    )

    st.metric(
        "Геометрични room candidates (LWPOLYLINE + HATCH)",
        analysis["geometry_candidates"],
        help="Приблизителен геометричен сигнал. Не се представя като доказан брой помещения.",
    )

    st.subheader("🏠 Room-label heuristics")
    st.caption("Класификация по TEXT/MTEXT надписи като БАНЯ-123 и КУХНЯ-123; това е heuristic, не geometry proof.")
    st.dataframe(
        pd.DataFrame(list(room_stats.items()), columns=["Тип", "Брой"]),
        use_container_width=True,
        hide_index=True,
    )
    st.bar_chart(room_stats)

    if room_texts:
        st.subheader("📝 Примери за DXF текстови надписи")
        for i, room in enumerate(room_texts[:20], 1):
            st.write(f"{i:2d}. {room}")

    with st.expander("🧾 Normalized DXF evidence preview"):
        st.dataframe(pd.DataFrame(evidence_records[:100]), use_container_width=True, hide_index=True)
        if len(evidence_records) > 100:
            st.caption(f"Показани са първите 100 от {len(evidence_records):,} evidence records.")

    # Deterministic classifications (accepted v1) — derived from normalized evidence and preserved separately
    st.subheader("🔖 Deterministic classifications (accepted v1)")
    st.caption("Deterministic classifications are derived from normalized evidence records by the accepted evidence classifier. They are shown separately from raw evidence and from optional AI inference.")

    evidence_classifications = analysis.get("evidence_classifications", [])
    # Compute counts including explicit 'unknown'
    from collections import Counter

    classification_counts = Counter(c.get("classification", "unknown") for c in evidence_classifications)
    st.write({"counts": dict(classification_counts)})

    # Prepare a bounded preview table that shows classification, provenance, and key source fields
    def prepare_classification_preview(classifications, evidence_records, limit=100):
        rows = []
        for idx, c in enumerate(classifications[:limit]):
            rec = c.get("record") or {}
            rows.append(
                {
                    "classification": c.get("classification", "unknown"),
                    "provenance": c.get("provenance", ""),
                    "entity_type": rec.get("entity_type"),
                    "layer": rec.get("layer"),
                    "text": rec.get("text"),
                }
            )
        return rows

    preview_rows = prepare_classification_preview(evidence_classifications, evidence_records, limit=100)
    if preview_rows:
        st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)
    else:
        st.caption("Няма налични детерминистични класификации за показване.")

    st.subheader("🤖 Gemini inference (optional)")
    if model is None:
        st.caption("Добави GEMINI_API_KEY като secret/environment variable, ако искаш AI inference.")
    if st.button("🔍 Класифицирай с Gemini", use_container_width=True, disabled=model is None):
        with st.spinner("Gemini анализира само извлечените текстови надписи..."):
            st.session_state.rooms_json = classify_rooms_gemini(room_texts)

    if st.session_state.get("rooms_json"):
        try:
            st.json(json.loads(st.session_state.rooms_json))
        except Exception:
            st.write(st.session_state.rooms_json)

    # Build product-facing reports and JSON artifacts (deterministic classifications are separate)
    reports = build_reports(analysis, filename)

    col_a, col_b = st.columns(2)
    with col_a:
        st.download_button(
            "📥 Evidence Report (.txt)",
            reports["evidence_report_txt"],
            f"{filename}_evidence_report.txt",
            use_container_width=True,
        )
    with col_b:
        st.download_button(
            "📥 Normalized Evidence (.json)",
            reports["normalized_evidence_json"],
            f"{filename}_evidence.json",
            mime="application/json",
            use_container_width=True,
        )

    # Explicitly expose deterministic classifications as a separate artifact
    col_c, col_d = st.columns(2)
    with col_c:
        st.download_button(
            "📥 Deterministic Classifications (.json)",
            reports["deterministic_classifications_json"],
            f"{filename}_deterministic_classifications.json",
            mime="application/json",
            use_container_width=True,
        )
    with col_d:
        st.caption("Deterministic classifications are a separate JSON artifact, derived from normalized evidence. The raw normalized evidence JSON is unchanged and provided above.")

st.markdown("---")
st.caption("ZURU BIM Analyzer · DXF evidence first · AI inference optional")
