from sqlalchemy import create_engine
import pandas as pd
import streamlit as st
import geopandas as gpd

# Conexión con postgis
@st.cache_resource
def get_engine():
    
    DB_USER = "geouser"
    DB_PASS = "geopass"
    DB_HOST = "postgis"
    DB_PORT = "5432"
    DB_NAME = "geodatabase"

    engine = create_engine(
        f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    return engine

# Crear el dataset 
@st.cache_data
def load_master():
    engine = get_engine()

    gdf = gpd.read_postgis(
        "SELECT * FROM processed_data.manzanas_atributos",
        engine,
        geom_col="geometry"
    )

    df_net = pd.read_sql("SELECT * FROM processed_data.metrics_network", engine)
    df_env = pd.read_sql("SELECT * FROM processed_data.metrics_manzanas", engine)
    df_usos = pd.read_sql("SELECT * FROM processed_data.manzanas_uso_suelo", engine)

    df_usos = df_usos.drop_duplicates(subset="manzent")

    # conversiones
    for d in [gdf, df_net, df_env, df_usos]:
        d["manzent"] = d["manzent"].astype(str)

    # merge principal
    gdf_master = gdf.merge(df_net, on="manzent", how="left")

    cols_env = [c for c in df_env.columns if c not in gdf_master.columns and c != "manzent"]
    gdf_master = gdf_master.merge(df_env[['manzent'] + cols_env], on="manzent", how="left")

    gdf_master = gdf_master.merge(df_usos[['manzent','nom']], on="manzent", how="left")

    gdf_master["nom"] = gdf_master["nom"].fillna("Sin clasificar")

    return gdf_master
