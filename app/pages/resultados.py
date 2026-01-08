import streamlit as st
import pandas as pd
from components.loaders import load_csv
from components.figures import load_image
from components.sidebar import render_sidebar, sidebar_down

page = render_sidebar()

st.header("📈 Síntesis de Resultados")

st.markdown("""
Esta sección consolida los resultados finales del análisis territorial,
integrando la comparación entre enfoques geoestadísticos y modelos de
Machine Learning, así como su validación espacial.
""")

st.subheader("⚖️ Comparación de Desempeño de Modelos")

df_metrics = load_csv("cv_all_variables.csv")

st.markdown("""
Los resultados de validación cruzada permiten comparar el desempeño
predictivo entre interpolación geoestadística (Kriging) y regresión
multivariada (Random Forest).
""")

st.markdown("""
Random Forest es elegido de entre XGBoost y SVM espacial por ser el mejor modelo según su valor RMSE.
""")

df_models = load_csv("model_comparison.csv") 
st.dataframe(df_models, use_container_width=True)

st.markdown("""
Los resultados de comparación entre interpolación geoestadística (Kriging) y regresión
multivariada (Random Forest) son:
""")


st.dataframe(df_metrics, use_container_width=True)

# Métricas clave (si existen en el CSV)
if {"RMSE", "R2", "Metodo"}.issubset(df_metrics.columns):
    col1, col2 = st.columns(2)

    best_rmse = df_metrics.loc[df_metrics["RMSE"].idxmin()]
    best_r2 = df_metrics.loc[df_metrics["R2"].idxmax()]

    col1.metric(
        "Mejor RMSE",
        f"{best_rmse['RMSE']:.3f}",
        help=f"Modelo: {best_rmse['Metodo']}"
    )

    col2.metric(
        "Mejor R²",
        f"{best_r2['R2']:.3f}",
        help=f"Modelo: {best_r2['Metodo']}"
    )

# Gráfico comparativo generado en el notebook
st.subheader("📊 Síntesis Gráfica de Comparación")
load_image("05_sintesis_comparacion_modelos.png")

# ==========================================================
# 2. Síntesis espacial del modelo ganador
# ==========================================================
st.subheader("🗺️ Síntesis Espacial del Modelo Predictivo")

st.markdown("""
El mapa de síntesis muestra la predicción espacial generada por el modelo
de Machine Learning, permitiendo evaluar su coherencia con la estructura
territorial, densidad urbana y morfología de la comuna.
""")

load_image("06_mapa_sintesis_prediccion_ml.png")

# ==========================================================
# 3. Validación conceptual
# ==========================================================
st.subheader("🧠 Validación e Interpretación")

st.markdown("""
**Comparación de modelos**

* Kriging obtuvo mejor desempeño que Random Forest en la predicción de densidad poblacional
(RMSE menor y mayor R²). Esto indica que, en San Joaquín, la densidad se explica mejor por
la **autocorrelación espacial** entre manzanas que por variables explicativas como
vías, NDVI o morfología urbana.

* El bajo R² en ambos modelos refleja la **alta heterogeneidad y verticalización** de la comuna,
donde cambios bruscos de densidad ocurren a escala muy local, dificultando su modelación.

""")

st.markdown("""

**Validación espacial del modelo ML**

El mapa predictivo del modelo de Machine Learning reproduce correctamente la
**estructura urbana general** de San Joaquín, concentrando altas densidades en
zonas verticalizadas y evitando sobreestimar población en áreas industriales.

Sin embargo, el modelo tiende a **suavizar los valores extremos**, lo que explica su
mayor error numérico. Aun así, el mapa resulta útil para estimar densidad poblacional
en zonas donde el Censo pueda estar desactualizado.

""")



# ==========================================================
# 4. Conclusión metodológica
# ==========================================================
st.subheader("📌 Conclusión de la Síntesis")

st.markdown("""
**Conclusión**

El análisis integrado muestra que la densidad poblacional en San Joaquín es un
fenómeno altamente localizado, dominado por la autocorrelación espacial más que
por variables de entorno.

La geoestadística (Kriging) resulta más confiable para la predicción espacial,
mientras que el Machine Learning aporta una lectura coherente de la estructura
urbana, aunque con limitaciones para capturar valores extremos.

En conjunto, ambos enfoques permiten comprender la comuna como un sistema urbano
complejo, heterogéneo y en proceso de verticalización, reforzando el valor de
combinar métodos espaciales clásicos y modelos de aprendizaje automático.

""")

st.markdown("""
**Recomendaciones operativas**

* **Priorización de infraestructura en zonas de alta densidad predicha**  
  Las manzanas con mayores valores de densidad poblacional (tonos claros) deben priorizarse para inversiones en infraestructura urbana crítica, como transporte público, equipamiento de salud, áreas verdes y servicios básicos, debido a la alta carga poblacional estimada.

* **Monitoreo de zonas en proceso de verticalización**  
  Sectores donde el modelo predice densidades medias-altas, pero que no aparecen como altamente densos en el Censo, pueden corresponder a procesos recientes de verticalización (tendencia de las ciudades a aumentar la densidad de la población mediante la construcción de edificios de altura). Estas áreas deben ser monitoreadas para actualización temprana de catastros y planificación preventiva.

* **Gestión de riesgos urbanos**  
  En zonas con alta densidad predicha y baja disponibilidad de espacio abierto, se recomienda evaluar riesgos asociados a evacuación, acceso a servicios de emergencia y sobrecarga de infraestructura urbana.

""")




sidebar_down()

