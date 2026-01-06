import streamlit as st
import pandas as pd
from components.loaders import load_txt, load_csv
from components.charts import variogram_plot
import folium
from streamlit_folium import st_folium
import plotly.express as px

st.header("🗺️ Análisis de Autocorrelación Espacial")

gdf = st.session_state["gdf_master"]

# Coordenadas aproximadas del centro de San Joaquín
CENTER_LAT = -33.4926
CENTER_LON = -70.6272

st.subheader("📈 Gráficos Folium")
m = folium.Map(
    location=[CENTER_LAT, CENTER_LON],
    zoom_start=14
)

folium.GeoJson(
    gdf,
    tooltip=["manzent", "nom", "pop_density"]
).add_to(m)

st_folium(m, height=600, width=1000)

st.subheader("📈 Gráficos dinámicos con Plotly")

fig = px.scatter(
    gdf,
    x="pop_density",
    y="ndvi_mean",
    color="nom",
    hover_name="manzent"
)

st.plotly_chart(fig, use_container_width=True)


summary = load_txt("moran_results.txt")

col1, col2, col3, col4 = st.columns(4)

col1.metric("Variable", summary["variable"])
col2.metric("Moran I", round(summary["morans_i"], 4))
col3.metric("p-value", round(summary["p-value"], 4))
col4.metric("Metodo Pesos", summary["metodo_pesos"])


st.subheader("📈 Variograma Experimental")

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