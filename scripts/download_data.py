#!/usr/bin/env python3
"""
Script para descargar datos geoespaciales de la comuna seleccionada (ej. "San Joaquín").
Para descargar todos los datos solicitados, ejecutar:
- python download_data.py --comuna "San Joaquín" --sources all
"""

import os  # Para la gestión de variables de entorno y rutas del sistema operativo
import sys  # Para los parámetros y funciones específicas del intérprete de Python
import stat  # Para la definición de constantes para permisos de archivos
import click  # Para la creación de interfaces de línea de comandos (CLI) 
import requests  # Para la realización de peticiones HTTP para descarga de datos web
import geopandas as gpd  # Para la manipulación y análisis de datos geoespaciales vectoriales
import pandas as pd  # Para el procesamiento y análisis de datos tabulares (CSV, Excel)
import osmnx as ox  # Para la descarga y análisis de redes viales y POIs desde OpenStreetMap
from pathlib import Path  # Para la manipulación de rutas de archivos de forma orientada a objetos
from datetime import datetime, date, timedelta  # Para la gestión de fechas y tiempos
import logging  # Para el registro de eventos y mensajes de error durante la ejecución
import unicodedata  # Para la normalización de caracteres Unicode (manejo de tildes y ñ)
import traceback  # Para la extracción y visualización de errores detallados (stack traces)
import zipfile  # Para la compresión y descompresión de archivos en formato ZIP
import tempfile  # Para la creación de archivos y directorios temporales
import shutil  # Para operaciones de alto nivel con archivos (copiar, mover, borrar)
import json  # Para la codificación y decodificación de datos en formato JSON
import rasterio  # Para la lectura, escritura y análisis de datos geoespaciales raster
import gzip  # Para la compresión y descompresión de archivos en formato ZIP
from rasterio.mask import mask  # Para el recorte de rasters mediante máscaras vectoriales
from rasterio.warp import calculate_default_transform, reproject, Resampling  # Para la reproyección de coordenadas raster
from tqdm import tqdm  # Para la visualización de barras de progreso en consola (para que el usuario sepa el progreso de la descarga)

# --- CONFIGURACIÓN DE URLs POR DEFECTO ---
DEFAULT_CENSO_URL = "https://services5.arcgis.com/hUyD8u3TeZLKPe4T/arcgis/rest/services/Manzana_2017_2/FeatureServer/0"
DEFAULT_CENSO_MICRO_URL = "https://redatam-ine.ine.cl/tab/Censo2017_ManzanaEntidad_CSV.rar"
DEFAULT_MINVU_USO_SUELO_URL = "https://catalogo.minvu.cl/cgi-bin/koha/tracklinks.pl?uri=https%3A%2F%2Fcatalogo.minvu.cl%2Fcgi-bin%2Fkoha%2Fopac-retrieve-file.pl%3Fid%3Deea77d4fcd8a800c121da5f9f3d135fd&biblionumber=25215"
DEFAULT_DPA_URL = "https://www.geoportal.cl/geoportal/catalog/download/912598ad-ac92-35f6-8045-098f214bd9c2"

# Configurar logging para salida por consola
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DataDownloader:
    """Clase para gestionar la descarga de datos geoespaciales.

    Descripción: Incluye la descarga de límites administrativos, datos censales, red vial OSM, 
                 uso de suelo (MINVU), DEM (SRTM) y bandas Sentinel-2.

    Atributos principales:
    - comuna (str): Nombre de la comuna objetivo, como "San Joaquín".
    - output_dir (Path): Carpeta donde se guardarán los archivos descargados (data/raw).
    - boundary_gdf (GeoDataFrame | None): Límites comunales cargados en memoria.
    """

    def __init__(self, comuna_name: str, output_dir: Path):
        """
        Descripción: Función que inicializa el descargador.

        Entradas:
        - comuna_name (str): Nombre de la comuna (ej. "San Joaquín").
        - output_dir (Path): Ruta/base de salida para los archivos (data/raw).

        Salida: Inicializa atributos y crea la carpeta de salida si no existe.
        """
        # Guardar nombre de comuna y preparar directorio de salida
        self.comuna = comuna_name # Asignar nombre de la comuna objetivo
        # Definir y crear el directorio raíz para los datos descargados
        self.output_dir = Path(output_dir) 
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # Placeholder (elemento temporal) para almacenar el GeoDataFrame del límite comunal
        self.boundary_gdf = None
        logger.info(f"Inicializando descarga para comuna: {comuna_name}")

    def _normalize(self, text: str) -> str:
        """
        Descripción: Función que normaliza cadenas para comparaciones robustas. Usada para los CSV.
                     Se usó porque "San Joaquín" tiene tilde y puede causar problemas.

        Entrada:
        - text (str): Cadena original.

        Salida:
        - (str) Texto en mayúsculas, sin acentos ni caracteres especiales.
        """
        # Normalización: quitar acentos y caracteres fuera de ASCII
        if text is None: return ""
        text = str(text)
        # Intentar corregir errores comunes de encoding en fuentes locales
        try: text = text.encode("latin1").decode("windows-1252")
        except: pass
        # Eliminar tildes descomponiendo caracteres Unicode
        text = unicodedata.normalize("NFKD", text)
        text = "".join(c for c in text if not unicodedata.combining(c))
        # Filtrar caracteres no imprimibles
        text = "".join(c for c in text if 32 <= ord(c) <= 126)
        return text.upper().strip()
    
    def _safe_read_csv(self, path):
        """
        Descripción: Función que lee CSV con encoding resiliente (latin-1) y separador ';'.

        Entrada:
        - path (Path | str): Ruta al archivo CSV.

        Salida:
        - (pd.DataFrame) DataFrame con todas las columnas como texto.
        """
        # Evitar errores de encoding típicos en archivos del INE
        from io import StringIO
        # Leer archivo en binario para manejar manualmente el encoding
        with open(path, "rb") as f: 
            raw = f.read()
        # Decodificar usando latin-1 para compatibilidad con datos del INE/Gobierno
        text = raw.decode("latin-1", errors="replace")
        return pd.read_csv(StringIO(text), sep=";", dtype=str)
    
    def _closest_match(self, target: str, candidates: list, cutoff: float = 0.75):
        """
        Descripción: Función que encuentra la mejor coincidencia aproximada para un texto dado,
                     útil para corregir errores tipográficos o variaciones en nombres.
                     Se usa porque "San Joaquín" puede estar mal escrito en algunos CSV.

        Entrada:
        - target (str): Texto objetivo.
        - candidates (list[str]): Lista de posibles coincidencias.
        - cutoff (float): Umbral de similitud (0-1).

        Salida:
        - (str | None) Mejor coincidencia o None si no alcanza el umbral.
        """
        import difflib
        # Buscar el texto más parecido dentro de una lista para evitar fallos por tipeo
        matches = difflib.get_close_matches(target, candidates, n=1, cutoff=cutoff)
        return matches[0] if matches else None

    def _download_file(self, url, dest_path, desc="Descargando"):
        """
        Descripción: Función que descarga un archivo con barra de progreso
                     para que el usuario sepa el progreso de su descarga.

        Entrada:
        - url (str): URL del recurso.
        - dest_path (Path | str): Ruta destino del archivo a escribir.
        - desc (str): Texto a mostrar en la barra de progreso.

        Salida:
        - (bool) True si la descarga fue exitosa, False en caso de error.
        """
        # Descarga fragmentada y visualización con tqdm
        try:
            # Solicitar recurso habilitando streaming para archivos grandes
            with requests.get(url, stream=True, timeout=300) as r:
                r.raise_for_status()
                # Obtener el tamaño total desde los headers HTTP
                total_size = int(r.headers.get('content-length', 0))
                # Configurar barra de progreso visual
                with tqdm(total=total_size, unit='iB', unit_scale=True, desc=desc, ncols=80) as bar:
                    with open(dest_path, 'wb') as f:
                        # Escribir en disco por bloques de 8KB para optimizar RAM
                        for chunk in r.iter_content(chunk_size=8192):
                            size = f.write(chunk)
                            bar.update(size)
            return True # Descarga exitosa
        except Exception as e: # En caso de error se retorna False
            logger.error(f"Error descargando {url}: {e}")
            return False

    def _load_boundary(self):
        """
        Descripción: Carga límites comunales desde disco si no están en memoria.

        Salida:
        - (GeoDataFrame | None) Límites comunales con CRS definido.
        """
        # Intenta leer 'comuna_boundaries_oficial.geojson' del directorio de salida
        if self.boundary_gdf is None:
            f = self.output_dir / 'comuna_boundaries_oficial.geojson'
            if f.exists():
                # Cargar archivo GeoJSON previamente descargado
                try:
                    self.boundary_gdf = gpd.read_file(f)
                    # Forzar sistema de coordenadas WGS84 si no está presente
                    if self.boundary_gdf.crs is None:
                        self.boundary_gdf.set_crs(epsg=4326, inplace=True)
                except Exception as e: # En caso de error retornar mensaje de advertencia
                    logger.warning(f"Archivo de límites corrupto o ilegible: {e}")
        return self.boundary_gdf # Retornar límites comunales cargados

    def _reproject_raster(self, src_path: Path, target_epsg: int = 32719):
        """
        Descripción: Función que calcula transformaciones y reproyecta un raster a un EPSG objetivo.

        Entrada:
        - src_path (Path): Ruta del raster de entrada.
        - target_epsg (int): Código EPSG destino (ej. 32719 - WGS84/UTM 19S).

        Salida:
        - (None) Genera un archivo nuevo en el mismo directorio con sufijo del EPSG.
        """
        # Definir nombre de salida basado en el EPSG (ej: 32719 para UTM 19S)
        out_path = src_path.parent / f"{src_path.stem}_{target_epsg}.tif"
        try:
            with rasterio.open(src_path) as src:
                dst_crs = f"EPSG:{target_epsg}"
                # Calcular dimensiones y transformación necesaria para la nueva proyección
                transform, width, height = calculate_default_transform(
                    src.crs, dst_crs, src.width, src.height, *src.bounds)
                # Copiar metadatos del original y actualizar con el nuevo CRS
                meta = src.meta.copy()
                meta.update({'crs': dst_crs, 'transform': transform, 'width': width, 'height': height})
                # Ejecutar la reproyección banda por banda
                with rasterio.open(out_path, 'w', **meta) as dst:
                    # Reproyectar cada banda del raster original
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
        """
        Descripción: Función que descarga red vial y POIs desde OpenStreetMap.

        Entrada:
        - debug (bool): Si es True, muestra logs detallados.

        Salida:
        - (bool) True si se descargó la red vial, False si no hubo éxito.
        """
        # Habilitar caché y logs en OSMnx para diagnósticos
        logger.info(">>> Iniciando descarga OSM (Fuente: OpenStreetMap)")
        try:
            # Optimizar OSMnx guardando peticiones repetidas en disco local
            if hasattr(ox, 'settings'):
                ox.settings.use_cache = True
                ox.settings.log_console = debug
        except: pass # Ignorar si no se puede configurar

        # Intentar con variantes del nombre de la comuna para mejorar geocodificación
        # Probar nombres normalizados para asegurar el geocoding
        queries = [f"{self.comuna}, Chile", f"{self._normalize(self.comuna)}, Chile"]
        success = False

        for q in queries:
            logger.info(f"Consultando OSM: '{q}'")
            try:
                # Descargar grafo de calles filtrado para vehículos
                G = ox.graph_from_place(q, network_type='drive')
                # Guardar en formato GraphML para uso posterior en SIG o NetworkX
                ox.save_graphml(G, self.output_dir / 'osm_network.graphml')
                logger.info("✔ Red vial descargada.")
                success = True
                try:
                    # Intentar obtener la geometría poligonal de la comuna desde OSM
                    if hasattr(ox, 'geocode_to_gdf'):
                        self.boundary_gdf = ox.geocode_to_gdf(q)
                except: pass # Ignorar si no se puede obtener geometría
            except Exception: # En caso de error, mostrar advertencia
                if debug: logger.warning(f"No se encontró red vial para {q}")
            # Si se logró descargar la red vial, proceder a descargar edificios y amenidades
            if success: # Función interna para descargar puntos de interés y polígonos
                # Descargar edificios y amenidades como capas temáticas
                def get_features(tags, name):
                    try:
                        # Extraer geometrías basadas en etiquetas OSM (key:value)
                        if hasattr(ox, 'features'): # si ox.features existe (versión nueva)
                            gdf = ox.features.features_from_place(q, tags=tags)
                        else: # si no, usar geometries_from_place (versión antigua)
                            gdf = ox.geometries_from_place(q, tags=tags)
                        if gdf is not None and not gdf.empty: # Guardar como GeoJSON
                            gdf.to_file(self.output_dir / f'osm_{name}.geojson', driver='GeoJSON')
                            logger.info(f"✔ {name.capitalize()} descargados.")
                    except Exception as e: # Capturar errores al descargar características
                        if debug: logger.warning(f"Error en {name}: {e}")
                # Descargar edificios y amenidades
                get_features({'building': True}, 'buildings')
                get_features({'amenity': True}, 'amenities')
                break
        return success # Retornar si se logró descargar la red vial

    def download_boundaries(self, wfs_url=None, dpa_url=None, skip_wfs=False, debug=False):
        """
        Descripción: Función que descarga límites comunales vía WFS (IDE) o ZIP DPA.

        Entrada:
        - wfs_url (str | None): URL alternativa del servicio WFS.
        - dpa_url (str | None): URL del ZIP DPA para fallback.
        - skip_wfs (bool): Si True, salta WFS y usa DPA directamente.
        - debug (bool): Logs detallados al fallar.

        Salida:
        - (bool) True si se descargaron límites, False en caso de error.
        """
        logger.info(">>> Descargando Límites Administrativos (Fuente: IDE Chile/DPA)")
        if not skip_wfs: # Intentar descargar vía WFS primero
            try: # Intentar obtener límites vía WFS
                wfs = wfs_url or "https://www.ide.cl/geoserver/wfs"
                # Definir parámetros para consulta OGC WFS filtrada por nombre de comuna
                params = {
                    'service': 'WFS', 'version': '2.0.0', 'request': 'GetFeature',
                    'typeName': 'division_comunal', 'outputFormat': 'application/json',
                    'CQL_FILTER': f"comuna='{self.comuna.upper()}'"
                }
                # Realizar petición HTTP al servicio WFS
                r = requests.get(wfs, params=params, timeout=30)
                # Verificar respuesta y contenido
                if r.status_code == 200 and 'features' in r.json() and len(r.json()['features']) > 0:
                    with open(self.output_dir / 'comuna_boundaries_oficial.geojson', 'w') as f:
                        f.write(r.text)
                    logger.info("✔ Límites WFS descargados.") # Guardar GeoJSON
                    return True
            except Exception as e: # Capturar errores al obtener límites vía WFS
                if debug: logger.warning(f"Fallo WFS: {e}")
        # Fallback a la descarga del archivo DPA nacional si el servicio WFS falla
        return self.download_boundaries_dpa_zip(dpa_url or DEFAULT_DPA_URL, self.comuna, debug)

    def download_boundaries_dpa_zip(self, dpa_url, comuna_name, debug):
        """
        Descripción: Función que descarga y filtra límites comunales desde ZIP DPA.

        Entrada:
        - dpa_url (str): URL del ZIP oficial DPA.
        - comuna_name (str): Nombre de la comuna a filtrar (ej. "San Joaquín").
        - debug (bool): Logs de error detallados.

        Salida:
        - (bool) True si se logra procesar y guardar el GeoJSON de límites.
        """
        try:
            # Descargar y extraer ZIP DPA en carpeta temporal
            with tempfile.TemporaryDirectory() as tmp:
                zpath = Path(tmp) / 'dpa.zip' # Ruta temporal para el ZIP
                logger.info("Iniciando descarga DPA (ZIP)...")
                # Descargar archivo ZIP DPA
                if not self._download_file(dpa_url, zpath, desc="DPA Oficial"):
                    return False
                # Descomprimir contenido en carpeta temporal
                with zipfile.ZipFile(zpath) as zf: zf.extractall(tmp)
                # Localizar el archivo shapefile (.shp) dentro del ZIP
                shp = next(Path(tmp).rglob('*.shp'), None)
                if not shp: return False # Si no se encuentra, retornar False
                # Cargar shapefile y filtrar por comuna
                gdf = gpd.read_file(shp)
                # Normalizar nombre de comuna para comparación
                norm_name = self._normalize(comuna_name)
                # Identificar dinámicamente la columna que contiene los nombres de comuna
                cols = [c for c in gdf.columns if 'comuna' in c.lower()]
                if not cols: return False # Si no hay columna con nombre de la comuna, retornar False
                # Filtrar el GeoDataFrame nacional para extraer solo el polígono de interés
                gdf['norm'] = gdf[cols[0]].apply(self._normalize)
                filtered = gdf[gdf['norm'] == norm_name]
                # Verificar si se encontró la comuna
                if filtered.empty: # Si no se encuentra, retornar False y mensaje de error.
                    logger.warning(f"Comuna {comuna_name} no encontrada en DPA.")
                    return False
                # Limpiar columna temporal y exportar a GeoJSON
                filtered = filtered.drop(columns=['norm'])
                filtered.to_file(self.output_dir / 'comuna_boundaries_oficial.geojson', driver='GeoJSON')
                self.boundary_gdf = filtered
                logger.info("✔ Límites DPA procesados.") # Mensaje de éxito
                return True
        except Exception as e: # En caso de error, mostrar mensaje de fallo
            logger.error(f"Error DPA: {e}")
            return False

    def download_census_data(self, censo_url=None, micro_url=None, debug=False):
        """
        Descripción: Función que descarga manzanas censales (INE) y microdatos del Censo.

        Entrada:
        - censo_url (str | None): Endpoint de ArcGIS FeatureServer.
        - micro_url (str | None): URL del RAR de microdatos.
        - debug (bool): Logs detallados.

        Salida:
        - (None) Genera 'manzanas_censales.geojson' y extrae microdatos en carpeta.
        """
        logger.info(">>> Iniciando descarga INE (Manzanas + Datos Socioeconómicos)")
        
        # 1. Geometría Manzanas (INE) via ArcGIS FeatureServer
        url = censo_url or DEFAULT_CENSO_URL
        query_url = url.rstrip('/') + '/query'
        names_to_try = [self.comuna.upper(), self._normalize(self.comuna)]
        
        success = False
        for n in names_to_try:
            # Consulta SQL espacial para obtener manzanas de la comuna específica
            where = f"UPPER(COMUNA) LIKE '{n}%'"
            try:
                # Parámetros para la consulta
                params = {'where': where, 'outFields': '*', 'returnGeometry': 'true', 'f': 'geojson', 'outSR': '4326'}
                # Realizar petición HTTP al FeatureServer
                r = requests.get(query_url, params=params, timeout=60)
                if r.status_code == 200: # Verificar respuesta exitosa
                    data = r.json()
                    if 'features' in data and len(data['features']) > 0: # Verificar si hay features
                        # Si lo hay, guardar GeoJSON de manzanas censales
                        with open(self.output_dir / 'manzanas_censales.geojson', 'w', encoding='utf-8') as f:
                            f.write(r.text)
                        logger.info(f"✔ Geometría de manzanas descargada ({len(data['features'])} features).")
                        success = True
                        break
            except Exception: pass
        if not success: logger.warning("No se encontraron manzanas censales.")

        # 2. Censo 2017 Microdatos (INE)
        m_url = micro_url or DEFAULT_CENSO_MICRO_URL
        # Descargar y extraer microdatos del Censo 2017
        self.download_and_extract_censo_rar(m_url)
        self.filter_censo_manzanas_by_comuna(self.comuna)

    def download_and_extract_censo_rar(self, url):
        """
        Descripción: Función que descarga y extrae el RAR de microdatos del Censo 2017.

        Entrada:
        - url (str): URL del archivo .rar.

        Salida:
        - (None) Extrae los archivos en 'Censo2017_ManzanaEntidad_CSV/'.
        """
        fname = url.split("/")[-1] # Nombre del archivo RAR
        rar_path = self.output_dir / fname
        # En caso de que el archivo ya exista, no descargar de nuevo
        if rar_path.exists():
            logger.info("RAR Censo ya existe.")
        # En caso contrario, descargar el archivo RAR
        else:
            logger.info("Iniciando descarga Microdatos Censo...")
            if not self._download_file(url, rar_path, desc="Microdatos Censo"):
                return
        # Extraer el archivo RAR usando rarfile o 7zip
        # Carpeta para alojar los CSVs extraídos
        extract_dir = self.output_dir / "Censo2017_ManzanaEntidad_CSV"
        # Asegurarse de que la carpeta de extracción exista
        extract_dir.mkdir(exist_ok=True)
        
        extracted = False
        # Intento 1: rarfile
        # Intentar extracción nativa con librería rarfile
        try: 
            import rarfile
            with rarfile.RarFile(rar_path) as rf:
                # Extraer dentro de la carpeta específica
                rf.extractall(path=extract_dir)
            extracted = True
        except Exception as e:
            logger.warning(f"Fallo rarfile ({e}). Intentando fallback con 7zip...")

        # Intento 2: 7zip
        # Fallback a herramienta de sistema 7-Zip si rarfile no está configurado/disponible
        if not extracted:
            import subprocess
            sevenzip_candidates = ["7z", "7za", r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"]
            sevenzip_exe = None
            # Buscar el ejecutable en rutas comunes de Windows y Linux
            for candidate in sevenzip_candidates:
                if shutil.which(candidate) or Path(candidate).exists():
                    sevenzip_exe = candidate
                    break
            if sevenzip_exe:
                try:
                    # Llamar al proceso de sistema para extraer de forma forzada
                    cmd = [sevenzip_exe, "x", "-y", str(rar_path), f"-o{extract_dir}"]
                    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                    extracted = True
                    logger.info("✔ Extracción exitosa con 7-Zip.")
                except: pass
        # Eliminar el archivo RAR tras la extracción (para ahorrar espacio)
        if extracted and rar_path.exists():
            rar_path.unlink()

    def filter_censo_manzanas_by_comuna(self, comuna_name):
        """
        Descripción: Función que filtra el CSV de manzanas para dejar solo la comuna objetivo.

        Entrada:
        - comuna_name (str): Nombre de la comuna a filtrar.

        Salida:
        - (None) Sobrescribe 'Censo2017_Manzanas.csv' dejando filas de la comuna.
        """
        # Ruta base de los CSV extraídos
        base = self.output_dir / "Censo2017_ManzanaEntidad_CSV"
        try:
            # Buscar archivos CSV específicos dentro de la estructura extraída
            csv_path = next(base.rglob("Censo2017_Manzanas.csv"), None)
            comunas_path = next(base.rglob("*Comunas.csv"), None)
            # Verificar que ambos archivos existan antes de continuar
            if not csv_path or not comunas_path: 
                logger.error(f"No se encontraron los archivos CSV del Censo en {base}")
                return
            # Cargar CSV de comunas para obtener el código CUT
            df_com = self._safe_read_csv(comunas_path)
            norm = self._normalize(comuna_name)
            df_com['NORM'] = df_com['NOM_COMUNA'].apply(self._normalize)
            
            # Determinar código CUT de la comuna mediante coincidencia exacta o aproximada
            # Identificar el código CUT (Código Único Territorial) para el filtrado
            code = None
            match = df_com[df_com['NORM'] == norm]
            if not match.empty:
                code = match.iloc[0]['COMUNA']
            else:
                # Búsqueda parcial si el nombre no es exacto
                match = df_com[df_com['NORM'].str.contains(norm, na=False)]
                if not match.empty: 
                    code = match.iloc[0]['COMUNA']
                else:
                    # Fuzzy match: Aplicar lógica fuzzy si fallan las búsquedas anteriores
                    possibles = df_com['NORM'].tolist() # Lista de nombres normalizados
                    best = self._closest_match(norm, possibles) # Buscar la mejor coincidencia aproximada
                    if best:
                        code = df_com[df_com['NORM'] == best].iloc[0]['COMUNA']
            # Filtrar el CSV de manzanas para conservar solo las filas de la comuna objetivo
            if code:
                logger.info(f"Filtrando Censo para código comuna: {code}")
                df_data = self._safe_read_csv(csv_path)
                # Reducir el archivo de millones de filas a solo las de la comuna
                df_filtered = df_data[df_data['COMUNA'] == code]
                # Si hay datos, sobrescribir el CSV original
                if not df_filtered.empty:
                    # Asegurar permisos de escritura antes de sobreescribir (evita Permission denied en Windows)
                    try:
                        os.chmod(csv_path, stat.S_IWRITE)
                    except Exception: pass
                    # Sobrescribir CSV con solo las filas filtradas
                    df_filtered.to_csv(csv_path, sep=";", index=False)
                    logger.info(f"✔ Microdatos filtrados para comuna {code} (Filas: {len(df_filtered)}).")
                else: # En caso de que no hayan registro de esa comuna en las filas
                    logger.warning(f"No se encontraron registros para la comuna {code}.")
            else: # En caso de no encontrar código CUT, mostrar error
                logger.error(f"No se encontró código CUT para la comuna '{comuna_name}'.")
        except Exception as e: logger.error(f"Error filtrando CSV: {e}")

    def download_srtm_tiles(self, debug=False):
        """
        Descripción: Función que descarga y procesa el mosaico SRTM correspondiente a la comuna.

        Entrada:
        - debug (bool): Muestra errores de mirrors si es True.

        Salida:
        - (None) Genera 'srtm_dem.tif' (recortado) y reproyectado 'srtm_dem_32719.tif'.
        """
        logger.info(">>> Descargando DEM SRTM")
        boundary = self._load_boundary() # Cargar límites comunales
        if boundary is None: # Si no están cargados, solicitar descarga previa de límites comunales
            logger.error("ERROR: falta límite comunal: Ejecuta primero --sources ide")
            return
        # Determinar coordenadas de la esquina suroeste para identificar el mosaico SRTM
        minx, miny, maxx, maxy = boundary.total_bounds # Obtener límites en coordenadas
        import math # Para funciones matemáticas
        lat_sw = math.floor(miny) 
        lon_sw = math.floor(minx) 
        ns = 'S' if lat_sw < 0 else 'N' # Determinar hemisferio norte/sur
        ew = 'W' if lon_sw < 0 else 'E' # Determinar hemisferio este/oeste
        tile_name = f"{ns}{abs(lat_sw):02d}{ew}{abs(lon_sw):03d}" # Formatear nombre del mosaico SRTM
        
        # Lista de mirrors conocidos para SRTM
        # Múltiples fuentes para robustez ante caídas de servidores
        urls = [
            f"https://srtm.kurviger.de/SRTM3/{tile_name}.hgt.zip",
            f"https://dds.cr.usgs.gov/srtm/version2_1/SRTM3/South_America/{tile_name}.hgt.zip",
            f"https://srtmtiles.s3.amazonaws.com/{tile_name}.hgt.gz",
            f"https://s3.amazonaws.com/elevation-tiles-prod/skadi/{tile_name[:3]}/{tile_name}.hgt.gz" 
        ]
        # Descargar el archivo HGT desde los mirrors disponibles
        hgt_path = self.output_dir / f"{tile_name}.hgt"
        # Si no existe, intentar descargar desde cada mirror hasta tener éxito
        if not hgt_path.exists():
            downloaded = False
            for url in urls:
                try:
                    logger.info(f"Probando mirror: {url}")
                    # Manejar descompresión según el formato del servidor (ZIP o GZ)
                    if url.endswith('.zip'): # Si es un ZIP
                        temp_path = self.output_dir / f"{tile_name}.zip" # Ruta temporal para el ZIP
                        # Si la descarga es exitosa, extraer el archivo HGT del ZIP
                        if self._download_file(url, temp_path, desc=f"SRTM {tile_name}"):
                            with zipfile.ZipFile(temp_path, 'r') as zf:
                                for member in zf.namelist():
                                    if member.endswith('.hgt'):
                                        with zf.open(member) as src, open(hgt_path, 'wb') as dst:
                                            dst.write(src.read())
                            temp_path.unlink()
                            downloaded = True
                            break
                    elif url.endswith('.gz'): # Si es un GZ
                        temp_path = self.output_dir / f"{tile_name}.hgt.gz" # Ruta temporal para el GZ
                        # Si la descarga es exitosa, descomprimir el archivo GZ a HGT
                        if self._download_file(url, temp_path, desc=f"SRTM {tile_name}"):
                            with gzip.open(temp_path, 'rb') as f_in:
                                with open(hgt_path, 'wb') as f_out:
                                    shutil.copyfileobj(f_in, f_out)
                            temp_path.unlink()
                            downloaded = True
                            break
                except Exception as e: # Capturar errores de descarga y mostrar advertencia
                    if debug: logger.warning(f"Error mirror {url}: {e}")

        # Recorte del DEM al contorno comunal
        final_dem_path = self.output_dir / "srtm_dem.tif"
        if hgt_path.exists(): # Si se descargó el HGT, proceder al recorte
            try:
                # Recorte del HGT al contorno comunal y guardado como GeoTIFF
                # Recortar el archivo HGT global al polígono exacto de la comuna
                with rasterio.open(hgt_path) as src:
                    out_image, out_transform = mask(src, boundary.geometry, crop=True)
                    out_meta = src.meta.copy()
                    out_meta.update({"driver": "GTiff", "height": out_image.shape[1], "width": out_image.shape[2], "transform": out_transform})
                    with rasterio.open(final_dem_path, "w", **out_meta) as dest:
                        dest.write(out_image)
                logger.info("✔ SRTM procesado y recortado (srtm_dem.tif).")
                # Reproyectar a UTM para permitir cálculos de pendiente y área precisos
                self._reproject_raster(final_dem_path, 32719)
            except Exception as e:
                logger.error(f"Error recortando SRTM: {e}")

    def download_sentinel2(self, year=None, debug=False):
        """
        Descripción: Función que descarga bandas B04 (rojo) y B08 (NIR) de Sentinel-2.

        Entrada:
        - year (int | None): Año objetivo; si None, busca últimos 90 días.
        - debug (bool): Imprime traceback en caso de error.

        Salida:
        - (None) Genera 'sentinel2_B04.tif' y 'sentinel2_B08.tif' recortados.
        """
        logger.info(f">>> Descargando Sentinel-2 (Copernicus) [Año: {year if year else 'Reciente'}]")
        try:
            # Importaciones diferidas para no obligar a instalar estas librerías si no se usan
            from pystac_client import Client
            import planetary_computer as pc
        except ImportError: 
            logger.error("Error: Faltan librerías: pip install pystac-client planetary-computer")
            return

        boundary = self._load_boundary() # Cargar límites comunales
        if boundary is None: # En caso de no tener límites comunales, solicitar descarga previa
            logger.error("Error: Falta límite comunal: Ejecuta primero --sources ide")
            return
        # Definir rango de fechas para la búsqueda de imágenes
        if year: # Definir ventana de tiempo para la búsqueda satelital
            date_range = f"{year}-01-01/{year}-12-31"
        else:
            # Buscar en los últimos 90 días
            end = date.today()
            start = end - timedelta(days=90)
            date_range = f"{start}/{end}"
        
        try:
            # Buscar escenas con baja nubosidad y recortar al contorno comunal
            # Conectar al catálogo STAC de Microsoft Planetary Computer
            catalog = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
            search = catalog.search( # Buscar escenas con menos del 10% de nubes que cubran la comuna
                collections=["sentinel-2-l2a"],
                bbox=boundary.total_bounds,
                datetime=date_range,
                query={"eo:cloud_cover": {"lt": 10}},
                limit=1
            )
            items = list(search.items())
            # Si no se encuentran imágenes, mostrar advertencia
            if not items:
                logger.warning("No se encontraron imágenes Sentinel-2.")
                return
            # Descargar y recortar las bandas B04 y B08
            item = items[0]
            # Firmar el item para obtener permisos temporales de lectura en Azure
            signed_item = pc.sign(item)
            # Descargar solo las bandas necesarias para el cálculo de vegetación (NDVI)
            for band in ['B04', 'B08']:
                if band in signed_item.assets:
                    href = signed_item.assets[band].href
                    with rasterio.open(href) as src:
                        geom = boundary
                        # Asegurar que el polígono de recorte esté en el mismo CRS que la imagen satelital
                        if geom.crs and src.crs and geom.crs.to_string() != src.crs.to_string():
                            geom = geom.to_crs(src.crs)
                        # Recortar y guardar la banda como GeoTIFF
                        out_image, out_transform = mask(src, geom.geometry, crop=True)
                        meta = src.meta.copy()
                        meta.update({"driver": "GTiff", "height": out_image.shape[1], "width": out_image.shape[2], "transform": out_transform})
                        with rasterio.open(self.output_dir / f"sentinel2_{band}.tif", "w", **meta) as dest:
                            dest.write(out_image)
            logger.info("✔ Sentinel-2 (B04, B08) descargado.")
        # Si hay errores generales, mostrar mensaje de fallo
        except Exception as e:
            logger.error(f"Error Sentinel-2: {e}")
            if debug: traceback.print_exc()

    def download_minvu_uso_suelo(self, minvu_url=None, local_path=None, debug=False):
        """
        Descripción: Función que descarga y consolida capas de uso de suelo del MINVU.

        Entrada:
        - minvu_url (str | None): URL del ZIP con capas MINVU.
        - local_path (str | None): No usado, reservado para futuros casos.
        - debug (bool): Logs detallados.

        Salida:
        - (None) Genera 'uso_suelo_minvu.geojson' consolidado por comuna.
        """
        logger.info(">>> Descargando Uso de Suelo (MINVU)")
        # Descargar y extraer ZIP MINVU
        url = minvu_url or DEFAULT_MINVU_USO_SUELO_URL
        zip_path = self.output_dir / 'uso_suelo_minvu.zip'
        # En caso de que el archivo ya exista, no descargar de nuevo
        if not zip_path.exists():
            logger.info("Iniciando descarga MINVU...")
            if not self._download_file(url, zip_path, desc="Uso Suelo MINVU"):
                return
        # Extraer el ZIP en carpeta específica
        extract_dir = self.output_dir / 'uso_suelo_minvu'
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_dir)
        # Eliminar el ZIP tras la extracción para ahorrar espacio
        if zip_path.exists(): zip_path.unlink()
        # Buscar shapefiles que coincidan con la comuna
        shps = list(extract_dir.rglob("*.shp"))
        comuna_norm = self._normalize(self.comuna).split()
        matches = [s for s in shps if all(part in self._normalize(s.name) for part in comuna_norm)]

        # Poda de archivos sobrantes: eliminamos de la carpeta PRC los shapefiles que no son de la comuna
        prc_dir = extract_dir / 'IPT_Metropolitana' / 'PRC'
        # Lógica de limpieza para borrar archivos de otras comunas y ahorrar espacio
        if prc_dir.exists():
            kept_count = 0
            removed_count = 0
            chosen_stems = {p.stem for p in matches}
            # Iterar sobre los archivos en la carpeta PRC
            for f in prc_dir.iterdir():
                if f.is_file():
                    # Determinar si el archivo pertenece a uno de los shapefiles elegidos
                    stem = f.name.replace('.shp.xml', '') # manejo simple de extensiones
                    stem = Path(stem).stem
                    # Si no está en los elegidos, eliminarlo
                    if stem in chosen_stems:
                        kept_count += 1
                    else:
                        try:
                            f.unlink()
                            removed_count += 1
                        except: pass
            if removed_count > 0:
                logger.info(f"Poda completada: Se eliminaron {removed_count} archivos ajenos a {self.comuna} en carpeta PRC.")
        if matches: # Si se encontraron shapefiles coincidentes, consolidar
            try: # Consolidar múltiples shapefiles (si existen) en un solo GeoJSON
                gdf = pd.concat([gpd.read_file(s) for s in matches], ignore_index=True)
                # Reproyectar a WGS84 si es necesario
                if gdf.crs and gdf.crs.to_epsg() != 4326: gdf = gdf.to_crs(4326)
                gdf.to_file(self.output_dir / 'uso_suelo_minvu.geojson', driver='GeoJSON')
                logger.info(f"✔ Uso de suelo consolidado ({len(gdf)} features).")
            except Exception as e:
                 logger.error(f"Error consolidando MINVU: {e}")
        else: # En caso de no encontrar shapefiles, mostrar advertencia
            logger.warning("No se detectaron shapefiles MINVU para la comuna.")

    def create_metadata(self):
        """
        Descripción: Función que crea archivo de metadatos de la sesión de descarga.

        Salida:
        - (None) Crea 'metadata.txt' con comuna, timestamp y listado de archivos.
        """
        # Construir estructura de metadatos sencilla y guardarla como JSON
        meta = {
            'comuna': self.comuna, # Nombre de la comuna
            'timestamp': datetime.now().isoformat(), # Fecha y hora de la descarga
            'files': [f.name for f in self.output_dir.glob('*')] # Listado de archivos generados
        }
        with open(self.output_dir / 'metadata.txt', 'w') as f: # Guardar como JSON legible
            json.dump(meta, f, indent=2)

# Parámetros obligatorios y opcionales para ejecutar el script desde terminal
@click.command()
@click.option('--comuna', required=True, help='Nombre de la comuna (ej. "La Florida")')
@click.option('--year', type=int, default=None, help='Año de los datos (ej. 2024).')
@click.option('--sources', default='all', show_default=True, help='Fuentes: ide, ine, osm, sentinel, minvu, srtm, all.')
@click.option('--debug', is_flag=True, help='Activar logs detallados')
@click.option('--output', default='data/raw', help='Directorio de salida')
@click.option('--skip-wfs', is_flag=True, help='Saltar WFS (IDE)')
def main(comuna, year, sources, debug, output, skip_wfs):
    """CLI de descarga de datos del Laboratorio Integrador.

    Descripción:
    - Permite seleccionar fuentes a descargar (IDE, INE, OSM, MINVU, SRTM, Sentinel).
        Integra todo en una misma interfaz de línea de comandos.

    Entrada:
    - comuna (str): Nombre de la comuna.
    - year (int | None): Año para Sentinel-2.
    - sources (str): Lista separada por comas de fuentes o 'all'.
    - debug (bool): Activa mensajes detallados.
    - output (str): Carpeta de salida (por defecto 'data/raw').
    - skip_wfs (bool): Si True, evita WFS y usa DPA.

    Salida:
    - (None) Escribe archivos en la carpeta de salida y muestra logs del proceso.
    """
    logger.info("=" * 60)
    logger.info(f"PROYECTO GEOINFORMÁTICA - DESCARGA DE DATOS")
    logger.info(f"Comuna: {comuna} | Año: {year or 'Reciente'} | Fuentes: {sources}")
    logger.info("=" * 60)
    
    out_path = Path(output)
    downloader = DataDownloader(comuna, out_path)
    # Parsear lista de fuentes separadas por comas
    s_list = [s.strip().lower() for s in sources.split(',')]
    download_all = 'all' in s_list
    
    # 1. Límites Administrativos (IDE Chile)
    # Fuente IDE
    if download_all or 'ide' in s_list:
        downloader.download_boundaries(skip_wfs=skip_wfs, debug=debug)

    # 2. Datos Censales (INE)
    # Fuente INE (Manzanas + Censo 2017)
    if download_all or 'ine' in s_list or 'censo' in s_list:
        downloader.download_census_data(debug=debug)
        
    # 3. Red Vial (OpenStreetMap)
    # Fuente OpenStreetMap
    if download_all or 'osm' in s_list:
        downloader.download_osm_data(debug=debug)
        
    # 4. Uso de Suelo (IDE Minvu)
    # Fuente IDE Minvu
    if download_all or 'minvu' in s_list or 'ide_minvu' in s_list:
        downloader.download_minvu_uso_suelo(debug=debug)
        
    # 5. DEM (SRTM)
    # Fuente ALOS PALSAR / SRTM
    # Nota: Requiere límites previos. Si no existen, avisar.
    if download_all or 'srtm' in s_list or 'dem' in s_list:
        if (out_path / 'comuna_boundaries_oficial.geojson').exists():
            downloader.download_srtm_tiles(debug=debug)
        else:
            logger.warning("ADVERTENCIA: Se requieren límites (IDE) para descargar SRTM. Ejecute con --sources ide primero.")
        
    # 6. Sentinel-2 (Copernicus)
    # Fuente Copernicus
    if download_all or 'sentinel' in s_list or 'copernicus' in s_list:
        if (out_path / 'comuna_boundaries_oficial.geojson').exists():
            downloader.download_sentinel2(year=year, debug=debug)
        else:
            logger.warning("ADVERTENCIA: Se requieren límites (IDE) para descargar Sentinel-2. Ejecute con --sources ide primero.")

    downloader.create_metadata() # Crear archivo de metadatos
    # Mensaje final de proceso completado
    logger.info("\n>>> Proceso finalizado. Verifique la carpeta 'data/raw/'.")

if __name__ == '__main__':
    main()