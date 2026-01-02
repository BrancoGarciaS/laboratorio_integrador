import streamlit as st
from components.loaders import load_json

# Mostraer resultados de resumen? por ahora pondo algunas tablas de json

st.header("📈 Síntesis de Resultados")

st.subheader("Variables Analizadas")
ndvi = load_json("summary_ndvi_mean.json")
popd = load_json("summary_pop_density.json")
slope = load_json("summary_slope_mean.json")

st.json({
    "NDVI_mean": ndvi,
    "Population_density": popd,
    "Slope_mean": slope
})
