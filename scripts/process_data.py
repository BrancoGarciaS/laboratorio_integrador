#!/usr/bin/env python3
"""
Script MAESTRO de procesamiento e ingesta de datos a PostGIS.
Fusiona la ingesta de fuentes base con la generación de productos analíticos.
Incluye análisis de redes (Betweenness/Densidad) para criterio de excelencia.
"""

import os
import sys
import click
import logging
import numpy as np
import geopandas as gpd
import pandas as pd
import rasterio
import rasterio.mask
import osmnx as ox
import networkx as nx
from shapely.geometry import Point, LineString
from shapely import wkt
from pathlib import Path
from sqlalchemy import create_engine, text
from geoalchemy2 import Geometry
from dotenv import load_dotenv
from rasterio.warp import calculate_default_transform, reproject, Resampling

# Cargar variables de entorno
load_dotenv()

# Configuración de Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Rutas dinámicas
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_RAW = BASE_DIR / 'data' / 'raw'
DATA_PROCESSED = BASE_DIR / 'data' / 'processed'

# Asegurar que existe processed
DATA_PROCESSED.mkdir(parents=True, exist_ok=True)

class DataProcessor:
    def __init__(self, db_url=None):
        self.db_url = db_url or self._get_db_url()
        self.engine = create_engine(self.db_url)

    def _get_db_url(self):
        return (
            f"postgresql://{os.getenv('POSTGRES_USER')}:"
            f"{os.getenv('POSTGRES_PASSWORD')}@"
            f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
            f"{os.getenv('POSTGRES_PORT', '5432')}/"
            f"{os.getenv('POSTGRES_DB')}"
        )

    def setup_database(self, schemas=['raw_data', 'processed_data']):
        """Crea extensión PostGIS y esquemas necesarios."""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
                for schema in schemas:
                    conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema};"))
                conn.commit()
            logger.info(f"✅ Base de datos configurada (Esquemas: {schemas})")
        except Exception as e:
            logger.error(f"Error conectando a BD: {e}")
            sys.exit(1)

    def _clean_columns(self, gdf):
        """Limpia columnas problemáticas para PostGIS."""
        gdf.columns = [c.lower() for c in gdf.columns]
        gdf = gdf.loc[:, ~gdf.columns.duplicated()]
        # Eliminar columnas técnicas de shapefile que ensucian o causan conflicto
        cols_to_drop = [c for c in gdf.columns if c.startswith('shape_') or c in ['len', 'area', 'objectid', 'st_area', 'st_length']]
        if cols_to_drop:
            gdf.drop(columns=cols_to_drop, inplace=True, errors='ignore')
        return gdf

    # --- MÉTODOS DE INGESTA BASE (FASE 1) ---

    def load_vector(self, filename, table_name, schema='raw_data', srid=32719):
        """Carga vector a PostGIS y guarda copia procesada en disco."""
        file_path = DATA_RAW / filename
        if not file_path.exists():
            logger.warning(f"⚠️ Archivo no encontrado: {filename} (Saltando)")
            return

        try:
            logger.info(f"Procesando {filename}...")
            gdf = gpd.read_file(file_path)
            
            if gdf.crs is None:
                gdf.set_crs(epsg=4326, inplace=True)
            
            if gdf.crs.to_epsg() != srid:
                logger.info(f"  -> Reproyectando a EPSG:{srid}")
                gdf = gdf.to_crs(epsg=srid)

            gdf = self._clean_columns(gdf)

            processed_path = DATA_PROCESSED / filename
            driver = 'GeoJSON' if filename.endswith('.geojson') else 'ESRI Shapefile'
            gdf.to_file(processed_path, driver=driver)
            logger.info(f"  💾 Guardado en processed: {processed_path.name}")

            gdf.to_postgis(
                name=table_name,
                con=self.engine,
                schema=schema,
                if_exists='replace',
                index=False,
                dtype={'geometry': Geometry(geometry_type='GEOMETRY', srid=srid)}
            )
            logger.info(f"  ✅ Cargado en BD: '{schema}.{table_name}'")
        except Exception as e:
            logger.error(f"❌ Error procesando {table_name}: {e}")

    def load_osm_network(self, filename, table_name, schema='raw_data', srid=32719):
        file_path = DATA_RAW / filename
        if not file_path.exists():
            return

        try:
            logger.info(f"Procesando red vial {filename}...")
            G = ox.load_graphml(file_path)
            gdf_nodes, gdf_edges = ox.graph_to_gdfs(G)
            gdf = gdf_edges.reset_index()

            if srid != 4326:
                gdf = gdf.to_crs(epsg=srid)
            
            # Limpieza de listas
            for col in gdf.columns:
                if gdf[col].apply(lambda x: isinstance(x, list)).any():
                    gdf[col] = gdf[col].astype(str)
            
            gdf = self._clean_columns(gdf)

            processed_path = DATA_PROCESSED / "osm_network.gpkg"
            gdf.to_file(processed_path, driver="GPKG", layer="edges")
            logger.info(f"  💾 Guardado en processed: osm_network.gpkg")

            gdf.to_postgis(
                name=table_name,
                con=self.engine,
                schema=schema,
                if_exists='replace',
                index=False,
                dtype={'geometry': Geometry(geometry_type='LINESTRING', srid=srid)}
            )
            logger.info(f"  ✅ Cargado en BD: '{schema}.{table_name}'")
        except Exception as e:
            logger.error(f"❌ Error procesando red vial: {e}")

    def load_csv_microdatos(self, schema='raw_data'):
        # Buscar recursivamente porque la descarga del INE crea subcarpetas
        csv_files = list(DATA_RAW.rglob("Censo2017_Manzanas.csv"))
        if not csv_files:
            logger.warning("⚠️ No se encontró Censo2017_Manzanas.csv en data/raw (revisar subcarpetas).")
            return

        csv_path = csv_files[0]
        table_name = 'censo_microdatos'
        
        try:
            logger.info(f"Procesando microdatos desde {csv_path.relative_to(DATA_RAW)}...")
            df = pd.read_csv(csv_path, sep=';', low_memory=False)
            df.columns = [c.lower() for c in df.columns]
            
            processed_path = DATA_PROCESSED / "censo_microdatos.csv"
            df.to_csv(processed_path, index=False, sep=';')
            logger.info(f"  💾 Guardado en processed: censo_microdatos.csv")

            df.to_sql(table_name, self.engine, schema=schema, if_exists='replace', index=False)
            logger.info(f"  ✅ Cargado en BD: '{schema}.{table_name}'")
        except Exception as e:
            logger.error(f"❌ Error procesando microdatos: {e}")

    def catalog_rasters(self, schema='raw_data'):
        """Cataloga rasters de RAW en la BD."""
        table_name = 'raster_catalog'
        raster_files = list(DATA_RAW.glob("*.tif")) + list(DATA_RAW.glob("*.hgt"))
        
        if not raster_files:
            return

        records = []
        for rbox in raster_files:
            try:
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

        if records:
            df = pd.DataFrame(records)
            df.to_sql(table_name, self.engine, schema=schema, if_exists='replace', index=False)
            with self.engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE {schema}.{table_name} ADD PRIMARY KEY (filename);"))
                conn.commit()
            logger.info(f"✅ Catálogo de rasters RAW actualizado ({len(df)} archivos).")

    # --- MÉTODOS DE ANÁLISIS Y DERIVADOS (FASE 2) ---

    def generate_ndvi(self):
        """Genera NDVI a partir de bandas Sentinel-2."""
        logger.info("Calculando NDVI...")
        b4_path = DATA_RAW / "sentinel2_B04.tif"
        b8_path = DATA_RAW / "sentinel2_B08.tif"
        out_path = DATA_PROCESSED / "sentinel2_ndvi.tif"

        if not b4_path.exists() or not b8_path.exists():
            logger.warning("⚠️ Faltan bandas Sentinel-2 para NDVI.")
            return

        try:
            with rasterio.open(b4_path) as r4, rasterio.open(b8_path) as r8:
                red = r4.read(1).astype('float32')
                nir = r8.read(1).astype('float32')
                
                ndvi = (nir - red) / (nir + red + 1e-6)
                
                meta = r4.meta.copy()
                meta.update(dtype='float32', nodata=-9999, compress='lzw')
                
                ndvi = np.where(np.isfinite(ndvi), ndvi, -9999).astype('float32')
                
                with rasterio.open(out_path, 'w', **meta) as dst:
                    dst.write(ndvi, 1)
            logger.info(f"  ✨ NDVI generado: {out_path.name}")
        except Exception as e:
            logger.error(f"Error calculando NDVI: {e}")

    def generate_dem_derivatives(self):
        """Genera pendiente (Slope) y aspecto (Aspect) del DEM."""
        logger.info("Calculando derivados del DEM...")
        dem_path = DATA_RAW / "srtm_dem_32719.tif"
        
        if not dem_path.exists():
            dem_path = DATA_RAW / "srtm_dem.tif"
        
        if not dem_path.exists():
            logger.warning("⚠️ No se encontró DEM para calcular derivados.")
            return

        try:
            with rasterio.open(dem_path) as src:
                dem = src.read(1).astype('float32')
                px, py = src.transform.a, abs(src.transform.e)
                dzdy, dzdx = np.gradient(dem, py, px)
                
                slope = np.degrees(np.arctan(np.sqrt(dzdx**2 + dzdy**2)))
                aspect = np.degrees(np.arctan2(-dzdx, dzdy))
                aspect = np.where(aspect < 0, aspect + 360, aspect)

                meta = src.meta.copy()
                meta.update(dtype='float32', nodata=-9999, compress='lzw')

                with rasterio.open(DATA_PROCESSED / 'slope.tif', 'w', **meta) as dst:
                    dst.write(slope.astype('float32'), 1)
                
                with rasterio.open(DATA_PROCESSED / 'aspect.tif', 'w', **meta) as dst:
                    dst.write(aspect.astype('float32'), 1)
                    
            logger.info("  ✨ Derivados DEM generados (slope.tif, aspect.tif)")
        except Exception as e:
            logger.error(f"Error derivados DEM: {e}")

    def join_censo(self, srid=32719):
        """Cruza Manzanas (Geo) con Microdatos (CSV)."""
        logger.info("Ejecutando Join Censo...")
        geo_path = DATA_PROCESSED / "manzanas_censales.geojson"
        csv_path = DATA_PROCESSED / "censo_microdatos.csv"
        out_path = DATA_PROCESSED / "manzanas_atributos.geojson"

        if not geo_path.exists() or not csv_path.exists():
            logger.warning("⚠️ Faltan archivos para Join Censo. Ejecute ingest-minimum primero.")
            return

        try:
            gdf = gpd.read_file(geo_path)
            df = pd.read_csv(csv_path, sep=';', low_memory=False)
            
            # Normalización de columnas
            gdf.columns = [c.lower() for c in gdf.columns]
            df.columns = [c.lower() for c in df.columns]
            
            key_geo = next((c for c in gdf.columns if 'manzent' in c), None)
            key_csv = next((c for c in df.columns if 'manzent' in c), None)
            
            if not key_geo or not key_csv:
                logger.error(f"No se encontró columna 'manzent' (Geo: {key_geo}, CSV: {key_csv})")
                return

            logger.info(f"Uniendo por claves: Geo='{key_geo}' ↔ CSV='{key_csv}'")

            gdf[key_geo] = gdf[key_geo].astype(str).str.strip()
            df[key_csv] = df[key_csv].astype(str).str.strip()

            merged = gdf.merge(df, left_on=key_geo, right_on=key_csv, how='left')
            merged = self._clean_columns(merged)
            
            merged.to_file(out_path, driver='GeoJSON')
            logger.info(f"  ✨ Join Censo completado: {out_path.name}")
        except Exception as e:
            logger.error(f"Error Join Censo: {e}")

    def join_uso_suelo(self, srid=32719):
        """Cruza Manzanas con Uso de Suelo (Intersección Espacial)."""
        logger.info("Ejecutando Join Uso de Suelo (Overlay)...")
        manzanas_path = DATA_PROCESSED / "manzanas_censales.geojson"
        usos_path = DATA_RAW / "uso_suelo_minvu.geojson"
        out_path = DATA_PROCESSED / "manzanas_uso_suelo.geojson"

        if not manzanas_path.exists() or not usos_path.exists():
            logger.warning("⚠️ Faltan archivos para Join Uso Suelo.")
            return

        try:
            gdf_m = gpd.read_file(manzanas_path).to_crs(epsg=srid)
            gdf_u = gpd.read_file(usos_path).to_crs(epsg=srid)
            
            join = gpd.sjoin(gdf_m, gdf_u, how='left', predicate='intersects')
            join = self._clean_columns(join)
            
            join.to_file(out_path, driver='GeoJSON')
            logger.info(f"  ✨ Join Uso Suelo completado: {out_path.name}")
        except Exception as e:
            logger.error(f"Error Join Uso Suelo: {e}")

    def generate_metrics(self, srid=32719):
        """Calcula métricas resumen por manzana (Edificios/Amenidades)."""
        logger.info("Calculando métricas básicas por manzana...")
        manzanas_path = DATA_PROCESSED / "manzanas_censales.geojson"
        build_path = DATA_PROCESSED / "osm_buildings.geojson"
        amen_path = DATA_PROCESSED / "osm_amenities.geojson"
        out_path = DATA_PROCESSED / "metrics_manzanas.csv"

        if not manzanas_path.exists(): return

        try:
            gdf_m = gpd.read_file(manzanas_path).to_crs(epsg=srid)
            
            # 1. Área
            gdf_m['area_m2'] = gdf_m.geometry.area
            
            # 2. Conteo Edificios
            if build_path.exists():
                gdf_b = gpd.read_file(build_path).to_crs(epsg=srid)
                join_b = gpd.sjoin(gdf_b, gdf_m, predicate='intersects')
                counts_b = join_b.groupby('index_right').size()
                gdf_m['num_edificios'] = counts_b
                gdf_m['num_edificios'] = gdf_m['num_edificios'].fillna(0)

            # 3. Conteo Amenidades
            if amen_path.exists():
                gdf_a = gpd.read_file(amen_path).to_crs(epsg=srid)
                join_a = gpd.sjoin(gdf_a, gdf_m, predicate='intersects')
                counts_a = join_a.groupby('index_right').size()
                gdf_m['num_amenidades'] = counts_a
                gdf_m['num_amenidades'] = gdf_m['num_amenidades'].fillna(0)

            df_metrics = pd.DataFrame(gdf_m.drop(columns='geometry'))
            df_metrics.to_csv(out_path, index=False)
            logger.info(f"  ✨ Métricas generadas: {out_path.name}")

        except Exception as e:
            logger.error(f"Error generando métricas: {e}")

    def generate_network_metrics(self, srid=32719):
        """
        Calcula métricas avanzadas de red vial (Criterio Excelencia).
        Genera: metrics_network.csv y network_nodes_metrics.geojson
        """
        logger.info("📈 Calculando métricas avanzadas de red vial...")
        
        graph_path = DATA_RAW / 'osm_network.graphml'
        manzanas_path = DATA_PROCESSED / 'manzanas_censales.geojson'
        
        nodes_out = DATA_PROCESSED / 'network_nodes_metrics.geojson'
        # Renombrado a metrics_network.csv para que ingest_processed lo detecte automáticamente
        csv_out = DATA_PROCESSED / 'metrics_network.csv'

        if not graph_path.exists() or not manzanas_path.exists():
            logger.warning("⚠️ Faltan archivos de red o manzanas.")
            return

        try:
            logger.info("  Cargando grafo y geometrías...")
            G = ox.load_graphml(graph_path)
            gdf_m = gpd.read_file(manzanas_path).to_crs(epsg=srid)
            
            manzana_key = next((c for c in gdf_m.columns if 'manzent' in c), None) or gdf_m.columns[0]
            
            logger.info("  Calculando centralidad de nodos...")
            degree_c = nx.degree_centrality(G)
            
            if len(G) > 5000:
                import random
                sample_nodes = random.sample(list(G.nodes()), 1000)
                betw_c = nx.betweenness_centrality(G, k=len(sample_nodes))
            else:
                betw_c = nx.betweenness_centrality(G)

            node_records = []
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
            
            gdf_nodes = gpd.GeoDataFrame(node_records, crs="EPSG:4326").to_crs(epsg=srid)
            gdf_nodes.to_file(nodes_out, driver='GeoJSON')
            logger.info(f"  💾 Nodos guardados: {nodes_out.name}")

            logger.info("  Cruzando y agregando por manzana...")
            join_nodes = gpd.sjoin(gdf_nodes, gdf_m, predicate='intersects')
            stats_nodes = join_nodes.groupby(manzana_key).agg({
                'degree': 'mean',
                'betweenness': 'mean',
                'node_id': 'count'
            }).rename(columns={'node_id': 'node_count', 'degree': 'degree_mean', 'betweenness': 'betweenness_mean'})

            gdf_nodes_tmp, gdf_edges = ox.graph_to_gdfs(G)
            gdf_edges = gdf_edges.to_crs(epsg=srid)
            
            inter = gpd.overlay(gdf_edges, gdf_m, how='intersection')
            inter['length_m'] = inter.geometry.length
            stats_edges = inter.groupby(manzana_key)['length_m'].sum().to_frame(name='road_length_m')
            
            df_final = pd.DataFrame({manzana_key: gdf_m[manzana_key]})
            df_final = df_final.merge(stats_nodes, on=manzana_key, how='left').fillna(0)
            df_final = df_final.merge(stats_edges, on=manzana_key, how='left').fillna(0)
            
            areas_km2 = gdf_m.set_index(manzana_key).geometry.area / 1e6
            df_final['road_density_km2'] = df_final.apply(
                lambda row: row['road_length_m'] / areas_km2.get(row[manzana_key], 1), axis=1
            )

            df_final.to_csv(csv_out, index=False)
            logger.info(f"  ✨ Métricas de red generadas: {csv_out.name}")

        except Exception as e:
            logger.error(f"❌ Error en métricas de red: {e}")

    def ingest_processed(self, schema='processed_data'):
        """Carga los productos derivados a PostGIS."""
        logger.info(f"Ingestando datos procesados al esquema '{schema}'...")
        
        # 1. Vectores procesados
        # Agregamos network_nodes_metrics.geojson a la lista
        vectors = ['manzanas_atributos.geojson', 'manzanas_uso_suelo.geojson', 'network_nodes_metrics.geojson']
        for fname in vectors:
            fpath = DATA_PROCESSED / fname
            if fpath.exists():
                try:
                    gdf = gpd.read_file(fpath)
                    gdf = self._clean_columns(gdf)
                    table_name = fpath.stem
                    gdf.to_postgis(table_name, self.engine, schema=schema, if_exists='replace', index=False)
                    logger.info(f"  ✅ Tabla cargada: {table_name}")
                except Exception as e:
                    logger.error(f"Error cargando {fname}: {e}")

        # 2. Tablas procesadas
        # Busca metrics_*.csv (esto detectará metrics_manzanas.csv y metrics_network.csv)
        for f in DATA_PROCESSED.glob("metrics_*.csv"):
            try:
                df = pd.read_csv(f)
                df.columns = [c.lower() for c in df.columns]
                df.to_sql(f.stem, self.engine, schema=schema, if_exists='replace', index=False)
                logger.info(f"  ✅ Tabla cargada: {f.stem}")
            except Exception as e:
                logger.error(f"Error cargando {f.name}: {e}")

        # 3. Catalogar nuevos Rasters
        processed_rasters = list(DATA_PROCESSED.glob("*.tif"))
        if processed_rasters:
            records = []
            for rbox in processed_rasters:
                try:
                    with rasterio.open(rbox) as src:
                        records.append({
                            'filename': rbox.name,
                            'location': str(rbox.relative_to(BASE_DIR)),
                            'crs': str(src.crs),
                            'width': src.width,
                            'height': src.height,
                            'bands': src.count,
                            'source_group': 'derived'
                        })
                except: pass
            
            if records:
                df = pd.DataFrame(records)
                try:
                    df.to_sql('raster_catalog', self.engine, schema='raw_data', if_exists='append', index=False)
                    logger.info(f"  ✅ Catálogo actualizado.")
                except: pass

    def create_spatial_indices(self, schema='raw_data'):
        logger.info(f"Optimizando índices en '{schema}'...")
        with self.engine.connect() as conn:
            result = conn.execute(text(
                f"SELECT table_name FROM information_schema.columns WHERE table_schema = '{schema}' AND column_name = 'geometry'"
            ))
            for row in result:
                table = row[0]
                try:
                    conn.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{table}_geom ON {schema}.{table} USING GIST (geometry);"))
                except: pass
        logger.info("✅ Índices creados.")

@click.command()
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
    """
    Pipeline Maestro de Procesamiento Geoespacial.
    """
    logger.info("="*50)
    logger.info("INICIANDO PROCESAMIENTO DE DATOS")
    logger.info("="*50)

    processor = DataProcessor()
    
    # Comportamiento por defecto: Si no hay argumentos, EJECUTAR TODO (Incluye Redes)
    if not any([ingest_minimum, analyze_all, ingest_processed, ndvi, dem_derivatives, metrics, join_uso_suelo, network_metrics]):
        logger.info("ℹ️ Modo por defecto: Ejecutando Pipeline Completo (Fase 1 + 2 + 3)")
        ingest_minimum = True
        analyze_all = True
        ingest_processed = True
        index = True

    if ingest_minimum:
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

    if ingest_processed:
        logger.info("--- FASE 3: INGESTA PROCESADOS ---")
        processor.ingest_processed()

    if index:
        processor.create_spatial_indices('raw_data')
        processor.create_spatial_indices('processed_data')

    logger.info("\n>>> Procesamiento finalizado exitosamente.")

if __name__ == '__main__':
    main()