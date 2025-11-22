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
