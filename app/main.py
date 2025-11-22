"""
Aplicación web para visualización de análisis geoespacial.
"""

import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración de la página
st.set_page_config(
    page_title="Análisis Territorial - Laboratorio Integrador",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado
st.markdown("""
    <style>
    .main {
        padding-top: 2rem;
    }
    .stButton>button {
        background-color: #0066CC;
        color: white;
    }
    .st-emotion-cache-16idsys p {
        font-size: 1.1rem;
    }
    </style>
""", unsafe_allow_html=True)

# Título principal
st.title("🗺️ Sistema de Análisis Territorial")
st.markdown(f"### Comuna: {os.getenv('COMUNA_NAME', 'No configurada')}")

# Sidebar
with st.sidebar:
    st.image("https://via.placeholder.com/300x100?text=Logo+USACH", width=300)
    st.markdown("---")

    st.markdown("### 📊 Navegación")
    page = st.selectbox(
        "Seleccione una sección:",
        ["🏠 Inicio", "📊 Datos", "🗺️ Análisis Espacial",
         "🤖 Machine Learning", "📈 Resultados"]
    )

    st.markdown("---")
    st.markdown("### ℹ️ Información")
    st.info(
        """
        **Laboratorio Integrador**

        Geoinformática 2025

        USACH
        """
    )

# Contenido principal según página seleccionada
if page == "🏠 Inicio":
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Área Total", "125.4 km²", "+2.3%")

    with col2:
        st.metric("Población", "245,678", "+5.2%")

    with col3:
        st.metric("Densidad", "1,958 hab/km²", "+2.8%")

    st.markdown("---")

    # Mapa principal
    st.subheader("📍 Ubicación de la Comuna")

    # Crear mapa con Folium
    m = folium.Map(
        location=[-33.45, -70.65],  # Santiago
        zoom_start=11,
        tiles='OpenStreetMap'
    )

    # Agregar marcador
    folium.Marker(
        [-33.45, -70.65],
        popup="Centro de la Comuna",
        tooltip="Click para más info",
        icon=folium.Icon(icon="info-sign", color="red")
    ).add_to(m)

    # Mostrar mapa
    st_folium(m, height=500, width=None, returned_objects=["last_clicked"])

elif page == "📊 Datos":
    st.header("📊 Exploración de Datos")

    tab1, tab2, tab3 = st.tabs(["📋 Resumen", "📈 Estadísticas", "🗂️ Metadatos"])

    with tab1:
        st.subheader("Fuentes de Datos Integradas")

        data_sources = pd.DataFrame({
            'Fuente': ['OpenStreetMap', 'INE', 'IDE Chile', 'Sentinel-2', 'SRTM DEM'],
            'Tipo': ['Vectorial', 'Tabular', 'Vectorial', 'Raster', 'Raster'],
            'Última Actualización': ['2024-01', '2023-12', '2024-01', '2024-01', '2023-06'],
            'Estado': ['✅ Cargado', '✅ Cargado', '⏳ Pendiente', '⏳ Pendiente', '✅ Cargado']
        })

        st.dataframe(data_sources, use_container_width=True)

    with tab2:
        st.subheader("Estadísticas Descriptivas")

        # Gráfico de ejemplo
        fig = px.bar(
            x=['Residencial', 'Comercial', 'Industrial', 'Áreas Verdes', 'Otros'],
            y=[45, 20, 15, 12, 8],
            labels={'x': 'Uso del Suelo', 'y': 'Porcentaje (%)'},
            title='Distribución de Uso del Suelo'
        )
        st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.subheader("Metadatos del Proyecto")
        st.json({
            'proyecto': 'Laboratorio Integrador',
            'version': '1.0.0',
            'fecha_creacion': '2024-01-15',
            'ultima_actualizacion': '2024-01-20',
            'crs': 'EPSG:32719',
            'formato_datos': ['GeoJSON', 'Shapefile', 'GeoTIFF', 'CSV']
        })

elif page == "🗺️ Análisis Espacial":
    st.header("🗺️ Análisis Espacial")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Autocorrelación Espacial - Moran's I")

        # Placeholder para gráfico
        st.info("Aquí se mostrará el análisis de autocorrelación espacial")

    with col2:
        st.subheader("Métricas")
        st.metric("Moran's I Global", "0.642", "Alto clustering")
        st.metric("P-value", "0.001", "Significativo")
        st.metric("Z-score", "15.23", "")

elif page == "🤖 Machine Learning":
    st.header("🤖 Modelos de Machine Learning")

    model_type = st.selectbox(
        "Seleccione el modelo:",
        ["Random Forest", "XGBoost", "Red Neuronal"]
    )

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Parámetros del Modelo")

        if model_type == "Random Forest":
            n_estimators = st.slider("Número de árboles:", 10, 500, 100)
            max_depth = st.slider("Profundidad máxima:", 1, 20, 5)
            min_samples_split = st.slider("Min samples split:", 2, 20, 2)

    with col2:
        st.subheader("Métricas de Rendimiento")
        st.metric("R² Score", "0.872")
        st.metric("RMSE", "12.34")
        st.metric("MAE", "8.76")

    if st.button("🚀 Entrenar Modelo"):
        with st.spinner("Entrenando modelo..."):
            st.success("Modelo entrenado exitosamente!")

elif page == "📈 Resultados":
    st.header("📈 Síntesis de Resultados")

    st.markdown("""
    ### Hallazgos Principales

    1. **Patrón espacial identificado**: Se detectó clustering significativo en las variables socioeconómicas
    2. **Predicción exitosa**: El modelo ML alcanzó un R² de 0.87
    3. **Zonas críticas**: Se identificaron 5 hot spots que requieren atención

    ### Recomendaciones

    - Implementar políticas focalizadas en las zonas identificadas
    - Continuar monitoreo con imágenes satelitales actualizadas
    - Expandir el análisis a comunas vecinas
    """)

    # Botón de descarga
    st.download_button(
        label="📥 Descargar Informe Completo (PDF)",
        data=b"Contenido del PDF aquí",
        file_name="informe_analisis_territorial.pdf",
        mime="application/pdf"
    )

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center'>
        <p>Desarrollado para el curso de Geoinformática - USACH 2025</p>
        <p>Prof. Francisco Parra O. | <a href='mailto:francisco.parra.o@usach.cl'>francisco.parra.o@usach.cl</a></p>
    </div>
    """,
    unsafe_allow_html=True
)
