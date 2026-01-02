import pandas as pd
import geopandas as gpd
import rasterio
import json
from pathlib import Path
import joblib

# Componente para cargar archivos json, txt, csv, etc

# raíz del proyecto
PROJECT_ROOT = Path(__file__).resolve().parents[2]

BASE_REPORTS = PROJECT_ROOT / "outputs" / "reports"
BASE_MODELS = PROJECT_ROOT / "outputs" / "models"

def load_csv(filename: str):
    path = BASE_REPORTS / filename
    return pd.read_csv(path)

def load_json(name):
    with open(BASE_REPORTS / name) as f:
        return json.load(f)

def load_model(name):
    return joblib.load(BASE_MODELS / name)

def load_raster(name):
    return rasterio.open(BASE_MODELS / name)

def load_geojson(name):
    return gpd.read_file(BASE_REPORTS / name)

def load_txt(name: str):
    """Carga un archivo de texto plano y lo devuelve como dict si tiene formato clave: valor"""
    path = BASE_REPORTS / name
    results = {}
    with open(path, "r") as f:
        for line in f:
            if ":" in line:
                key, value = line.strip().split(":", 1)
                key = key.strip().lower().replace(" ", "_").replace("'", "")
                try:
                    results[key] = float(value.strip())
                except ValueError:
                    results[key] = value.strip()
    return results