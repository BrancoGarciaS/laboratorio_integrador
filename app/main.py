"""
Aplicación web para visualización de análisis geoespacial.
"""

import streamlit as st
from components.dataset import load_master


# Revisar si ya existe en session_state
if "gdf_master" not in st.session_state:
    gdf_master = load_master()
    st.success("Datos cargados correctamente desde PostGIS")
    st.session_state["gdf_master"] = gdf_master
else:
    gdf_master = st.session_state["gdf_master"]


# Configuración de la página
st.set_page_config(
    page_title="Análisis Territorial - Laboratorio Integrador",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado
st.markdown("""
    <style>
    .main {
        padding-top: 2rem;
    }
    .stButton>button {
        background-color: #0066CC;
        color: white;
    }
    .st-emotion-cache-16idsys p {
        font-size: 1.1rem;
    }
    </style>
""", unsafe_allow_html=True)

# Título principal
st.title("🗺️ Sistema de Análisis Territorial")

# Sidebar
with st.sidebar:
    st.image("https://via.placeholder.com/300x100?text=Logo+USACH", width=300)
    st.markdown("---")

    st.markdown("### 📊 Navegación")
    page = st.selectbox(
        "Seleccione una sección:",
        ["🏠 Inicio", "📊 Datos", "🗺️ Análisis Espacial", "🤖 Machine Learning", "📈 Resultados"]
    )

    st.markdown("---")
    st.markdown("### ℹ️ Información")
    st.info(
        """
        **Laboratorio Integrador**

        Geoinformática 2025

        USACH
        """
    )

# Contenido principal según página seleccionada
if page == "🏠 Inicio":
    st.switch_page("pages/inicio.py")

elif page == "📊 Datos":
    st.switch_page("pages/datos.py")


elif page == "🗺️ Análisis Espacial":
    st.switch_page("pages/analisis_espacial.py")

elif page == "🤖 Machine Learning":
    st.switch_page("pages/machine_learning.py")

elif page == "📈 Resultados":
    st.switch_page("pages/resultados.py")

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center'>
        <p>Desarrollado para el curso de Geoinformática - USACH 2025</p>
        <p>Prof. Francisco Parra O. | <a href='mailto:francisco.parra.o@usach.cl'>francisco.parra.o@usach.cl</a></p>
    </div>
    """,
    unsafe_allow_html=True
)
