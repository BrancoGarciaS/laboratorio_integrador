import streamlit as st
from components.loaders import load_json
from components.sidebar import render_sidebar, sidebar_down

page = render_sidebar()

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


'''
    st.header("📈 Síntesis de Resultados")

    st.markdown("""
    ### Hallazgos Principales

    1. **Patrón espacial identificado**: Se detectó clustering significativo en las variables socioeconómicas
    2. **Predicción exitosa**: El modelo ML alcanzó un R² de 0.87
    3. **Zonas críticas**: Se identificaron 5 hot spots que requieren atención

    ### Recomendaciones

    - Implementar políticas focalizadas en las zonas identificadas
    - Continuar monitoreo con imágenes satelitales actualizadas
    - Expandir el análisis a comunas vecinas
    """)

    # Botón de descarga
    st.download_button(
        label="📥 Descargar Informe Completo (PDF)",
        data= "Contenido del PDF aquí",
        file_name="informe_analisis_territorial.pdf",
        mime="application/pdf"
    )
    '''

sidebar_down()