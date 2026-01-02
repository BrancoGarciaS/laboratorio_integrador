import streamlit as st
import folium
from streamlit_folium import st_folium
from .loaders import load_raster
import numpy as np
import io
import base64
import matplotlib.pyplot as plt
from PIL import Image


# Componente para cargar y mostrar mapas


# Coordenadas aproximadas de San Joaquín
SAN_JOAQUIN_LAT = -33.5
SAN_JOAQUIN_LON = -70.6167

def base_map(lat=SAN_JOAQUIN_LAT, lon=SAN_JOAQUIN_LON, zoom=13):
    """Mapa base centrado en la comuna de San Joaquín."""
    return folium.Map(location=[lat, lon], zoom_start=zoom, tiles="OpenStreetMap")

def add_raster_layer(m, raster_name, layer_name, cmap="viridis"):
    src = load_raster(raster_name)
    bounds = src.bounds
    arr = src.read(1)

    # Normalizar valores
    arr_norm = (arr - np.nanmin(arr)) / (np.nanmax(arr) - np.nanmin(arr))

    # Crear imagen con matplotlib y exportar a PNG en memoria
    fig, ax = plt.subplots(figsize=(6,6))
    ax.axis("off")
    ax.imshow(arr_norm, cmap=cmap)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    data = base64.b64encode(buf.getvalue()).decode("utf-8")
    img_url = "data:image/png;base64," + data

    # Bounds en orden correcto
    south, west, north, east = bounds.bottom, bounds.left, bounds.top, bounds.right

    folium.raster_layers.ImageOverlay(
        image=img_url,
        bounds=[[south, west], [north, east]],
        opacity=0.7,
        name=layer_name
    ).add_to(m)



def render_map(m):
    """Renderiza el mapa con control de capas en Streamlit."""
    folium.LayerControl().add_to(m)
    st_folium(m, height=600, width=None)
