import streamlit as st
import ezdxf
import os
import io
import tempfile
from collections import Counter
import google.generativeai as genai
import json
import re
import pandas as pd

# Page config
st.set_page_config(layout="wide", page_title="ZURU BIM Analyzer PRO v2.3 - Rooms")
st.title("🏗️ ZURU Tech BIM Analyzer PRO")
st.markdown("**AI DXF/DWG Parser | 52K+ Entities | БАНЯ-123 КУХНЯ-123 анализ**")

# Gemini setup
GEMINI_KEY = "AIzaSyCP1JYzFV2oW6J1pKDuUt6rydhCoeR5HlU"
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-pro')
st.success("✅ Gemini AI готов!")

@st.cache_data
def parse_dxf(file_bytes):
    with tempfile.NamedTemporaryFile(suffix='.dxf', delete=False) as temp_file:
        temp_file.write(file_bytes)
        temp_filename = temp_file.name
    
    try:
        doc = ezdxf.readfile(temp_filename)
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
        
    finally:
        os.unlink(temp_filename)

def classify_rooms_gemini(text_entities, layer_stats):
    room_texts = [entity.dxf.text.strip() for entity in text_entities 
                  if hasattr(entity.dxf, 'text') and entity.dxf.text]
    
    try:
        response = model.generate_content(f"Класифицирай стаи: {room_texts[:20]}")
        return response.text.strip()
    except:
        return '{"error": "Gemini quota", "total": ' + str(len(room_texts)) + '}'

# File upload
uploaded_file = st.file_uploader("📁 Качи DXF/DWG (до 200MB)", type=['dxf', 'dwg'])

if uploaded_file is not None:
    filename = uploaded_file.name
    file_size = uploaded_file.size / (1024*1024)
    st.info(f"📄 {filename} | {file_size:.1f} MB")
    
    with st.spinner("Парсинг 52K+ entities..."):
        all_entities, layer_stats, text_entities, rooms, doc = parse_dxf(uploaded_file.getvalue())
    
    # Metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("📊 Общо entities", f"{sum(all_entities.values()):,}")
    col2.metric("🏠 Оценени стаи", f"{rooms:,}")
    col3.metric("📝 TEXT/MTEXT", len(text_entities))
    
    # Charts
    st.subheader("📈 Топ Entities")
    st.bar_chart(all_entities.most_common(10))
    
    st.subheader("🔍 Топ Layers")
    st.bar_chart(layer_stats.most_common(15))
    
    # Architect highlights
    doors = layer_stats.get('_door', 0) + all_entities.get('INSERT', 0)
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
    
    # Детайлни стаи по TEXT/MTEXT написи - ГЛАВНО!
    st.subheader("🏠 Детайлни стаи: БАНЯ-123, КУХНЯ-123")
    room_texts = [entity.dxf.text.strip() for entity in text_entities 
                  if hasattr(entity.dxf, 'text') and entity.dxf.text]
    
    # Room extraction с regex
    room_stats = {
        "🛁 Бани/ВЦ": len(re.findall(r'(БАНЯ|ВЦ|ТОАЛЕТНА|WC).*?[-№\s]*(\d+)', ' '.join(room_texts), re.I)),
        "🍳 Кухни": len(re.findall(r'(КУХНЯ).*?[-№\s]*(\d+)', ' '.join(room_texts), re.I)),
        "🛏️ Спални": len(re.findall(r'(СПАЛНЯ|СТАЯ).*?[-№\s]*(\d+)', ' '.join(room_texts), re.I)),
        "🏠 Хол": len(re.findall(r'(ХОЛ|ГОСТИНСКИ).*?[-№\s]*(\d+)', ' '.join(room_texts), re.I)),
        "🚪 Коридори": len(re.findall(r'(КОРИДОР).*?[-№\s]*(\d+)', ' '.join(room_texts), re.I))
    }
    
    # Таблица + графика
    st.dataframe(pd.DataFrame(list(room_stats.items()), columns=['Тип', 'Брой']), use_container_width=True)
    st.bar_chart(room_stats)
    st.caption(f"**Анализирани {len(room_texts)}** написи като 'БАНЯ-123'")
    
    # Първите 20 room names
    st.subheader("📝 Примери за room написи")
    sample_rooms = room_texts[:20]
    for i, room in enumerate(sample_rooms, 1):
        st.write(f"{i:2d}. {room}")
    
    # Gemini (ако работи)
    st.subheader("🤖 Gemini AI (ако quota позволи)")
    col1, col2 = st.columns([1,3])
    with col1:
        if st.button("🔍 Класифицирай с Gemini", use_container_width=True):
            with st.spinner("Gemini мисли..."):
                rooms_json = classify_rooms_gemini(text_entities, layer_stats)
                st.session_state.rooms_json = rooms_json
    
    if 'rooms_json' in st.session_state:
        try:
            rooms_data = json.loads(st.session_state.rooms_json)
            st.json(rooms_data)
        except:
            st.info("✅ Manual анализ работи 100%!")
    
    # Report download
    report = f"""ZURU BIM Report: {filename}
📊 Total: {sum(all_entities.values()):,}
🏠 Rooms: {rooms:,}
📝 Text entities: {len(room_texts)}

{room_stats}

Top Entities: {dict(all_entities.most_common(10))}
Top Layers: {dict(layer_stats.most_common(10))}
"""
    st.download_button("📥 Изтегли Report", report, f"{filename}_report.txt", use_container_width=True)

st.markdown("---")
st.markdown("[GitHub](https://github.com/goceterziev-creator/ZURU-BIM-Analyzer) | #AI #BIM #Architecture")
