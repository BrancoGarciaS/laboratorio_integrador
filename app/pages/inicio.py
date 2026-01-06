import streamlit as st
import folium
from streamlit_folium import st_folium
import os
import plotly.express as px
from main import load_master

def show_inicio():

    # Similar al de main.py

    st.title("🗺️ Sistema de Análisis Territorial")
    st.markdown(f"### Comuna: {os.getenv('COMUNA_NAME', 'No configurada')}")

    # Estos datos los saque de google
    col1, col2, col3 = st.columns(3)
    col1.metric("Área Total", "9.70 km²")
    col2.metric("Población", "94.46K hab")
    col3.metric("Densidad", f"{round(94460/9.7, 1)} hab/km²")

    st.markdown("---")
    st.subheader("📍 Ubicación de la Comuna")

    # Mapa base centrado en San Joaquín
    m = folium.Map(
        location=[-33.5, -70.6167],  # coordenadas San Joaquín
        zoom_start=13,
        tiles="OpenStreetMap"
    )

    folium.Marker(
        [-33.5, -70.6167],
        popup="Centro de la Comuna",
        tooltip="Click para más info",
        icon=folium.Icon(icon="info-sign", color="red")
    ).add_to(m)

    st_folium(m, height=500)

    st.dataframe(df_sel[['manzent','pop_density','ndvi_mean','slope_mean']])

show_inicio()
