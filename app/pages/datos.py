import streamlit as st
from components.loaders import load_csv
from components.figures import load_image
from components.dataset import load_master
from components.sidebar import render_sidebar, sidebar_down
import os
from pathlib import Path
import pandas as pd
from components.dataset import get_engine

page = render_sidebar()

# Revisar si ya existe en session_state
if "gdf_master" not in st.session_state:
    gdf_master = load_master()
    st.success("Datos cargados correctamente desde PostGIS")
    st.session_state["gdf_master"] = gdf_master
else:
    gdf_master = st.session_state["gdf_master"]


st.header("📊 Exploración de Datos")

df = load_csv("estadisticas_numericas.csv")

st.subheader("Vista general de variables")
st.dataframe(df, use_container_width=True)

st.subheader("Descripción estadística")
st.write(df.describe())

# Correlación
st.subheader("Correlación de las variables")

nombre_imagen = st.text_input(
    "Matriz de correlación de las variables",
    value="00_matriz_correlacion.png"
)

if nombre_imagen:
    load_image(nombre_imagen)

# Histograma
nombre_imagen = st.text_input(
    "Histograma de las variables",
    value="01_histogramas_variables.png"
)

if nombre_imagen:
    load_image(nombre_imagen)

# Uso de suelo I
nombre_imagen = st.text_input(
    "Uso de suelo",
    value="05_uso_suelo.png"
)

# Uso de suelo II
nombre_imagen = st.text_input(
    "Gráfico de barra: uso de suelo",
    value="01_uso_suelo_diagrama_barras.png"
)

if nombre_imagen:
    load_image(nombre_imagen)

# mapa socioeconomico
nombre_imagen = st.text_input(
    "Mapas socioeconómicos",
    value="02_mapas_socioeconomicos.png"
)

if nombre_imagen:
    load_image(nombre_imagen)

# mapa red vial
nombre_imagen = st.text_input(
    "Mapas de red vial",
    value="03_mapas_red_vial.png"
)

if nombre_imagen:
    load_image(nombre_imagen)

# --- CONFIGURACIÓN DE ENTORNO ---
BASE_DIR = Path('..')
DATA_RAW = BASE_DIR / 'data' / 'raw'
DATA_PROCESSED = BASE_DIR / 'data' / 'processed'

engine = get_engine()

# --- FUNCIÓN DE VERIFICACIÓN ---
def check_files(directory, file_list):
    results = []
    for f in file_list:
        fpath = directory / f
        if fpath.exists():
            size_mb = fpath.stat().st_size / (1024 * 1024)
            results.append({"Archivo": f, "Estado": "✅ Encontrado", "Tamaño (MB)": f"{size_mb:.2f}"})
        else:
            results.append({"Archivo": f, "Estado": "❌ No encontrado", "Tamaño (MB)": "-"})
    return pd.DataFrame(results)

# --- LISTAS DE ARCHIVOS ---
raw_expected = [
    'manzanas_censales.geojson',
    'comuna_boundaries_oficial.geojson',
    'osm_buildings.geojson',
    'osm_network.graphml',
    'uso_suelo_minvu.geojson',
    'sentinel2_B04.tif',
    'sentinel2_B08.tif',
    'srtm_dem_32719.tif'
]

processed_expected = [
    'manzanas_atributos.geojson',
    'manzanas_uso_suelo.geojson',
    'metrics_network.csv',
    'censo_microdatos.csv',
    'network_nodes_metrics.geojson',
    'sentinel2_ndvi.tif',
    'slope.tif'
]

# --- INTERFAZ STREAMLIT ---
st.title("🔎 Verificación de Archivos y Conexión a BD")

tab1, tab2, tab3 = st.tabs(["📂 Archivos RAW", "📂 Archivos Procesados", "🗄️ Conexión BD"])

DB_HOST = "postgis"
DB_NAME = "geodatabase"

with tab1:
    st.subheader("Archivos RAW esperados")
    df_raw = check_files(DATA_RAW, raw_expected)
    st.dataframe(df_raw, use_container_width=True)

with tab2:
    st.subheader("Archivos PROCESSED esperados")
    df_proc = check_files(DATA_PROCESSED, processed_expected)
    st.dataframe(df_proc, use_container_width=True)

with tab3:
    st.subheader("Conexión a PostGIS")
    try:
        with engine.connect() as conn:
            st.success(f"✔ Conectado a: {DB_NAME} en {DB_HOST}")
    except Exception as e:
        st.error(f"❌ Error de conexión: {e}")

    
sidebar_down()