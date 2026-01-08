import streamlit as st
import pandas as pd
from components.loaders import load_txt, load_csv
from components.charts import variogram_plot
import folium
from streamlit_folium import st_folium
import plotly.express as px
from components.figures import load_image
from components.sidebar import render_sidebar, sidebar_down
from components.dataset import load_master

# Revisar si ya existe en session_state
if "gdf_master" not in st.session_state:
    gdf_master = load_master()
    st.success("Datos cargados correctamente desde PostGIS")
    st.session_state["gdf_master"] = gdf_master
else:
    gdf_master = st.session_state["gdf_master"]

page = render_sidebar()

st.header("🗺️ Análisis de Autocorrelación Espacial")

st.subheader("Autocorrelación Espacial - Moran's I")

# Histograma
nombre_imagen = st.text_input(
    "Scatterplot Moran - total personas",
    value="07_moran_scatterplot.png"
)

if nombre_imagen:
    load_image(nombre_imagen)

summary = load_txt("moran_results.txt")

col1, col2, col3, col4 = st.columns(4)

col1.metric("Variable", summary["variable"])
col2.metric("Moran I", round(summary["morans_i"], 4))
col3.metric("p-value", round(summary["p-value"], 4))
col4.metric("Metodo Pesos", summary["metodo_pesos"])

st.subheader("Análisis de Clusters Espaciales - LISA")

# LISA - ndvi
nombre_imagen = st.text_input(
    "LISA - NDVI",
    value="08_lisa_ndvi.png"
)

if nombre_imagen:
    load_image(nombre_imagen)


# LISA - poblacion
nombre_imagen = st.text_input(
    "LISA - Población Total",
    value="08_lisa_poblacion.png"
)

if nombre_imagen:
    load_image(nombre_imagen)

st.subheader("📈 Variogramas Experimentales")

# Cargar CSVs
vario_ndvi = load_csv("variogram_experimental_ndvi_mean.csv")
vario_pop_density = load_csv("variogram_experimental_pop_density.csv")
vario_slope = load_csv("variogram_experimental_slope_mean.csv")

# Renombrar columnas para que coincidan con lo que espera variogram_plot
vario_ndvi = vario_ndvi.rename(columns={
    "distance_bin_m": "distance",
    "gamma": "semivariance"
})

vario_pop_density = vario_pop_density.rename(columns={
    "distance_bin_m": "distance",
    "gamma": "semivariance"
})

vario_slope = vario_slope.rename(columns={
    "distance_bin_m": "distance",
    "gamma": "semivariance"
})

# Graficar
fig = variogram_plot(vario_ndvi, "Variograma NDVI Mean")
st.plotly_chart(fig, use_container_width=True)

fig = variogram_plot(vario_pop_density, "Variograma POP DENSITY")
st.plotly_chart(fig, use_container_width=True)

fig = variogram_plot(vario_slope, "Variograma SLOPE Mean")
st.plotly_chart(fig, use_container_width=True)

df = st.session_state["gdf_master"]

st.subheader("📊 Gráfico Plotly: Relación entre área y número de edificios")

fig = px.scatter(
    df,
    x="area_m2",
    y="num_edificios",
    color="comuna",          # colorear por comuna
    hover_name="manzent",    # mostrar identificador de manzana
    size="num_amenidades",   # tamaño proporcional a amenidades
    title="Área de manzana vs número de edificios"
)

st.plotly_chart(fig, use_container_width=True)