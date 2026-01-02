import streamlit as st
from components.loaders import load_csv
from components.figures import load_image

# Por ahora solo se me ocurrió colocar tabla de datos, correlación e histogramas

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