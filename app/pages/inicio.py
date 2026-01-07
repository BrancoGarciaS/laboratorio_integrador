import streamlit as st
import folium
from streamlit_folium import st_folium
import os
from components.dataset import load_master
from components.sidebar import render_sidebar, sidebar_down

page = render_sidebar()

# Revisar si ya existe en session_state
if "gdf_master" not in st.session_state:
    gdf_master = load_master()
    st.success("Datos cargados correctamente desde PostGIS")
    st.session_state["gdf_master"] = gdf_master
else:
    gdf_master = st.session_state["gdf_master"]

COMUNA_NAME = "San Joaquín"

st.markdown(f"### Comuna: {COMUNA_NAME}")

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

sidebar_down()