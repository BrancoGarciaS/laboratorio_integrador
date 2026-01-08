# Datos del laboratorio integrador:

Este archivo documenta el contenido de la carpeta `data/`, separando fuentes originales (`raw/`) de los archivos procesados (`processed/`). Permitiendo la reproducibilidad, control de calidad y verificación del cumplimiento de las fuentes mínimas requeridas en la guía del laboratorio.

## 1. Requisitos previos:

Asegurarse de tener el entorno virtual activado y las dependencias instaladas:

```bash
# Levantar servicios Docker
docker compose up -d

# Activar entorno (Windows PowerShell)
../venv/Scripts/Activate.ps1

# Instalar dependencias
pip install -r ../requirements.txt
```

## 2. Resumen: comandos a ejecutar para descargar y procesar datos:

Para descargar y procesar los datos, se deben ejecutar los siguientes comandos:

```bash
# Descarga de datos
python download_data.py --comuna "San Joaquín" --year 2024 --sources all

# Procesamiento de datos
python scripts/process_data.py
```

## 3. Descargar datos:

En la carpeta `scripts/` se tiene el código para la adquisición de datos (`download_data.py`), el cual se conecta a diversas APIs y servicios (INE, OpenStreetMap, Google Earth Engine / Copernicus, IDE Minvu) para descargar los datos crudos en `data/raw/`.

Para descargar todas las capas necesarias para una comuna específica (ej.: San Joaquín) y un año de referencia, se debe ejecutar el siguiente comando:

```bash
python download_data.py --comuna "San Joaquín" --year 2024 --sources all
```

Si se necesita descargar o actualizar solo una fuente en particular, se puede usar el flag --sources con las siguientes combinaciones:

| Fuente de Datos        | Comando              | Descripción                                                                 | Archivos Generados (data/raw)                                               |
|------------------------|----------------------|------------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| INE / IDE Chile        | --sources ine     | Límites comunales, manzanas censales y datos del Censo 2017.                 | comuna_boundaries_oficial.geojson, manzanas_censales.geojson, Censo2017_... |
| OpenStreetMap          | --sources osm     | Red vial, edificios y equipamiento (amenities).                              | osm_network.graphml, osm_buildings.geojson, osm_amenities.geojson           |
| DEM (Topografía)       | --sources srtm    | Modelo Digital de Elevación (SRTM).                                          | srtm_dem.tif, srtm_dem_32719.tif (reproyectado)                             |
| Sentinel-2             | --sources sentinel| Imágenes satelitales (bandas roja e infrarroja) para cálculo de NDVI.         | sentinel2_B04.tif (Roja), sentinel2_B08.tif (NIR)                          |
| IDE Minvu              | --sources minvu   | Capas de uso de suelo y planificación territorial.                           | uso_suelo_minvu.geojson                                                    |

Por ejemplo, se pueden ejecutar los siguientes comandos:

```bash
# Solo descargar la red vial
python download_data.py --comuna "San Joaquín" --year 2024 --sources osm

# Solo descargar topografía (DEM)
python download_data.py --comuna "San Joaquín" --year 2024 --sources srtm
```

### Fuentes de datos mínimas requeridas (obtenidas con el script de descarga):

La siguiente tabla detalla los datos requeridos del enunciado, obtenidos para la comuna de San Joaquín en la carpeta de descarga `data/raw`, con el script `download_data.py`:

| Tipo de Dato | Archivo obtenido (Raw) | Fuente | Uso Principal |
| :--- | :--- | :--- | :--- |
| **Límites administrativos** | `comuna_boundaries_oficial.geojson` | IDE Chile (API) | Recorte de capas y definición de zona de estudio |
| **Manzanas censales** | `manzanas_censales.geojson` | INE (ArcGIS REST) | Unidad mínima de análisis espacial (vectores) |
| **Censo 2017** | `Censo2017_Manzanas.csv` | INE (Redatam) | Variables demográficas y socioeconómicas (tabla) |
| **Red vial** | `osm_network.graphml` | OpenStreetMap (OSMnx) | Cálculo de accesibilidad, centralidad y densidad |
| **Uso del suelo** | `uso_suelo_minvu.geojson` | IDE Minvu | Zonificación y planificación territorial |
| **DEM** | `srtm_dem_32719.tif` | SRTM (NASA/USGS) | Análisis topográfico (pendiente, aspecto) |
| **Sentinel-2** | `sentinel2_B04.tif` y `B08.tif` | Copernicus (AWS) | Cálculo de índice de vegetación (NDVI) |

> **Notas:**
> * `Censo2017_Manzanas.csv` está ubicado en: `data/raw/Censo2017_ManzanaEntidad_CSV/...`
> * `uso_suelo_minvu.geojson` fue consolidado desde: `data/raw/uso_suelo_minvu/IPT_Metropolitana/PRC/IPT_13_PRC_San_Joaquin.shp`
> * `srtm_dem_32719.tif` derivado de: `S34W071.hgt` (recortado y reproyectado a EPSG:32719)
> Se genera automáticamente el archivo `metadata.txt` que tiene la función de ser un inventario de fuentes detectadas y archivos.

## 4. Procesar datos:

En la carpeta `scripts/` se tiene el código para el procesamiento de datos (`process_data.py`), el cual toma los archivos crudos de `data/raw/`, realiza limpieza, cálculos espaciales (como NDVI, pendientes, métricas de red) y genera productos listos para el análisis en `data/processed/`. También maneja la ingesta a la base de datos PostGIS.

Para ejecutar el pipeline completo de procesamiento (limpieza, generación de métricas e ingesta a base de datos), se debe ejecutar el siguiente comando:

```bash
python scripts/process_data.py
```

También se pueden usar ciertas banderas para fines específicos:
```bash
# Solo calcular NDVI y pendientes (sin tocar la base de datos)
python process_data.py --ndvi --dem

# Ejecutar todo el análisis pero SIN ingestar a PostGIS (solo archivos locales)
python process_data.py --ndvi --dem --network --metrics --uso-suelo

```

Nota: La bandera `--ingest-minimum` carga en PostGIS las fuentes originales mínimas (límite oficial, manzanas censales, uso_suelo_minvu consolidado, microdatos censo) y cataloga los rasters base (DEM y bandas Sentinel) sin mover píxeles a la base.

### Datos procesados

La siguiente tabla detalla todos los archivos resultantes del pipeline de procesamiento (`process_data.py`), guardados en `data/processed`:

| Categoría | Archivo Procesado | Contenido / Transformación Realizada |
| :--- | :--- | :--- |
| **Dataset integrado** | `manzanas_atributos.geojson` | Unión de geometría de manzanas + Datos Censo (Join por `manzent`). Base del análisis sociodemográfico. |
|  | `manzanas_uso_suelo.geojson` | Cruce espacial (Overlay) entre manzanas y zonas de uso de suelo del MINVU. |
| **Métricas calculadas** | `metrics_network.csv` | Métricas avanzadas de red (Betweenness, Densidad vial) por manzana. |
|  | `metrics_manzanas.csv` | Métricas básicas por manzana: conteo de edificios y amenidades interiores. |
| **Elementos de red** | `network_nodes_metrics.geojson` | Nodos de la red vial con valores de centralidad calculados. |
|  | `osm_network.gpkg` | Grafo vial convertido a formato GeoPackage optimizado para GIS. |
| **Índices raster** | `sentinel2_ndvi.tif` | Índice de Vegetación (NDVI) calculado desde bandas Sentinel-2 (B08 y B04). |
| **Topografía** | `slope.tif` / `aspect.tif` | Mapas de Pendiente (grados) y Orientación derivados del DEM. |
| **Capas base procesadas** | `comuna_boundaries_oficial.geojson` | Límite comunal reproyectado a EPSG:32719 para consistencia espacial. |
|  | `manzanas_censales.geojson` | Geometrías de manzanas reproyectadas y con topología limpia. |
|  | `uso_suelo_minvu.geojson` | Capa de uso de suelo reproyectada y estandarizada. |
|  | `osm_buildings.geojson` | Edificios de OSM filtrados, reproyectados y limpios. |
|  | `osm_amenities.geojson` | Puntos de interés (escuelas, hospitales, etc.) reproyectados. |
| **Tablas auxiliares** | `censo_microdatos.csv` | CSV del Censo con codificación corregida y separado por punto y coma. |

