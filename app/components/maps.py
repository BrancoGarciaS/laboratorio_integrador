import streamlit as st
import folium
from streamlit_folium import st_folium
from .loaders import load_raster
import numpy as np
import io
import base64
import matplotlib.pyplot as plt
from PIL import Image
import rasterio

# Componente para cargar y mostrar mapas

# Coordenadas aproximadas de San Joaquín
SAN_JOAQUIN_LAT = -33.5
SAN_JOAQUIN_LON = -70.6167

def base_map(lat=SAN_JOAQUIN_LAT, lon=SAN_JOAQUIN_LON, zoom=13):
    """Mapa base centrado en la comuna de San Joaquín."""
    return folium.Map(location=[lat, lon], zoom_start=zoom, tiles="OpenStreetMap")


def add_raster_layer(m, raster_name, layer_name, cmap="viridis"):
    src = load_raster(raster_name)

    # ---- 1) reproyectar a EPSG:4326 si es necesario ----
    if src.crs is not None and src.crs.to_string() != "EPSG:4326":
        from rasterio.warp import calculate_default_transform, reproject, Resampling

        transform, width, height = calculate_default_transform(
            src.crs, "EPSG:4326", src.width, src.height, *src.bounds
        )

        kwargs = src.meta.copy()
        kwargs.update({
            "crs": "EPSG:4326",
            "transform": transform,
            "width": width,
            "height": height
        })

        data = np.empty((height, width), dtype=src.dtypes[0])

        reproject(
            source=rasterio.band(src, 1),
            destination=data,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs="EPSG:4326",
            resampling=Resampling.bilinear
        )

        arr = data
        bounds = rasterio.transform.array_bounds(height, width, transform)

    else:
        arr = src.read(1)
        bounds = src.bounds

    # ---- 2) manejar nodata como NaN ----
    nodata = src.nodata
    if nodata is not None:
        arr = np.where(arr == nodata, np.nan, arr)

    # ---- 3) normalización ignorando NaN ----
    vmin = np.nanmin(arr)
    vmax = np.nanmax(arr)
    arr_norm = (arr - vmin) / (vmax - vmin)

    # ---- 4) invertir eje vertical ----
    arr_norm = np.flipud(arr_norm)

    # ---- 5) aplicar colormap con transparencia ----
    cmap = plt.get_cmap(cmap)
    rgba = cmap(arr_norm)  # RGBA en [0,1]

    # transparencia para NaN
    mask_nan = np.isnan(arr)
    rgba[mask_nan, 3] = 0.0  # alpha = 0 → invisible

    # ---- 6) guardar imagen en memoria sin bordes y con fondo transparente ----
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.axis("off")
    ax.imshow(rgba)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", pad_inches=0, dpi=150, transparent=True)
    plt.close(fig)

    img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    img_url = f"data:image/png;base64,{img_b64}"

    # ---- 7) bounds en orden folium (S,W,N,E) ----
    south, west, north, east = bounds[1], bounds[0], bounds[3], bounds[2]

    folium.raster_layers.ImageOverlay(
        image=img_url,
        bounds=[[south, west], [north, east]],
        opacity=0.9,
        name=layer_name
    ).add_to(m)

    return arr 


def plot_raster_histogram(arr, layer_name, cmap="viridis", bins=50):
    """
    Genera un histograma de valores de un raster con el colormap aplicado.
    
    Parameters
    ----------
    arr : np.ndarray
        Matriz de valores del raster (con NaN en nodata).
    layer_name : str
        Nombre de la capa para el título.
    cmap : str
        Nombre del colormap de matplotlib.
    bins : int
        Número de bins para el histograma.
    """
    # Filtrar valores válidos
    vals = arr[~np.isnan(arr)]
    
    # Calcular histograma
    counts, edges = np.histogram(vals, bins=bins)
    
    # Normalizar para aplicar colormap
    norm_vals = (edges[:-1] - vals.min()) / (vals.max() - vals.min())
    colors = plt.get_cmap(cmap)(norm_vals)
    
    # Graficar
    fig, ax = plt.subplots(figsize=(6,4))
    ax.bar(edges[:-1], counts, width=np.diff(edges), color=colors, align="edge")
    ax.set_title(f"Distribución de valores - {layer_name}")
    ax.set_xlabel("Valor raster")
    ax.set_ylabel("Frecuencia")
    
    # Mostrar en Streamlit
    st.pyplot(fig)


def render_map(m):
    """Renderiza el mapa con control de capas en Streamlit."""
    folium.LayerControl().add_to(m)
    st_folium(m, height=600, width=None)
