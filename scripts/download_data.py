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
import unicodedata
import traceback
import zipfile
import tempfile
import shutil
import json
import rasterio
from rasterio.mask import mask

# URL por defecto (urbano Manzanas Censo 2017). Si cambia, actualizar aquí.
DEFAULT_CENSO_URL = "https://services5.arcgis.com/hUyD8u3TeZLKPe4T/arcgis/rest/services/Manzana_2017_2/FeatureServer/0"
# URL por defecto microdatos (manzana) Censo 2017 (formato RAR con CSV interno)
DEFAULT_CENSO_MICRO_URL = "https://redatam-ine.ine.cl/tab/Censo2017_ManzanaEntidad_CSV.rar"
DEFAULT_MINVU_USO_SUELO_URL = "https://catalogo.minvu.cl/cgi-bin/koha/tracklinks.pl?uri=https%3A%2F%2Fcatalogo.minvu.cl%2Fcgi-bin%2Fkoha%2Fopac-retrieve-file.pl%3Fid%3Deea77d4fcd8a800c121da5f9f3d135fd&biblionumber=25215"

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DataDownloader:
    """Clase para gestionar la descarga de datos geoespaciales.

    Incluye lógica de fallback para:
        - Nombres de comuna con y sin acentos.
        - Diferentes tipos de red (drive, all) si falla.
        - Control de cache y logging según versión de OSMnx.
    """

    def __init__(self, comuna_name: str, output_dir: Path):
        self.comuna = comuna_name
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.boundary_gdf = None  # geometría de la comuna para fallback límites
        logger.info(f"Inicializando descarga para comuna: {comuna_name}")

    def _normalize(self, text: str) -> str:
        import unicodedata
        if text is None:
            return ""
        text = str(text)
        # 1. Reparar CP1252 → UTF-8 (soluciona SAN JOAQUA\x8dN)
        try:
            text = text.encode("latin1").decode("windows-1252")
        except:
            pass
        # 2. Quitar acentos
        text = unicodedata.normalize("NFKD", text)
        text = "".join(c for c in text if not unicodedata.combining(c))
        # 3. Borrar cualquier carácter raro residual (<32 o >126)
        text = "".join(c for c in text if 32 <= ord(c) <= 126)
        # 4. Mayúsculas
        return text.upper().strip()
    
    def _closest_match(self, target: str, candidates: list, cutoff: float = 0.75):
        """Devuelve el string más parecido usando similarity ratio."""
        import difflib
        matches = difflib.get_close_matches(target, candidates, n=1, cutoff=cutoff)
        return matches[0] if matches else None


    def _safe_read_csv(self, path):
        """Lee un CSV con encoding desconocido sin lanzar errores."""
        import pandas as pd
        from io import StringIO

        with open(path, "rb") as f:
            raw = f.read()

        text = raw.decode("latin-1", errors="replace")

        return pd.read_csv(
            StringIO(text),
            sep=";",
            dtype=str
        )





    def download_osm_data(self, debug: bool = False):
        """Descarga datos de OpenStreetMap usando OSMnx con fallbacks."""
        logger.info("Descargando datos OSM (red vial, edificios, amenidades)...")

        # Ajustar settings según versión (OSMnx >=2.0 no tiene ox.config)
        try:
            if hasattr(ox, 'settings'):
                ox.settings.use_cache = True
                ox.settings.log_console = debug
        except Exception as e:
            logger.warning(f"No se pudieron ajustar settings OSMnx: {e}")

        queries = []
        original = f"{self.comuna}, Chile"
        normalized = f"{self._normalize(self.comuna)}, Chile"
        if original != normalized:
            queries = [original, normalized]
        else:
            queries = [original]

        graph_saved = False
        buildings_saved = False
        amenities_saved = False

        for q in queries:
            logger.info(f"Intentando query OSM: '{q}'")
            for net_type in ['drive', 'all']:
                try:
                    G = ox.graph_from_place(q, network_type=net_type)
                    output_file = self.output_dir / 'osm_network.graphml'
                    ox.save_graphml(G, output_file)
                    logger.info(f"Red vial ({net_type}) guardada en: {output_file}")
                    graph_saved = True
                    # Obtener geometría de la comuna para posible fallback de límites
                    try:
                        if hasattr(ox, 'geocode_to_gdf'):
                            self.boundary_gdf = ox.geocode_to_gdf(q)
                    except Exception as e:
                        if debug:
                            logger.warning(f"No se pudo obtener geometría OSM de la comuna para fallback: {e}")
                    break
                except Exception as e:
                    if debug:
                        logger.warning(f"Fallo red vial ({net_type}) para '{q}': {e}")
            if graph_saved:
                # Función wrapper para compatibilidad entre versiones (OSMnx <2 y >=2)
                def _features_from_place(place, tags):
                    # Versión antigua tenía geometries_from_place en el root
                    if hasattr(ox, 'geometries_from_place'):
                        return ox.geometries_from_place(place, tags=tags)
                    # Versión nueva organiza bajo ox.features.features_from_place
                    if hasattr(ox, 'features') and hasattr(ox.features, 'features_from_place'):
                        return ox.features.features_from_place(place, tags=tags)
                    raise AttributeError("OSMnx no expone geometries/features_from_place en esta versión.")

                # Edificios
                try:
                    logger.info("Descargando edificios...")
                    buildings = _features_from_place(q, tags={'building': True})
                    if buildings is not None and len(buildings) > 0:
                        buildings_file = self.output_dir / 'osm_buildings.geojson'
                        buildings.to_file(buildings_file, driver='GeoJSON')
                        logger.info(f"Edificios guardados: {buildings_file}")
                        buildings_saved = True
                    else:
                        logger.warning("No se encontraron edificios en la consulta.")
                except Exception as e:
                    logger.error(f"Error descargando edificios: {e}")
                    if debug:
                        traceback.print_exc()

                # Amenidades
                try:
                    logger.info("Descargando amenidades...")
                    amenities = _features_from_place(q, tags={'amenity': True})
                    if amenities is not None and len(amenities) > 0:
                        amenities_file = self.output_dir / 'osm_amenities.geojson'
                        amenities.to_file(amenities_file, driver='GeoJSON')
                        logger.info(f"Amenidades guardadas: {amenities_file}")
                        amenities_saved = True
                    else:
                        logger.warning("No se encontraron amenidades en la consulta.")
                except Exception as e:
                    logger.error(f"Error descargando amenidades: {e}")
                    if debug:
                        traceback.print_exc()
                break  # salir del loop de queries tras éxito parcial

        if not graph_saved:
            logger.error("No se pudo guardar ninguna red vial OSM tras los intentos.")
        return graph_saved or buildings_saved or amenities_saved

    def save_osm_boundary_fallback(self):
        """Guarda límites derivados de la geometría OSM si WFS falla u se omite."""
        if self.boundary_gdf is None or len(self.boundary_gdf) == 0:
            logger.warning("No hay geometría disponible para fallback de límites.")
            return False
        try:
            boundary_file = self.output_dir / 'osm_boundary.geojson'
            self.boundary_gdf.to_file(boundary_file, driver='GeoJSON')
            logger.info(f"Fallback de límites (OSM) guardado en: {boundary_file}")
            return True
        except Exception as e:
            logger.error(f"Error guardando fallback de límites OSM: {e}")
            return False

    def download_boundaries(self, wfs_url_override: str | None = None):
        """Descarga límites administrativos vía WFS.

        Permite override de URL por si el endpoint cambia.
        """
        try:
            logger.info("Descargando límites administrativos (WFS)...")

            # Endpoint por defecto (placeholder). Reemplazar por uno válido si se dispone.
            wfs_url = wfs_url_override or "https://www.ide.cl/geoserver/wfs"

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
                boundaries_file = self.output_dir / 'comuna_boundaries.geojson'
                with open(boundaries_file, 'w') as f:
                    f.write(response.text)
                logger.info(f"Límites guardados (WFS) en: {boundaries_file}")
                return True
            else:
                logger.warning("No se pudieron descargar límites vía WFS (status != 200)")
                return False

        except Exception as e:
            logger.error(f"Error descargando límites: {e}")
            return False

    def download_boundaries_dpa_zip(self, dpa_url: str, comuna_name: str, debug: bool = False) -> bool:
        """Descarga ZIP oficial DPA y extrae límites de la comuna específica.

        Intenta identificar el shapefile de comunas y filtrar por nombre
        (sin acentos, case-insensitive).
        """
        logger.info("Intentando descarga oficial DPA (ZIP)...")
        try:
            r = requests.get(dpa_url, timeout=120)
            if r.status_code != 200:
                logger.warning(f"Fallo descarga DPA ZIP (status {r.status_code})")
                return False
            with tempfile.TemporaryDirectory() as tmpdir:
                zip_path = Path(tmpdir) / 'dpa.zip'
                zip_path.write_bytes(r.content)
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    zf.extractall(tmpdir)
                shp_candidates = []
                for f in Path(tmpdir).rglob('*.shp'):
                    lname = f.name.lower()
                    score = 0
                    if 'com' in lname:
                        score += 10
                    score += f.stat().st_size / 1024.0
                    shp_candidates.append((score, f))
                if not shp_candidates:
                    logger.warning("No se encontraron .shp en ZIP DPA")
                    return False
                shp_candidates.sort(reverse=True, key=lambda x: x[0])
                if debug:
                    logger.info("Ranking shapefiles candidatos (score | nombre | tamaño KB):")
                    for score, fp in shp_candidates:
                        logger.info(f"  {score:.2f} | {fp.name} | {fp.stat().st_size/1024:.1f} KB")
                shp_file = shp_candidates[0][1]
                logger.info(f"Shapefile DPA seleccionado: {shp_file.name}")
                gdf = gpd.read_file(shp_file)
                comuna_cols = [c for c in gdf.columns if 'comuna' in c.lower() or 'nom_com' in c.lower()]
                if not comuna_cols:
                    logger.warning("No se detectó columna de comuna en shapefile DPA")
                    return False
                col = comuna_cols[0]
                target_norm = self._normalize(comuna_name).lower()
                def norm_val(v):
                    return self._normalize(str(v)).lower()
                filtered = gdf[[norm_val(v) == target_norm for v in gdf[col]]]
                if len(filtered) == 0:
                    logger.warning(f"Comuna '{comuna_name}' no encontrada en DPA")
                    return False
                if debug:
                    logger.info(f"Registro filtrado columnas: {filtered.columns.tolist()}")
                    logger.info(f"Área declarada (SUPERFICIE) si existe: {filtered.get('SUPERFICIE', 'N/A')}")
                out_file = self.output_dir / 'comuna_boundaries_oficial.geojson'
                filtered.to_file(out_file, driver='GeoJSON')
                logger.info(f"Límites oficiales DPA guardados en: {out_file}")
                return True
        except Exception as e:
            logger.error(f"Error procesando DPA oficial: {e}")
            if debug:
                traceback.print_exc()
            return False

    def create_metadata(self):
        """Crea archivo de metadatos de la descarga."""
        archivos = list(self.output_dir.glob('*'))
        fuentes = []
        if any(f.name.startswith('osm_') for f in archivos):
            fuentes.append('OpenStreetMap')
        if any(f.name.startswith('comuna_boundaries') for f in archivos) or any(f.name == 'osm_boundary.geojson' for f in archivos):
            fuentes.append('IDE Chile / OSM límites')
        if any(f.name == 'manzanas_censales.geojson' for f in archivos):
            fuentes.append('INE Censo 2017')
        if any(f.name == 'censo_manzanas_atributos.csv' for f in archivos):
            fuentes.append('INE Censo 2017 Microdatos')
        if any(f.name == 'srtm_dem.tif' for f in archivos):
            fuentes.append('SRTM DEM')
        if any(f.name.startswith('sentinel2_B') for f in archivos):
            fuentes.append('Sentinel-2 Copernicus')
        if any(f.name == 'uso_suelo_minvu.geojson' for f in archivos):
            fuentes.append('Uso de suelo MINVU')
        metadata = {
            'comuna': self.comuna,
            'fecha_descarga': datetime.now().isoformat(),
            'fuentes_detectadas': fuentes,
            'archivos_generados': [f.name for f in archivos]
        }

        metadata_file = self.output_dir / 'metadata.txt'
        with open(metadata_file, 'w') as f:
            f.write(json.dumps(metadata, ensure_ascii=False, indent=2))

        logger.info(f"Metadatos guardados en: {metadata_file}")

    def download_census_manzanas(self, arcgis_url: str, comuna_name: str, debug: bool=False) -> bool:
        """Descarga manzanas censales (INE) desde un ArcGIS FeatureService.

        arcgis_url debe apuntar directamente a la capa (terminar en /FeatureServer/<layerId>). Ejemplo:
        https://servicesX.arcgis.com/<token>/ArcGIS/rest/services/Manzanas_Censo_2017/FeatureServer/0

        Parámetros:
            arcgis_url: URL base de la capa (sin /query al final)
            comuna_name: nombre de la comuna para filtrar
        """
        if not arcgis_url:
            logger.error("No se proporcionó --censo-url. Abortando descarga de manzanas.")
            return False
        logger.info("Descargando manzanas censales (INE)...")
        try:
            query_endpoint = arcgis_url.rstrip('/') + '/query'

            # Construir lista de variantes posibles del nombre de comuna
            variantes = []
            originales = [comuna_name]
            normalizado = self._normalize(comuna_name)
            if normalizado != comuna_name:
                originales.append(normalizado)

            # Intentar obtener nombre oficial desde límites ya descargados
            oficial_path = self.output_dir / 'comuna_boundaries_oficial.geojson'
            if oficial_path.exists():
                try:
                    gdf_off = gpd.read_file(oficial_path)
                    nombre_cols = [c for c in gdf_off.columns if 'comuna' in c.lower() or 'nom_com' in c.lower()]
                    for col in nombre_cols:
                        for v in gdf_off[col].unique():
                            if isinstance(v, str):
                                originales.append(v.strip())
                except Exception as e:
                    if debug:
                        logger.info(f"No se pudo leer nombre oficial desde {oficial_path}: {e}")

            # Deduplicar manteniendo orden
            seen = set()
            for v in originales:
                v_clean = v.strip()
                if v_clean and v_clean.lower() not in seen:
                    variantes.append(v_clean)
                    seen.add(v_clean.lower())

            # Generar cláusulas WHERE (accent y normalizado)
            where_clauses = []
            for v in variantes:
                upper_v = v.upper().replace("'", "''")
                upper_norm = self._normalize(v).upper().replace("'", "''")
                # UPPER(COMUNA)=valor original
                where_clauses.append(f"UPPER(COMUNA)='{upper_v}'")
                # Si difiere la versión normalizada agregar también
                if upper_norm != upper_v:
                    where_clauses.append(f"UPPER(COMUNA)='{upper_norm}'")
            # Agregar comodín LIKE si ninguna exacta funciona
            like_pattern = self._normalize(comuna_name).upper().split()
            if like_pattern:
                prefix = like_pattern[0]
                if prefix and all(not w.startswith(prefix) for w in where_clauses):
                    where_clauses.append(f"UPPER(COMUNA) LIKE '{prefix}%'")

            if debug:
                logger.info("Variantes de comuna para censo: " + ", ".join(variantes))
                logger.info("Cláusulas WHERE a intentar: " + " | ".join(where_clauses))

            for where in where_clauses:
                params = {
                    'where': where,
                    'outFields': '*',
                    'returnGeometry': 'true',
                    'f': 'geojson',
                    'outSR': '4326'
                }
                if debug:
                    logger.info(f"Probando WHERE: {where}")
                r = requests.get(query_endpoint, params=params, timeout=180)
                if r.status_code != 200:
                    if debug:
                        logger.info(f"HTTP {r.status_code} para WHERE {where}")
                    continue
                data = r.json()
                features = data.get('features', []) if isinstance(data, dict) else []
                if features:
                    outfile = self.output_dir / 'manzanas_censales.geojson'
                    with open(outfile, 'w', encoding='utf-8') as f:
                        f.write(r.text)
                    logger.info(f"Manzanas censales guardadas en: {outfile} (features={len(features)}) usando WHERE: {where}")
                    return True
            logger.warning("No se obtuvieron manzanas tras probar variantes de nombre. Revise que la capa contenga la comuna.")
            return False
        except Exception as e:
            logger.error(f"Excepción descargando manzanas: {e}")
            if debug:
                traceback.print_exc()
            return False

    def download_census_microdatos(self, zip_url: str, comuna_id: int | None, debug: bool=False) -> bool:
        logger.info("Función obsoleta (reemplazada por download_and_extract_censo_rar + filter_censo_manzanas_by_comuna). No ejecuta trabajo.")
        return False

    def download_minvu_uso_suelo(self, minvu_url: str | None = None, local_path: str | None = None, debug: bool=False) -> bool:
        """Descarga y extrae ZIP de uso de suelo MINVU (Región Metropolitana).

        Fases actuales:
          1. Si se pasa --minvu-local y es zip/shp/geojson/json, copiar/convertir.
          2. Descargar ZIP oficial (Koha tracklinks) si no existe.
          3. Extraer todo a carpeta uso_suelo_minvu/ dentro de output_dir.
                    4. Filtrar shapefiles de la comuna y generar uso_suelo_minvu.geojson.
                    5. Mantener estructura IPT_Metropolitana pero podar PRC eliminando archivos de otras comunas.
        """
        # 1. Archivo local directo (permite saltar la descarga)
        if local_path:
            try:
                lp = Path(local_path)
                if not lp.exists():
                    logger.error(f"Ruta local MINVU no existe: {lp}")
                    return False
                if lp.suffix.lower() == '.zip':
                    logger.info("Extrayendo ZIP local MINVU...")
                    extract_dir = self.output_dir / 'uso_suelo_minvu'
                    extract_dir.mkdir(exist_ok=True)
                    with zipfile.ZipFile(lp, 'r') as zf:
                        zf.extractall(extract_dir)
                    logger.info(f"ZIP local MINVU extraído en: {extract_dir}")
                    return True
                out_geo = self.output_dir / 'uso_suelo_minvu.geojson'
                if lp.suffix.lower() == '.shp':
                    gdf_loc = gpd.read_file(lp)
                    gdf_loc.to_file(out_geo, driver='GeoJSON')
                    logger.info(f"Shapefile local MINVU convertido: {out_geo}")
                    return True
                elif lp.suffix.lower() in ['.geojson', '.json']:
                    shutil.copy2(lp, out_geo)
                    logger.info(f"GeoJSON/JSON local MINVU copiado a: {out_geo}")
                    return True
                else:
                    logger.error("Formato local MINVU no soportado por ahora. Use .zip/.shp/.geojson/.json")
                    return False
            except Exception as e_loc:
                logger.error(f"Error usando archivo local MINVU: {e_loc}")
                if debug:
                    traceback.print_exc()
                return False

        # 2. Descargar ZIP remoto
        url = minvu_url or DEFAULT_MINVU_USO_SUELO_URL
        zip_path = self.output_dir / 'uso_suelo_minvu.zip'
        extract_dir = self.output_dir / 'uso_suelo_minvu'
        if zip_path.exists():
            logger.info(f"ZIP MINVU ya existe: {zip_path.name} (omitimos descarga)")
        else:
            logger.info(f"Descargando ZIP MINVU desde: {url}")
            try:
                with requests.get(url, stream=True, timeout=300, allow_redirects=True) as r:
                    if r.status_code != 200:
                        logger.error(f"Status inesperado {r.status_code} descargando MINVU ZIP")
                        return False
                    total = int(r.headers.get('Content-Length', '0'))
                    downloaded = 0
                    with open(zip_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if debug and total > 0 and downloaded % (1024*1024) < 8192:
                                    pct = (downloaded/total)*100
                                    logger.info(f"Progreso ZIP MINVU: {pct:.1f}%")
                size_mb = zip_path.stat().st_size / 1e6
                logger.info(f"ZIP MINVU descargado ({size_mb:.2f} MB) en: {zip_path}")
            except Exception as e_dl:
                logger.error(f"Fallo descarga ZIP MINVU: {e_dl}")
                if debug:
                    traceback.print_exc()
                return False

        # 3. Extraer ZIP + filtrar comuna + borrar ZIP
        try:
            extract_dir.mkdir(exist_ok=True)
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_dir)
            logger.info(f"ZIP MINVU extraído en: {extract_dir}")
            shp_list = list(extract_dir.rglob('*.shp'))
            if shp_list:
                logger.info(f"Shapefiles encontrados MINVU: {', '.join([p.name for p in shp_list[:10]])}{' ...' if len(shp_list)>10 else ''}")
            else:
                logger.warning("No se encontraron .shp en ZIP MINVU (revisar estructura del paquete)")
            # Borrar ZIP para no duplicar espacio
            try:
                zip_path.unlink(missing_ok=True)
            except Exception as e_del:
                if debug:
                    logger.info(f"No se pudo borrar ZIP MINVU: {e_del}")
            # Filtrar shapefiles por comuna
            comuna_norm = self._normalize(self.comuna)
            tokens = comuna_norm.split()
            def _matches(path: Path) -> bool:
                norm_base = self._normalize(path.stem.replace('_', ' '))
                idx = 0
                for t in tokens:
                    pos = norm_base.find(t, idx)
                    if pos == -1:
                        return False
                    idx = pos + len(t)
                return True
            matches = [p for p in shp_list if _matches(p)]
            prc_matches = [p for p in matches if '_PRC_' in p.stem.upper()]
            chosen = prc_matches or matches
            if not chosen:
                logger.warning(f"Sin shapefiles que coincidan con la comuna '{self.comuna}'. Se deja sólo carpeta extraída.")
                return True
            if debug:
                logger.info("Seleccionados: " + ", ".join([c.name for c in chosen]))
            gdfs = []
            for shp in chosen:
                try:
                    gdf_tmp = gpd.read_file(shp)
                    gdfs.append(gdf_tmp)
                except Exception as e_read:
                    logger.warning(f"Fallo leyendo {shp.name}: {e_read}")
            if not gdfs:
                logger.warning("No se pudieron leer shapefiles seleccionados.")
                return True
            try:
                gdf_all = gpd.pd.concat(gdfs, ignore_index=True, sort=False)
            except Exception:
                gdf_all = gdfs[0]
                for extra in gdfs[1:]:
                    try:
                        gdf_all = gpd.GeoDataFrame(gdf_all.append(extra, ignore_index=True))
                    except Exception:
                        pass
            # Normalizar CRS a 4326
            try:
                if gdf_all.crs is None:
                    gdf_all.set_crs(4326, inplace=True)
                elif gdf_all.crs.to_epsg() != 4326:
                    gdf_all = gdf_all.to_crs(4326)
            except Exception as e_crs:
                if debug:
                    logger.info(f"No se pudo ajustar CRS MINVU: {e_crs}")
            out_geojson = self.output_dir / 'uso_suelo_minvu.geojson'
            try:
                gdf_all.to_file(out_geojson, driver='GeoJSON')
                logger.info(f"Uso de suelo MINVU filtrado guardado: {out_geojson} (features={len(gdf_all)})")
            except Exception as e_write:
                logger.error(f"Error escribiendo uso_suelo_minvu.geojson: {e_write}")
            # Podar subcarpeta PRC eliminando conjuntos de otras comunas
            try:
                prc_dir = extract_dir / 'IPT_Metropolitana' / 'PRC'
                if prc_dir.exists():
                    chosen_stems = {p.stem for p in chosen}
                    removed = 0
                    for f in prc_dir.iterdir():
                        name = f.name
                        # Determinar stem real del shapefile (shp.xml -> quitar sufijo)
                        if name.endswith('.shp.xml'):
                            stem = name[:-8]
                        else:
                            stem = Path(name).stem
                        if stem not in chosen_stems:
                            try:
                                f.unlink()
                                removed += 1
                            except Exception:
                                if debug:
                                    logger.info(f"No se pudo borrar {f.name}")
                    if removed > 0:
                        logger.info(f"Podados {removed} archivos PRC ajenos a la comuna {self.comuna}.")
                    else:
                        logger.info("No había archivos PRC adicionales que podar.")
            except Exception as e_prune:
                if debug:
                    logger.info(f"Error podando PRC: {e_prune}")
            return True
        except Exception as e_ext:
            logger.error(f"Error extrayendo/filtrando ZIP MINVU: {e_ext}")
            if debug:
                traceback.print_exc()
            return False

    def _load_boundary_for_dem(self, debug: bool=False):
        """Obtiene geometría de límites para recorte DEM.

        Prioridad: límites oficiales DPA -> fallback OSM guardado -> boundary_gdf en memoria -> geocode.
        Devuelve GeoDataFrame (EPSG:4326) o None.
        """
        try:
            gdf = self.boundary_gdf
            if gdf.crs is None:
                gdf = gdf.set_crs(4326)
            elif gdf.crs.to_epsg() != 4326:
                gdf = gdf.to_crs(4326)
            return gdf
        except Exception as e:
            if debug:
                logger.info(f"No se pudo usar boundary_gdf para DEM: {e}")
        # Geocode directo (último recurso)
        try:
            if hasattr(ox, 'geocode_to_gdf'):
                gdf = ox.geocode_to_gdf(f"{self.comuna}, Chile")
                if gdf.crs is None:
                    gdf = gdf.set_crs(4326)
                elif gdf.crs.to_epsg() != 4326:
                    gdf = gdf.to_crs(4326)
                return gdf
        except Exception as e:
            if debug:
                logger.info(f"No se pudo geocodificar comuna para DEM: {e}")
        return None

    def download_srtm_tiles(self, debug: bool=False) -> bool:
        """Descarga tiles SRTM3 (.hgt) públicos, genera mosaico y recorta a límites comunales.

        Guarda:
          - Tiles .hgt en el directorio de salida.
          - Mosaico recortado: srtm_dem.tif
        """
        boundary = self._load_boundary_for_dem(debug=debug)
        if boundary is None or boundary.empty:
            logger.warning("No hay límites para SRTM.")
            return False
        # Bounding box
        minx, miny, maxx, maxy = boundary.total_bounds
        import math, gzip
        logger.info(f"BBox límites: minx={minx:.4f} miny={miny:.4f} maxx={maxx:.4f} maxy={maxy:.4f}")
        # Candidatos southwestern corners (mínimo número de tiles)
        lat_sw = {math.floor(miny), math.floor(maxy - 1e-9)}
        lon_sw = {math.floor(minx), math.floor(maxx - 1e-9)}
        def tile_code(lat_sw, lon_sw):
            ns = 'N' if lat_sw >= 0 else 'S'
            ew = 'E' if lon_sw >= 0 else 'W'
            return f"{ns}{abs(lat_sw):02d}{ew}{abs(lon_sw):03d}"  # ejemplo S33W071
        codes = sorted({tile_code(la, lo) for la in lat_sw for lo in lon_sw})
        logger.info(f"Tiles SRTM candidatos (SW corners): {codes}")
        hgt_files = []
        for code in codes:
            base = self.output_dir / f"{code}.hgt"
            if base.exists():
                hgt_files.append(base)
                continue
            urls = [
                f"https://srtm.kurviger.de/SRTM3/{code}.hgt.gz",
                f"https://dds.cr.usgs.gov/srtm/version2_1/SRTM3/South_America/{code}.hgt.zip",
                f"https://srtm.kurviger.de/SRTM3/{code}.hgt",
                f"https://srtmtiles.s3.amazonaws.com/{code}.hgt.gz",
                # Mapzen Skadi (subcarpeta por los primeros 3 caracteres: e.g. S34/S34W071.hgt.gz)
                f"https://s3.amazonaws.com/elevation-tiles-prod/skadi/{code[:3]}/{code}.hgt.gz"
            ]
            downloaded = False
            for url in urls:
                try:
                    if debug:
                        logger.info(f"Intentando URL tile {code}: {url}")
                    r = requests.get(url, timeout=120)
                    if r.status_code != 200:
                        if debug:
                            logger.info(f"Status {r.status_code} para {url}")
                        continue
                    if url.endswith('.gz'):
                        gz_path = self.output_dir / f"{code}.hgt.gz"
                        gz_path.write_bytes(r.content)
                        with gzip.open(gz_path, 'rb') as gzf:
                            base.write_bytes(gzf.read())
                        gz_path.unlink(missing_ok=True)
                    elif url.endswith('.zip'):
                        ztmp = self.output_dir / f"{code}.zip"
                        ztmp.write_bytes(r.content)
                        with zipfile.ZipFile(ztmp, 'r') as zf:
                            for member in zf.namelist():
                                if member.lower().endswith('.hgt'):
                                    with zf.open(member) as srcf:
                                        base.write_bytes(srcf.read())
                                    break
                        ztmp.unlink(missing_ok=True)
                    if base.exists():
                        size = base.stat().st_size
                        if size < 2000000:  # SRTM3 ~ 2.9MB uncompressed (1201*1201*2 bytes)
                            logger.warning(f"Tile {code} tamaño inesperado ({size} bytes).")
                        hgt_files.append(base)
                        downloaded = True
                        logger.info(f"Tile {code} descargado desde {url}")
                        break
                except Exception as e:
                    if debug:
                        logger.info(f"Error tile {code} con {url}: {e}")
            if not downloaded:
                logger.warning(f"No se pudo descargar tile {code}")
        if not hgt_files:
            logger.warning("Sin tiles SRTM exitosos. Reintentando con enumeración completa de rango y mirrors.")
            # Enumeración completa de lats/lons (método original) como segundo intento
            full_lons = range(math.floor(minx), math.ceil(maxx) + 1)
            full_lats = range(math.floor(miny), math.ceil(maxy) + 1)
            full_codes = sorted({tile_code(la, lo) for la in full_lats for lo in full_lons})
            logger.info(f"Segundo intento tiles completos: {full_codes}")
            for code in full_codes:
                base = self.output_dir / f"{code}.hgt"
                if base.exists():
                    hgt_files.append(base)
                    continue
                urls = [
                    f"https://srtm.kurviger.de/SRTM3/{code}.hgt.gz",
                    f"https://dds.cr.usgs.gov/srtm/version2_1/SRTM3/South_America/{code}.hgt.zip",
                    f"https://srtm.kurviger.de/SRTM3/{code}.hgt",
                    f"https://srtmtiles.s3.amazonaws.com/{code}.hgt.gz",
                    f"https://s3.amazonaws.com/elevation-tiles-prod/skadi/{code[:3]}/{code}.hgt.gz"
                ]
                downloaded2 = False
                for url in urls:
                    try:
                        if debug:
                            logger.info(f"(Segundo intento) URL tile {code}: {url}")
                        r = requests.get(url, timeout=120)
                        if r.status_code != 200:
                            if debug:
                                logger.info(f"Status {r.status_code} para {url}")
                            continue
                        if url.endswith('.gz'):
                            gz_path = self.output_dir / f"{code}.hgt.gz"
                            gz_path.write_bytes(r.content)
                            with gzip.open(gz_path, 'rb') as gzf:
                                base.write_bytes(gzf.read())
                            gz_path.unlink(missing_ok=True)
                        elif url.endswith('.zip'):
                            ztmp = self.output_dir / f"{code}.zip"
                            ztmp.write_bytes(r.content)
                            with zipfile.ZipFile(ztmp, 'r') as zf:
                                for member in zf.namelist():
                                    if member.lower().endswith('.hgt'):
                                        with zf.open(member) as srcf:
                                            base.write_bytes(srcf.read())
                                        break
                            ztmp.unlink(missing_ok=True)
                        elif url.endswith('.hgt'):
                            base.write_bytes(r.content)
                        if base.exists():
                            size = base.stat().st_size
                            if size < 2000000:
                                logger.warning(f"Tile {code} tamaño inesperado ({size} bytes) segundo intento.")
                            hgt_files.append(base)
                            downloaded2 = True
                            logger.info(f"Tile {code} descargado (segundo intento) desde {url}")
                            break
                    except Exception as e:
                        if debug:
                            logger.info(f"Error segundo intento tile {code} con {url}: {e}")
                if not downloaded2:
                    logger.warning(f"Segundo intento falló para tile {code}")
        if not hgt_files:
            logger.warning("Sin tiles SRTM tras segundo intento. Usando fallback directo Mapzen + Copernicus.")
            # Intento final: forzar descarga Mapzen Skadi tile(s) esperados (lat sur usa S34 para -33.x)
            expected_lat = math.floor(miny)  # e.g. -34
            expected_lon = math.floor(minx)  # e.g. -71
            code_force = tile_code(expected_lat, expected_lon)
            logger.info(f"Forzando descarga Mapzen tile esperado: {code_force}")
            mapzen_url = f"https://s3.amazonaws.com/elevation-tiles-prod/skadi/{code_force[:3]}/{code_force}.hgt.gz"
            try:
                r = requests.get(mapzen_url, timeout=180)
                if r.status_code == 200:
                    gz_path = self.output_dir / f"{code_force}.hgt.gz"
                    gz_path.write_bytes(r.content)
                    with gzip.open(gz_path, 'rb') as gzf:
                        raw_bytes = gzf.read()
                    base_force = self.output_dir / f"{code_force}.hgt"
                    base_force.write_bytes(raw_bytes)
                    size = base_force.stat().st_size
                    logger.info(f"Tile forzado {code_force} tamaño {size} bytes")
                    if size > 1000000:
                        hgt_files.append(base_force)
                else:
                    logger.warning(f"Mapzen forzado status {r.status_code}")
            except Exception as e_forced:
                if debug:
                    logger.info(f"Error descarga forzada Mapzen: {e_forced}")
            if not hgt_files:
                # Copernicus DEM búsqueda con bbox ampliado
                try:
                    from pystac_client import Client
                    import planetary_computer as pc
                    buffer = 0.05
                    bbox_buf = [minx-buffer, miny-buffer, maxx+buffer, maxy+buffer]
                    catalog = Client.open('https://planetarycomputer.microsoft.com/api/stac/v1')
                    search = catalog.search(collections=['copernicus-dem-glo-30'], bbox=bbox_buf, limit=10)
                    items = list(search.items()) if hasattr(search, 'items') else list(search.get_items())
                    if not items:
                        logger.warning("No se encontró Copernicus DEM para bbox ampliado.")
                        return False
                    item = items[0]
                    signed = pc.sign(item)
                    asset = signed.assets.get('data') or signed.assets.get('DEM') or list(signed.assets.values())[0]
                    import rasterio
                    from rasterio.mask import mask
                    out_cop = self.output_dir / 'copernicus_dem.tif'
                    with rasterio.open(asset.href) as src:
                        geom = boundary
                        if geom.crs and src.crs and geom.crs.to_string() != src.crs.to_string():
                            geom = geom.to_crs(src.crs)
                        geoms = [g.__geo_interface__ for g in geom.geometry]
                        clipped, transform = mask(src, geoms, crop=True)
                        meta = src.meta.copy()
                        meta.update({'height': clipped.shape[1], 'width': clipped.shape[2], 'transform': transform})
                    with rasterio.open(out_cop, 'w', **meta) as dst:
                        dst.write(clipped)
                    logger.info(f"Copernicus DEM recortado guardado: {out_cop}")
                    try:
                        self._reproject_dem(out_cop, 32719)
                    except Exception as e2:
                        if debug:
                            logger.info(f"No se pudo reproyectar Copernicus DEM: {e2}")
                    return True
                except Exception as e3:
                    logger.error(f"Fallback Copernicus DEM (ampliado) falló: {e3}")
                    if debug:
                        traceback.print_exc()
                    return False
            # Si se logró forzar al menos un tile, continuar a mosaico
            if not hgt_files:
                return False
        # Mosaico / single tile y recorte
        try:
            import rasterio
            from rasterio.mask import mask
            if len(hgt_files) == 1:
                # Caso simple: un solo tile, recortar directamente
                tile_path = hgt_files[0]
                with rasterio.open(tile_path) as src:
                    geom_gdf = boundary
                    if geom_gdf.crs and src.crs and geom_gdf.crs.to_string() != src.crs.to_string():
                        geom_gdf = geom_gdf.to_crs(src.crs)
                    geoms = [g.__geo_interface__ for g in geom_gdf.geometry]
                    clipped, clipped_transform = mask(src, geoms, crop=True)
                    meta = src.meta.copy()
                    meta.update({'driver': 'GTiff', 'height': clipped.shape[1], 'width': clipped.shape[2], 'transform': clipped_transform})
                out_path = self.output_dir / 'srtm_dem.tif'
                with rasterio.open(out_path, 'w', **meta) as dst:
                    dst.write(clipped)
                logger.info(f"DEM SRTM (single tile) recortado guardado: {out_path}")
            else:
                from rasterio.merge import merge
                srcs = [rasterio.open(str(p)) for p in hgt_files]
                mosaic, transform = merge(srcs)
                meta = srcs[0].meta.copy()
                meta.update({
                    'driver': 'GTiff',
                    'height': mosaic.shape[1],
                    'width': mosaic.shape[2],
                    'transform': transform,
                    'count': mosaic.shape[0]
                })
                geom_gdf = boundary.to_crs(srcs[0].crs) if srcs[0].crs and boundary.crs and srcs[0].crs.to_string()!=boundary.crs.to_string() else boundary
                geoms = [g.__geo_interface__ for g in geom_gdf.geometry]
                tmp_path = self.output_dir / 'srtm_mosaic_tmp.tif'
                with rasterio.open(tmp_path, 'w', **meta) as tmp:
                    tmp.write(mosaic)
                with rasterio.open(tmp_path) as tmp:
                    clipped, clipped_transform = mask(tmp, geoms, crop=True)
                    meta.update({'height': clipped.shape[1], 'width': clipped.shape[2], 'transform': clipped_transform})
                out_path = self.output_dir / 'srtm_dem.tif'
                with rasterio.open(out_path, 'w', **meta) as dst:
                    dst.write(clipped)
                os.remove(tmp_path)
                logger.info(f"DEM SRTM (mosaico) recortado guardado: {out_path}")
            # Reproyección automática a EPSG:32719
            try:
                self._reproject_dem(out_path, 32719)
            except Exception as e:
                if debug:
                    logger.info(f"No se pudo reproyectar SRTM: {e}")
            return True
        except Exception as e:
            logger.error(f"Error procesando SRTM: {e}")
            if debug:
                traceback.print_exc()
            return False

    def _reproject_dem(self, dem_path: Path, target_epsg: int = 32719):
        """Reproyecta un raster DEM a CRS destino generando archivo *_<epsg>.tif."""
        import rasterio
        from rasterio.warp import calculate_default_transform, reproject, Resampling
        out_path = dem_path.parent / f"{dem_path.stem}_{target_epsg}.tif"
        with rasterio.open(dem_path) as src:
            dst_crs = f"EPSG:{target_epsg}"
            transform, width, height = calculate_default_transform(src.crs, dst_crs, src.width, src.height, *src.bounds)
            meta = src.meta.copy()
            meta.update({"crs": dst_crs, "transform": transform, "width": width, "height": height})
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
        logger.info(f"DEM reproyectado guardado: {out_path.name}")

    def download_sentinel2(self, days_back: int = 90, cloud_lt: int = 20, limit: int = 1, debug: bool=False) -> bool:
        """Descarga bandas Sentinel-2 (B04,B08) vía Planetary Computer STAC y las guarda en raw.

        Parámetros:
          - days_back: ventana temporal hacia atrás (días) desde ayer.
          - cloud_lt: nubosidad máxima.
          - limit: máximo de escenas a inspeccionar (descarga la de menor nubosidad).
        """
        try:
            from pystac_client import Client
            import planetary_computer as pc
        except Exception:
            os.system("pip -q install pystac-client planetary-computer")
            from pystac_client import Client
            import planetary_computer as pc
        boundary = self._load_boundary_for_dem(debug=debug)
        if boundary is None or boundary.empty:
            logger.warning("No hay límites para Sentinel-2.")
            return False
        minx, miny, maxx, maxy = boundary.total_bounds
        from datetime import date, timedelta
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=days_back)
        logger.info(f"Buscando Sentinel-2 bbox=[{minx:.4f},{miny:.4f},{maxx:.4f},{maxy:.4f}] rango={start.isoformat()}..{end.isoformat()} nubosidad<={cloud_lt}")
        catalog = Client.open('https://planetarycomputer.microsoft.com/api/stac/v1')
        search = catalog.search(
            collections=['sentinel-2-l2a'],
            bbox=[minx, miny, maxx, maxy],
            datetime=f"{start.isoformat()}/{end.isoformat()}",
            query={'eo:cloud_cover': {'lt': cloud_lt}},
            limit=limit
        )
        try:
            items = list(search.items())
        except Exception:
            items = list(search.get_items())
        if not items:
            logger.warning("Sin escenas Sentinel-2 encontradas en ventana / criterio.")
            return False
        logger.info(f"Escenas encontradas: {len(items)}")
        item = sorted(items, key=lambda it: it.properties.get('eo:cloud_cover', 100))[0]
        logger.info(f"Escena seleccionada ID={item.id} nubosidad={item.properties.get('eo:cloud_cover')}%")
        signed = pc.sign(item)
        red = signed.assets.get('B04')
        nir = signed.assets.get('B08')
        if not red or not nir:
            logger.warning("Escena sin bandas B04/B08 disponibles.")
            return False
        red_out = self.output_dir / 'sentinel2_B04.tif'
        nir_out = self.output_dir / 'sentinel2_B08.tif'
        def _stream_clip(asset, out_path):
            import rasterio
            from rasterio.mask import mask
            logger.info(f"Clip remoto banda {asset.title}")
            href = asset.href
            for attempt in range(3):
                try:
                    with rasterio.open(href) as src:
                        geom = boundary
                        if geom.crs and src.crs and geom.crs.to_string() != src.crs.to_string():
                            geom = geom.to_crs(src.crs)
                        geoms = [g.__geo_interface__ for g in geom.geometry]
                        clipped, transform = mask(src, geoms, crop=True)
                        meta = src.meta.copy()
                        meta.update({'height': clipped.shape[1], 'width': clipped.shape[2], 'transform': transform})
                    with rasterio.open(out_path, 'w', **meta) as dst:
                        dst.write(clipped)
                    size = out_path.stat().st_size if out_path.exists() else 0
                    logger.info(f"Banda {asset.title} recortada (intento {attempt+1}, ~{size/1e6:.2f} MB)")
                    return True
                except Exception as e:
                    logger.warning(f"Fallo clip intento {attempt+1} {asset.title}: {e}")
                    try:
                        href = pc.sign(asset).href
                    except Exception:
                        pass
            return False
        ok_red = _stream_clip(red, red_out)
        ok_nir = _stream_clip(nir, nir_out)
        if not (ok_red and ok_nir):
            logger.warning("Clip remoto falló para alguna banda; usando fallback descarga completa.")
            import urllib.request, rasterio
            from rasterio.mask import mask
            def _download_then_clip(asset, out_path):
                tmp_full = self.output_dir / (out_path.stem + '_full.tmp')
                for attempt in range(2):
                    try:
                        urllib.request.urlretrieve(asset.href, tmp_full)
                        with rasterio.open(tmp_full) as src:
                            geom = boundary
                            if geom.crs and src.crs and geom.crs.to_string() != src.crs.to_string():
                                geom = geom.to_crs(src.crs)
                            geoms = [g.__geo_interface__ for g in geom.geometry]
                            clipped, transform = mask(src, geoms, crop=True)
                            meta = src.meta.copy()
                            meta.update({'height': clipped.shape[1], 'width': clipped.shape[2], 'transform': transform})
                        with rasterio.open(out_path, 'w', **meta) as dst:
                            dst.write(clipped)
                        tmp_full.unlink(missing_ok=True)
                        logger.info(f"Banda {asset.title} descargada completa y recortada.")
                        return True
                    except Exception as e:
                        logger.warning(f"Fallback intento {attempt+1} {asset.title} error: {e}")
                tmp_full.unlink(missing_ok=True)
                return False
            if not ok_red:
                ok_red = _download_then_clip(red, red_out)
            if not ok_nir:
                ok_nir = _download_then_clip(nir, nir_out)
        if not (ok_red and ok_nir):
            logger.warning("Fallo final alguna banda Sentinel-2.")
            return False
        logger.info(f"Bandas Sentinel-2 guardadas: {red_out.name}, {nir_out.name}")
        return True
    
    def download_and_extract_censo_rar(self, url: str) -> bool:
        """Descarga un archivo RAR y lo extrae automáticamente dentro de output_dir."""
        try:
            import rarfile
            import shutil
            from pathlib import Path
            import subprocess

            filename = url.split("/")[-1]
            rar_path = self.output_dir / filename
            extract_dir = self.output_dir / filename.replace(".rar", "")

            # 1) Descargar
            logger.info(f"Descargando RAR desde: {url}")
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(rar_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            logger.info(f"RAR descargado en: {rar_path}")

            # Crear carpeta destino
            extract_dir.mkdir(exist_ok=True)

            # 2) Intentar extraer usando rarfile (requiere unrar instalado)
            try:
                if rarfile.is_rarfile(str(rar_path)):
                    with rarfile.RarFile(rar_path) as rf:
                        rf.extractall(path=extract_dir)
                    logger.info(f"RAR extraído con rarfile en: {extract_dir}")
                else:
                    raise Exception("No es un archivo RAR válido o rarfile no soporta este formato")

            except Exception as e:
                logger.warning(f"Fallo extracción con rarfile: {e}. Intentando 7zip...")

                # Fallback 7zip (Windows-friendly)
                sevenzip = shutil.which("7z") or shutil.which("7zz") or r"C:/Program Files/7-Zip/7z.exe"
                if not sevenzip or not Path(sevenzip).exists():
                    logger.error("No se encontró 7zip. Instala 7zip o unrar para extraer el archivo.")
                    return False

                cmd = [sevenzip, "x", "-y", str(rar_path), f"-o{extract_dir}"]
                result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode != 0:
                    logger.error(f"7zip falló al extraer: {result.stderr[:200]}")
                    return False

                logger.info(f"RAR extraído correctamente con 7zip en: {extract_dir}")

            # 3) Eliminar el .rar opcionalmente
            rar_path.unlink(missing_ok=True)

            return True

        except Exception as e:
            logger.error(f"Error descargando y extrayendo RAR: {e}")
            return False
        
    def filter_censo_manzanas_by_comuna(self, comuna_name: str) -> bool:
        import pandas as pd
        import os

        base_dir = self.output_dir / "Censo2017_ManzanaEntidad_CSV"

        # Detectar carpeta interna
        subdirs = [d for d in base_dir.iterdir() if d.is_dir()]
        if not subdirs:
            logger.error(f"No se encontró subcarpeta interna dentro de {base_dir}")
            return False

        inner_dir = subdirs[0]
        logger.info(f"Detectada carpeta interna: {inner_dir}")

        manzanas_csv = inner_dir / "Censo2017_Manzanas.csv"
        geo_dir = inner_dir / "Censo2017_Identificación_Geográfica"
        comunas_csv = geo_dir / "Microdato_Censo2017-Comunas.csv"

        if not comunas_csv.exists():
            logger.error(f"No se encontró Microdato_Censo2017-Comunas.csv en {geo_dir}")
            return False
        if not manzanas_csv.exists():
            logger.error(f"No se encontró Censo2017_Manzanas.csv en {inner_dir}")
            return False

        # 1. Forzar encoding correcto
        df_com = self._safe_read_csv(comunas_csv)



        # 2. Normalizar entrada
        comuna_user_norm = self._normalize(comuna_name)

        # 3. Normalizar CSV
        df_com["NOM_COMUNA_NORM"] = df_com["NOM_COMUNA"].apply(self._normalize)

        # 4. Buscar coincidencia exacta
        # 1. Intento exacto
        fila = df_com[df_com["NOM_COMUNA_NORM"] == comuna_user_norm]

        # 2. Intento parcial
        if fila.empty:
            fila = df_com[df_com["NOM_COMUNA_NORM"].str.contains(comuna_user_norm, na=False)]

        # 3. Fuzzy match (fallback final)
        if fila.empty:
            possible = df_com["NOM_COMUNA_NORM"].tolist()
            best = self._closest_match(comuna_user_norm, possible, cutoff=0.70)

            if best:
                logger.warning(f"Usando fuzzy match: '{comuna_name}' → '{best}'")
                fila = df_com[df_com["NOM_COMUNA_NORM"] == best]

        # 4. Si aun así no encuentra → error
        if fila.empty:
            logger.error(f"No se encontró código de comuna para '{comuna_name}'")
            logger.error(f"Valores en CSV normalizados: {df_com['NOM_COMUNA_NORM'].unique()}")
            return False

        
        if fila.empty:
            logger.error(f"No se encontró código de comuna para '{comuna_name}'")
            logger.error(f"Valores en CSV normalizados: {df_com['NOM_COMUNA_NORM'].unique()}")
            return False

        codigo_comuna = fila["COMUNA"].iloc[0]
        logger.info(f"Código de comuna detectado: {codigo_comuna}")

        # 5. Quitar read-only del archivo antes de escribir
        try:
            os.chmod(manzanas_csv, 0o666)  # quitar solo-lectura
        except:
            pass

        # 6. Filtrar manzanas
        df_manz = self._safe_read_csv(manzanas_csv)

        df_filtrado = df_manz[df_manz["COMUNA"] == codigo_comuna]

        logger.info(f"Filas originales: {len(df_manz)}, filtradas: {len(df_filtrado)}")

        # 7. Guardar sobreescribiendo
        df_filtrado.to_csv(manzanas_csv, sep=";", index=False)
        logger.info(f"Archivo filtrado guardado en {manzanas_csv}")

        return True







@click.command()
@click.option('--comuna', required=True, help='Nombre de la comuna')
@click.option('--output', default='data/raw', show_default=True, help='Directorio de salida relativo al root del proyecto')
@click.option('--sources', default='all', show_default=True, help='Fuentes a descargar (osm,ide,ine_manzanas_censales,ine_censo2017,censo,srtm,copernicus,all). Separar múltiples con coma: ej. "osm,ide,srtm,copernicus"')
@click.option('--skip-wfs', is_flag=True, help='Omitir descarga de límites administrativos (WFS IDE Chile)')
@click.option('--debug', is_flag=True, help='Modo debug: logging adicional y trazas de error')
@click.option('--wfs-url', default=None, help='Override URL WFS para límites administrativos')
@click.option('--dpa-url', default='https://www.geoportal.cl/geoportal/catalog/download/912598ad-ac92-35f6-8045-098f214bd9c2', show_default=True, help='URL ZIP DPA oficial para límites administrativos')
@click.option('--censo-url', default=None, help='URL ArcGIS FeatureService capa de manzanas (termina en /FeatureServer/<layerId>)')
@click.option('--download-censo', is_flag=True, help='(DEPRECATED) Usar sources=censo. Mantenido por compatibilidad.')
@click.option('--censo-micro-url', default=None, help='URL directa ZIP microdatos Redatam (manzana)')
@click.option('--censo-comuna-id', default=None, type=int, help='Código oficial de comuna para filtrar microdatos (ej 13129)')
@click.option('--minvu-url', default=None, help='Override URL(s) MINVU uso de suelo separados por coma si se desea probar múltiples')
@click.option('--minvu-local', default=None, type=click.Path(exists=True), help='Archivo local uso de suelo (geojson/json/shp) para saltar descarga')
def main(comuna, output, sources, skip_wfs, debug, wfs_url, dpa_url, censo_url, download_censo, censo_micro_url, censo_comuna_id, minvu_url, minvu_local):
    """Script principal para descarga de datos."""

    logger.info("=" * 50)
    logger.info("INICIANDO DESCARGA DE DATOS")
    logger.info("=" * 50)

    # Normalizar path de salida para permitir ejecución desde cualquier carpeta dentro del proyecto
    output_path = Path(output)
    if not output_path.exists():
        try:
            output_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"No se pudo crear directorio {output_path}: {e}")
            sys.exit(1)

    # Saneamiento básico del parámetro comuna por si el usuario incluyó accidentalmente flags dentro de las comillas
    raw_comuna = comuna.strip()
    if '--sources' in raw_comuna or '--debug' in raw_comuna:
        # Cortar en el primer flag conocido y quedarnos sólo con la parte anterior
        for flag in ['--sources', '--debug', '--skip-wfs', '--censo-url', '--censo-micro-url', '--censo-comuna-id']:
            if flag in raw_comuna:
                raw_comuna = raw_comuna.split(flag)[0].strip().strip('"').strip("'")
                logger.warning(f"Detectado flag embebido dentro de --comuna. Usando comuna sanitizada='{raw_comuna}'.")
                break
    downloader = DataDownloader(raw_comuna, output_path)

    # Parseo de fuentes: permitir lista separada por coma.
    sources_raw = sources.strip().lower()
    if sources_raw == 'all':
        # Conjunto completo: incluye SRTM y Copernicus
        sources_list = ['osm', 'ide', 'censo', 'srtm', 'copernicus']
    else:
        sources_list = [s.strip() for s in sources_raw.split(',') if s.strip()]

    # Alias varias fuentes:
    # Manzanas censales: ine_manzanas_censales / manzanas / manzanas_censales -> censo
    # DEM: dem / strm -> srtm
    # Sentinel-2: sentinel / sentinel2 -> copernicus
    normalized_sources = []
    auto_micro = False
    for s in sources_list:
        if s in ['ine_manzanas_censales', 'manzanas', 'manzanas_censales']:
            normalized_sources.append('censo')
        elif s in ['ine_censo2017']:
            normalized_sources.append('censo')
            auto_micro = True
        elif s in ['dem', 'strm']:
            normalized_sources.append('srtm')
        elif s in ['sentinel', 'sentinel2']:
            normalized_sources.append('copernicus')
        elif s in ['ide_minvu','minvu','uso_suelo','usosuelo','suelo']:
            normalized_sources.append('ide_minvu')
        else:
            normalized_sources.append(s)
    sources_list = normalized_sources

    # Backward compatibility: si se pasó --download-censo activar 'censo'
    if download_censo and 'censo' not in sources_list:
        sources_list.append('censo')

    logger.info(f"Fuentes solicitadas: {sources_list}")

    # OSM
    if 'osm' in sources_list:
        ok_osm = downloader.download_osm_data(debug=debug)
        if not ok_osm:
            logger.warning("Descarga OSM incompleta (red/edificios/amenidades). Revise logs.")

    # Límites IDE (WFS + DPA + fallback)
    if 'ide' in sources_list:
        ok_wfs = False
        ok_dpa = False
        if not skip_wfs:
            ok_wfs = downloader.download_boundaries(wfs_url_override=wfs_url)
            if not ok_wfs:
                logger.warning("Límites WFS no descargados. Se intentará DPA o fallback.")
        else:
            logger.info("--skip-wfs activo: se omite descarga de límites (WFS)")
        if (skip_wfs or not ok_wfs):
            ok_dpa = downloader.download_boundaries_dpa_zip(dpa_url=dpa_url, comuna_name=comuna, debug=debug)
            if not ok_dpa:
                logger.info("Usando fallback OSM para límites (geocode_to_gdf).")
                downloader.save_osm_boundary_fallback()

    # Censo manzanas
    if 'censo' in sources_list:
        if not censo_url:
            censo_url = DEFAULT_CENSO_URL
            logger.info(f"Usando URL censo por defecto: {censo_url}")
        ok_censo = downloader.download_census_manzanas(arcgis_url=censo_url, comuna_name=comuna, debug=debug)
        if ok_censo:
            logger.info("Manzanas censales descargadas correctamente.")
        else:
            logger.warning("Fallo descarga de manzanas censales. Revise --censo-url (o el fallback) y nombre de comuna.")
        # Configuración automática microdatos si fuente ine_censo2017
        if auto_micro and not censo_micro_url:
            censo_micro_url = DEFAULT_CENSO_MICRO_URL
            logger.info(f"Usando microdatos por defecto: {censo_micro_url}")

        if auto_micro:
            logger.info("Descargando y descomprimiendo microdatos RAR...")
            downloader.download_and_extract_censo_rar(censo_micro_url)
            # Filtrar archivo principal según la comuna ingresada
            logger.info(f"Filtrando microdatos para la comuna '{comuna}'...")
            downloader.filter_censo_manzanas_by_comuna(comuna)


        # Microdatos manuales usando nuevo flujo (si se proporcionan y no auto_micro)
        if censo_micro_url and not auto_micro:
            logger.info("Procesando microdatos manuales (nuevo flujo)...")
            downloader.download_and_extract_censo_rar(censo_micro_url)
            downloader.filter_censo_manzanas_by_comuna(comuna)

    # SRTM (fuente srtm) - usar método basado en tiles si disponible
    if 'srtm' in sources_list:
        try:
            ok_srtm = downloader.download_srtm_tiles(debug=debug)
            if ok_srtm:
                logger.info("SRTM descargado y mosaico generado correctamente.")
            else:
                logger.warning("Fallo descarga SRTM (sin tiles válidos).")
        except AttributeError:
            logger.warning("Método download_srtm_tiles no implementado en DataDownloader.")
        except Exception as e:
            logger.error(f"Error inesperado SRTM: {e}")

    # Sentinel-2 (Copernicus)
    if 'copernicus' in sources_list:
        try:
            ok_s2 = downloader.download_sentinel2(debug=debug)
            if ok_s2:
                logger.info("Sentinel-2 (Copernicus) descargado correctamente (B04/B08).")
            else:
                logger.warning("Fallo descarga Sentinel-2.")
        except AttributeError:
            logger.warning("Método download_sentinel2 no implementado en DataDownloader.")
        except Exception as e:
            logger.error(f"Error inesperado Sentinel-2: {e}")

    # Uso de suelo MINVU
    if 'ide_minvu' in sources_list:
        ok_minvu = downloader.download_minvu_uso_suelo(minvu_url=minvu_url, local_path=minvu_local, debug=debug)
        if ok_minvu:
            logger.info("Uso de suelo MINVU descargado correctamente.")
        else:
            logger.warning("Fallo descarga uso de suelo MINVU.")

    # Metadatos finales
    downloader.create_metadata()

    logger.info("Descarga completada!")
    logger.info("Archivos generados:")
    for f in sorted(output_path.glob('*')):
        logger.info(f" - {f.name}")


if __name__ == '__main__':
    main()
