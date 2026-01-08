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

st.markdown("""
### 🗺️ Densidad Poblacional  
Este mapa de la esquina izquierda muestra cómo se distribuye la población en el área. Los colores más oscuros representan zonas con mayor densidad de habitantes, mientras que los tonos claros indican áreas menos pobladas. Se observa que la población no está repartida de manera uniforme: existen sectores muy concentrados y otros con baja densidad, lo que refleja desigualdad espacial en la ocupación del territorio.  

### 🏠 Cantidad de Viviendas  
Aquí se representa el número de viviendas por zona. Los tonos más oscuros indican áreas con mayor cantidad de casas, mientras que los claros muestran sectores con pocas viviendas. El patrón revela que las viviendas tienden a agruparse en ciertos sectores, lo que puede estar relacionado con la densidad poblacional y el desarrollo urbano.  

### ⚠️ Vulnerabilidad (Material Irrecuperable)  
Este mapa de la esquina derecha señala las zonas donde existen viviendas construidas con materiales vulnerables o irrecuperables. El contraste entre negro (sin vulnerabilidad) y amarillo (con vulnerabilidad) permite identificar áreas críticas. Aunque son menos numerosas, estas zonas vulnerables son importantes porque concentran riesgos sociales y estructurales, lo que puede afectar la resiliencia frente a desastres o problemas urbanos. 

""")


# mapa red vial
nombre_imagen = st.text_input(
    "Mapas de red vial",
    value="03_mapas_red_vial.png"
)

if nombre_imagen:
    load_image(nombre_imagen)

st.markdown("""
### 🚦 Densidad Vial  
Este mapa de la izquierda muestra la cantidad de vías presentes en cada zona. Los colores más intensos (rojo y amarillo) indican sectores con mayor densidad de calles, mientras que el negro refleja áreas sin presencia vial. En términos simples, el mapa permite identificar cuáles sectores están mejor conectados por infraestructura vial y cuáles presentan carencias, lo que influye directamente en la accesibilidad y movilidad urbana.  

### 🌐 Centralidad (Betweenness)  
Este mapa de la derecha representa la importancia de ciertos nodos o sectores dentro de la red vial, medida por cuántas veces aparecen en las rutas más cortas entre distintos puntos. Los colores más cálidos (magenta, naranja y amarillo) señalan zonas con mayor centralidad, es decir, lugares clave para el flujo de tránsito y la conectividad. Los tonos oscuros (azul y púrpura) muestran áreas con baja relevancia en la red. En otras palabras, este mapa ayuda a identificar los puntos estratégicos que funcionan como “puentes” o conexiones críticas dentro de la ciudad.  

""")

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