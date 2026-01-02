import streamlit as st
from components.maps import base_map, add_raster_layer, render_map


# Quiero mostrar algunos raster, por ahora están las capas pero no se pintan 

st.header("🌍 Mapas Temáticos Raster - San Joaquín")

m = base_map()

add_raster_layer(m, "idw_ndvi_mean.tif", "NDVI IDW")
add_raster_layer(m, "kriging_ndvi_mean.tif", "NDVI Kriging")
add_raster_layer(m, "kriging_variance_ndvi_mean.tif", "Kriging Variance")

render_map(m)
