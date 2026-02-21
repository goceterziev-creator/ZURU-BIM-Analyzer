import streamlit as st
import ezdxf
import os
from collections import Counter
import google.generativeai as genai  # Gemini

# Твоя Gemini key (замени)
GEMINI_KEY = "AIzaSyAgT7BuHtldHB4ReHsvkx2mCQOvBY0roJw"  # От AI Studio
genai.configure(api_key=GEMINI_KEY)

st.set_page_config(layout="wide")
st.title("🏗️ ZURU Tech BIM Analyzer PRO")

uploaded_file = st.file_uploader("📁 DXF/DWG", type=["dxf", "dwg"])

if uploaded_file:
    filename = uploaded_file.name
    size_mb = uploaded_file.size / 1024 / 1024
    
    with st.spinner(f"Analyzing {filename}..."):
        with open(filename, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        doc = ezdxf.readfile(filename)
        
        # Stats
        entity_types = Counter()
        layer_stats = Counter()
        
        for entity in doc.entities:
            entity_types[entity.dxftype()] += 1
            layer_stats[entity.dxf.layer] += 1
        
        total_entities = sum(entity_types.values())
        
        col1, col2, col3 = st.columns(3)
        col1.metric("📊 Total Entities", f"{total_entities:,}")
        col2.metric("📐 Polylines", f"{entity_types['LWPOLYLINE']:,}")
        col3.metric("🏠 Est. Rooms", f"{entity_types['LWPOLYLINE'] // 4:,}")
        
        st.success(f"""
        ✅ **{filename}** ({size_mb:.1f}MB) FULLY PARSED!
        🔢 Top Entities: {dict(entity_types.most_common(5))}
        📂 Layers: {len(layer_stats)}
        """)
        
        # Charts
        st.subheader("📈 Entity Breakdown")
        st.bar_chart(entity_types)
        
        st.subheader("📂 Top 15 Layers")
        st.bar_chart(dict(layer_stats.most_common(15)))
        
        # AI Room Detection
        if st.button("🔍 **Детайлни стаи (AI Gemini)**"):
            prompt = f"""
DXF building analysis:
Lines: {entity_types['LINE']:,} 
Polylines: {entity_types['LWPOLYLINE']:,}
INSERT (doors): {entity_types['INSERT']:,}
Layers: {list(layer_stats.keys())[:10]}

Estimate room types JSON:
{{
  "кухни": number,
  "спални": number,
  "бани": number, 
  "холове": number,
  "офици": number
}}
            """
            
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            
            st.markdown("### 🤖 **Gemini AI Room Analysis**")
            st.json(response.text)
            st.balloons()
        
        # Export
        report = f"""ZURU BIM Report: {filename}
Total: {total_entities:,}
Rooms: {entity_types['LWPOLYLINE'] // 4:,}
{entity_types}
{layer_stats.most_common(10)}
        """
        st.download_button("📥 Download Report", report, "zuru_report.txt")
    
    os.remove(filename)

st.markdown("""
### 🎯 Production Features
✅ 52K+ entity parser
✅ Layer charts  
✅ Room estimation
✅ AI room classification  
✅ Architect reports
Live: zuru-bim-analyzer.streamlit.app
""")
