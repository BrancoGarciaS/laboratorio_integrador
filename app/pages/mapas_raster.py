import streamlit as st
from components.maps import base_map, add_raster_layer, render_map, plot_raster_histogram
from components.sidebar import render_sidebar, sidebar_down

page = render_sidebar()

st.header("🌍 Mapas Temáticos Raster - San Joaquín")

m = base_map()

hist_arrays = []

# Definir todas las capas raster en una lista
layers = [
    # IDW layers
    ("idw_ndvi_mean.tif", "NDVI IDW"),
    ("idw_pop_density.tif", "Pop Density IDW"),
    ("idw_slope_mean.tif", "Slope Mean IDW"),

    # Kriging layers
    ("kriging_ndvi_mean.tif", "NDVI Kriging"),
    ("kriging_pop_density.tif", "Pop Density Kriging"),
    ("kriging_slope_mean.tif", "Slope Mean Kriging"),

    # Kriging variance layers
    ("kriging_variance_ndvi_mean.tif", "Kriging Variance NDVI"),
    ("kriging_variance_pop_density.tif", "Kriging Variance Pop Density"),
    ("kriging_variance_slope_mean.tif", "Kriging Variance Slope Mean"),
]

for raster_name, layer_name in layers:
    arr = add_raster_layer(m, raster_name, layer_name)
    hist_arrays.append((arr, layer_name))

render_map(m)

st.markdown("---")
st.subheader("📊 Histogramas de capas raster")

for arr, layer_name in hist_arrays:
    plot_raster_histogram(arr, layer_name)

sidebar_down()