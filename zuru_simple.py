import streamlit as st
import ezdxf
import os
import io
from collections import Counter
import google.generativeai as genai
import json

# Page config
st.set_page_config(layout="wide", page_title="ZURU BIM Analyzer PRO v2.2 - Gemini AI")
st.title("🏗️ ZURU Tech BIM Analyzer PRO")
st.markdown("**AI DXF/DWG Parser | 52K+ Entities | Room Classification с Gemini**")

# Gemini setup - ТВОЯТ КЛЮЧ Е ВКЛЮЧЕН!
GEMINI_KEY = "AIzaSyAgT7BuHtldHB4ReHsvkx2mCQOvBY0roJw"
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-pro')
st.success("✅ Gemini AI готов!")

@st.cache_data
def parse_dxf(file_bytes, filename):
    doc = ezdxf.readfile(io.BytesIO(file_bytes))
    msp = doc.modelspace()
    
    all_entities = Counter()
    layer_stats = Counter()
    text_entities = []
    
    for entity in msp:
        dxftype = entity.dxftype()
        all_entities[dxftype] += 1
        layer_stats[entity.dxf.layer] += 1
        
        if dxftype in ('TEXT', 'MTEXT'):
            text_entities.append(entity)
    
    rooms = len(msp.query('LWPOLYLINE HATCH'))
    
    return all_entities, layer_stats, text_entities, rooms, doc

def classify_rooms_gemini(text_entities, layer_stats):
    room_texts = []
    for entity in text_entities:
        if hasattr(entity.dxf, 'text') and entity.dxf.text:
            room_texts.append(entity.dxf.text.strip())
    
    top_layers = dict(layer_stats.most_common(10))
    
    prompt = f"""
    Анализирай архитектурен DXF чертеж (български/руски текст):
    
    TEXT/MTEXT написи (стаи): {room_texts[:30]}
    
    Топ layers (обекти): {top_layers}
    
    Класифицирай в точен JSON:
    {{
        "кухни": ["КУХНЯ 101", "КУХНЯ 2"],
        "спални": ["СПАЛНЯ 205", "СТАЯ 301"],
        "бани": ["БАНЯ 15", "ТОАЛЕТНА"],
        "коридори": ["КОРИДОР А"],
        "други": ["ОРГАНИЗАТОРСКА"],
        "total_rooms": {len(room_texts)},
        "confidence": 0.95
    }}
    
    Само валиден JSON, без допълнителен текст.
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except:
        return '{"error": "Gemini ключ невалиден или лимит"}'

# File upload
uploaded_file = st.file_uploader("📁 Качи DXF/DWG (до 200MB)", type=['dxf', 'dwg'])

if uploaded_file is not None:
    filename = uploaded_file.name
    file_size = uploaded_file.size / (1024*1024)  # MB
    st.info(f"📄 {filename} | {file_size:.1f} MB")
    
    # Parse ТУК - ВНТРЕ в if!
    with st.spinner("Парсинг 52K+ entities..."):
        all_entities, layer_stats, text_entities, rooms, doc = parse_dxf(uploaded_file.getvalue(), uploaded_file.name)
    
    # Metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("📊 Общо entities", f"{sum(all_entities.values()):,}")
    col2.metric("🏠 Оценени стаи", f"{rooms:,}")
    col3.metric("📝 TEXT/MTEXT", len(text_entities))
    
    # Top entities & layers
    st.subheader("📈 Топ Entities")
    st.bar_chart(all_entities.most_common(10))
    
    st.subheader("🔍 Топ Layers")
    st.bar_chart(layer_stats.most_common(15))
    
    # Architect highlights
    doors = layer_stats.get('_door', 0) + all_entities['INSERT']
    windows = layer_stats.get('_window', 0)
    walls = layer_stats.get('_wall', 0)
    furnish = layer_stats.get('_furnish', 0)
    
    st.markdown(f"""
    **🏠 Ключови обекти:**
    - 🚪 Врати/блокове: **{doors:,}**
    - 🪟 Прозорци: **{windows:,}**
    - 🏗️ Стени: **{walls:,}**
    - 🛋️ Мебели: **{furnish:,}**
    """)
    
    # Gemini Room Classification
    st.subheader("🤖 Gemini AI Класификация на стаи")
    col_gem1, col_gem2 = st.columns([1,3])
    with col_gem1:
        if st.button("🔍 Класифицирай стаи", use_container_width=True):
            with st.spinner("Gemini анализира..."):
                rooms_json = classify_rooms_gemini(text_entities, layer_stats)
                st.session_state.rooms_json = rooms_json
    
    if 'rooms_json' in st.session_state:
        try:
            rooms_data = json.loads(st.session_state.rooms_json)
            st.json(rooms_data)
            
            # Charts от Gemini
            chart_data = {}
            for key in ['кухни', 'спални', 'бани', 'коридори']:
                chart_data[key.title()] = len(rooms_data.get(key, []))
            st.bar_chart(chart_data)
            
        except:
            st.error("❌ JSON грешка: " + st.session_state.rooms_json)
    
    # Report download
    report = f"""
    🏗️ ZURU BIM Report: {filename}
    📊 Total: {sum(all_entities.values()):,}
    🏠 Rooms: {rooms:,}
    
    Top Entities: {dict(all_entities.most_common(10))}
    Top Layers: {dict(layer_stats.most_common(15))}
    
    🚪 Doors: {doors:,} | 🪟 Windows: {windows:,} | 🏗️ Walls: {walls:,}
    """
    st.download_button("📥 Изтегли Report", report, f"{filename}_report.txt")

st.markdown("---")
st.markdown("[GitHub](https://github.com/goceterziev-creator/ZURU-BIM-Analyzer) | #AI #BIM #Architecture")
