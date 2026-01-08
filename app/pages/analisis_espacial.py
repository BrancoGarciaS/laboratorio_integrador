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

# moran
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


st.markdown("""
### 📊 Scatterplot de Moran – Total de Personas  

Este gráfico evalúa la autocorrelación espacial de la variable **total_personas** usando el método de pesos KNN.  
El valor de **Moran’s I = 0.0437** indica una autocorrelación espacial **positiva pero débil**: las zonas con alta población tienden a estar cerca de otras zonas con alta población, y las zonas con baja población tienden a estar cerca de otras con baja población, aunque el efecto no es muy fuerte.  

El **p-value = 0.013** confirma que este resultado es **estadísticamente significativo**, es decir, no se debe al azar.  
En términos prácticos, esto significa que la población no está distribuida de manera completamente aleatoria, sino que existen **clusters locales** de alta y baja densidad poblacional.  

En resumen, aunque la autocorrelación es débil, el análisis confirma que la población presenta cierta tendencia a agruparse espacialmente, lo cual es relevante para entender la estructura urbana y planificar recursos.  

""")

st.subheader("Análisis de Clusters Espaciales - LISA")

# LISA - ndvi
nombre_imagen = st.text_input(
    "LISA - NDVI",
    value="08_lisa_ndvi.png"
)

if nombre_imagen:
    load_image(nombre_imagen)

st.markdown("""
### 🌱 NDVI (Índice de Vegetación) 
El análisis LISA muestra cómo se agrupan los valores de vegetación en el espacio. El scatterplot indica la relación entre cada valor y sus vecinos, mientras que el mapa de clusters revela zonas con alta vegetación rodeadas de áreas similares (HH en rojo) y zonas de baja vegetación rodeadas de áreas igualmente bajas (LL en azul). También aparecen áreas de transición (HL y LH) que reflejan contrastes locales. El mapa de NDVI confirma estas diferencias, mostrando que la vegetación no está distribuida de manera uniforme, sino que se concentra en ciertos sectores y se dispersa en otros. 
""")

# LISA - poblacion
nombre_imagen = st.text_input(
    "LISA - Población Total",
    value="08_lisa_poblacion.png"
)

if nombre_imagen:
    load_image(nombre_imagen)

st.markdown("""
### 👥 Población Total 
Para el caso de densidad poblacional. El scatterplot muestra la correlación espacial, y el mapa de clusters distingue zonas con alta población rodeadas de alta población (HH en rojo), así como sectores de baja población rodeados de baja población (LL en azul). Los clusters HL y LH reflejan áreas donde hay un contraste entre una zona y sus vecinos, lo que sugiere desigualdades en la distribución. El mapa de densidad poblacional confirma esta estructura: existen sectores muy concentrados en habitantes y otros con densidad baja, generando un patrón espacial heterogéneo.
""")

st.subheader("📈 Variogramas Experimentales")

nombre_imagen = st.text_input(
    "Variograma - NDVI mean",
    value="variogram_ndvi_mean.png"
)

if nombre_imagen:
    load_image(nombre_imagen)

st.markdown("""
            
### 🌱 NDVI (ndvi_mean)  
Este gráfico muestra cómo cambia la similitud de la vegetación (medida con el índice NDVI) a medida que aumenta la distancia entre los puntos. En la dirección de 135°, se observa que cuanto más lejos están los puntos, más diferentes son sus valores de vegetación. Dicho de otra forma, la vegetación se vuelve más variable y menos parecida conforme nos alejamos, lo que indica que en esa dirección hay una distribución desigual del verdor en el paisaje, como se mencionó antes.

""")

nombre_imagen = st.text_input(
    "Variograma - POP density",
    value="variogram_pop_density.png"
)

if nombre_imagen:
    load_image(nombre_imagen)

st.markdown("""
### 👥 Densidad poblacional (pop_density)  
Aquí se analiza cómo varía la densidad de población según la distancia en la dirección de 135°. El gráfico muestra que la variabilidad aumenta hasta unos 1600 metros y luego disminuye. Esto significa que, al principio, los valores de población se vuelven más distintos conforme nos alejamos, pero después aparece un patrón repetido o agrupado. En términos simples, la población no está distribuida de manera uniforme: hay zonas donde se concentra y otras donde se dispersa, generando este comportamiento de “subida y bajada” en la variabilidad.

""")
nombre_imagen = st.text_input(
    "Variograma - Slope mean",
    value="variogram_slope_mean.png"
)

if nombre_imagen:
    load_image(nombre_imagen)

st.markdown("""
### 🏔️ Pendiente del terreno (slope_mean)  
Este gráfico refleja cómo cambia la similitud de las pendientes del terreno en la dirección de 135°. Se observa que la variabilidad aumenta de manera continua con la distancia, lo que quiere decir que las pendientes se vuelven cada vez más diferentes cuanto más lejos están los puntos. En otras palabras, el relieve del terreno en esa dirección es bastante irregular: mientras más nos alejamos, más contrastes aparecen en las inclinaciones del suelo.  

""")



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