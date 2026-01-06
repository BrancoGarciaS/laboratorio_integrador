import streamlit as st
import folium
from streamlit_folium import st_folium
import os

st.title("🗺️ Sistema de Análisis Territorial")
st.markdown(f"### Comuna: {os.getenv('COMUNA_NAME', 'No configurada')}")

col1, col2, col3 = st.columns(3)
col1.metric("Área Total", "9.70 km²")
col2.metric("Población", "94.46K hab")
col3.metric("Densidad", f"{round(94460/9.7, 1)} hab/km²")

st.markdown("---")
st.subheader("📍 Ubicación de la Comuna")

m = folium.Map(
    location=[-33.5, -70.6167],
    zoom_start=13,
    tiles="OpenStreetMap"
)

folium.Marker(
    [-33.5, -70.6167],
    popup="Centro de la Comuna",
    tooltip="Click para más info",
    icon=folium.Icon(icon="info-sign", color="red")
).add_to(m)

st_folium(m, height=500, width=800)

# Dataset
df = st.session_state["gdf_master"]

st.markdown("---")
st.subheader("📊 Exploración de Variables")

# Opciones de conjuntos de columnas que sí existen
options = {
    "Demografía": ["manzent", "total_personas", "total_hombres", "total_mujeres", "edad_15a64", "edad_65ymas"],
    "Vivienda": ["manzent", "total_viviendas", "cantidad_hogares", "viv_part", "viv_col"],
    "Red vial y morfología": ["manzent", "area_m2", "road_length_m", "road_density_km2", "num_edificios", "num_amenidades"]
}

choice = st.selectbox("Seleccione el conjunto de variables a mostrar:", list(options.keys()))

st.dataframe(df[options[choice]])
