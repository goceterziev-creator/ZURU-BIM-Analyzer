import streamlit as st
import ezdxf
import os
import pandas as pd
import re
import io
import tempfile
from collections import Counter
import google.generativeai as genai
import json

# Page config
st.set_page_config(layout="wide", page_title="ZURU BIM Analyzer PRO v2.2 - Gemini AI")
st.title("🏗️ ZURU Tech BIM Analyzer PRO")
st.markdown("**AI DXF/DWG Parser | 52K+ Entities | Room Classification с Gemini**")

# Gemini setup - ТВОЯТ КЛЮЧ Е ВКЛЮЧЕН!
GEMINI_KEY = "AIzaSyCP1JYzFV2oW6J1pKDuUt6rydhCoeR5HlU"
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-pro')
st.success("✅ Gemini AI готов!")

@st.cache_data
def parse_dxf(file_bytes):
    # Создаваме temp файл (ezdxf изисква)
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
        os.unlink(temp_filename)  # Изтрива temp файл

def classify_rooms_gemini(text_entities, layer_stats):
    room_texts = []
    for entity in text_entities:
        if hasattr(entity.dxf, 'text') and entity.dxf.text:
            room_texts.append(entity.dxf.text.strip())
    
    top_layers = dict(layer_stats.most_common(10))
    
    prompt = f"""Анализирай архитектурен DXF чертеж (български/руски текст):

TEXT/MTEXT написи (стаи): {room_texts[:30]}

Топ layers: {top_layers}

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

Само валиден JSON, без допълнителен текст."""

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return '{"error": "Gemini грешка", "fallback": {"total_rooms": ' + str(len(room_texts)) + '}}'

# File upload
uploaded_file = st.file_uploader("📁 Качи DXF/DWG (до 200MB)", type=['dxf', 'dwg'])

if uploaded_file is not None:
    filename = uploaded_file.name
    file_size = uploaded_file.size / (1024*1024)  # MB
    st.info(f"📄 {filename} | {file_size:.1f} MB")
    
    with st.spinner("Парсинг 52K+ entities..."):
        all_entities, layer_stats, text_entities, rooms, doc = parse_dxf(uploaded_file.getvalue())
    
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
    
# Детайлни стаи по TEXT/MTEXT написи
st.subheader("🏠 Детайлни стаи по написи")
room_texts = [entity.dxf.text.strip() for entity in text_entities if hasattr(entity.dxf, 'text') and entity.dxf.text]

# Regex за room patterns
import re
rooms = {
    "🛁 Бани/ВЦ": len(re.findall(r'(БАНЯ|ВЦ|ТОАЛЕТНА|WC).*?[-№]?\s*(\d+)', ' '.join(room_texts), re.I)),
    "🍳 Кухни": len(re.findall(r'(КУХНЯ).*?[-№]?\s*(\d+)', ' '.join(room_texts), re.I)),
    "🛏️ Хол/Гостински": len(re.findall(r'(ХОЛ|ГОСТИНСКА).*?[-№]?\s*(\d+)', ' '.join(room_texts), re.I)),
    "🛋️ Спални": len(re.findall(r'(СПАЛНЯ|СТАЯ).*?[-№]?\s*(\d+)', ' '.join(room_texts), re.I)),
    "🚪 Коридори": len(re.findall(r'(КОРИДОР).*?[-№]?\s*(\d+)', ' '.join(room_texts), re.I))
}

st.dataframe(pd.DataFrame.from_dict(rooms, orient='index', columns=['Брой']), use_container_width=True)
st.bar_chart(rooms)
st.caption(f"Анализирани **{len(room_texts)}** написи като 'БАНЯ-123'")

    # Gemini Room Classification
    st.subheader("🏠 Детайлни стаи (TEXT анализ)")
manual_rooms = {
    "📝 Кухни": sum(1 for t in room_texts if 'КУХН' in t.upper()),
    "🛏️ Спални": sum(1 for t in room_texts if 'СПАЛН' in t.upper()),
    "🚿 Бани": sum(1 for t in room_texts if any(word in t.upper() for word in ['БАНЯ', 'ТОАЛЕТ', 'WC'])),
    "🚪 Коридори": sum(1 for t in room_texts if 'КОРИД' in t.upper())
}
st.bar_chart(manual_rooms)
st.write(f"Общо анализирани: **{len(room_texts)}** написи")
    
    # Report download
    report = f"""
🏗️ ZURU BIM Report: {filename}
📊 Total: {sum(all_entities.values()):,}
🏠 Rooms: {rooms:,}

Top Entities: {dict(all_entities.most_common(10))}
Top Layers: {dict(layer_stats.most_common(15))}

🚪 Doors: {doors:,} | 🪟 Windows: {windows:,} | 🏗️ Walls: {walls:,}
📝 Rooms analyzed: {len(text_entities)}
"""
    st.download_button("📥 Изтегли Report", report, f"{filename}_report.txt")

st.markdown("---")
st.markdown("[GitHub](https://github.com/goceterziev-creator/ZURU-BIM-Analyzer) | #AI #BIM #Architecture")
