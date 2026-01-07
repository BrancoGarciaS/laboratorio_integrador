import streamlit as st
from components.loaders import load_csv
from components.figures import load_image
from components.dataset import load_master
from components.sidebar import render_sidebar, sidebar_down

page = render_sidebar()

# Revisar si ya existe en session_state
if "gdf_master" not in st.session_state:
    gdf_master = load_master()
    st.success("Datos cargados correctamente desde PostGIS")
    st.session_state["gdf_master"] = gdf_master
else:
    gdf_master = st.session_state["gdf_master"]


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


# Tabla de master
if "gdf_master" not in st.session_state:
    st.error("No se encontró gdf_master. Vuelve a la página principal primero.")
else:
    gdf_master = st.session_state["gdf_master"]

    st.write("Filas:", len(gdf_master))
    st.dataframe(
        gdf_master.drop(columns="geometry").head(100),
        use_container_width=True
    )


    '''
    st.header("📊 Exploración de Datos")

    tab1, tab2, tab3 = st.tabs(["📋 Resumen", "📈 Estadísticas", "🗂️ Metadatos"])

    with tab1:
        st.subheader("Fuentes de Datos Integradas")

        data_sources = pd.DataFrame({
            'Fuente': ['OpenStreetMap', 'INE', 'IDE Chile', 'Sentinel-2', 'SRTM DEM'],
            'Tipo': ['Vectorial', 'Tabular', 'Vectorial', 'Raster', 'Raster'],
            'Última Actualización': ['2024-01', '2023-12', '2024-01', '2024-01', '2023-06'],
            'Estado': ['✅ Cargado', '✅ Cargado', '⏳ Pendiente', '⏳ Pendiente', '✅ Cargado']
        })

        st.dataframe(data_sources, use_container_width=True)

    with tab2:
        st.subheader("Estadísticas Descriptivas")

        # Gráfico de ejemplo
        fig = px.bar(
            x=['Residencial', 'Comercial', 'Industrial', 'Áreas Verdes', 'Otros'],
            y=[45, 20, 15, 12, 8],
            labels={'x': 'Uso del Suelo', 'y': 'Porcentaje (%)'},
            title='Distribución de Uso del Suelo'
        )
        st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.subheader("Metadatos del Proyecto")
        st.json({
            'proyecto': 'Laboratorio Integrador',
            'version': '1.0.0',
            'fecha_creacion': '2024-01-15',
            'ultima_actualizacion': '2024-01-20',
            'crs': 'EPSG:32719',
            'formato_datos': ['GeoJSON', 'Shapefile', 'GeoTIFF', 'CSV']
        })
        '''
    
sidebar_down()