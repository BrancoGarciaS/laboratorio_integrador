#!/bin/bash

# =============================================================================
# Setup Script para Laboratorio Integrador de Geoinformática
# =============================================================================

set -e  # Detener si hay errores

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Banner
echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║         LABORATORIO INTEGRADOR - GEOINFORMÁTICA                   ║"
echo "║              Configuración Inicial del Proyecto                   ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Función para imprimir mensajes con color
print_message() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

# Verificar prerrequisitos
echo -e "${BLUE}Verificando prerrequisitos...${NC}"

# Verificar Docker
if command -v docker &> /dev/null; then
    print_message "Docker instalado: $(docker --version)"
else
    print_error "Docker no está instalado. Por favor instale Docker Desktop."
    exit 1
fi

# Verificar Docker Compose
if command -v docker-compose &> /dev/null; then
    print_message "Docker Compose instalado: $(docker-compose --version)"
else
    print_error "Docker Compose no está instalado."
    exit 1
fi

# Verificar Python (fallback a 'python' para Windows donde 'python3' puede no existir)
PY_CMD=""
if command -v python3 &> /dev/null; then
    PY_CMD="python3"
elif command -v python &> /dev/null; then
    PY_CMD="python"
fi
if [ -n "$PY_CMD" ]; then
    print_message "Python instalado: $($PY_CMD --version)"
else
    print_error "Python 3 no está instalado (no se encontró 'python3' ni 'python'). Instale Python desde https://www.python.org/downloads/"
    exit 1
fi

# Verificar Git
if command -v git &> /dev/null; then
    print_message "Git instalado: $(git --version)"
else
    print_warning "Git no está instalado. Se recomienda instalarlo para control de versiones."
fi

echo ""
echo -e "${BLUE}Creando estructura de directorios...${NC}"

# Crear directorios principales
directories=(
    "data/raw"
    "data/processed"
    "data/external"
    "notebooks"
    "scripts"
    "app/pages"
    "app/components"
    "app/static"
    "outputs/figures"
    "outputs/models"
    "outputs/reports"
    "docker/jupyter"
    "docker/postgis"
    "docker/web"
    "tests"
)

for dir in "${directories[@]}"; do
    mkdir -p "$dir"
    print_message "Directorio creado: $dir"
done

echo ""
echo -e "${BLUE}Creando archivos de configuración...${NC}"

# Crear archivo .env
if [ ! -f .env ]; then
    cat > .env << 'EOF'
# Database Configuration
POSTGRES_DB=geodatabase
POSTGRES_USER=geouser
POSTGRES_PASSWORD=geopass
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Jupyter Configuration
JUPYTER_TOKEN=laboratorio2025
JUPYTER_PORT=8888

# Web App Configuration
STREAMLIT_PORT=5000

# Project Configuration
COMUNA_NAME=
PROJECT_NAME=laboratorio_integrador

# API Keys (agregar si es necesario)
# GOOGLE_EARTH_ENGINE_KEY=
# SENTINEL_HUB_KEY=

# Paths
DATA_DIR=./data
OUTPUT_DIR=./outputs
EOF
    print_message "Archivo .env creado"
else
    print_warning "Archivo .env ya existe, no se sobrescribe"
fi

# Crear .gitignore
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
ENV/
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Jupyter Notebook
.ipynb_checkpoints
*/.ipynb_checkpoints/*

# Environment
.env
.venv

# Data files
data/raw/*
data/processed/*
data/external/*
*.tif
*.tiff
*.shp
*.shx
*.dbf
*.prj
*.cpg
*.gpkg
*.geojson
*.csv
!data/raw/.gitkeep
!data/processed/.gitkeep
!data/external/.gitkeep

# Models
*.pkl
*.h5
*.pt
*.pth
*.joblib

# Outputs
outputs/figures/*
outputs/models/*
outputs/reports/*
!outputs/figures/.gitkeep
!outputs/models/.gitkeep
!outputs/reports/.gitkeep

# OS
.DS_Store
Thumbs.db
desktop.ini

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# Docker
.dockerignore

# Logs
*.log
logs/

# Temporary files
*.tmp
*.temp
tmp/
temp/
EOF
print_message "Archivo .gitignore creado"

# Crear archivos .gitkeep para mantener directorios vacíos
touch data/raw/.gitkeep
touch data/processed/.gitkeep
touch data/external/.gitkeep
touch outputs/figures/.gitkeep
touch outputs/models/.gitkeep
touch outputs/reports/.gitkeep

echo ""
echo -e "${BLUE}Creando Docker Compose...${NC}"

# Crear docker-compose.yml
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  postgis:
    image: postgis/postgis:15-3.3-alpine
    container_name: postgis_lab
    environment:
      - POSTGRES_DB=${POSTGRES_DB}
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./docker/postgis/init.sql:/docker-entrypoint-initdb.d/01-init.sql
    ports:
      - "${POSTGRES_PORT}:5432"
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

  jupyter:
    build: ./docker/jupyter
    container_name: jupyter_lab
    environment:
      - JUPYTER_ENABLE_LAB=yes
      - JUPYTER_TOKEN=${JUPYTER_TOKEN}
      - POSTGRES_HOST=postgis
      - POSTGRES_DB=${POSTGRES_DB}
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    volumes:
      - ./notebooks:/home/jovyan/work
      - ./data:/home/jovyan/data
      - ./scripts:/home/jovyan/scripts
      - ./outputs:/home/jovyan/outputs
    ports:
      - "${JUPYTER_PORT}:8888"
    depends_on:
      postgis:
        condition: service_healthy
    restart: unless-stopped

  pgadmin:
    image: dpage/pgadmin4:latest
    container_name: pgadmin_lab
    environment:
      - PGADMIN_DEFAULT_EMAIL=admin@geoinformatica.cl
      - PGADMIN_DEFAULT_PASSWORD=admin
    ports:
      - "5050:80"
    volumes:
      - pgadmin_data:/var/lib/pgadmin
    depends_on:
      - postgis
    restart: unless-stopped

volumes:
  postgres_data:
  pgadmin_data:
EOF
print_message "docker-compose.yml creado"

echo ""
echo -e "${BLUE}Creando Dockerfiles...${NC}"

# Dockerfile para Jupyter (versión actualizada con Python 3.11 y mejoras de build)
cat > docker/jupyter/Dockerfile << 'EOF'
FROM jupyter/scipy-notebook:python-3.11

USER root

# Instalar dependencias del sistema necesarias para stack geoespacial
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal-dev \
    libspatialindex-dev \
    libproj-dev \
    libgeos-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Configurar GDAL / PROJ
ENV GDAL_CONFIG=/usr/bin/gdal-config
ENV PROJ_LIB=/usr/share/proj

USER $NB_UID

# Copiar requirements
COPY requirements.txt /tmp/

# Instalar librerías Python (usa pip dentro del entorno conda base)
RUN pip install --no-cache-dir -r /tmp/requirements.txt && \
    fix-permissions "${CONDA_DIR}" && \
    fix-permissions "/home/${NB_USER}"

# Extensiones (JupyterLab 4 soporta muchas vía Python; mantener mientras sean compatibles)
RUN jupyter labextension install @jupyter-widgets/jupyterlab-manager \
    jupyterlab-plotly \
    @jupyterlab/geojson-extension || echo "Extensiones opcionales (ignorando fallo)"

WORKDIR /home/jovyan/work
EOF
print_message "Dockerfile para Jupyter creado (actualizado)"

# requirements.txt para Jupyter (actualizado)
cat > docker/jupyter/requirements.txt << 'EOF'
# Geospatial Core
geopandas==0.14.1
shapely==2.0.2
pyproj==3.6.1
rasterio==1.3.9
fiona==1.9.5
rtree==1.1.0
osmnx==1.8.0
contextily==1.4.0
geopy==2.4.1

# Data Science
pandas==2.1.4
numpy==1.24.3
scipy==1.11.4
scikit-learn==1.3.2
xgboost==2.0.2
lightgbm==4.1.0

# Spatial Analysis
pysal==23.7
esda==2.5.1
splot==1.1.5.post1
libpysal==4.9.2
momepy==0.6.0
pointpats==2.4.0

# Geostatistics
# scikit-gstat 1.0.15 ya no está disponible en PyPI; usar 1.0.22 compatible con Python 3.11
scikit-gstat==1.0.22
pykrige==1.7.0

# Visualization
matplotlib==3.8.2
seaborn==0.13.0
plotly==5.18.0
folium==0.15.1
ipyleaflet==0.18.1
bokeh==3.3.2
altair==5.2.0

# Database
psycopg2-binary==2.9.9
sqlalchemy==2.0.23
geoalchemy2==0.14.3

# Image Processing
scikit-image==0.22.0
opencv-python==4.8.1.78
earthpy==0.9.4

# Web and APIs
requests==2.31.0
beautifulsoup4==4.12.2
lxml==4.9.4

# Google Earth Engine
earthengine-api==0.1.381
geemap==0.29.6

# Utilities
tqdm==4.66.1
python-dotenv==1.0.0
click==8.1.7
pyyaml==6.0.1
h3==3.7.6

# ML Interpretability
shap==0.43.0
lime==0.2.0.1

# Jupyter Extensions
ipywidgets==8.1.1
jupyterlab==4.0.9
notebook==7.0.6
EOF
print_message "requirements.txt para Jupyter creado (actualizado)"

# Script de inicialización para PostGIS
cat > docker/postgis/init.sql << 'EOF'
-- Crear extensiones espaciales
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS postgis_raster;
CREATE EXTENSION IF NOT EXISTS pgrouting;
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;
CREATE EXTENSION IF NOT EXISTS postgis_tiger_geocoder;
CREATE EXTENSION IF NOT EXISTS address_standardizer;

-- Crear esquemas
CREATE SCHEMA IF NOT EXISTS raw_data;
CREATE SCHEMA IF NOT EXISTS processed;
CREATE SCHEMA IF NOT EXISTS analysis;

-- Tabla de metadatos del proyecto
CREATE TABLE IF NOT EXISTS public.project_metadata (
    id SERIAL PRIMARY KEY,
    key VARCHAR(255) UNIQUE NOT NULL,
    value TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insertar metadatos iniciales
INSERT INTO project_metadata (key, value) VALUES
    ('project_name', 'Laboratorio Integrador'),
    ('version', '1.0.0'),
    ('created_date', CURRENT_DATE::TEXT),
    ('srid', '32719'); -- UTM Zone 19S para Chile

-- Función para actualizar timestamp
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger para actualización automática
CREATE TRIGGER update_project_metadata_updated_at
    BEFORE UPDATE ON project_metadata
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- Tabla de log de procesos
CREATE TABLE IF NOT EXISTS public.process_log (
    id SERIAL PRIMARY KEY,
    process_name VARCHAR(255),
    status VARCHAR(50),
    message TEXT,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    created_by VARCHAR(100) DEFAULT CURRENT_USER
);

-- Vista de información espacial
CREATE OR REPLACE VIEW spatial_info AS
SELECT
    f_table_schema as schema,
    f_table_name as table_name,
    f_geometry_column as geom_column,
    coord_dimension,
    srid,
    type
FROM geometry_columns
ORDER BY f_table_schema, f_table_name;

-- Mensaje de confirmación
DO $$
BEGIN
    RAISE NOTICE 'PostGIS configurado exitosamente!';
    RAISE NOTICE 'Versión: %', PostGIS_Version();
END $$;
EOF
print_message "Script SQL de inicialización creado"

echo ""
echo -e "${BLUE}Creando requirements.txt principal...${NC}"

# requirements.txt principal
cat > requirements.txt << 'EOF'
# Core Geospatial
geopandas>=0.14.0
shapely>=2.0.0
pyproj>=3.6.0
rasterio>=1.3.0
fiona>=1.9.0
osmnx>=1.8.0

# Data Science
pandas>=2.1.0
numpy>=1.24.0
scikit-learn>=1.3.0
xgboost>=2.0.0

# Spatial Analysis
pysal>=23.0
esda>=2.5.0
splot>=1.1.5

# Visualization
matplotlib>=3.8.0
seaborn>=0.13.0
plotly>=5.18.0
folium>=0.15.0
streamlit>=1.29.0
streamlit-folium>=0.17.0

# Database
psycopg2-binary>=2.9.0
sqlalchemy>=2.0.0
geoalchemy2>=0.14.0

# Utilities
python-dotenv>=1.0.0
tqdm>=4.66.0
click>=8.1.0
EOF
print_message "requirements.txt principal creado"

echo ""
echo -e "${BLUE}Creando scripts de ejemplo...${NC}"

# Script de descarga de datos
cat > scripts/download_data.py << 'EOF'
#!/usr/bin/env python3
"""
Script para descargar datos geoespaciales de la comuna seleccionada.
"""

import os
import sys
import click
import requests
import geopandas as gpd
import osmnx as ox
from pathlib import Path
from datetime import datetime
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DataDownloader:
    """Clase para gestionar la descarga de datos geoespaciales."""

    def __init__(self, comuna_name: str, output_dir: Path):
        self.comuna = comuna_name
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Inicializando descarga para comuna: {comuna_name}")

    def download_osm_data(self):
        """Descarga datos de OpenStreetMap usando OSMnx."""
        try:
            logger.info("Descargando red vial desde OSM...")

            # Configurar OSMnx
            ox.config(use_cache=True, log_console=True)

            # Descargar red vial
            place_query = f"{self.comuna}, Chile"
            G = ox.graph_from_place(place_query, network_type='all')

            # Guardar grafo
            output_file = self.output_dir / 'osm_network.graphml'
            ox.save_graphml(G, output_file)
            logger.info(f"Red vial guardada en: {output_file}")

            # Descargar edificios
            logger.info("Descargando edificios...")
            buildings = ox.geometries_from_place(
                place_query,
                tags={'building': True}
            )

            # Guardar edificios
            buildings_file = self.output_dir / 'osm_buildings.geojson'
            buildings.to_file(buildings_file, driver='GeoJSON')
            logger.info(f"Edificios guardados en: {buildings_file}")

            # Descargar amenidades
            logger.info("Descargando amenidades...")
            amenities = ox.geometries_from_place(
                place_query,
                tags={'amenity': True}
            )

            amenities_file = self.output_dir / 'osm_amenities.geojson'
            amenities.to_file(amenities_file, driver='GeoJSON')
            logger.info(f"Amenidades guardadas en: {amenities_file}")

            return True

        except Exception as e:
            logger.error(f"Error descargando datos OSM: {e}")
            return False

    def download_boundaries(self):
        """Descarga límites administrativos de IDE Chile."""
        try:
            logger.info("Descargando límites administrativos...")

            # URL del servicio WFS de IDE Chile (ejemplo)
            wfs_url = "https://www.ide.cl/geoserver/wfs"

            # Parámetros para la petición
            params = {
                'service': 'WFS',
                'version': '2.0.0',
                'request': 'GetFeature',
                'typeName': 'division_comunal',
                'outputFormat': 'application/json',
                'CQL_FILTER': f"comuna='{self.comuna.upper()}'"
            }

            # Realizar petición
            response = requests.get(wfs_url, params=params)

            if response.status_code == 200:
                # Guardar respuesta
                boundaries_file = self.output_dir / 'comuna_boundaries.geojson'
                with open(boundaries_file, 'w') as f:
                    f.write(response.text)
                logger.info(f"Límites guardados en: {boundaries_file}")
                return True
            else:
                logger.warning("No se pudieron descargar límites de IDE Chile")
                return False

        except Exception as e:
            logger.error(f"Error descargando límites: {e}")
            return False

    def create_metadata(self):
        """Crea archivo de metadatos de la descarga."""
        metadata = {
            'comuna': self.comuna,
            'fecha_descarga': datetime.now().isoformat(),
            'fuentes': ['OpenStreetMap', 'IDE Chile'],
            'archivos_generados': list(self.output_dir.glob('*'))
        }

        metadata_file = self.output_dir / 'metadata.txt'
        with open(metadata_file, 'w') as f:
            for key, value in metadata.items():
                f.write(f"{key}: {value}\n")

        logger.info(f"Metadatos guardados en: {metadata_file}")


@click.command()
@click.option('--comuna', required=True, help='Nombre de la comuna')
@click.option('--output', default='../data/raw', help='Directorio de salida')
@click.option('--sources', default='all', help='Fuentes a descargar (osm,ide,all)')
def main(comuna, output, sources):
    """Script principal para descarga de datos."""

    logger.info("=" * 50)
    logger.info("INICIANDO DESCARGA DE DATOS")
    logger.info("=" * 50)

    downloader = DataDownloader(comuna, Path(output))

    # Descargar según las fuentes especificadas
    if sources in ['osm', 'all']:
        downloader.download_osm_data()

    if sources in ['ide', 'all']:
        downloader.download_boundaries()

    # Crear metadatos
    downloader.create_metadata()

    logger.info("Descarga completada exitosamente!")


if __name__ == '__main__':
    main()
EOF
print_message "Script de descarga de datos creado"

# Script de procesamiento
cat > scripts/process_data.py << 'EOF'
#!/usr/bin/env python3
"""
Script para procesar y preparar datos para análisis.
"""

import geopandas as gpd
import pandas as pd
from pathlib import Path
from sqlalchemy import create_engine
import logging
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataProcessor:
    """Procesa y prepara datos para análisis."""

    def __init__(self):
        self.engine = self.create_db_connection()

    def create_db_connection(self):
        """Crea conexión a PostGIS."""
        db_url = (
            f"postgresql://{os.getenv('POSTGRES_USER')}:"
            f"{os.getenv('POSTGRES_PASSWORD')}@"
            f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
            f"{os.getenv('POSTGRES_PORT', '5432')}/"
            f"{os.getenv('POSTGRES_DB')}"
        )
        return create_engine(db_url)

    def load_to_postgis(self, gdf, table_name, schema='raw_data'):
        """Carga GeoDataFrame a PostGIS."""
        try:
            gdf.to_postgis(
                table_name,
                self.engine,
                schema=schema,
                if_exists='replace',
                index=False
            )
            logger.info(f"Tabla {schema}.{table_name} creada exitosamente")
            return True
        except Exception as e:
            logger.error(f"Error cargando a PostGIS: {e}")
            return False

    def process_osm_network(self, input_file):
        """Procesa red vial de OSM."""
        logger.info("Procesando red vial...")
        # Implementar procesamiento
        pass

    def create_spatial_indices(self):
        """Crea índices espaciales en las tablas."""
        logger.info("Creando índices espaciales...")
        # Implementar creación de índices
        pass


def main():
    processor = DataProcessor()
    # Implementar lógica principal
    logger.info("Procesamiento completado!")


if __name__ == '__main__':
    main()
EOF
print_message "Script de procesamiento creado"

echo ""
echo -e "${BLUE}Creando aplicación Streamlit de ejemplo...${NC}"

# App principal Streamlit
cat > app/main.py << 'EOF'
"""
Aplicación web para visualización de análisis geoespacial.
"""

import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

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
st.markdown(f"### Comuna: {os.getenv('COMUNA_NAME', 'No configurada')}")

# Sidebar
with st.sidebar:
    st.image("https://via.placeholder.com/300x100?text=Logo+USACH", width=300)
    st.markdown("---")

    st.markdown("### 📊 Navegación")
    page = st.selectbox(
        "Seleccione una sección:",
        ["🏠 Inicio", "📊 Datos", "🗺️ Análisis Espacial",
         "🤖 Machine Learning", "📈 Resultados"]
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
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Área Total", "125.4 km²", "+2.3%")

    with col2:
        st.metric("Población", "245,678", "+5.2%")

    with col3:
        st.metric("Densidad", "1,958 hab/km²", "+2.8%")

    st.markdown("---")

    # Mapa principal
    st.subheader("📍 Ubicación de la Comuna")

    # Crear mapa con Folium
    m = folium.Map(
        location=[-33.45, -70.65],  # Santiago
        zoom_start=11,
        tiles='OpenStreetMap'
    )

    # Agregar marcador
    folium.Marker(
        [-33.45, -70.65],
        popup="Centro de la Comuna",
        tooltip="Click para más info",
        icon=folium.Icon(icon="info-sign", color="red")
    ).add_to(m)

    # Mostrar mapa
    st_folium(m, height=500, width=None, returned_objects=["last_clicked"])

elif page == "📊 Datos":
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

elif page == "🗺️ Análisis Espacial":
    st.header("🗺️ Análisis Espacial")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Autocorrelación Espacial - Moran's I")

        # Placeholder para gráfico
        st.info("Aquí se mostrará el análisis de autocorrelación espacial")

    with col2:
        st.subheader("Métricas")
        st.metric("Moran's I Global", "0.642", "Alto clustering")
        st.metric("P-value", "0.001", "Significativo")
        st.metric("Z-score", "15.23", "")

elif page == "🤖 Machine Learning":
    st.header("🤖 Modelos de Machine Learning")

    model_type = st.selectbox(
        "Seleccione el modelo:",
        ["Random Forest", "XGBoost", "Red Neuronal"]
    )

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Parámetros del Modelo")

        if model_type == "Random Forest":
            n_estimators = st.slider("Número de árboles:", 10, 500, 100)
            max_depth = st.slider("Profundidad máxima:", 1, 20, 5)
            min_samples_split = st.slider("Min samples split:", 2, 20, 2)

    with col2:
        st.subheader("Métricas de Rendimiento")
        st.metric("R² Score", "0.872")
        st.metric("RMSE", "12.34")
        st.metric("MAE", "8.76")

    if st.button("🚀 Entrenar Modelo"):
        with st.spinner("Entrenando modelo..."):
            st.success("Modelo entrenado exitosamente!")

elif page == "📈 Resultados":
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
        data=b"Contenido del PDF aquí",
        file_name="informe_analisis_territorial.pdf",
        mime="application/pdf"
    )

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
EOF
print_message "Aplicación Streamlit creada"

echo ""
echo -e "${BLUE}Creando notebook de ejemplo...${NC}"

# Crear directorio y archivo Python que luego convertiremos
cat > notebooks/00_template.py << 'EOF'
# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: light
#       format_version: '1.5'
#       jupytext_version: 1.14.0
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# # Notebook Template - Laboratorio Integrador
#
# Este notebook sirve como plantilla para los análisis del laboratorio.

# ## 1. Configuración Inicial

import warnings
warnings.filterwarnings('ignore')

import os
import sys
from pathlib import Path

# Agregar scripts al path
sys.path.append('../scripts')

# Librerías principales
import pandas as pd
import numpy as np
import geopandas as gpd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime

# Configuración de visualización
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")

# Configurar pandas
pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', 100)

print(f"Ambiente configurado: {datetime.now()}")
print(f"Python version: {sys.version}")

# ## 2. Definición de Paths

# Paths principales
DATA_DIR = Path('../data')
RAW_DATA = DATA_DIR / 'raw'
PROCESSED_DATA = DATA_DIR / 'processed'
OUTPUT_DIR = Path('../outputs')
FIGURES_DIR = OUTPUT_DIR / 'figures'
MODELS_DIR = OUTPUT_DIR / 'models'

# Verificar que existan
for path in [DATA_DIR, OUTPUT_DIR]:
    if not path.exists():
        print(f"⚠️ Directorio no existe: {path}")
    else:
        print(f"✅ Directorio encontrado: {path}")

# ## 3. Conexión a Base de Datos

from sqlalchemy import create_engine
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Crear conexión a PostGIS
def create_db_connection():
    """Crea conexión a la base de datos PostGIS."""
    try:
        engine = create_engine(
            f"postgresql://{os.getenv('POSTGRES_USER')}:"
            f"{os.getenv('POSTGRES_PASSWORD')}@"
            f"localhost:{os.getenv('POSTGRES_PORT')}/"
            f"{os.getenv('POSTGRES_DB')}"
        )
        print("✅ Conexión a PostGIS exitosa")
        return engine
    except Exception as e:
        print(f"❌ Error conectando a PostGIS: {e}")
        return None

engine = create_db_connection()

# ## 4. Funciones Auxiliares

def load_geodata(filepath):
    """Carga archivo geoespacial."""
    try:
        gdf = gpd.read_file(filepath)
        print(f"✅ Cargado: {filepath.name}")
        print(f"   Registros: {len(gdf)}")
        print(f"   CRS: {gdf.crs}")
        return gdf
    except Exception as e:
        print(f"❌ Error cargando {filepath}: {e}")
        return None

def save_figure(fig, name, dpi=300):
    """Guarda figura en alta resolución."""
    filepath = FIGURES_DIR / f"{name}.png"
    fig.savefig(filepath, dpi=dpi, bbox_inches='tight')
    print(f"📊 Figura guardada: {filepath}")

def calculate_statistics(gdf, column):
    """Calcula estadísticas descriptivas para una columna."""
    stats = {
        'count': gdf[column].count(),
        'mean': gdf[column].mean(),
        'std': gdf[column].std(),
        'min': gdf[column].min(),
        '25%': gdf[column].quantile(0.25),
        '50%': gdf[column].median(),
        '75%': gdf[column].quantile(0.75),
        'max': gdf[column].max()
    }
    return pd.Series(stats)

# ## 5. Carga de Datos de Ejemplo

# Intentar cargar datos si existen
sample_file = RAW_DATA / 'sample_data.geojson'
if sample_file.exists():
    gdf = load_geodata(sample_file)
    if gdf is not None:
        print("\nPrimeras filas:")
        print(gdf.head())
else:
    print("ℹ️ No hay datos de ejemplo disponibles")

# ## 6. Análisis Exploratorio Básico

if 'gdf' in locals() and gdf is not None:
    # Información general
    print("\n📊 Información del Dataset:")
    print(f"Filas: {len(gdf)}")
    print(f"Columnas: {len(gdf.columns)}")
    print(f"Tipos de geometría: {gdf.geometry.type.unique()}")

    # Visualización básica
    fig, ax = plt.subplots(figsize=(10, 10))
    gdf.plot(ax=ax, edgecolor='black', facecolor='lightblue', alpha=0.7)
    ax.set_title('Vista General de la Comuna', fontsize=16)
    ax.set_xlabel('Longitud')
    ax.set_ylabel('Latitud')
    plt.tight_layout()
    plt.show()

# ## 7. Próximos Pasos

print("\n📝 Próximos pasos sugeridos:")
print("1. Cargar datos específicos de la comuna")
print("2. Realizar análisis exploratorio completo")
print("3. Aplicar técnicas de análisis espacial")
print("4. Desarrollar modelos de ML")
print("5. Crear visualizaciones para el dashboard")

# ## 8. Información de la Sesión

print("\n" + "="*50)
print("INFORMACIÓN DE LA SESIÓN")
print("="*50)
print(f"Fecha y hora: {datetime.now()}")
print(f"Usuario: {os.getenv('USER', 'unknown')}")
print(f"Comuna analizada: {os.getenv('COMUNA_NAME', 'No configurada')}")
print(f"Directorio de trabajo: {os.getcwd()}")
EOF
print_message "Notebook de ejemplo creado"

echo ""
echo -e "${BLUE}Finalizando configuración...${NC}"

# Crear archivo de variables de entorno de ejemplo
cat > .env.example << 'EOF'
# Database Configuration
POSTGRES_DB=geodatabase
POSTGRES_USER=geouser
POSTGRES_PASSWORD=geopass
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Jupyter Configuration
JUPYTER_TOKEN=laboratorio2025
JUPYTER_PORT=8888

# Web App Configuration
STREAMLIT_PORT=5000

# Project Configuration
COMUNA_NAME=Your_Comuna_Here
PROJECT_NAME=laboratorio_integrador

# API Keys (optional)
# GOOGLE_EARTH_ENGINE_KEY=your_key_here
# SENTINEL_HUB_KEY=your_key_here
EOF
print_message "Archivo .env.example creado"

# Hacer el script ejecutable
chmod +x scripts/*.py 2>/dev/null

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                   CONFIGURACIÓN COMPLETADA ✓                      ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════╝${NC}"

echo ""
echo -e "${BLUE}Próximos pasos:${NC}"
echo ""
echo "1. Editar el archivo .env con los valores de su proyecto:"
echo -e "   ${YELLOW}nano .env${NC}"
echo ""
echo "2. Iniciar los servicios Docker:"
echo -e "   ${YELLOW}docker-compose up -d${NC}"
echo ""
echo "3. Verificar que los servicios estén corriendo:"
echo -e "   ${YELLOW}docker-compose ps${NC}"
echo ""
echo "4. Acceder a Jupyter Lab:"
echo -e "   ${YELLOW}http://localhost:8888${NC}"
echo "   Token: laboratorio2025 (o el configurado en .env)"
echo ""
echo "5. Acceder a PgAdmin:"
echo -e "   ${YELLOW}http://localhost:5050${NC}"
echo "   Email: admin@geoinformatica.cl"
echo "   Password: admin"
echo ""
echo "6. Para detener los servicios:"
echo -e "   ${YELLOW}docker-compose down${NC}"
echo ""
echo -e "${GREEN}¡Buena suerte con su proyecto!${NC} 🚀"