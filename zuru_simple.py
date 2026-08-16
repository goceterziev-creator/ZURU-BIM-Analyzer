import json
import os

import google.generativeai as genai
import pandas as pd
import streamlit as st

from zuru_core import analyze_dxf_bytes

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


uploaded_file = st.file_uploader("📁 Качи DXF файл (до 200MB)", type=["dxf"])

if uploaded_file is not None:
    filename = uploaded_file.name
    file_size = uploaded_file.size / (1024 * 1024)
    st.info(f"📄 {filename} | {file_size:.1f} MB")

    try:
        with st.spinner("Анализ на DXF source evidence..."):
            analysis = analyze_dxf_bytes(uploaded_file.getvalue())
    except Exception as exc:
        st.error(f"Файлът не можа да бъде прочетен като DXF: {exc}")
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

    report = f"""ZURU BIM Analyzer Report: {filename}

EVIDENCE-BOUND DXF FACTS
Total DXF entities: {sum(entity_stats.values()):,}
Normalized evidence records: {len(evidence_records):,}
TEXT/MTEXT labels: {len(room_texts):,}
Top entity types: {dict(entity_stats.most_common(10))}
Top layers: {dict(layer_stats.most_common(10))}
Source signals: {source_signals}

BOUNDED HEURISTICS
Geometry candidates (LWPOLYLINE + HATCH): {analysis['geometry_candidates']}
Room-label heuristics: {room_stats}

Note: source signals and heuristics are not equivalent to validated BIM element classification.
"""
    col_a, col_b = st.columns(2)
    with col_a:
        st.download_button(
            "📥 Evidence Report (.txt)",
            report,
            f"{filename}_evidence_report.txt",
            use_container_width=True,
        )
    with col_b:
        st.download_button(
            "📥 Normalized Evidence (.json)",
            json.dumps(evidence_records, ensure_ascii=False, indent=2),
            f"{filename}_evidence.json",
            mime="application/json",
            use_container_width=True,
        )

st.markdown("---")
st.caption("ZURU BIM Analyzer · DXF evidence first · AI inference optional")
