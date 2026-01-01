#!/usr/bin/env python3
"""
Script MAESTRO de procesamiento e ingesta de datos a PostGIS.
Fusiona la ingesta de fuentes base con la generación de productos analíticos.
Incluye análisis de redes (Betweenness/Densidad) para criterio de excelencia.
"""
import os # Para la gestión de variables de entorno y rutas del sistema operativo
import sys # Para el acceso a parámetros y funciones específicas del intérprete de Python
import click # Para la creación de interfaces de línea de comandos (CLI) con opciones y flags
import logging # Para la configuración de mensajes de seguimiento (logs) por consola o archivo
from pathlib import Path # Para la manipulación de rutas de archivos
from dotenv import load_dotenv # Para la carga de variables de configuración desde archivos .env
import numpy as np # Para operaciones matemáticas avanzadas y manejo de grandes arreglos (arrays)
import pandas as pd # Para la manipulación de datos tabulares (tablas CSV, Excel, DataFrames)
import geopandas as gpd # Extensión de pandas para trabajar con geometrías (Shapefiles, GeoJSON)
import osmnx as ox # Para la descarga y modelado de redes de transporte desde OpenStreetMap
import networkx as nx # Para algoritmos de análisis de grafos (centralidad, rutas más cortas)
from shapely.geometry import Point, LineString # Para la definición de objetos geométricos (puntos y líneas)
from shapely import wkt # Para la lectura y escritura de geometrías en formato de texto (Well-Known Text)
import rasterio # Para la lectura y escritura de archivos raster (GeoTIFF, DEM, Sentinel)
import rasterio.mask # Para el recorte de imágenes raster basado en polígonos vectoriales
from rasterio.warp import calculate_default_transform, reproject, Resampling # Para la reproyección y cambio de resolución (resampling) de rasters
from sqlalchemy import create_engine, text # Motor de conexión y ejecución de sentencias SQL en PostgreSQL
from geoalchemy2 import Geometry # Extensión para integrar tipos de datos espaciales con SQLAlchemy (PostGIS)

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# Configuración de Logging para seguimiento en consola
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Definición de rutas base del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_RAW = BASE_DIR / 'data' / 'raw'
DATA_PROCESSED = BASE_DIR / 'data' / 'processed'

# Crear carpeta para datos procesados si no existe
DATA_PROCESSED.mkdir(parents=True, exist_ok=True)

class DataProcessor:
    """Orquesta el procesamiento e ingesta de datos geoespaciales.

    Descripción: Encapsula métodos para cargar datos crudos (FASE 1), generar productos
                 derivados/análisis (FASE 2) y cargar resultados a PostGIS (FASE 3).

    Atributos:
    - db_url (str): Cadena de conexión a PostgreSQL/PostGIS.
    - engine (sqlalchemy.Engine): Motor de conexión SQL para operaciones.
    """
    def __init__(self, db_url=None):
        """Inicializa la conexión a la base de datos.

        Entrada:
        - db_url (str | None): URL de conexión. Si no se entrega, se construye
          desde variables de entorno (.env).

        Salida:
        - None. Crea el engine SQLAlchemy listo para usar.
        """
        # Preparar URL de BD y crear motor de conexión
        self.db_url = db_url or self._get_db_url() # Seleccionar URL: proporcionada o leída de variables de entorno
        # Crear motor de SQLAlchemy para interactuar con la base de datos
        self.engine = create_engine(self.db_url)

    def _get_db_url(self):
        """
        Descripción: Función que construye la URL de conexión PostgreSQL a partir de .env.

        Entrada:
        - None. Lee variables de entorno: POSTGRES_USER, POSTGRES_PASSWORD,
          POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB.

        Salida:
        - (str) Cadena de conexión en formato postgresql://user:pass@host:port/db
        """
        # Concatena componentes de conexión desde el archivo .env
        return (
            f"postgresql://{os.getenv('POSTGRES_USER')}:"
            f"{os.getenv('POSTGRES_PASSWORD')}@"
            f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
            f"{os.getenv('POSTGRES_PORT', '5432')}/"
            f"{os.getenv('POSTGRES_DB')}"
        )

    def setup_database(self, schemas=['raw_data', 'processed_data']):
        """
        Descripción: Función que crea extensión PostGIS y los esquemas base.

        Entrada:
        - schemas (list[str]): Lista de nombres de esquemas a crear si no existen.

        Salida:
        - None. Asegura que PostGIS esté habilitado y los esquemas disponibles.
        """
        # Crear extensión PostGIS y esquemas para organizar datos crudos/derivados
        try:
            with self.engine.connect() as conn:
                # Habilitar soporte para tipos geométricos en PostgreSQL
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
                # Organizar las tablas en esquemas separados para orden y seguridad
                for schema in schemas:
                    conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema};"))
                conn.commit()
            logger.info(f"✔ Base de datos configurada (Esquemas: {schemas})")
        except Exception as e: # En caso de error, mandar mensaje de advertencia
            logger.error(f"Error conectando a BD: {e}")
            sys.exit(1)

    def _clean_columns(self, gdf):
        """
        Descripción: Función que limpia columnas problemáticas para PostGIS.

        Entrada:
        - gdf (GeoDataFrame): Tabla espacial con posibles columnas conflictivas.

        Salida:
        - (GeoDataFrame) Misma tabla con columnas en minúscula, sin duplicadas
          ni campos técnicos que causen conflictos al cargar a PostGIS.
        """
        # Normalizar nombres y remover columnas técnicas comunes en shapefiles
        # Convertir nombres a minúsculas para evitar problemas de comillas en SQL
        gdf.columns = [c.lower() for c in gdf.columns]
        # Eliminar columnas con nombres idénticos (limpieza de joins previos)
        gdf = gdf.loc[:, ~gdf.columns.duplicated()]
        # Eliminar columnas técnicas de shapefile que ensucian o causan conflicto
        cols_to_drop = [c for c in gdf.columns if c.startswith('shape_') or c in ['len', 'area', 'objectid', 'st_area', 'st_length']]
        if cols_to_drop:
            # Eliminar columnas detectadas de forma segura
            gdf.drop(columns=cols_to_drop, inplace=True, errors='ignore')
        return gdf

    # --- MÉTODOS DE INGESTA BASE (FASE 1) ---

    def load_vector(self, filename, table_name, schema='raw_data', srid=32719):
        """
        Descripción: Función que carga un archivo vectorial y lo ingresa a PostGIS.

        Entrada:
        - filename (str): Nombre del archivo en data/raw/.
        - table_name (str): Nombre de la tabla destino en PostGIS.
        - schema (str): Esquema destino (por defecto 'raw_data').
        - srid (int): EPSG objetivo para reproyección.

        Salida:
        - (None) Guarda copia en data/processed/ y carga la tabla en PostGIS.
        """
        file_path = DATA_RAW / filename # Construir ruta completa al archivo
        if not file_path.exists(): # Si no existe, se lo salta
            logger.warning(f"ADVERTENCIA: Archivo no encontrado: {filename} (Saltando)")
            return

        try: # Leer archivo vectorial (GeoJSON o Shapefile)
            logger.info(f"Procesando {filename}...")
            gdf = gpd.read_file(file_path)
            # Asignar WGS84 por defecto si el archivo no trae CRS definido
            if gdf.crs is None:
                gdf.set_crs(epsg=4326, inplace=True)
            # Reproyectar a coordenadas planas (ej. UTM) para cálculos precisos
            if gdf.crs.to_epsg() != srid:
                logger.info(f"  -> Reproyectando a EPSG:{srid}")
                gdf = gdf.to_crs(epsg=srid)
            # Limpieza de columnas problemáticas
            gdf = self._clean_columns(gdf)
            # Guardar una copia local del dato ya normalizado
            processed_path = DATA_PROCESSED / filename
            # Seleccionar driver según extensión
            driver = 'GeoJSON' if filename.endswith('.geojson') else 'ESRI Shapefile'
            gdf.to_file(processed_path, driver=driver)
            logger.info(f"✔ Guardado en processed: {processed_path.name}")
            # Cargar a PostGIS usando GeoAlchemy2 para manejar la geometría
            gdf.to_postgis(
                name=table_name,
                con=self.engine,
                schema=schema,
                if_exists='replace',
                index=False,
                dtype={'geometry': Geometry(geometry_type='GEOMETRY', srid=srid)}
            ) # Avisa que se carga tabla a PostGIS
            logger.info(f"✔ Cargado en BD: '{schema}.{table_name}'")
        except Exception as e: # En caso de error, mandar mensaje de error
            logger.error(f"ERROR: Error procesando {table_name}: {e}")

    def load_osm_network(self, filename, table_name, schema='raw_data', srid=32719):
        """
        Descripción: Función que convierte y carga la red vial OSM (GraphML) a PostGIS.

        Entrada:
        - filename (str): Nombre del .graphml en data/raw/.
        - table_name (str): Nombre de la tabla a crear.
        - schema (str): Esquema destino.
        - srid (int): EPSG objetivo para las geometrías.

        Salida:
        - (None) Genera 'osm_network.gpkg' (edges) y carga la tabla en PostGIS.
        """
        file_path = DATA_RAW / filename # Construir ruta completa al archivo
        if not file_path.exists(): # Si no existe, se lo salta
            return
        # Cargar grafo OSM desde GraphML
        try:
            logger.info(f"Procesando red vial {filename}...")
            # Cargar grafo OSMnx desde archivo de disco
            G = ox.load_graphml(file_path)
            # Convertir grafo a GeoDataFrames (nodos y aristas)
            gdf_nodes, gdf_edges = ox.graph_to_gdfs(G)
            # Solo cargamos las aristas (calles) para visualización e ingesta
            gdf = gdf_edges.reset_index()
            # Asegurar que el CRS coincida con el resto del proyecto
            if srid != 4326:
                gdf = gdf.to_crs(epsg=srid) # Reproyectar si es necesario
            # PostGIS no soporta listas; convertimos tipos complejos a strings
            # Limpieza de listas
            for col in gdf.columns:
                if gdf[col].apply(lambda x: isinstance(x, list)).any():
                    gdf[col] = gdf[col].astype(str)
            # Limpiar columnas problemáticas
            gdf = self._clean_columns(gdf)
            # Exportar a GeoPackage para compatibilidad con QGIS/ArcGIS
            processed_path = DATA_PROCESSED / "osm_network.gpkg"
            gdf.to_file(processed_path, driver="GPKG", layer="edges")
            logger.info(f"✔ Guardado en processed: osm_network.gpkg")
            # Cargar red vial a la base de datos como LineStrings
            gdf.to_postgis(
                name=table_name,
                con=self.engine,
                schema=schema,
                if_exists='replace',
                index=False,
                dtype={'geometry': Geometry(geometry_type='LINESTRING', srid=srid)}
            ) # Avisa que se carga tabla a PostGIS
            logger.info(f"  ✔ Cargado en BD: '{schema}.{table_name}'")
        except Exception as e: # En caso de error, mandar mensaje de error
            logger.error(f"ERROR: Error procesando red vial: {e}")

    def load_csv_microdatos(self, schema='raw_data'):
        """
        Descripción: Función que carga microdatos del Censo (CSV) al esquema 'raw_data'.

        Entrada:
        - schema (str): Esquema destino para la tabla.

        Salida:
        - (None) Escribe una copia en data/processed/ y carga la tabla.
        """
        # Buscar recursivamente porque la descarga del INE crea subcarpetas
        # Buscar el archivo CSV sin importar en qué subcarpeta del INE esté
        csv_files = list(DATA_RAW.rglob("Censo2017_Manzanas.csv"))
        if not csv_files: # Si no se encuentra, avisar
            logger.warning(" No se encontró Censo2017_Manzanas.csv en data/raw (revisar subcarpetas).")
            return
        # Solo procesar el primer archivo encontrado
        csv_path = csv_files[0]
        table_name = 'censo_microdatos'
        # Si el archivo existe, proceder a cargarse
        try:
            logger.info(f"Procesando microdatos desde {csv_path.relative_to(DATA_RAW)}...")
            # Leer CSV (usar low_memory=False por el tamaño del archivo censal)
            df = pd.read_csv(csv_path, sep=';', low_memory=False)
            df.columns = [c.lower() for c in df.columns]
            # Guardar copia limpia en CSV para auditoría
            processed_path = DATA_PROCESSED / "censo_microdatos.csv"
            df.to_csv(processed_path, index=False, sep=';')
            logger.info(f"  ✔ Guardado en processed: censo_microdatos.csv")
            # Cargar a tabla SQL estándar (sin geometría inicial)
            df.to_sql(table_name, self.engine, schema=schema, if_exists='replace', index=False)
            logger.info(f"  ✔ Cargado en BD: '{schema}.{table_name}'")
        except Exception as e: # En caso de error al procesar el CSV
            logger.error(f"ERROR: Error procesando microdatos: {e}")

    def catalog_rasters(self, schema='raw_data'):
        """
        Descripción: Función que cataloga rasters en disco dentro de una tabla SQL.

        Entrada:
        - schema (str): Esquema donde se crea/actualiza 'raster_catalog'.

        Salida:
        - (None) Inserta/actualiza registros con metadatos de rasters.
        """
        table_name = 'raster_catalog'
        # Listar archivos GeoTIFF y HGT (formato SRTM)
        raster_files = list(DATA_RAW.glob("*.tif")) + list(DATA_RAW.glob("*.hgt"))
        # Si no hay archivos, salir
        if not raster_files:
            return
        records = []
        # Extraer metadatos de cada raster
        for rbox in raster_files:
            try:
                # Abrir archivo para extraer metadatos sin cargar los píxeles a RAM
                with rasterio.open(rbox) as src:
                    records.append({
                        'filename': rbox.name,
                        'location': str(rbox.relative_to(BASE_DIR)),
                        'crs': str(src.crs),
                        'width': src.width,
                        'height': src.height,
                        'bands': src.count,
                        'source_group': 'raw'
                    })
            except: pass
        # Crear tabla de índice para saber qué rasters se tienen y dónde están
        if records: 
            df = pd.DataFrame(records)
            df.to_sql(table_name, self.engine, schema=schema, if_exists='replace', index=False)
            # Definir llave primaria para consultas SQL rápidas
            with self.engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE {schema}.{table_name} ADD PRIMARY KEY (filename);"))
                conn.commit()
            logger.info(f"✔ Catálogo de rasters RAW actualizado ({len(df)} archivos).")

    # --- MÉTODOS DE ANÁLISIS Y DERIVADOS (FASE 2) ---

    def generate_ndvi(self):
        """
        Descripción: Función que calcula NDVI usando bandas B04 (rojo) y B08 (NIR).

        Entrada:
        - None. Requiere archivos 'sentinel2_B04.tif' y 'sentinel2_B08.tif' en data/raw.

        Salida:
        - (None) Escribe 'sentinel2_ndvi.tif' en data/processed/.
        """
        logger.info("Calculando NDVI...")
        # Rutas de las bandas de salida
        b4_path = DATA_RAW / "sentinel2_B04.tif"
        b8_path = DATA_RAW / "sentinel2_B08.tif"
        out_path = DATA_PROCESSED / "sentinel2_ndvi.tif"
        # Si faltan las bandas, avisar
        if not b4_path.exists() or not b8_path.exists():
            logger.warning("ADVERTENCIA: Faltan bandas Sentinel-2 para NDVI.")
            return
        # Calcular NDVI
        try:
            with rasterio.open(b4_path) as r4, rasterio.open(b8_path) as r8:
                # Cargar bandas como arreglos de NumPy para operaciones matemáticas
                red = r4.read(1).astype('float32')
                nir = r8.read(1).astype('float32')
                # Fórmula estándar NDVI: (NIR - Red) / (NIR + Red)
                # Se agrega un valor ínfimo (1e-6) para evitar división por cero
                ndvi = (nir - red) / (nir + red + 1e-6)
                # Configurar metadatos del raster de salida (float32 para decimales)
                meta = r4.meta.copy()
                meta.update(dtype='float32', nodata=-9999, compress='lzw')
                # Se reemplazan valores nulos o infinitos por el valor nodata definido
                ndvi = np.where(np.isfinite(ndvi), ndvi, -9999).astype('float32')
                # Escribir el resultado a un nuevo archivo GeoTIFF
                with rasterio.open(out_path, 'w', **meta) as dst:
                    dst.write(ndvi, 1)
            logger.info(f"  ✔ NDVI generado: {out_path.name}")
        except Exception as e:
            logger.error(f"Error calculando NDVI: {e}")

    def generate_dem_derivatives(self):
        """
        Descripción: Función que genera derivados del DEM: pendiente (slope) y aspecto (aspect).

        Entrada:
        - None. Usa 'srtm_dem_32719.tif' o 'srtm_dem.tif' si el primero no existe.

        Salida:
        - (None) Guarda 'slope.tif' y 'aspect.tif' en data/processed/.
        """
        logger.info("Calculando derivados del DEM...")
        dem_path = DATA_RAW / "srtm_dem_32719.tif" # Ruta preferida del DEM reproyectado
        # Fallback si no existe la versión proyectada
        if not dem_path.exists(): 
            dem_path = DATA_RAW / "srtm_dem.tif"
        # Si no existe ningún DEM, avisar
        if not dem_path.exists():
            logger.warning("ADVERTENCIA: No se encontró DEM para calcular derivados.")
            return
        # Calcular pendientes y aspectos
        try: 
            with rasterio.open(dem_path) as src:
                dem = src.read(1).astype('float32')
                # Obtener la resolución del pixel (tamaño en metros) de la matriz de transformación
                px, py = src.transform.a, abs(src.transform.e)
                # Calcular el gradiente (derivada espacial) en ejes X e Y
                dzdy, dzdx = np.gradient(dem, py, px)
                # Pendiente: Magnitud del gradiente convertida a grados
                slope = np.degrees(np.arctan(np.sqrt(dzdx**2 + dzdy**2)))
                # Orientación (Aspect): Dirección del gradiente en grados (0-360)
                aspect = np.degrees(np.arctan2(-dzdx, dzdy))
                aspect = np.where(aspect < 0, aspect + 360, aspect)
                # Configurar metadatos para los rasters derivados
                meta = src.meta.copy()
                meta.update(dtype='float32', nodata=-9999, compress='lzw')
                # Exportar capas de pendiente y aspecto
                with rasterio.open(DATA_PROCESSED / 'slope.tif', 'w', **meta) as dst:
                    dst.write(slope.astype('float32'), 1)
                with rasterio.open(DATA_PROCESSED / 'aspect.tif', 'w', **meta) as dst:
                    dst.write(aspect.astype('float32'), 1)
            logger.info("  ✔ Derivados DEM generados (slope.tif, aspect.tif)")
        except Exception as e: # En caso de error, mandar mensaje
            logger.error(f"Error derivados DEM: {e}")

    def join_censo(self, srid=32719):
        """
        Descripción: Función que cruza geometrías de manzanas con microdatos censales.

        Entrada:
        - srid (int): EPSG objetivo para asegurar consistencia de CRS.

        Salida:
        - (None) Genera 'manzanas_atributos.geojson' en data/processed/.
        """
        logger.info("Ejecutando Join Censo...")
        # Rutas de archivos necesarios
        geo_path = DATA_PROCESSED / "manzanas_censales.geojson"
        csv_path = DATA_PROCESSED / "censo_microdatos.csv"
        out_path = DATA_PROCESSED / "manzanas_atributos.geojson"
        # Verificar que los archivos de Join Censo estén disponibles
        if not geo_path.exists() or not csv_path.exists():
            logger.warning("ADVERTENCIA: Faltan archivos para Join Censo. Ejecute ingest-minimum primero.")
            return
        # Realizar el cruce (merge) entre geometrías y atributos censales
        try:
            gdf = gpd.read_file(geo_path)
            df = pd.read_csv(csv_path, sep=';', low_memory=False)
            # Normalización de columnas
            gdf.columns = [c.lower() for c in gdf.columns]
            df.columns = [c.lower() for c in df.columns]
            # Buscar la columna 'manzent' (Código de manzana) dinámicamente
            key_geo = next((c for c in gdf.columns if 'manzent' in c), None) 
            key_csv = next((c for c in df.columns if 'manzent' in c), None)
            if not key_geo or not key_csv: # Si no se encuentra la columna 'manzent', avisar
                logger.error(f"No se encontró columna 'manzent' (Geo: {key_geo}, CSV: {key_csv})")
                return
            # Informar las claves usadas para la unión
            logger.info(f"Uniendo por claves: Geo='{key_geo}' ↔ CSV='{key_csv}'")
            # Forzar tipo string y limpiar espacios para asegurar el match perfecto
            gdf[key_geo] = gdf[key_geo].astype(str).str.strip()
            df[key_csv] = df[key_csv].astype(str).str.strip()
            # Realizar unión de atributos (Left Join) basado en el código de manzana
            merged = gdf.merge(df, left_on=key_geo, right_on=key_csv, how='left')
            merged = self._clean_columns(merged)
            # Exportar el producto final enriquecido
            merged.to_file(out_path, driver='GeoJSON')
            logger.info(f"  ✔ Join Censo completado: {out_path.name}")
        except Exception as e: # En caso de error, mandar mensaje
            logger.error(f"Error Join Censo: {e}")

    def join_uso_suelo(self, srid=32719):
        """
        Descripción: Función que cruza manzanas con uso de suelo mediante intersección espacial.

        Entrada:
        - srid (int): EPSG objetivo para reproyección.

        Salida:
        - (None) Genera 'manzanas_uso_suelo.geojson' en data/processed/.
        """
        logger.info("Ejecutando Join Uso de Suelo (Overlay)...")
        # Rutas de archivos necesarios para el uso de suelo
        manzanas_path = DATA_PROCESSED / "manzanas_censales.geojson"
        usos_path = DATA_RAW / "uso_suelo_minvu.geojson"
        out_path = DATA_PROCESSED / "manzanas_uso_suelo.geojson"
        # Verificar que los archivos de Join Uso Suelo estén disponibles
        if not manzanas_path.exists() or not usos_path.exists():
            logger.warning("ADVERTENCIA: Faltan archivos para Join Uso Suelo.")
            return
        # Realizar el cruce espacial entre manzanas y uso de suelo
        try:
            # Asegurar que ambas capas tengan el mismo sistema de coordenadas antes del cruce espacial
            gdf_m = gpd.read_file(manzanas_path).to_crs(epsg=srid)
            gdf_u = gpd.read_file(usos_path).to_crs(epsg=srid)
            # Transferir atributos de uso de suelo a las manzanas que intersectan geométricamente
            join = gpd.sjoin(gdf_m, gdf_u, how='left', predicate='intersects')
            join = self._clean_columns(join)
            # Exportar el resultado final
            join.to_file(out_path, driver='GeoJSON')
            logger.info(f"  ✔ Join Uso Suelo completado: {out_path.name}")
        except Exception as e: # En caso de error, mandar mensaje
            logger.error(f"Error Join Uso Suelo: {e}")

    def generate_metrics(self, srid=32719):
        """
        Descripción: Función que calcula métricas básicas por manzana (área, conteos).

        Entrada:
        - srid (int): EPSG objetivo para operaciones geométricas.

        Salida:
        - (None) Genera CSV 'metrics_manzanas.csv' con estadísticas por manzana.
        """
        logger.info("Calculando métricas básicas por manzana...")
        # Rutas de archivos necesarios para las métricas
        manzanas_path = DATA_PROCESSED / "manzanas_censales.geojson"
        build_path = DATA_PROCESSED / "osm_buildings.geojson"
        amen_path = DATA_PROCESSED / "osm_amenities.geojson"
        out_path = DATA_PROCESSED / "metrics_manzanas.csv"
        # Verificar que el archivo de manzanas esté disponible, sino se sale
        if not manzanas_path.exists(): return
        
        try:
            gdf_m = gpd.read_file(manzanas_path).to_crs(epsg=srid) 
            # 1. Área
            # Cálculo de área geométrica en metros cuadrados (requiere CRS proyectado)
            gdf_m['area_m2'] = gdf_m.geometry.area
            # 2. Conteo Edificios
            # Cruce espacial para contar cuántos edificios hay dentro de cada manzana
            if build_path.exists():
                gdf_b = gpd.read_file(build_path).to_crs(epsg=srid)
                join_b = gpd.sjoin(gdf_b, gdf_m, predicate='intersects')
                counts_b = join_b.groupby('index_right').size()
                gdf_m['num_edificios'] = counts_b
                gdf_m['num_edificios'] = gdf_m['num_edificios'].fillna(0)
            # 3. Conteo Amenidades
            # Cruce espacial para contar servicios/amenidades (hospitales, escuelas, etc.)
            if amen_path.exists():
                gdf_a = gpd.read_file(amen_path).to_crs(epsg=srid)
                join_a = gpd.sjoin(gdf_a, gdf_m, predicate='intersects')
                counts_a = join_a.groupby('index_right').size()
                gdf_m['num_amenidades'] = counts_a
                gdf_m['num_amenidades'] = gdf_m['num_amenidades'].fillna(0)
            # Exportar estadísticas a CSV omitiendo la columna de geometría para ligereza
            df_metrics = pd.DataFrame(gdf_m.drop(columns='geometry'))
            df_metrics.to_csv(out_path, index=False)
            logger.info(f"  ✔ Métricas generadas: {out_path.name}")
        # En caso de error, mandar mensaje
        except Exception as e:
            logger.error(f"Error generando métricas: {e}")

    def generate_network_metrics(self, srid=32719):
        """
        Descripción: Función que calcula métricas avanzadas de la red vial, como
                     centralidades (degree y betweenness) y densidad vial por manzana.

        Entrada:
        - srid (int): EPSG objetivo para manejo de geometrías.

        Salida:
        - (None) Genera 'network_nodes_metrics.geojson' y 'metrics_network.csv'.
        """
        logger.info("✔ Calculando métricas avanzadas de red vial...")
        # Rutas de archivos necesarios para las métricas
        graph_path = DATA_RAW / 'osm_network.graphml'
        manzanas_path = DATA_PROCESSED / 'manzanas_censales.geojson'
        nodes_out = DATA_PROCESSED / 'network_nodes_metrics.geojson'
        # Renombrado a metrics_network.csv para que ingest_processed lo detecte automáticamente
        csv_out = DATA_PROCESSED / 'metrics_network.csv'
        # Verificar que los archivos necesarios estén disponibles
        if not graph_path.exists() or not manzanas_path.exists():
            logger.warning("ADVERTENCIA: Faltan archivos de red o manzanas.")
            return
        try: # Cargar grafo y manzanas
            logger.info("  Cargando grafo y geometrías...")
            G = ox.load_graphml(graph_path) # Cargar grafo OSMnx desde archivo de disco
            gdf_m = gpd.read_file(manzanas_path).to_crs(epsg=srid)
            # Detectar clave de manzana dinámicamente
            manzana_key = next((c for c in gdf_m.columns if 'manzent' in c), None) or gdf_m.columns[0]
            # Centralidad de Grado: Número de conexiones de cada intersección
            logger.info("  Calculando centralidad de nodos...")
            degree_c = nx.degree_centrality(G)
            # Centralidad de Intermediación (Betweenness): Importancia de un nodo en rutas más cortas
            # Si el grafo es muy grande (>5000 nodos), usamos una muestra aleatoria para optimizar tiempo
            if len(G) > 5000:
                import random
                sample_nodes = random.sample(list(G.nodes()), 1000)
                betw_c = nx.betweenness_centrality(G, k=len(sample_nodes))
            else: # Si no, calcular para todos los nodos
                betw_c = nx.betweenness_centrality(G)
            # Construir GeoDataFrame de nodos con sus respectivas centralidades calculadas
            node_records = []
            # Extraer coordenadas de cada nodo y agregar métricas
            for n, data in G.nodes(data=True):
                lon = data.get('x') or data.get('lon')
                lat = data.get('y') or data.get('lat')
                if lon and lat:
                    node_records.append({
                        'node_id': n,
                        'degree': degree_c.get(n, 0),
                        'betweenness': betw_c.get(n, 0),
                        'geometry': Point(float(lon), float(lat))
                    })
            # Crear GeoDataFrame y exportar nodos con métricas
            gdf_nodes = gpd.GeoDataFrame(node_records, crs="EPSG:4326").to_crs(epsg=srid)
            gdf_nodes.to_file(nodes_out, driver='GeoJSON')
            logger.info(f"  ✔ Nodos guardados: {nodes_out.name}")
            # Promediar centralidad de nodos por cada manzana urbana
            logger.info("  Cruzando y agregando por manzana...")
            join_nodes = gpd.sjoin(gdf_nodes, gdf_m, predicate='intersects')
            stats_nodes = join_nodes.groupby(manzana_key).agg({
                'degree': 'mean',
                'betweenness': 'mean',
                'node_id': 'count'
            }).rename(columns={'node_id': 'node_count', 'degree': 'degree_mean', 'betweenness': 'betweenness_mean'})
            # Calcular Densidad Vial (metros lineales de calle / km2 de manzana)
            gdf_nodes_tmp, gdf_edges = ox.graph_to_gdfs(G)
            gdf_edges = gdf_edges.to_crs(epsg=srid)
            # Recortar líneas de calle por los polígonos de manzana
            inter = gpd.overlay(gdf_edges, gdf_m, how='intersection')
            inter['length_m'] = inter.geometry.length
            stats_edges = inter.groupby(manzana_key)['length_m'].sum().to_frame(name='road_length_m')
            # Consolidar todas las métricas de red en un solo archivo CSV
            df_final = pd.DataFrame({manzana_key: gdf_m[manzana_key]})
            df_final = df_final.merge(stats_nodes, on=manzana_key, how='left').fillna(0)
            df_final = df_final.merge(stats_edges, on=manzana_key, how='left').fillna(0)
            # Calcular densidad final (longitud / área)
            areas_km2 = gdf_m.set_index(manzana_key).geometry.area / 1e6
            df_final['road_density_km2'] = df_final.apply(
                lambda row: row['road_length_m'] / areas_km2.get(row[manzana_key], 1), axis=1
            )
            # Exportar métricas a CSV
            df_final.to_csv(csv_out, index=False)
            logger.info(f"  ✔ Métricas de red generadas: {csv_out.name}")
        # En caso de error, mandar mensaje
        except Exception as e:
            logger.error(f"ERROR: Error en métricas de red: {e}")

    def ingest_processed(self, schema='processed_data'):
        """
        Descripción: Función que carga productos derivados (vectores/CSV/rasters) a PostGIS.

        Entrada:
        - schema (str): Esquema destino para las tablas de productos.

        Salida:
        - (None) Carga vectores y tablas; actualiza catálogo de rasters.
        """
        logger.info(f"Ingestando datos procesados al esquema '{schema}'...")
        
        # 1. Vectores procesados
        # Agregamos network_nodes_metrics.geojson a la lista
        # Ingesta masiva de los GeoJSON generados en la fase de análisis
        vectors = ['manzanas_atributos.geojson', 'manzanas_uso_suelo.geojson', 'network_nodes_metrics.geojson']
        for fname in vectors: # Iterar sobre cada archivo vectorial
            fpath = DATA_PROCESSED / fname
            if fpath.exists(): # Solo procesar si el archivo existe
                try:
                    gdf = gpd.read_file(fpath)
                    gdf = self._clean_columns(gdf)
                    table_name = fpath.stem
                    gdf.to_postgis(table_name, self.engine, schema=schema, if_exists='replace', index=False)
                    logger.info(f"  ✔ Tabla cargada: {table_name}")
                except Exception as e:
                    logger.error(f"Error cargando {fname}: {e}")

        # 2. Tablas procesadas
        # Busca metrics_*.csv (esto detectará metrics_manzanas.csv y metrics_network.csv)
        # Ingesta masiva de todos los archivos CSV de métricas
        for f in DATA_PROCESSED.glob("metrics_*.csv"):
            try: # Leer CSV y cargar a tabla SQL
                df = pd.read_csv(f)
                df.columns = [c.lower() for c in df.columns]
                df.to_sql(f.stem, self.engine, schema=schema, if_exists='replace', index=False)
                logger.info(f"  ✔ Tabla cargada: {f.stem}")
            except Exception as e:
                logger.error(f"Error cargando {f.name}: {e}")

        # 3. Catalogar nuevos Rasters
        # Actualizar el catálogo de rasters incluyendo ahora los productos derivados (NDVI, Slope)
        processed_rasters = list(DATA_PROCESSED.glob("*.tif"))
        if processed_rasters: # Si hay rasters procesados
            records = []
            for rbox in processed_rasters: # Iterar sobre cada raster
                try: # Extraer metadatos usando rasterio
                    with rasterio.open(rbox) as src:
                        records.append({ # Metadatos del raster
                            'filename': rbox.name,
                            'location': str(rbox.relative_to(BASE_DIR)),
                            'crs': str(src.crs),
                            'width': src.width,
                            'height': src.height,
                            'bands': src.count,
                            'source_group': 'derived'
                        })
                except: pass
            
            if records: # Si hay registros para agregar
                # Agregar nuevos registros a la tabla de catálogo existente
                df = pd.DataFrame(records)
                try: # Actualizar tabla raster_catalog en la base de datos
                    df.to_sql('raster_catalog', self.engine, schema='raw_data', if_exists='append', index=False)
                    logger.info(f"  ✔ Catálogo actualizado.")
                except: pass

    def create_spatial_indices(self, schema='raw_data'):
        """
        Descripción: Función que crea índices espaciales GIST en tablas con columna 'geometry'.

        Entrada:
        - schema (str): Esquema en el que se crearán los índices.

        Salida:
        - (None) Índices creados/asegurados para acelerar consultas espaciales.
        """
        logger.info(f"Optimizando índices en '{schema}'...")
        with self.engine.connect() as conn:
            # Buscar todas las tablas que tengan una columna de tipo geometría
            result = conn.execute(text(
                f"SELECT table_name FROM information_schema.columns WHERE table_schema = '{schema}' AND column_name = 'geometry'"
            ))
            # Crear índice GIST para acelerar filtros espaciales (ej. ST_Intersects)
            for row in result:
                table = row[0]
                try: # Crear índice espacial GIST si no existe
                    conn.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{table}_geom ON {schema}.{table} USING GIST (geometry);"))
                except: pass
        logger.info("✔ Índices creados.")

@click.command()
# Ingesta mínima
@click.option('--ingest-minimum', is_flag=True, help='FASE 1: Carga datos base.')
@click.option('--analyze-all', is_flag=True, help='FASE 2: Genera TODOS los productos.')
@click.option('--ingest-processed', is_flag=True, help='FASE 3: Carga productos a BD.')
@click.option('--srid', default=32719, help='SRID objetivo (default: 32719).')
@click.option('--index', is_flag=True, help='Crear índices espaciales.')
@click.option('--network-metrics', is_flag=True, help='Calcula métricas de red (incluido en analyze-all).')
# Flags individuales
@click.option('--ndvi', is_flag=True, help='Solo calcular NDVI.')
@click.option('--dem-derivatives', is_flag=True, help='Solo calcular Slope/Aspect.')
@click.option('--metrics', is_flag=True, help='Solo calcular métricas vectoriales.')
@click.option('--join-uso-suelo', is_flag=True, help='Solo cruzar uso suelo.')
def main(ingest_minimum, analyze_all, ingest_processed, srid, index, network_metrics, ndvi, dem_derivatives, metrics, join_uso_suelo):
    """CLI del pipeline maestro de procesamiento geoespacial.

        Descripción:
        - Ejecuta fases de ingesta, análisis y carga final a PostGIS.
            Si no se especifican flags, corre el pipeline completo (Fase 1+2+3).

        Entrada:
        - ingest_minimum (bool): Ejecuta FASE 1 (carga de datos base).
        - analyze_all (bool): Ejecuta FASE 2 (todos los productos analíticos).
        - ingest_processed (bool): Ejecuta FASE 3 (carga de derivados a BD).
        - srid (int): EPSG objetivo para reproyección y análisis.
        - index (bool): Crea índices espaciales al finalizar.
        - network_metrics (bool): Calcula métricas de red (también en analyze_all).
        - ndvi (bool): Solo genera NDVI.
        - dem_derivatives (bool): Solo genera slope/aspect.
        - metrics (bool): Solo métricas vectoriales (incluye join censo).
        - join_uso_suelo (bool): Solo overlay de uso de suelo.

        Salida:
        - (None) Ejecuta el pipeline y registra el progreso por consola.
        """
    logger.info("="*50)
    logger.info("INICIANDO PROCESAMIENTO DE DATOS")
    logger.info("="*50)

    processor = DataProcessor()
    
    # Comportamiento por defecto: Si no hay argumentos, EJECUTAR TODO (Incluye Redes)
    # Activar pipeline completo si el usuario no especificó ninguna opción
    if not any([ingest_minimum, analyze_all, ingest_processed, ndvi, dem_derivatives, metrics, join_uso_suelo, network_metrics]):
        logger.info(" Modo por defecto: Ejecutando Pipeline Completo (Fase 1 + 2 + 3)")
        ingest_minimum = True
        analyze_all = True
        ingest_processed = True
        index = True
    # Orquestación de la FASE 1
    if ingest_minimum:
        # FASE 1: configuración BD + ingesta base (vectores/CSV/OSM)
        processor.setup_database()
        logger.info("--- FASE 1: INGESTA BASE ---")
        processor.load_vector('comuna_boundaries_oficial.geojson', 'comuna_boundaries_oficial', srid=srid)
        processor.load_vector('manzanas_censales.geojson', 'manzanas_censales', srid=srid)
        processor.load_vector('uso_suelo_minvu.geojson', 'uso_suelo_minvu', srid=srid)
        processor.load_vector('osm_amenities.geojson', 'osm_amenities', srid=srid)
        processor.load_vector('osm_buildings.geojson', 'osm_buildings', srid=srid)
        processor.load_osm_network('osm_network.graphml', 'osm_network', srid=srid)
        processor.load_csv_microdatos()
        processor.catalog_rasters()
    # Orquestación de la FASE 2 (Análisis)
    if analyze_all or ndvi:
        processor.generate_ndvi()
    
    if analyze_all or dem_derivatives:
        processor.generate_dem_derivatives()
        
    if analyze_all or metrics:
        processor.join_censo(srid=srid)
        processor.generate_metrics(srid=srid)
    
    if analyze_all or join_uso_suelo:
        processor.join_uso_suelo(srid=srid)
        
    # INTEGRACIÓN AUTOMÁTICA: Se ejecuta si es analyze_all o si se pide explícitamente
    if analyze_all or network_metrics:
        processor.generate_network_metrics(srid=srid)

    # Orquestación de la FASE 3 (Ingesta de resultados)
    if ingest_processed:
        logger.info("--- FASE 3: INGESTA PROCESADOS ---")
        processor.ingest_processed()
    # Optimización final de la Base de Datos
    if index:
        # Crear índices espaciales en ambos esquemas para mejorar performance
        processor.create_spatial_indices('raw_data')
        processor.create_spatial_indices('processed_data')
    # Fin del procesamiento de datos
    logger.info("\n>>> Procesamiento finalizado exitosamente.")

if __name__ == '__main__':
    main()