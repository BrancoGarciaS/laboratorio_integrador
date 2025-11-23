#!/usr/bin/env python3
"""Script para procesar y preparar datos para análisis.

Implementa una CLI simplificada que respeta el README del profesor:
  python scripts/process_data.py --load-osm --srid 32719

Si no se entregan rutas explicitas, intenta usar rutas por defecto en data/raw/.

Flags actuales:
  --load-osm              Ingesta de edificios y amenidades OSM (auto-detección)
  --buildings PATH        Ruta alternativa a edificios OSM
  --amenities PATH        Ruta alternativa a amenidades OSM
  --network PATH          Ingesta opcional de red vial (graphml o geojson) si disponible
  --schema NAME           Esquema destino (default raw_data)
  --srid EPSG            Reproyecta capas antes de cargar
  --index                 Crea índice espacial GIST tras ingesta

Placeholders futuros (no implementan lógica todavía):
  --dem-derivatives       Generar slope/aspect
  --ndvi                  Calcular NDVI Sentinel-2
  --join-censo            Enlazar microdatos con manzanas
  --join-uso-suelo        Overlay uso de suelo con manzanas
  --metrics               Crear métricas resumen
    --censo-key COL         Forzar nombre de columna clave para join censo
    --censo-geojson PATH    Ruta alternativa a manzanas censales
    --censo-csv PATH        Ruta alternativa al CSV base del censo
"""

import argparse
import logging
import os
from shapely.geometry import Point, LineString
from shapely import wkt
from pathlib import Path
import numpy as np
import geopandas as gpd
import pandas as pd
import rasterio
from rasterio.transform import Affine
from rasterio.warp import calculate_default_transform, reproject, Resampling
from sqlalchemy import create_engine, text
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
            # Crear esquema si no existe
            with self.engine.begin() as conn:
                conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS {schema}'))
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

    def create_spatial_index(self, table_name, schema='raw_data'):
        """Crea índice espacial si no existe."""
        try:
            with self.engine.begin() as conn:
                idx_name = f"idx_{table_name}_geom"
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON {schema}.{table_name} USING GIST(geometry)"
                ))
            logger.info(f"Índice espacial {idx_name} verificado/creado")
        except Exception as e:
            logger.error(f"Error creando índice espacial: {e}")

#############################################
# Funciones DEM y derivados (debían declararse antes de main)
#############################################

def generate_dem_derivatives():
    """Genera srtm_dem.tif, srtm_dem_32719.tif y slope/aspect en data/processed."""
    raw_dir = Path('data/raw')
    processed_dir = Path('data/processed')
    processed_dir.mkdir(parents=True, exist_ok=True)

    hgt_files = list(raw_dir.glob('*.hgt'))
    if not hgt_files:
        logger.warning('No se encontró archivo .hgt en data/raw; abortando derivados DEM.')
        return
    hgt_path = hgt_files[0]
    logger.info(f'Usando tile SRTM: {hgt_path.name}')

    dem4326_path = raw_dir / 'srtm_dem.tif'
    dem32719_path = raw_dir / 'srtm_dem_32719.tif'

    if not dem4326_path.exists():
        create_geotiff_from_hgt(hgt_path, dem4326_path)
    else:
        logger.info('srtm_dem.tif ya existe, se reutiliza.')

    boundary_path = raw_dir / 'comuna_boundaries_oficial.geojson'
    if boundary_path.exists():
        clip_dem_to_boundary(dem4326_path, boundary_path, dem4326_path)
    else:
        logger.info('No se encontró comuna_boundaries_oficial.geojson, se mantiene DEM completo.')

    if not dem32719_path.exists():
        reproject_dem(dem4326_path, dem32719_path, 32719)
    else:
        logger.info('srtm_dem_32719.tif ya existe, se reutiliza.')

    slope_path = processed_dir / 'slope.tif'
    aspect_path = processed_dir / 'aspect.tif'
    if slope_path.exists() and aspect_path.exists():
        logger.info('Slope y Aspect ya existen en processed, omitiendo cálculo.')
        return

    with rasterio.open(dem32719_path) as src:
        dem = src.read(1).astype('float32')
        nodata = src.nodata
        dem_mask = dem == nodata if nodata is not None else np.isnan(dem)
        dem = np.where(dem_mask, np.nan, dem)
        pixel_x = src.transform.a
        pixel_y = abs(src.transform.e)
        dzdy, dzdx = np.gradient(dem, pixel_y, pixel_x)
        slope = np.degrees(np.arctan(np.sqrt(dzdx**2 + dzdy**2)))
        aspect = np.degrees(np.arctan2(-dzdx, dzdy))
        aspect = np.where(np.isnan(aspect), np.nan, aspect)
        aspect[aspect < 0] += 360
        nodata_out = -9999 if nodata is None else nodata
        slope_out = np.where(np.isnan(slope), nodata_out, slope).astype('float32')
        aspect_out = np.where(np.isnan(aspect), nodata_out, aspect).astype('float32')
        meta = src.meta.copy()
        meta.update(dtype='float32', nodata=nodata_out, compress='lzw')
        for arr, out_path in [(slope_out, slope_path), (aspect_out, aspect_path)]:
            with rasterio.open(out_path, 'w', **meta) as dst:
                dst.write(arr, 1)
            logger.info(f'Escrito {out_path}')
    logger.info('Derivados DEM (slope/aspect) generados en data/processed/')


def create_geotiff_from_hgt(hgt_path: Path, out_path: Path):
    logger.info('Creando GeoTIFF desde HGT...')
    file_size = hgt_path.stat().st_size
    samples = int(np.sqrt(file_size / 2))
    if samples not in (1201, 3601):
        logger.warning(f'Tamaño inesperado para HGT: {samples}x{samples}')
    data = np.fromfile(hgt_path, np.dtype('>i2')).reshape((samples, samples))
    name = hgt_path.stem
    lat_sign = -1 if name[0] == 'S' else 1
    lat_deg = int(name[1:3]) * lat_sign
    lon_sign = -1 if name[3] == 'W' else 1
    lon_deg = int(name[4:7]) * lon_sign
    res = 1 / (samples - 1)
    top_lat = lat_deg + 1
    transform = Affine(res, 0, lon_deg, 0, -res, top_lat)
    profile = {
        'driver': 'GTiff', 'height': samples, 'width': samples, 'count': 1,
        'dtype': 'int16', 'crs': 'EPSG:4326', 'transform': transform,
        'nodata': -32768, 'compress': 'lzw'
    }
    with rasterio.open(out_path, 'w', **profile) as dst:
        dst.write(data, 1)
    logger.info(f'Escrito {out_path}')


def clip_dem_to_boundary(dem_path: Path, boundary_path: Path, out_path: Path):
    try:
        import rasterio.mask
        boundary = gpd.read_file(boundary_path).to_crs('EPSG:4326')
        geoms = [g.__geo_interface__ for g in boundary.geometry]
        with rasterio.open(dem_path) as src:
            out_image, out_transform = rasterio.mask.mask(src, geoms, crop=True, nodata=src.nodata)
            out_meta = src.meta.copy()
            out_meta.update({'height': out_image.shape[1], 'width': out_image.shape[2], 'transform': out_transform})
        with rasterio.open(dem_path, 'w', **out_meta) as dst:
            dst.write(out_image)
        logger.info('DEM recortado al límite de la comuna.')
    except Exception as e:
        logger.warning(f'No se pudo recortar DEM: {e}')


def reproject_dem(src_path: Path, dst_path: Path, epsg: int):
    with rasterio.open(src_path) as src:
        transform, width, height = calculate_default_transform(src.crs, f'EPSG:{epsg}', src.width, src.height, *src.bounds)
        meta = src.meta.copy()
        meta.update({'crs': f'EPSG:{epsg}', 'transform': transform, 'width': width, 'height': height})
        with rasterio.open(dst_path, 'w', **meta) as dst:
            reproject(
                source=rasterio.band(src, 1), destination=rasterio.band(dst, 1),
                src_transform=src.transform, src_crs=src.crs,
                dst_transform=transform, dst_crs=f'EPSG:{epsg}', resampling=Resampling.bilinear
            )
    logger.info(f'DEM reproyectado escrito en {dst_path}')


def parse_args():
    p = argparse.ArgumentParser(description="Pipeline de procesamiento geoespacial")
    p.add_argument('--load-osm', action='store_true', help='Ingestar capas OSM (buildings, amenities)')
    p.add_argument('--buildings', type=str, help='Ruta a edificios OSM (GeoJSON)')
    p.add_argument('--amenities', type=str, help='Ruta a amenidades OSM (GeoJSON)')
    p.add_argument('--network', type=str, help='Ruta a red vial (graphml o geojson)')
    p.add_argument('--schema', type=str, default='raw_data', help='Esquema destino PostGIS')
    p.add_argument('--srid', type=int, help='EPSG destino para reproyección')
    p.add_argument('--index', action='store_true', help='Crear índices espaciales')
    # Placeholders futuros
    p.add_argument('--dem-derivatives', action='store_true', help='Generar slope/aspect del DEM')
    p.add_argument('--ndvi', action='store_true', help='Calcular NDVI Sentinel-2 (requiere bandas B04/B08)')
    p.add_argument('--join-censo', action='store_true', help='Join microdatos INE con manzanas censales')
    p.add_argument('--join-uso-suelo', action='store_true', help='Overlay uso_suelo_minvu con manzanas')
    p.add_argument('--metrics', action='store_true', help='Crear metrics_manzanas.csv (conteos + básicos)')
    p.add_argument('--unify-uso-suelo', action='store_true', help='Unificar shapefiles PRC/PRMS/LU en un solo GeoJSON estándar')
    p.add_argument('--ingest-processed', action='store_true', help='Cargar archivos de data/processed a PostGIS (schema processed_data)')
    p.add_argument('--processed-schema', type=str, default='processed_data', help='Esquema destino para ingest processed')
    p.add_argument('--network-metrics', action='store_true', help='Generar métricas de red vial (centralidad y densidad por manzana)')
    p.add_argument('--ingest-minimum', action='store_true', help='Ingestar fuentes mínimas base (límites, manzanas, uso suelo, microdatos censo, rasters base al catálogo)')
    # Opciones extra censo
    p.add_argument('--censo-key', type=str, help='Columna clave explícita para join censo')
    p.add_argument('--censo-geojson', type=str, help='Ruta alternativa a manzanas_censales.geojson')
    p.add_argument('--censo-csv', type=str, help='Ruta alternativa al CSV de manzanas del censo')
    return p.parse_args()


def autodetect_file(default_path: Path):
    if default_path.exists():
        return str(default_path)
    return None


def ingest_osm(args, processor: DataProcessor):
    schema = args.schema
    srid = args.srid

    # Auto-detección si no se pasa ruta
    buildings_path = args.buildings or autodetect_file(Path('data/raw/osm_buildings.geojson'))
    amenities_path = args.amenities or autodetect_file(Path('data/raw/osm_amenities.geojson'))

    if not buildings_path and not amenities_path:
        logger.warning("No se hallaron archivos OSM buildings/amenities para ingesta")
        return

    if buildings_path:
        try:
            gdf_b = gpd.read_file(buildings_path)
            logger.info(f"Leídos edificios: {len(gdf_b)} features")
            if srid:
                gdf_b = gdf_b.to_crs(epsg=srid)
            if processor.load_to_postgis(gdf_b, 'osm_buildings', schema=schema) and args.index:
                processor.create_spatial_index('osm_buildings', schema)
        except Exception as e:
            logger.error(f"Error ingesta edificios: {e}")

    if amenities_path:
        try:
            gdf_a = gpd.read_file(amenities_path)
            logger.info(f"Leídas amenidades: {len(gdf_a)} features")
            if srid:
                gdf_a = gdf_a.to_crs(epsg=srid)
            if processor.load_to_postgis(gdf_a, 'osm_amenities', schema=schema) and args.index:
                processor.create_spatial_index('osm_amenities', schema)
        except Exception as e:
            logger.error(f"Error ingesta amenidades: {e}")

    # Red vial opcional (GraphML/GeoJSON)
    network_path = args.network or autodetect_file(Path('data/raw/osm_network.graphml'))
    if network_path:
        try:
            if network_path.lower().endswith('.geojson'):
                gdf_n = gpd.read_file(network_path)
                logger.info(f"Leída red vial (geojson): {len(gdf_n)} features")
                if srid:
                    gdf_n = gdf_n.to_crs(epsg=srid)
                if processor.load_to_postgis(gdf_n, 'osm_network', schema=schema) and args.index:
                    processor.create_spatial_index('osm_network', schema)
            elif network_path.lower().endswith('.graphml'):
                import networkx as nx
                G = nx.read_graphml(network_path)
                # Construir nodos GeoDataFrame
                node_records = []
                for n, data in G.nodes(data=True):
                    # OSMnx suele guardar x(lon), y(lat)
                    lon = data.get('x') or data.get('lon')
                    lat = data.get('y') or data.get('lat')
                    if lon is None or lat is None:
                        continue
                    geom = Point(float(lon), float(lat))
                    rec = {'node_id': n, **{k: v for k, v in data.items() if k not in ('x','y','lon','lat')}, 'geometry': geom}
                    node_records.append(rec)
                gdf_nodes = gpd.GeoDataFrame(node_records, geometry='geometry', crs='EPSG:4326')
                # Construir edges GeoDataFrame
                edge_records = []
                for u, v, data in G.edges(data=True):
                    geom_attr = data.get('geometry')
                    geom = None
                    if geom_attr is not None:
                        if hasattr(geom_attr, 'geom_type'):
                            geom = geom_attr  # ya es shapely
                        else:
                            # intentar parsear WKT
                            try:
                                geom = wkt.loads(geom_attr)
                            except Exception:
                                geom = None
                    if geom is None:
                        # Fallback line simple entre coordenadas de nodos
                        udata = G.nodes[u]
                        vdata = G.nodes[v]
                        lon_u = udata.get('x') or udata.get('lon')
                        lat_u = udata.get('y') or udata.get('lat')
                        lon_v = vdata.get('x') or vdata.get('lon')
                        lat_v = vdata.get('y') or vdata.get('lat')
                        if None in (lon_u, lat_u, lon_v, lat_v):
                            continue
                        geom = LineString([(float(lon_u), float(lat_u)), (float(lon_v), float(lat_v))])
                    rec = {
                        'u': u,
                        'v': v,
                        **{k: v for k, v in data.items() if k != 'geometry'},
                        'geometry': geom
                    }
                    edge_records.append(rec)
                gdf_edges = gpd.GeoDataFrame(edge_records, geometry='geometry', crs='EPSG:4326')
                if srid:
                    gdf_nodes = gdf_nodes.to_crs(epsg=srid)
                    gdf_edges = gdf_edges.to_crs(epsg=srid)
                logger.info(f"Red vial: {len(gdf_nodes)} nodos, {len(gdf_edges)} aristas")
                if processor.load_to_postgis(gdf_nodes, 'osm_network_nodes', schema=schema) and args.index:
                    processor.create_spatial_index('osm_network_nodes', schema)
                if processor.load_to_postgis(gdf_edges, 'osm_network_edges', schema=schema) and args.index:
                    processor.create_spatial_index('osm_network_edges', schema)
            else:
                logger.warning("Formato de red vial no soportado (use .graphml o .geojson)")
        except Exception as e:
            logger.error(f"Error ingesta red vial: {e}")

#############################################
# Ingesta de archivos procesados a PostGIS
#############################################

def ingest_processed_outputs(args, processor: DataProcessor):
    processed_dir = Path('data/processed')
    if not processed_dir.exists():
        logger.warning('Directorio data/processed no existe; omitiendo ingest processed.')
        return
    schema = args.processed_schema
    srid = args.srid
    # Crear esquema si no existe (para CSV también)
    try:
        with processor.engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS {schema}'))
    except Exception as e:
        logger.error(f'No se pudo crear/verificar esquema {schema}: {e}')
        return
    # GeoJSON primero
    geojson_files = list(processed_dir.glob('*.geojson'))
    for gj in geojson_files:
        try:
            gdf = gpd.read_file(gj)
            # Asegurar alias en minúsculas
            if 'MANZENT' in gdf.columns and 'manzent' not in gdf.columns:
                try:
                    gdf['manzent'] = gdf['MANZENT'].astype(str).str.strip()
                except Exception:
                    pass
            if gdf.empty:
                logger.info(f'{gj.name} vacío, se omite.')
                continue
            if srid and gdf.crs and gdf.crs.to_epsg() != srid:
                try:
                    gdf = gdf.to_crs(epsg=srid)
                except Exception:
                    pass
            table_name = gj.stem
            if processor.load_to_postgis(gdf, table_name, schema=schema):
                logger.info(f'Ingestado {table_name} en esquema {schema}')
                if args.index:
                    processor.create_spatial_index(table_name, schema)
        except Exception as e:
            logger.warning(f'No se pudo ingestar {gj.name}: {e}')
    # CSV sin geometría
    csv_files = [f for f in processed_dir.glob('*.csv')]
    for cf in csv_files:
        try:
            df = pd.read_csv(cf)
            if 'MANZENT' in df.columns and 'manzent' not in df.columns:
                try:
                    df['manzent'] = df['MANZENT'].astype(str).str.strip()
                except Exception:
                    pass
            table_name = cf.stem
            df.to_sql(table_name, processor.engine, schema=schema, if_exists='replace', index=False)
            logger.info(f'Ingestado {table_name} (CSV) en esquema {schema}')
        except Exception as e:
            logger.warning(f'No se pudo ingestar {cf.name}: {e}')
    # Catálogo de rasters: registrar metadatos de cada .tif en processed
    tif_files = list(processed_dir.glob('*.tif'))
    if tif_files:
        try:
            with processor.engine.begin() as conn:
                conn.execute(text(f"""
                    CREATE TABLE IF NOT EXISTS {schema}.raster_catalog (
                        id SERIAL PRIMARY KEY,
                        filename TEXT UNIQUE,
                        rel_path TEXT,
                        crs TEXT,
                        width INTEGER,
                        height INTEGER,
                        band_count INTEGER,
                        dtype TEXT,
                        nodata DOUBLE PRECISION,
                        transform TEXT,
                        minx DOUBLE PRECISION,
                        miny DOUBLE PRECISION,
                        maxx DOUBLE PRECISION,
                        maxy DOUBLE PRECISION,
                        created_at TIMESTAMPTZ DEFAULT now()
                    )
                """))
            for tif in tif_files:
                try:
                    with rasterio.open(tif) as ds:
                        b = ds.bounds
                        tr = ds.transform
                        transform_str = ' '.join(map(str, [tr.a, tr.b, tr.c, tr.d, tr.e, tr.f]))
                        params = {
                            'filename': tif.name,
                            'rel_path': str(tif.relative_to(processed_dir)),
                            'crs': ds.crs.to_string() if ds.crs else None,
                            'width': ds.width,
                            'height': ds.height,
                            'band_count': ds.count,
                            'dtype': ds.dtypes[0] if ds.count >= 1 else None,
                            'nodata': float(ds.nodata) if ds.nodata is not None else None,
                            'transform': transform_str,
                            'minx': b.left,
                            'miny': b.bottom,
                            'maxx': b.right,
                            'maxy': b.top
                        }
                    with processor.engine.begin() as conn:
                        exists = conn.execute(text(f"SELECT 1 FROM {schema}.raster_catalog WHERE filename=:filename"), {'filename': params['filename']}).fetchone()
                        if exists:
                            logger.info(f"Raster {params['filename']} ya catalogado, se omite.")
                        else:
                            conn.execute(text(f"""
                                INSERT INTO {schema}.raster_catalog (
                                    filename, rel_path, crs, width, height, band_count, dtype, nodata, transform,
                                    minx, miny, maxx, maxy
                                ) VALUES (
                                    :filename, :rel_path, :crs, :width, :height, :band_count, :dtype, :nodata, :transform,
                                    :minx, :miny, :maxx, :maxy
                                )
                            """), params)
                            logger.info(f"Catalogado raster {params['filename']}")
                except Exception as e:
                    logger.warning(f'No se pudo catalogar {tif.name}: {e}')
        except Exception as e:
            logger.error(f'Error creando catálogo raster: {e}')

#############################################
# Helper para asegurar alias manzent
#############################################

def ensure_lowercase_manzent(df):
    if 'MANZENT' in getattr(df, 'columns', []) and 'manzent' not in df.columns:
        try:
            df['manzent'] = df['MANZENT'].astype(str).str.strip()
        except Exception:
            pass
    return df


#############################################
# (Main se moverá al final para que todas las funciones existan antes de su ejecución)
#############################################

#############################################
# NDVI Sentinel-2
#############################################

def generate_ndvi(args):
    """Calcula NDVI a partir de bandas B04 (red) y B08 (nir).
    Patrones soportados de nombre de bandas (en data/raw):
      sentinel_B04.tif / sentinel_B08.tif
      sentinel2_B04.tif / sentinel2_B08.tif
      Cualquier archivo que termine en _B04.tif y _B08.tif (fallback genérico)
    Outputs:
      data/processed/sentinel2_ndvi.tif
      data/processed/sentinel2_ndvi_<SRID>.tif si se indica --srid
    """
    raw_dir = Path('data/raw')
    processed_dir = Path('data/processed')
    processed_dir.mkdir(exist_ok=True)
    # Normalizar nombres legacy -> estándar (sentinel2_*)
    legacy_b04 = raw_dir / 'sentinel_B04.tif'
    legacy_b08 = raw_dir / 'sentinel_B08.tif'
    std_b04 = raw_dir / 'sentinel2_B04.tif'
    std_b08 = raw_dir / 'sentinel2_B08.tif'
    import shutil
    try:
        if legacy_b04.exists() and not std_b04.exists():
            shutil.copy(legacy_b04, std_b04)
            logger.info('Copiado sentinel_B04.tif -> sentinel2_B04.tif')
        if legacy_b08.exists() and not std_b08.exists():
            shutil.copy(legacy_b08, std_b08)
            logger.info('Copiado sentinel_B08.tif -> sentinel2_B08.tif')
    except Exception as e:
        logger.warning(f'No se pudo copiar bandas legacy: {e}')
    # Intentos ordenados de detección
    candidates = [
        (raw_dir / 'sentinel_B04.tif', raw_dir / 'sentinel_B08.tif'),
        (raw_dir / 'sentinel2_B04.tif', raw_dir / 'sentinel2_B08.tif')
    ]
    # Fallback: cualquier *_B04.tif y *_B08.tif
    if not any(a.exists() and b.exists() for a, b in candidates):
        b04_generic = next((p for p in raw_dir.glob('*_B04.tif')), None)
        b08_generic = next((p for p in raw_dir.glob('*_B08.tif')), None)
        if b04_generic and b08_generic:
            candidates.append((b04_generic, b08_generic))
    # Seleccionar primer par existente
    pair = next(((a, b) for a, b in candidates if a.exists() and b.exists()), None)
    if pair is None:
        logger.warning('No se hallaron bandas B04/B08 (patrones sentinel*_B04/B08); omitiendo NDVI.')
        return
    b04, b08 = pair
    logger.info(f'Usando bandas: {b04.name}, {b08.name}')
    out_ndvi = processed_dir / 'sentinel2_ndvi.tif'
    if not out_ndvi.exists():
        with rasterio.open(b04) as r4, rasterio.open(b08) as r8:
            if r4.shape != r8.shape or r4.transform != r8.transform:
                logger.error('Las bandas B04 y B08 no alinean (dimensiones/transform).')
                return
            red = r4.read(1).astype('float32')
            nir = r8.read(1).astype('float32')
            ndvi = (nir - red) / (nir + red + 1e-6)
            meta = r4.meta.copy()
            meta.update(dtype='float32', nodata=-9999, compress='lzw')
            ndvi = np.where(np.isfinite(ndvi), ndvi, -9999).astype('float32')
            with rasterio.open(out_ndvi, 'w', **meta) as dst:
                dst.write(ndvi, 1)
        logger.info(f'Escrito {out_ndvi}')
        # Registrar en raster_catalog si existe
        try:
            user = os.getenv('POSTGRES_USER'); pwd = os.getenv('POSTGRES_PASSWORD')
            host = os.getenv('POSTGRES_HOST','localhost'); port = os.getenv('POSTGRES_PORT','5432')
            db = os.getenv('POSTGRES_DB')
            engine_local = create_engine(f'postgresql://{user}:{pwd}@{host}:{port}/{db}')
            with engine_local.begin() as conn:
                exists = conn.execute(text("SELECT to_regclass('raw_data.raster_catalog')")).scalar()
                if exists:
                    with rasterio.open(out_ndvi) as src:
                        meta_insert = {
                            'filename': out_ndvi.name,
                            'crs': str(src.crs),
                            'width': src.width,
                            'height': src.height,
                            'band_count': src.count,
                            'dtype': src.dtypes[0],
                            'transform': str(src.transform),
                            'bounds': str(src.bounds),
                            'nodata': str(src.nodata),
                            'source_group': 'derived'
                        }
                        conn.execute(text(
                            "INSERT INTO raw_data.raster_catalog (filename, crs, width, height, band_count, dtype, transform, bounds, nodata, source_group) VALUES (:filename,:crs,:width,:height,:band_count,:dtype,:transform,:bounds,:nodata,:source_group) ON CONFLICT (filename) DO NOTHING"
                        ), meta_insert)
                        logger.info('NDVI registrado en raster_catalog.')
        except Exception as e:
            logger.debug(f'No se pudo registrar NDVI en raster_catalog: {e}')
    else:
        logger.info('NDVI ya existe, reutilizando.')
    if getattr(args, 'srid', None):
        reproj_path = processed_dir / f'sentinel2_ndvi_{args.srid}.tif'
        if not reproj_path.exists():
            reproject_dem(out_ndvi, reproj_path, args.srid)
        else:
            logger.info('NDVI reproyectado ya existe, reutilizando.')

#############################################
# Join Censo con Manzanas
#############################################

def join_censo(args):
    """Une microdatos INE con geometrías de manzanas.
    Heurística: busca CSV principal Censo2017_Manzanas.csv y archivo Geografia_Manzanas.
    Detecta clave común por intersección de nombres de columnas.
    Salida: data/processed/manzanas_atributos.geojson
    """
    raw_dir = Path('data/raw')
    out_path = Path('data/processed/manzanas_atributos.geojson')
    out_path.parent.mkdir(exist_ok=True)
    if out_path.exists():
        logger.info('manzanas_atributos.geojson ya existe, se reutiliza.')
        return
    geojson_path = Path(args.censo_geojson) if args.censo_geojson else raw_dir / 'manzanas_censales.geojson'
    censo_base = Path(args.censo_csv) if args.censo_csv else raw_dir / 'Censo2017_ManzanaEntidad_CSV' / 'Censo2017_16R_ManzanaEntidad_CSV' / 'Censo2017_Manzanas.csv'
    geografia_dir = raw_dir / 'Censo2017_ManzanaEntidad_CSV' / 'Censo2017_16R_ManzanaEntidad_CSV' / 'Censo2017_Identificación_Geográfica'
    if not geojson_path.exists() or not censo_base.exists():
        logger.warning('Archivos de manzanas o microdatos faltan; omitiendo join censo.')
        return
    try:
        gdf = gpd.read_file(geojson_path)
        # El CSV del censo viene separado por ';'
        df_censo = pd.read_csv(censo_base, encoding='latin-1', sep=';')
    except Exception as e:
        logger.error(f'Error leyendo archivos censo: {e}')
        return
    # Sanitizar nombres de columnas (strip) en ambos DataFrames
    gdf.rename(columns=lambda c: c.strip(), inplace=True)
    df_censo.rename(columns=lambda c: c.strip(), inplace=True)
    # Normalizar nombres potenciales de clave a MANZENT si procede
    rename_map = {}
    if 'ID_MANZENT' in df_censo.columns and 'MANZENT' in gdf.columns and 'MANZENT' not in df_censo.columns:
        rename_map['ID_MANZENT'] = 'MANZENT'
    if 'MZ_ENT' in df_censo.columns and 'MANZENT' in gdf.columns and 'MANZENT' not in df_censo.columns and 'MANZENT' not in rename_map.values():
        rename_map['MZ_ENT'] = 'MANZENT'
    if rename_map:
        df_censo.rename(columns=rename_map, inplace=True)
        logger.info(f'Renombradas columnas para clave: {rename_map}')
    # Limpieza de espacios/tipos
    for col in ['MANZENT','ID_MANZENT','MZ_ENT','MANZANA']:
        if col in gdf.columns:
            gdf[col] = gdf[col].astype(str).str.strip()
        if col in df_censo.columns:
            df_censo[col] = df_censo[col].astype(str).str.strip()
    # Buscar clave
    if args.censo_key and args.censo_key in gdf.columns and args.censo_key in df_censo.columns:
        key = args.censo_key
    else:
        candidates = ['MANZENT', 'ID_MANZENT', 'MZ_ENT', 'MANZANA', 'ID_MANZENT_15R']
        key = next((c for c in candidates if c in gdf.columns and c in df_censo.columns), None)
    if key is None:
        # intentar intersección genérica
        common = set(gdf.columns) & set(df_censo.columns)
        key = next(iter(common), None)
    if key is None:
        logger.error('No se encontró clave común para join censo.')
        logger.info(f'Columnas manzanas: {list(gdf.columns)}')
        logger.info(f'Columnas censo: {list(df_censo.columns)[:40]} ...')
        return
    df_censo_reduced = df_censo[[key] + [c for c in df_censo.columns if c != key][:50]]  # limitar columnas
    merged = gdf.merge(df_censo_reduced, on=key, how='left')
    merged = ensure_lowercase_manzent(merged)
    try:
        merged.to_file(out_path, driver='GeoJSON')
        logger.info(f'Escrito {out_path}')
    except Exception as e:
        logger.error(f'Error escribiendo manzanas_atributos: {e}')

#############################################
# Overlay Uso Suelo con Manzanas
#############################################

def join_uso_suelo(args):
    """Intersecta uso_suelo_minvu con manzanas para obtener proporciones.
    Salida: data/processed/manzanas_uso_suelo.geojson
    """
    raw_dir = Path('data/raw')
    out_path = Path('data/processed/manzanas_uso_suelo.geojson')
    out_path.parent.mkdir(exist_ok=True)
    if out_path.exists():
        logger.info('manzanas_uso_suelo.geojson ya existe, se reutiliza.')
        return
    uso_path = raw_dir / 'uso_suelo_minvu.geojson'
    manzanas_path = Path(args.censo_geojson) if args.censo_geojson else raw_dir / 'manzanas_censales.geojson'
    if not uso_path.exists() or not manzanas_path.exists():
        logger.warning('Faltan uso_suelo_minvu.geojson o manzanas_censales.geojson; omitiendo overlay.')
        return
    try:
        gdf_m = gpd.read_file(manzanas_path)
        gdf_u = gpd.read_file(uso_path)
        # Reproyectar para cálculo de áreas si CRS geográfico
        target_epsg = args.srid or 32719
        if gdf_m.crs and gdf_m.crs.is_geographic:
            gdf_m = gdf_m.to_crs(epsg=target_epsg)
        if gdf_u.crs and gdf_u.crs.is_geographic:
            gdf_u = gdf_u.to_crs(epsg=target_epsg)
        # Asegurar mismo CRS
        if gdf_m.crs != gdf_u.crs:
            gdf_u = gdf_u.to_crs(gdf_m.crs)
        inter = gpd.overlay(gdf_m, gdf_u, how='intersection')
        if 'geometry' not in inter.columns or inter.empty:
            logger.warning('Overlay vacío o sin geometría.')
            return
        # Calcular área por fragmento
        inter['area_frag'] = inter.geometry.area
        # Detectar clave manzana
        key_candidates = ['MANZENT', 'ID_MANZANA', 'COD_MANZANA', 'MANZANA']
        manzana_key = next((k for k in key_candidates if k in inter.columns), None)
        if manzana_key is None:
            manzana_key = inter.columns[0]  # fallback
        # Agrupar áreas y contar categorías
        agg = inter.groupby(manzana_key).agg(
            area_zonas=('area_frag', 'sum'),
            zonas_count=('area_frag', 'count')
        ).reset_index()
        # Normalizar tipo clave a string para evitar conflictos posteriores
        gdf_m[manzana_key] = gdf_m[manzana_key].astype(str)
        agg[manzana_key] = agg[manzana_key].astype(str)
        # Unir de vuelta a gdf_m para tener geometría completa y stats
        result = gdf_m.merge(agg, on=manzana_key, how='left')
        result = ensure_lowercase_manzent(result)
        result.to_file(out_path, driver='GeoJSON')
        logger.info(f'Escrito {out_path}')
    except Exception as e:
        logger.error(f'Error en overlay uso suelo: {e}')

#############################################
# Métricas resumen por manzana
#############################################

def generate_metrics(args):
    """Genera metrics_manzanas.csv con conteos de edificios, amenidades y área.
    Si existen archivos de joins, añade columnas disponibles.
    """
    raw_dir = Path('data/raw')
    proc_dir = Path('data/processed')
    proc_dir.mkdir(exist_ok=True)
    manzanas_geo = raw_dir / 'manzanas_censales.geojson'
    buildings_geo = raw_dir / 'osm_buildings.geojson'
    amenities_geo = raw_dir / 'osm_amenities.geojson'
    out_csv = proc_dir / 'metrics_manzanas.csv'
    if not manzanas_geo.exists() or not buildings_geo.exists() or not amenities_geo.exists():
        logger.warning('Faltan archivos base para métricas (manzanas/OSM); omitiendo métricas.')
        return
    try:
        gdf_m = gpd.read_file(manzanas_geo)
        target_epsg = args.srid or 32719
        if gdf_m.crs and gdf_m.crs.is_geographic:
            gdf_m = gdf_m.to_crs(epsg=target_epsg)
        gdf_b = gpd.read_file(buildings_geo)
        if gdf_b.crs != gdf_m.crs:
            gdf_b = gdf_b.to_crs(gdf_m.crs)
        gdf_a = gpd.read_file(amenities_geo)
        if gdf_a.crs != gdf_m.crs:
            gdf_a = gdf_a.to_crs(gdf_m.crs)
    except Exception as e:
        logger.error(f'Error leyendo datos para métricas: {e}')
        return
    key_candidates = ['MANZENT', 'ID_MANZANA', 'COD_MANZANA', 'MANZANA']
    manzana_key = next((k for k in key_candidates if k in gdf_m.columns), None)
    if manzana_key is None:
        manzana_key = gdf_m.columns[0]
    # Forzar tipo string para evitar conflictos de dtype
    gdf_m[manzana_key] = gdf_m[manzana_key].astype(str)
    # Spatial joins (conteos)
    try:
        joined_b = gpd.sjoin(gdf_b, gdf_m, how='left', predicate='intersects')
        count_b = joined_b.groupby(manzana_key).size()
    except Exception:
        count_b = pd.Series(dtype='int')
    try:
        joined_a = gpd.sjoin(gdf_a, gdf_m, how='left', predicate='intersects')
        count_a = joined_a.groupby(manzana_key).size()
    except Exception:
        count_a = pd.Series(dtype='int')
    df = pd.DataFrame({manzana_key: gdf_m[manzana_key]})
    df['area_m2'] = gdf_m.geometry.area
    df['edificios_count'] = df[manzana_key].map(count_b).fillna(0).astype(int)
    df['amenidades_count'] = df[manzana_key].map(count_a).fillna(0).astype(int)
    # Estadística zonal NDVI (media por manzana) si raster existe y columna no presente
    if 'ndvi_mean' not in df.columns:
        ndvi_candidates = [proc_dir / f'sentinel2_ndvi_{args.srid}.tif' for _ in [0] if getattr(args, 'srid', None)]
        ndvi_candidates.append(proc_dir / 'sentinel2_ndvi.tif')
        ndvi_raster = next((p for p in ndvi_candidates if p.exists()), None)
        if ndvi_raster:
            try:
                import rasterio
                import rasterio.mask
                means = []
                with rasterio.open(ndvi_raster) as src:
                    # Reproyectar manzanas si CRS difiere
                    if gdf_m.crs and gdf_m.crs.to_string() != src.crs.to_string():
                        gdf_m = gdf_m.to_crs(src.crs)
                    for geom in gdf_m.geometry:
                        try:
                            out_img, _ = rasterio.mask.mask(src, [geom.__geo_interface__], crop=True, nodata=src.nodata)
                            arr = out_img[0]
                            valid = arr[arr != src.nodata]
                            if valid.size == 0:
                                means.append(np.nan)
                            else:
                                means.append(float(valid.mean()))
                        except Exception:
                            means.append(np.nan)
                df['ndvi_mean'] = means
                logger.info('Añadida columna ndvi_mean (media NDVI por manzana).')
            except Exception as e:
                logger.warning(f'Error calculando zonal NDVI: {e}')
        else:
            logger.info('Raster NDVI no encontrado; se omite zonal NDVI.')
    # Añadir atributos si existen outputs previos
    censo_path = proc_dir / 'manzanas_atributos.geojson'
    uso_path = proc_dir / 'manzanas_uso_suelo.geojson'
    if censo_path.exists():
        try:
            censo_gdf = gpd.read_file(censo_path)
            # Forzar dtype string en clave si existe
            if manzana_key in censo_gdf.columns:
                censo_gdf[manzana_key] = censo_gdf[manzana_key].astype(str)
            cols = [c for c in censo_gdf.columns if c not in ('geometry',)]
            censo_df = censo_gdf[cols]
            df = df.merge(censo_df, on=manzana_key, how='left')
        except Exception as e:
            logger.warning(f'No se pudo añadir atributos censo: {e}')
    if uso_path.exists():
        try:
            uso_gdf = gpd.read_file(uso_path)
            cols = [manzana_key, 'area_zonas', 'zonas_count']
            # Usar copy() para evitar SettingWithCopyWarning al modificar tipos
            uso_df = uso_gdf[cols].copy()
            # Forzar tipos a string en clave si difieren
            uso_df[manzana_key] = uso_df[manzana_key].astype(str)
            df = df.merge(uso_df, on=manzana_key, how='left')
        except Exception as e:
            logger.warning(f'No se pudo añadir atributos uso suelo: {e}')
    try:
        df.to_csv(out_csv, index=False)
        logger.info(f'Escrito {out_csv}')
    except Exception as e:
        logger.error(f'Error escribiendo metrics_manzanas.csv: {e}')
    # Añadir alias si se vuelve a usar en otros procesos posteriores
    if 'MANZENT' in df.columns and 'manzent' not in df.columns:
        try:
            df['manzent'] = df['MANZENT'].astype(str).str.strip()
        except Exception:
            pass

#############################################
# Métricas de red vial (centralidad / densidad)
#############################################

def generate_network_metrics(args):
    """Calcula métricas de red vial por manzana:
    - degree_mean, betweenness_mean, node_count
    - road_length_m, road_density_m_per_km2
    Salidas:
      data/processed/network_nodes_metrics.geojson (nodos con centralidades)
      data/processed/network_metrics.csv (agregado por manzana)
    Requiere: data/raw/osm_network.graphml y manzanas_censales.geojson
    """
    raw_dir = Path('data/raw')
    proc_dir = Path('data/processed')
    proc_dir.mkdir(exist_ok=True)
    graph_path = raw_dir / 'osm_network.graphml'
    manzanas_path = raw_dir / 'manzanas_censales.geojson'
    if not graph_path.exists() or not manzanas_path.exists():
        logger.warning('Faltan osm_network.graphml o manzanas_censales.geojson; omitiendo network metrics.')
        return
    try:
        import networkx as nx
        G = nx.read_graphml(graph_path)
    except Exception as e:
        logger.error(f'Error leyendo graphml: {e}')
        return
    # Construir nodos GeoDataFrame
    node_records = []
    for n, data in G.nodes(data=True):
        lon = data.get('x') or data.get('lon')
        lat = data.get('y') or data.get('lat')
        if lon is None or lat is None:
            continue
        geom = Point(float(lon), float(lat))
        rec = {'node_id': n, **{k: v for k, v in data.items() if k not in ('x','y','lon','lat')}, 'geometry': geom}
        node_records.append(rec)
    gdf_nodes = gpd.GeoDataFrame(node_records, geometry='geometry', crs='EPSG:4326')
    # Construir edges GeoDataFrame
    edge_records = []
    for u, v, data in G.edges(data=True):
        geom_attr = data.get('geometry')
        geom = None
        if geom_attr is not None:
            if hasattr(geom_attr, 'geom_type'):
                geom = geom_attr
            else:
                try:
                    geom = wkt.loads(geom_attr)
                except Exception:
                    geom = None
        if geom is None:
            udata = G.nodes[u]; vdata = G.nodes[v]
            lon_u = udata.get('x') or udata.get('lon'); lat_u = udata.get('y') or udata.get('lat')
            lon_v = vdata.get('x') or vdata.get('lon'); lat_v = vdata.get('y') or vdata.get('lat')
            if None in (lon_u, lat_u, lon_v, lat_v):
                continue
            geom = LineString([(float(lon_u), float(lat_u)), (float(lon_v), float(lat_v))])
        rec = {'u': u, 'v': v, **{k: v for k, v in data.items() if k != 'geometry'}, 'geometry': geom}
        edge_records.append(rec)
    gdf_edges = gpd.GeoDataFrame(edge_records, geometry='geometry', crs='EPSG:4326')
    # Centralidades
    try:
        degree_c = nx.degree_centrality(G)
        # Betweenness: usar muestreo si grafo grande (>5000 nodos) para performance
        if len(G) > 5000:
            import random
            sample_nodes = random.sample(list(G.nodes()), min(1000, len(G)))
            betw_c = nx.betweenness_centrality(G, k=len(sample_nodes))
        else:
            betw_c = nx.betweenness_centrality(G)
    except Exception as e:
        logger.warning(f'Error calculando centralidades: {e}')
        degree_c = {}; betw_c = {}
    gdf_nodes['degree'] = gdf_nodes['node_id'].map(degree_c).fillna(0.0)
    gdf_nodes['betweenness'] = gdf_nodes['node_id'].map(betw_c).fillna(0.0)
    # Reproyección a CRS métrico para longitud
    target_epsg = args.srid or 32719
    gdf_nodes = gdf_nodes.to_crs(epsg=target_epsg)
    gdf_edges = gdf_edges.to_crs(epsg=target_epsg)
    # Manzanas
    try:
        gdf_m = gpd.read_file(manzanas_path)
        if gdf_m.crs and gdf_m.crs.to_epsg() != target_epsg:
            gdf_m = gdf_m.to_crs(epsg=target_epsg)
    except Exception as e:
        logger.error(f'Error leyendo manzanas para network metrics: {e}')
        return
    key_candidates = ['MANZENT', 'ID_MANZANA', 'COD_MANZANA', 'MANZANA']
    manzana_key = next((k for k in key_candidates if k in gdf_m.columns), None) or gdf_m.columns[0]
    gdf_m[manzana_key] = gdf_m[manzana_key].astype(str)
    # Agregación nodos -> manzana
    try:
        nodes_join = gpd.sjoin(gdf_nodes, gdf_m, how='left', predicate='intersects')
        grp = nodes_join.groupby(manzana_key)
        node_count = grp.size()
        degree_mean = grp['degree'].mean()
        betweenness_mean = grp['betweenness'].mean()
    except Exception as e:
        logger.warning(f'Fallo join nodos-manzanas: {e}')
        node_count = pd.Series(dtype='int'); degree_mean = pd.Series(dtype='float'); betweenness_mean = pd.Series(dtype='float')
    # Longitud de vialidad por manzana (iterativo para precisión)
    road_length = {}
    for idx, row in gdf_m.iterrows():
        poly = row.geometry
        sel = gdf_edges[gdf_edges.geometry.intersects(poly)]
        total_len = 0.0
        for geom in sel.geometry:
            try:
                total_len += geom.intersection(poly).length
            except Exception:
                pass
        road_length[row[manzana_key]] = total_len
    df_net = pd.DataFrame({manzana_key: gdf_m[manzana_key]})
    df_net['node_count'] = df_net[manzana_key].map(node_count).fillna(0).astype(int)
    df_net['degree_mean'] = df_net[manzana_key].map(degree_mean).fillna(0.0)
    df_net['betweenness_mean'] = df_net[manzana_key].map(betweenness_mean).fillna(0.0)
    df_net['road_length_m'] = df_net[manzana_key].map(road_length).fillna(0.0)
    # Densidad en metros por km2
    areas_m2 = gdf_m.set_index(manzana_key).geometry.area
    df_net['road_density_m_per_km2'] = df_net.apply(lambda r: (r['road_length_m'] / (areas_m2.get(r[manzana_key], np.nan) / 1e6)) if areas_m2.get(r[manzana_key], np.nan) else np.nan, axis=1)
    # Escribir outputs
    nodes_out = proc_dir / 'network_nodes_metrics.geojson'
    csv_out = proc_dir / 'network_metrics.csv'
    try:
        gdf_nodes[['node_id','degree','betweenness','geometry']].to_file(nodes_out, driver='GeoJSON')
        logger.info(f'Escrito {nodes_out}')
    except Exception as e:
        logger.warning(f'No se pudo escribir nodes metrics: {e}')
    try:
        df_net.to_csv(csv_out, index=False)
        logger.info(f'Escrito {csv_out}')
    except Exception as e:
        logger.error(f'No se pudo escribir network_metrics.csv: {e}')
    if 'MANZENT' in df_net.columns and 'manzent' not in df_net.columns:
        try:
            df_net['manzent'] = df_net['MANZENT'].astype(str).str.strip()
        except Exception:
            pass

#############################################
# Unificación uso de suelo (PRC / PRMS / LU)
#############################################

def unify_uso_suelo(args):
    """Unifica múltiples shapefiles de uso de suelo en un único GeoJSON.
    Busca en data/raw/ archivos con patrones: PRC*.shp, PRMS*.shp, LU*.shp.
    Estandariza:
      - CRS (usa --srid o 32719)
      - Campo 'categoria' a partir del primero existente entre candidatos
      - Campo 'source' con el stem del archivo original
    Salida: data/processed/uso_suelo_unificado.geojson
    """
    raw_dir = Path('data/raw')
    out_path = Path('data/processed/uso_suelo_unificado.geojson')
    out_path.parent.mkdir(exist_ok=True)
    if out_path.exists():
        logger.info('uso_suelo_unificado.geojson ya existe, reutilizando.')
        return
    base_dir = raw_dir / 'uso_suelo_minvu'
    search_root = base_dir if base_dir.exists() else raw_dir
    patterns = ['**/*PRC*.shp', '**/*PRMS*.shp', '**/*LU*.shp']
    shp_files = []
    for pat in patterns:
        shp_files.extend(list(search_root.glob(pat)))
    if not shp_files:
        logger.warning('No se encontraron shapefiles PRC/PRMS/LU para unificar.')
        return
    target_epsg = args.srid or 32719
    gdfs = []
    cat_candidates = ['CLASE','USO','ZONA','DESCRIP','DESCRIPCION','CATEGORIA','TIPO']
    for f in shp_files:
        try:
            gdf = gpd.read_file(f)
            if gdf.empty:
                continue
            if gdf.crs and gdf.crs.is_geographic:
                gdf = gdf.to_crs(epsg=target_epsg)
            elif gdf.crs and gdf.crs.to_epsg() != target_epsg:
                try:
                    gdf = gdf.to_crs(epsg=target_epsg)
                except Exception:
                    pass
            cat_field = next((c for c in cat_candidates if c in gdf.columns), None)
            if cat_field is None:
                gdf['categoria'] = 'sin_categoria'
            else:
                gdf['categoria'] = gdf[cat_field].astype(str).str.strip()
            gdf['source'] = f.stem
            # Conservar sólo columnas esenciales
            keep_cols = ['categoria','source']
            gdf_min = gdf[keep_cols + ['geometry']].copy()
            gdfs.append(gdf_min)
        except Exception as e:
            logger.warning(f'Error leyendo {f.name}: {e}')
    if not gdfs:
        logger.warning('No se pudo construir ningún GeoDataFrame de uso de suelo.')
        return
    unified = gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True), geometry='geometry', crs=gdfs[0].crs)
    # Opcional: disolver geometrías por categoria + source? Mantener original para granularidad.
    try:
        unified.to_file(out_path, driver='GeoJSON')
        logger.info(f'Escrito {out_path} con {len(unified)} features')
    except Exception as e:
        logger.error(f'Error escribiendo uso_suelo_unificado.geojson: {e}')

#############################################
# Ingesta mínima de fuentes base
#############################################

def ingest_minimum_sources(args, processor: DataProcessor):
    """Ingesta de fuentes mínimas requeridas para trazabilidad completa.
    Vectoriales: límites oficiales, manzanas censales, uso_suelo_minvu.geojson.
    Tabular: microdatos censo (CSV filtrado) como tabla sin geometría.
    Raster (solo metadatos): DEM base y bandas Sentinel en raster_catalog.
    Usa esquema --schema (raw_data por defecto).
    """
    schema = args.schema
    srid = args.srid
    raw_dir = Path('data/raw')
    try:
        with processor.engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS {schema}'))
    except Exception as e:
        logger.error(f'No se pudo crear/verificar esquema {schema}: {e}')
        return
    vectores = {
        'comuna_boundaries_oficial': raw_dir / 'comuna_boundaries_oficial.geojson',
        'manzanas_censales': raw_dir / 'manzanas_censales.geojson',
        'uso_suelo_minvu': raw_dir / 'uso_suelo_minvu.geojson'
    }
    for nombre, path in vectores.items():
        if not path.exists():
            logger.warning(f'Falta {path.name}, se omite en ingest mínima.')
            continue
        try:
            gdf = gpd.read_file(path)
            if srid and gdf.crs:
                try:
                    gdf = gdf.to_crs(epsg=srid)
                except Exception:
                    logger.warning(f'No se pudo reproyectar {nombre} a EPSG:{srid}, se carga CRS original.')
            processor.load_to_postgis(gdf, nombre, schema=schema)
            if args.index:
                processor.create_spatial_index(nombre, schema)
            # Duplicar clave MANZENT en minúsculas para SQL simple si existe en este vectorial
            if nombre == 'manzanas_censales':
                try:
                    with processor.engine.begin() as conn:
                        # Verificar existencia variante original (mayúscula)
                        has_upper = conn.execute(text(f"SELECT 1 FROM information_schema.columns WHERE table_schema=:s AND table_name=:t AND column_name='MANZENT'"), {'s': schema, 't': nombre}).fetchone()
                        has_lower = conn.execute(text(f"SELECT 1 FROM information_schema.columns WHERE table_schema=:s AND table_name=:t AND column_name='manzent'"), {'s': schema, 't': nombre}).fetchone()
                        if has_upper and not has_lower:
                            conn.execute(text(f"ALTER TABLE {schema}.{nombre} ADD COLUMN manzent text"))
                            conn.execute(text(f"UPDATE {schema}.{nombre} SET manzent = \"MANZENT\"::text"))
                            logger.info('Añadida columna duplicada manzent (lowercase) en manzanas_censales.')
                except Exception as e:
                    logger.warning(f"No se pudo crear columna manzent duplicada en {nombre}: {e}")
        except Exception as e:
            logger.error(f'Error cargando {nombre}: {e}')
    # Microdatos censo
    censo_csv = raw_dir / 'Censo2017_ManzanaEntidad_CSV' / 'Censo2017_16R_ManzanaEntidad_CSV' / 'Censo2017_Manzanas.csv'
    if censo_csv.exists():
        try:
            df_censo = pd.read_csv(censo_csv, encoding='latin-1', sep=';')
            # Sanitizar nombres de columnas: eliminar espacios inicio/fin
            df_censo.rename(columns=lambda c: c.strip(), inplace=True)
            # Normalizar clave MANZENT desde variantes comunes (si no existe ya)
            if 'MANZENT' not in df_censo.columns:
                for alias in ['ID_MANZENT', 'MZ_ENT', 'MANZANA']:
                    if alias in df_censo.columns:
                        df_censo.rename(columns={alias: 'MANZENT'}, inplace=True)
                        logger.info(f"Renombrado alias de clave {alias} -> MANZENT (ingest mínima)")
                        break
            # Remover posibles espacios internos raros en la clave
            if 'MANZENT' in df_censo.columns:
                df_censo['MANZENT'] = df_censo['MANZENT'].astype(str).str.strip()
            cols = list(df_censo.columns)[:60]
            df_censo = df_censo[cols]
            table_name = 'censo_microdatos'
            with processor.engine.begin() as conn:
                conn.execute(text(f'DROP TABLE IF EXISTS {schema}.{table_name}'))
            df_censo.to_sql(table_name, processor.engine, schema=schema, if_exists='replace', index=False)
            logger.info(f'Ingestado microdatos censo como {schema}.{table_name}')
            # Crear columna manzent (lowercase) para facilitar joins futuros
            try:
                with processor.engine.begin() as conn:
                    has_upper = conn.execute(text("SELECT 1 FROM information_schema.columns WHERE table_schema=:s AND table_name='censo_microdatos' AND column_name='MANZENT'"), {'s': schema}).fetchone()
                    has_lower = conn.execute(text("SELECT 1 FROM information_schema.columns WHERE table_schema=:s AND table_name='censo_microdatos' AND column_name='manzent'"), {'s': schema}).fetchone()
                    if has_upper and not has_lower:
                        conn.execute(text(f"ALTER TABLE {schema}.censo_microdatos ADD COLUMN manzent text"))
                        conn.execute(text(f"UPDATE {schema}.censo_microdatos SET manzent = \"MANZENT\"::text"))
                        logger.info('Añadida columna duplicada manzent (lowercase) en censo_microdatos.')
            except Exception as e:
                logger.warning(f'No se pudo crear columna manzent en censo_microdatos: {e}')
            # Log rápido de existencia de columna MANZENT y cardinalidades
            with processor.engine.begin() as conn:
                # Usar la columna duplicada en minúsculas si existe para evitar problemas de case/quotes
                orphan_sql = text("""
                    SELECT COUNT(*) FROM raw_data.censo_microdatos c
                    LEFT JOIN raw_data.manzanas_censales m ON c.manzent = m.manzent
                    WHERE m.manzent IS NULL
                """)
                try:
                    orphan_count = conn.execute(orphan_sql).scalar()
                    logger.info(f"Microdatos sin geometría (post-ingest mínima): {orphan_count}")
                    # Cobertura microdatos con geometría
                    coverage_sql = text("""
                        SELECT ROUND(100.0 * (SELECT COUNT(*) FROM raw_data.censo_microdatos c JOIN raw_data.manzanas_censales m ON c.manzent = m.manzent) / NULLIF((SELECT COUNT(*) FROM raw_data.censo_microdatos),0),2)
                    """)
                    coverage = conn.execute(coverage_sql).scalar()
                    logger.info(f"Cobertura microdatos con geometría (%): {coverage}")
                    # Cobertura manzanas con microdatos
                    manz_cov_sql = text("""
                        SELECT ROUND(100.0 * (SELECT COUNT(DISTINCT m.manzent) FROM raw_data.manzanas_censales m JOIN raw_data.censo_microdatos c ON c.manzent = m.manzent) / NULLIF((SELECT COUNT(*) FROM raw_data.manzanas_censales),0),2)
                    """)
                    manz_cov = conn.execute(manz_cov_sql).scalar()
                    logger.info(f"Cobertura manzanas con microdatos (%): {manz_cov}")
                except Exception as e:
                    logger.warning(f"No se pudo calcular huérfanas censo: {e}")
        except Exception as e:
            logger.error(f'Error ingestando microdatos censo: {e}')
    else:
        logger.warning('Archivo microdatos censo CSV no encontrado; omitido.')
    # Rasters base a catálogo
    raster_candidates = []
    for dem_name in ['srtm_dem.tif','srtm_dem_32719.tif','copernicus_dem.tif','copernicus_dem_32719.tif']:
        p = raw_dir / dem_name
        if p.exists():
            raster_candidates.append(p)
    for b in ['sentinel_B04.tif','sentinel_B08.tif','sentinel2_B04.tif','sentinel2_B08.tif']:
        p = raw_dir / b
        if p.exists():
            raster_candidates.append(p)
    if raster_candidates:
        try:
            with processor.engine.begin() as conn:
                conn.execute(text(f"CREATE TABLE IF NOT EXISTS {schema}.raster_catalog (filename text PRIMARY KEY, crs text, width int, height int, band_count int, dtype text, transform text, bounds text, nodata text, source_group text)"))
            inserted = 0
            for rf in raster_candidates:
                try:
                    with rasterio.open(rf) as src:
                        meta = {
                            'filename': rf.name,
                            'crs': str(src.crs),
                            'width': src.width,
                            'height': src.height,
                            'band_count': src.count,
                            'dtype': src.dtypes[0],
                            'transform': ' '.join(map(str, src.transform.to_gdal())),
                            'bounds': f"{src.bounds.left},{src.bounds.bottom},{src.bounds.right},{src.bounds.top}",
                            'nodata': str(src.nodata),
                            'source_group': 'raw'
                        }
                    with processor.engine.begin() as conn:
                        conn.execute(text(
                            f"INSERT INTO {schema}.raster_catalog (filename, crs, width, height, band_count, dtype, transform, bounds, nodata, source_group) VALUES (:filename,:crs,:width,:height,:band_count,:dtype,:transform,:bounds,:nodata,:source_group) ON CONFLICT (filename) DO NOTHING"
                        ), meta)
                    inserted += 1
                except Exception as e:
                    logger.warning(f'No se pudo catalogar raster {rf.name}: {e}')
            logger.info(f'Catalogados {inserted} rasters base en {schema}.raster_catalog')
        except Exception as e:
            logger.error(f'Error creando/catalogando rasters base: {e}')
    else:
        logger.info('No se encontraron rasters base para catalogar en ingest mínima.')

#############################################
# Main (al final, después de todas las funciones)
#############################################

def main():
    args = parse_args()
    processor = DataProcessor()

    if args.load_osm:
        ingest_osm(args, processor)
    if args.ingest_minimum:
        ingest_minimum_sources(args, processor)
    if args.dem_derivatives:
        generate_dem_derivatives()
    if args.ndvi:
        generate_ndvi(args)
    if args.join_censo:
        join_censo(args)
    if args.join_uso_suelo:
        join_uso_suelo(args)
    if args.metrics:
        generate_metrics(args)
    if args.unify_uso_suelo:
        unify_uso_suelo(args)
    if args.ingest_processed:
        ingest_processed_outputs(args, processor)
    if args.network_metrics:
        generate_network_metrics(args)

    logger.info('Procesamiento completado!')


if __name__ == '__main__':
    main()
