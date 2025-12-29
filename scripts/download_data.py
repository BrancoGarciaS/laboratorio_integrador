#!/usr/bin/env python3
"""
Script para descargar datos geoespaciales de la comuna seleccionada.
Estructura ajustada a los requisitos de la Guía del Laboratorio Integrador.
"""

import os
import sys
import stat  # Importante para cambiar permisos de archivos
import click
import requests
import geopandas as gpd
import pandas as pd
import osmnx as ox
from pathlib import Path
from datetime import datetime, date, timedelta
import logging
import unicodedata
import traceback
import zipfile
import tempfile
import shutil
import json
import rasterio
import gzip 
from rasterio.mask import mask
from rasterio.warp import calculate_default_transform, reproject, Resampling
from tqdm import tqdm

# --- CONFIGURACIÓN DE URLs POR DEFECTO ---
DEFAULT_CENSO_URL = "https://services5.arcgis.com/hUyD8u3TeZLKPe4T/arcgis/rest/services/Manzana_2017_2/FeatureServer/0"
DEFAULT_CENSO_MICRO_URL = "https://redatam-ine.ine.cl/tab/Censo2017_ManzanaEntidad_CSV.rar"
DEFAULT_MINVU_USO_SUELO_URL = "https://catalogo.minvu.cl/cgi-bin/koha/tracklinks.pl?uri=https%3A%2F%2Fcatalogo.minvu.cl%2Fcgi-bin%2Fkoha%2Fopac-retrieve-file.pl%3Fid%3Deea77d4fcd8a800c121da5f9f3d135fd&biblionumber=25215"
DEFAULT_DPA_URL = "https://www.geoportal.cl/geoportal/catalog/download/912598ad-ac92-35f6-8045-098f214bd9c2"

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
        self.boundary_gdf = None
        logger.info(f"Inicializando descarga para comuna: {comuna_name}")

    def _normalize(self, text: str) -> str:
        if text is None: return ""
        text = str(text)
        try: text = text.encode("latin1").decode("windows-1252")
        except: pass
        text = unicodedata.normalize("NFKD", text)
        text = "".join(c for c in text if not unicodedata.combining(c))
        text = "".join(c for c in text if 32 <= ord(c) <= 126)
        return text.upper().strip()
    
    def _safe_read_csv(self, path):
        from io import StringIO
        with open(path, "rb") as f:
            raw = f.read()
        text = raw.decode("latin-1", errors="replace")
        return pd.read_csv(StringIO(text), sep=";", dtype=str)
    
    def _closest_match(self, target: str, candidates: list, cutoff: float = 0.75):
        import difflib
        matches = difflib.get_close_matches(target, candidates, n=1, cutoff=cutoff)
        return matches[0] if matches else None

    def _download_file(self, url, dest_path, desc="Descargando"):
        """Descarga un archivo con barra de progreso tqdm."""
        try:
            with requests.get(url, stream=True, timeout=300) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
                
                with tqdm(total=total_size, unit='iB', unit_scale=True, desc=desc, ncols=80) as bar:
                    with open(dest_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            size = f.write(chunk)
                            bar.update(size)
            return True
        except Exception as e:
            logger.error(f"Error descargando {url}: {e}")
            return False

    def _load_boundary(self):
        if self.boundary_gdf is None:
            f = self.output_dir / 'comuna_boundaries_oficial.geojson'
            if f.exists():
                try:
                    self.boundary_gdf = gpd.read_file(f)
                    if self.boundary_gdf.crs is None:
                        self.boundary_gdf.set_crs(epsg=4326, inplace=True)
                except Exception as e:
                    logger.warning(f"Archivo de límites corrupto o ilegible: {e}")
        return self.boundary_gdf

    def _reproject_raster(self, src_path: Path, target_epsg: int = 32719):
        out_path = src_path.parent / f"{src_path.stem}_{target_epsg}.tif"
        try:
            with rasterio.open(src_path) as src:
                dst_crs = f"EPSG:{target_epsg}"
                transform, width, height = calculate_default_transform(
                    src.crs, dst_crs, src.width, src.height, *src.bounds)
                meta = src.meta.copy()
                meta.update({'crs': dst_crs, 'transform': transform, 'width': width, 'height': height})
                with rasterio.open(out_path, 'w', **meta) as dst:
                    for i in range(1, src.count + 1):
                        reproject(
                            source=rasterio.band(src, i),
                            destination=rasterio.band(dst, i),
                            src_transform=src.transform,
                            src_crs=src.crs,
                            dst_transform=transform,
                            dst_crs=dst_crs,
                            resampling=Resampling.bilinear
                        )
            logger.info(f"✔ Raster reproyectado generado: {out_path.name}")
        except Exception as e:
            logger.warning(f"No se pudo reproyectar raster: {e}")

    # --- MÉTODOS DE DESCARGA ---

    def download_osm_data(self, debug: bool = False):
        logger.info(">>> Iniciando descarga OSM (Fuente: OpenStreetMap)")
        try:
            if hasattr(ox, 'settings'):
                ox.settings.use_cache = True
                ox.settings.log_console = debug
        except: pass

        queries = [f"{self.comuna}, Chile", f"{self._normalize(self.comuna)}, Chile"]
        success = False

        for q in queries:
            logger.info(f"Consultando OSM: '{q}'")
            try:
                G = ox.graph_from_place(q, network_type='drive')
                ox.save_graphml(G, self.output_dir / 'osm_network.graphml')
                logger.info("✔ Red vial descargada.")
                success = True
                try:
                    if hasattr(ox, 'geocode_to_gdf'):
                        self.boundary_gdf = ox.geocode_to_gdf(q)
                except: pass
            except Exception:
                if debug: logger.warning(f"No se encontró red vial para {q}")

            if success:
                def get_features(tags, name):
                    try:
                        if hasattr(ox, 'features'):
                            gdf = ox.features.features_from_place(q, tags=tags)
                        else:
                            gdf = ox.geometries_from_place(q, tags=tags)
                        if gdf is not None and not gdf.empty:
                            gdf.to_file(self.output_dir / f'osm_{name}.geojson', driver='GeoJSON')
                            logger.info(f"✔ {name.capitalize()} descargados.")
                    except Exception as e:
                        if debug: logger.warning(f"Error en {name}: {e}")

                get_features({'building': True}, 'buildings')
                get_features({'amenity': True}, 'amenities')
                break
        return success

    def download_boundaries(self, wfs_url=None, dpa_url=None, skip_wfs=False, debug=False):
        logger.info(">>> Descargando Límites Administrativos (Fuente: IDE Chile/DPA)")
        if not skip_wfs:
            try:
                wfs = wfs_url or "https://www.ide.cl/geoserver/wfs"
                params = {
                    'service': 'WFS', 'version': '2.0.0', 'request': 'GetFeature',
                    'typeName': 'division_comunal', 'outputFormat': 'application/json',
                    'CQL_FILTER': f"comuna='{self.comuna.upper()}'"
                }
                r = requests.get(wfs, params=params, timeout=30)
                if r.status_code == 200 and 'features' in r.json() and len(r.json()['features']) > 0:
                    with open(self.output_dir / 'comuna_boundaries_oficial.geojson', 'w') as f:
                        f.write(r.text)
                    logger.info("✔ Límites WFS descargados.")
                    return True
            except Exception as e:
                if debug: logger.warning(f"Fallo WFS: {e}")

        return self.download_boundaries_dpa_zip(dpa_url or DEFAULT_DPA_URL, self.comuna, debug)

    def download_boundaries_dpa_zip(self, dpa_url, comuna_name, debug):
        try:
            with tempfile.TemporaryDirectory() as tmp:
                zpath = Path(tmp) / 'dpa.zip'
                logger.info("Iniciando descarga DPA (ZIP)...")
                if not self._download_file(dpa_url, zpath, desc="DPA Oficial"):
                    return False
                
                with zipfile.ZipFile(zpath) as zf: zf.extractall(tmp)
                
                shp = next(Path(tmp).rglob('*.shp'), None)
                if not shp: return False
                
                gdf = gpd.read_file(shp)
                norm_name = self._normalize(comuna_name)
                cols = [c for c in gdf.columns if 'comuna' in c.lower()]
                if not cols: return False
                
                gdf['norm'] = gdf[cols[0]].apply(self._normalize)
                filtered = gdf[gdf['norm'] == norm_name]
                
                if filtered.empty:
                    logger.warning(f"Comuna {comuna_name} no encontrada en DPA.")
                    return False
                
                filtered = filtered.drop(columns=['norm'])
                filtered.to_file(self.output_dir / 'comuna_boundaries_oficial.geojson', driver='GeoJSON')
                self.boundary_gdf = filtered
                logger.info("✔ Límites DPA procesados.")
                return True
        except Exception as e:
            logger.error(f"Error DPA: {e}")
            return False

    def download_census_data(self, censo_url=None, micro_url=None, debug=False):
        logger.info(">>> Iniciando descarga INE (Manzanas + Datos Socioeconómicos)")
        
        # 1. Geometría Manzanas (INE)
        url = censo_url or DEFAULT_CENSO_URL
        query_url = url.rstrip('/') + '/query'
        names_to_try = [self.comuna.upper(), self._normalize(self.comuna)]
        
        success = False
        for n in names_to_try:
            where = f"UPPER(COMUNA) LIKE '{n}%'"
            try:
                params = {'where': where, 'outFields': '*', 'returnGeometry': 'true', 'f': 'geojson', 'outSR': '4326'}
                r = requests.get(query_url, params=params, timeout=60)
                if r.status_code == 200:
                    data = r.json()
                    if 'features' in data and len(data['features']) > 0:
                        with open(self.output_dir / 'manzanas_censales.geojson', 'w', encoding='utf-8') as f:
                            f.write(r.text)
                        logger.info(f"✔ Geometría de manzanas descargada ({len(data['features'])} features).")
                        success = True
                        break
            except Exception: pass
        if not success: logger.warning("No se encontraron manzanas censales.")

        # 2. Censo 2017 Microdatos (INE)
        m_url = micro_url or DEFAULT_CENSO_MICRO_URL
        self.download_and_extract_censo_rar(m_url)
        self.filter_censo_manzanas_by_comuna(self.comuna)

    def download_and_extract_censo_rar(self, url):
        fname = url.split("/")[-1]
        rar_path = self.output_dir / fname
        if rar_path.exists():
            logger.info("RAR Censo ya existe.")
        else:
            logger.info("Iniciando descarga Microdatos Censo...")
            if not self._download_file(url, rar_path, desc="Microdatos Censo"):
                return

        extract_dir = self.output_dir / "Censo2017_ManzanaEntidad_CSV"
        extract_dir.mkdir(exist_ok=True)
        
        extracted = False
        # Intento 1: rarfile
        try:
            import rarfile
            with rarfile.RarFile(rar_path) as rf:
                # CORRECCIÓN: Extraer DENTRO de la carpeta específica
                rf.extractall(path=extract_dir)
            extracted = True
        except Exception as e:
            logger.warning(f"Fallo rarfile ({e}). Intentando fallback con 7zip...")

        # Intento 2: 7zip
        if not extracted:
            import subprocess
            sevenzip_candidates = ["7z", "7za", r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"]
            sevenzip_exe = None
            for candidate in sevenzip_candidates:
                if shutil.which(candidate) or Path(candidate).exists():
                    sevenzip_exe = candidate
                    break
            if sevenzip_exe:
                try:
                    # CORRECCIÓN: Usar extract_dir como destino
                    cmd = [sevenzip_exe, "x", "-y", str(rar_path), f"-o{extract_dir}"]
                    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                    extracted = True
                    logger.info("✔ Extracción exitosa con 7-Zip.")
                except: pass
        
        if extracted and rar_path.exists():
            rar_path.unlink()

    def filter_censo_manzanas_by_comuna(self, comuna_name):
        """Filtra el CSV gigante de manzanas por la comuna seleccionada."""
        base = self.output_dir / "Censo2017_ManzanaEntidad_CSV"
        try:
            # Buscar recursivamente porque a veces extrae en subcarpetas
            csv_path = next(base.rglob("Censo2017_Manzanas.csv"), None)
            comunas_path = next(base.rglob("*Comunas.csv"), None)
            
            if not csv_path or not comunas_path: 
                logger.error(f"No se encontraron los archivos CSV del Censo en {base}")
                return

            df_com = self._safe_read_csv(comunas_path)
            norm = self._normalize(comuna_name)
            df_com['NORM'] = df_com['NOM_COMUNA'].apply(self._normalize)
            
            code = None
            match = df_com[df_com['NORM'] == norm]
            if not match.empty:
                code = match.iloc[0]['COMUNA']
            else:
                match = df_com[df_com['NORM'].str.contains(norm, na=False)]
                if not match.empty: 
                    code = match.iloc[0]['COMUNA']
                else:
                    # Fuzzy match
                    possibles = df_com['NORM'].tolist()
                    best = self._closest_match(norm, possibles)
                    if best:
                        code = df_com[df_com['NORM'] == best].iloc[0]['COMUNA']
            
            if code:
                logger.info(f"Filtrando Censo para código comuna: {code}")
                df_data = self._safe_read_csv(csv_path)
                df_filtered = df_data[df_data['COMUNA'] == code]
                
                if not df_filtered.empty:
                    # CORRECCIÓN CRÍTICA: Cambiar permisos antes de escribir (fix Permission denied)
                    try:
                        os.chmod(csv_path, stat.S_IWRITE)
                    except Exception: pass
                    
                    df_filtered.to_csv(csv_path, sep=";", index=False)
                    logger.info(f"✔ Microdatos filtrados para comuna {code} (Filas: {len(df_filtered)}).")
                else:
                    logger.warning(f"No se encontraron registros para la comuna {code}.")
            else:
                logger.error(f"No se encontró código CUT para la comuna '{comuna_name}'.")

        except Exception as e: logger.error(f"Error filtrando CSV: {e}")

    def download_srtm_tiles(self, debug=False):
        logger.info(">>> Descargando DEM SRTM")
        boundary = self._load_boundary()
        if boundary is None:
            logger.error("❌ FALTA LÍMITE COMUNAL: Ejecuta primero --sources ide")
            return

        minx, miny, maxx, maxy = boundary.total_bounds
        import math
        lat_sw = math.floor(miny)
        lon_sw = math.floor(minx)
        ns = 'S' if lat_sw < 0 else 'N'
        ew = 'W' if lon_sw < 0 else 'E'
        tile_name = f"{ns}{abs(lat_sw):02d}{ew}{abs(lon_sw):03d}"
        
        urls = [
            f"https://srtm.kurviger.de/SRTM3/{tile_name}.hgt.zip",
            f"https://dds.cr.usgs.gov/srtm/version2_1/SRTM3/South_America/{tile_name}.hgt.zip",
            f"https://srtmtiles.s3.amazonaws.com/{tile_name}.hgt.gz",
            f"https://s3.amazonaws.com/elevation-tiles-prod/skadi/{tile_name[:3]}/{tile_name}.hgt.gz" 
        ]
        
        hgt_path = self.output_dir / f"{tile_name}.hgt"
        
        if not hgt_path.exists():
            downloaded = False
            for url in urls:
                try:
                    logger.info(f"Probando mirror: {url}")
                    if url.endswith('.zip'):
                        temp_path = self.output_dir / f"{tile_name}.zip"
                        if self._download_file(url, temp_path, desc=f"SRTM {tile_name}"):
                            with zipfile.ZipFile(temp_path, 'r') as zf:
                                for member in zf.namelist():
                                    if member.endswith('.hgt'):
                                        with zf.open(member) as src, open(hgt_path, 'wb') as dst:
                                            dst.write(src.read())
                            temp_path.unlink()
                            downloaded = True
                            break
                    elif url.endswith('.gz'):
                        temp_path = self.output_dir / f"{tile_name}.hgt.gz"
                        if self._download_file(url, temp_path, desc=f"SRTM {tile_name}"):
                            with gzip.open(temp_path, 'rb') as f_in:
                                with open(hgt_path, 'wb') as f_out:
                                    shutil.copyfileobj(f_in, f_out)
                            temp_path.unlink()
                            downloaded = True
                            break
                except Exception as e:
                    if debug: logger.warning(f"Error mirror {url}: {e}")

        # Recortar
        final_dem_path = self.output_dir / "srtm_dem.tif"
        if hgt_path.exists():
            try:
                with rasterio.open(hgt_path) as src:
                    out_image, out_transform = mask(src, boundary.geometry, crop=True)
                    out_meta = src.meta.copy()
                    out_meta.update({"driver": "GTiff", "height": out_image.shape[1], "width": out_image.shape[2], "transform": out_transform})
                    with rasterio.open(final_dem_path, "w", **out_meta) as dest:
                        dest.write(out_image)
                logger.info("✔ SRTM procesado y recortado (srtm_dem.tif).")
                self._reproject_raster(final_dem_path, 32719)
            except Exception as e:
                logger.error(f"Error recortando SRTM: {e}")

    def download_sentinel2(self, year=None, debug=False):
        logger.info(f">>> Descargando Sentinel-2 (Copernicus) [Año: {year if year else 'Reciente'}]")
        try:
            from pystac_client import Client
            import planetary_computer as pc
        except ImportError:
            logger.error("❌ Faltan librerías: pip install pystac-client planetary-computer")
            return

        boundary = self._load_boundary()
        if boundary is None:
            logger.error("❌ FALTA LÍMITE COMUNAL: Ejecuta primero --sources ide")
            return

        if year:
            date_range = f"{year}-01-01/{year}-12-31"
        else:
            end = date.today()
            start = end - timedelta(days=90)
            date_range = f"{start}/{end}"
        
        try:
            catalog = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
            search = catalog.search(
                collections=["sentinel-2-l2a"],
                bbox=boundary.total_bounds,
                datetime=date_range,
                query={"eo:cloud_cover": {"lt": 10}},
                limit=1
            )
            items = list(search.items())
            if not items:
                logger.warning("No se encontraron imágenes Sentinel-2.")
                return

            item = items[0]
            signed_item = pc.sign(item)
            
            for band in ['B04', 'B08']:
                if band in signed_item.assets:
                    href = signed_item.assets[band].href
                    with rasterio.open(href) as src:
                        geom = boundary
                        if geom.crs and src.crs and geom.crs.to_string() != src.crs.to_string():
                            geom = geom.to_crs(src.crs)
                        
                        out_image, out_transform = mask(src, geom.geometry, crop=True)
                        meta = src.meta.copy()
                        meta.update({"driver": "GTiff", "height": out_image.shape[1], "width": out_image.shape[2], "transform": out_transform})
                        with rasterio.open(self.output_dir / f"sentinel2_{band}.tif", "w", **meta) as dest:
                            dest.write(out_image)
            logger.info("✔ Sentinel-2 (B04, B08) descargado.")

        except Exception as e:
            logger.error(f"Error Sentinel-2: {e}")
            if debug: traceback.print_exc()

    def download_minvu_uso_suelo(self, minvu_url=None, local_path=None, debug=False):
        logger.info(">>> Descargando Uso de Suelo (MINVU)")
        url = minvu_url or DEFAULT_MINVU_USO_SUELO_URL
        zip_path = self.output_dir / 'uso_suelo_minvu.zip'
        
        if not zip_path.exists():
            logger.info("Iniciando descarga MINVU...")
            if not self._download_file(url, zip_path, desc="Uso Suelo MINVU"):
                return
            
        extract_dir = self.output_dir / 'uso_suelo_minvu'
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_dir)
            
        if zip_path.exists(): zip_path.unlink()
            
        shps = list(extract_dir.rglob("*.shp"))
        comuna_norm = self._normalize(self.comuna).split()
        matches = [s for s in shps if all(part in self._normalize(s.name) for part in comuna_norm)]
        
        # PODA DE ARCHIVOS SOBRANTES (Lógica recuperada del script antiguo)
        # Eliminamos de la carpeta PRC los shapefiles que no son de la comuna
        prc_dir = extract_dir / 'IPT_Metropolitana' / 'PRC'
        if prc_dir.exists():
            kept_count = 0
            removed_count = 0
            chosen_stems = {p.stem for p in matches}
            
            for f in prc_dir.iterdir():
                if f.is_file():
                    # Determinar si el archivo pertenece a uno de los shapefiles elegidos
                    stem = f.name.replace('.shp.xml', '') # manejo simple de extensiones
                    stem = Path(stem).stem
                    
                    if stem in chosen_stems:
                        kept_count += 1
                    else:
                        try:
                            f.unlink()
                            removed_count += 1
                        except: pass
            
            if removed_count > 0:
                logger.info(f"🧹 Poda completada: Se eliminaron {removed_count} archivos ajenos a {self.comuna} en carpeta PRC.")

        if matches:
            try:
                gdf = pd.concat([gpd.read_file(s) for s in matches], ignore_index=True)
                if gdf.crs and gdf.crs.to_epsg() != 4326: gdf = gdf.to_crs(4326)
                gdf.to_file(self.output_dir / 'uso_suelo_minvu.geojson', driver='GeoJSON')
                logger.info(f"✔ Uso de suelo consolidado ({len(gdf)} features).")
            except Exception as e:
                 logger.error(f"Error consolidando MINVU: {e}")
        else:
            logger.warning("No se detectaron shapefiles MINVU para la comuna.")

    def create_metadata(self):
        meta = {
            'comuna': self.comuna,
            'timestamp': datetime.now().isoformat(),
            'files': [f.name for f in self.output_dir.glob('*')]
        }
        with open(self.output_dir / 'metadata.txt', 'w') as f:
            json.dump(meta, f, indent=2)


@click.command()
@click.option('--comuna', required=True, help='Nombre de la comuna (ej. "La Florida")')
@click.option('--year', type=int, default=None, help='Año de los datos (ej. 2024).')
@click.option('--sources', default='all', show_default=True, help='Fuentes: ide, ine, osm, sentinel, minvu, srtm, all.')
@click.option('--debug', is_flag=True, help='Activar logs detallados')
@click.option('--output', default='data/raw', help='Directorio de salida')
@click.option('--skip-wfs', is_flag=True, help='Saltar WFS (IDE)')
def main(comuna, year, sources, debug, output, skip_wfs):
    """
    Herramienta de descarga de datos para el Laboratorio Integrador.
    """
    logger.info("=" * 60)
    logger.info(f"PROYECTO GEOINFORMÁTICA - DESCARGA DE DATOS")
    logger.info(f"Comuna: {comuna} | Año: {year or 'Reciente'} | Fuentes: {sources}")
    logger.info("=" * 60)
    
    out_path = Path(output)
    downloader = DataDownloader(comuna, out_path)
    
    s_list = [s.strip().lower() for s in sources.split(',')]
    download_all = 'all' in s_list
    
    # 1. Límites Administrativos (IDE Chile)
    # Tabla 1: Fuente IDE
    if download_all or 'ide' in s_list:
        downloader.download_boundaries(skip_wfs=skip_wfs, debug=debug)

    # 2. Datos Censales (INE)
    # Tabla 1: Fuente INE (Manzanas + Censo 2017)
    if download_all or 'ine' in s_list or 'censo' in s_list:
        downloader.download_census_data(debug=debug)
        
    # 3. Red Vial (OpenStreetMap)
    # Tabla 1: Fuente OpenStreetMap
    if download_all or 'osm' in s_list:
        downloader.download_osm_data(debug=debug)
        
    # 4. Uso de Suelo (IDE Minvu)
    # Tabla 1: Fuente IDE Minvu
    if download_all or 'minvu' in s_list or 'ide_minvu' in s_list:
        downloader.download_minvu_uso_suelo(debug=debug)
        
    # 5. DEM (SRTM)
    # Tabla 1: Fuente ALOS PALSAR / SRTM
    # Nota: Requiere límites previos. Si no existen, avisar.
    if download_all or 'srtm' in s_list or 'dem' in s_list:
        if (out_path / 'comuna_boundaries_oficial.geojson').exists():
            downloader.download_srtm_tiles(debug=debug)
        else:
            logger.warning("⚠️ Se requieren límites (IDE) para descargar SRTM. Ejecute con --sources ide primero.")
        
    # 6. Sentinel-2 (Copernicus)
    # Tabla 1: Fuente Copernicus
    if download_all or 'sentinel' in s_list or 'copernicus' in s_list:
        if (out_path / 'comuna_boundaries_oficial.geojson').exists():
            downloader.download_sentinel2(year=year, debug=debug)
        else:
            logger.warning("⚠️ Se requieren límites (IDE) para descargar Sentinel-2. Ejecute con --sources ide primero.")

    downloader.create_metadata()
    logger.info("\n>>> Proceso finalizado. Verifique la carpeta 'data/raw/'.")

if __name__ == '__main__':
    main()