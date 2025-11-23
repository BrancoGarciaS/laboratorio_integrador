# Datos del Laboratorio Integrador

Este archivo documenta el contenido de la carpeta `data/`, separando fuentes originales (`raw/`) de productos procesados (`processed/`). Permite reproducibilidad, control de calidad y verificación del cumplimiento de las fuentes mínimas requeridas en la guía del laboratorio.

## Resumen de Fuentes (raw/)

Cada dataset se limita a la comuna ingresada vía parámetro `--comuna` del script `scripts/download_data.py`.

| Archivo / Carpeta | Fuente | Filtro por comuna | Uso principal |
|-------------------|--------|-------------------|---------------|
| `comuna_boundaries_oficial.geojson` | IDE Chile (ZIP DPA oficial) | Sí (filtrado nominal dentro del shapefile) | Base cartográfica oficial / recortes |
| `osm_network.graphml` | OpenStreetMap (OSMnx) | Sí (query place) | Red vial y análisis de accesibilidad |
| `osm_buildings.geojson` | OpenStreetMap | Sí | Edificaciones (densidad, tipologías futuras) |
| `osm_amenities.geojson` | OpenStreetMap | Sí | Amenidades (POIs para accesibilidad / servicios) |
| `osm_boundary.geojson` | OSM (fallback) | Sí | Límite alternativo si falla IDE / DPA |
| `manzanas_censales.geojson` | INE (FeatureService) | Sí (WHERE sobre COMUNA) | Unidad de análisis espacial (manzana) |
| `Censo2017_ManzanaEntidad_CSV/` | INE (microdatos RAR) | Sí (CSV de manzanas reducido a código de comuna) | Atributos socio-demográficos por manzana |
| `uso_suelo_minvu/` | IDE MINVU (ZIP Koha) | Sí (podado subdir PRC sólo para la comuna) | Insumos normativos (PRC, zonas, regulaciones) |
| `uso_suelo_minvu.geojson` | Derivado (MINVU) | Sí (merge PRC comuna) | GeoJSON consolidado para análisis rápidos |
| `S34W071.hgt` (u otros tiles) | SRTM / Skadi mirrors | Indirecto (selección espacial por bbox de comuna) | Elevación bruta original tile |
| `srtm_dem.tif` | Procesado SRTM | Sí (recorte a límites) | DEM para análisis topográfico local |
| `srtm_dem_32719.tif` | Procesado SRTM reproyectado | Sí | DEM en UTM (EPSG:32719) para métricas derivadas |
| `sentinel2_B04.tif`, `sentinel2_B08.tif` | Sentinel-2 L2A (Planetary Computer) | Sí (clip a bbox + máscara límites) | Cálculo índices (NDVI, etc.) |
| `metadata.txt` | Generado | N/A | Inventario de fuentes detectadas y archivos |

## Detalle de Carpetas Importantes

### `raw/uso_suelo_minvu/IPT_Metropolitana/`
- `LU/`: Capa de usos de suelo general (se conserva completa).
- `PRC/`: Tras la descarga se filtra y se eliminan todos los archivos de otras comunas; quedan sólo los conjuntos para la comuna (variantes base, `_R`, `_ZNE` si existen).
- `PRMS/`: Capa metropolitana (referencia; no se filtra por ser supra-comunal).
- Consolidación: Los shapefiles seleccionados se combinan en `uso_suelo_minvu.geojson` para facilitar carga y análisis.

### `raw/Censo2017_ManzanaEntidad_CSV/`
Estructura RAR descomprimida del INE. El archivo `Censo2017_Manzanas.csv` ha sido filtrado para conservar sólo filas de la comuna seleccionada (manteniendo archivos de referencia regional/provincial para trazabilidad). Subcarpeta `Censo2017_Identificación_Geográfica/` incluye tablas auxiliares (Regiones, Provincias, Comunas, Distritos, Áreas, etc.).

## Filtro por Comuna (confirmación)

El script `download_data.py` aplica filtro específico para cada fuente:
- OSM (network, buildings, amenities): consulta place `"<comuna>, Chile"` restringe geocódigo.
- Límites DPA: se lee shapefile y se filtra por nombre normalizado de la comuna.
- Manzanas censales (FeatureService): cláusulas `WHERE` sobre campo COMUNA (varias variantes + fallback LIKE) hasta obtener la geometría.
- Microdatos Censo (manzanas CSV): filtrado por código oficial de comuna (fuzzy matching si nombre difiere en encoding/acentos).
- Uso de suelo MINVU: selección de shapefiles cuyo stem contiene tokens normalizados de la comuna y poda de PRC ajenos.
- DEM SRTM: selección de tiles mínimos que cubren bbox de la comuna y recorte espacial de raster.
- Sentinel-2: búsqueda STAC con `bbox` de la comuna y clip/mask por límites.

## Comandos de Ejemplo

Descarga sólo uso de suelo MINVU:
```
python scripts/download_data.py --comuna "San Joaquin" --sources ide_minvu --debug
```

Descarga completa (todas las fuentes principales):
```
python scripts/download_data.py --comuna "San Joaquin" --sources all --debug
```

Descarga censo + microdatos (activando flujo nuevo):
```
python scripts/download_data.py --comuna "San Joaquin" --sources censo --debug
```

Descarga sólo OSM + SRTM + Sentinel-2:
```
python scripts/download_data.py --comuna "San Joaquin" --sources osm,srtm,copernicus --debug
```

Uso de archivo local MINVU (ejemplo shapefile ya descargado):
```
python scripts/download_data.py --comuna "San Joaquin" --sources ide_minvu --minvu-local data/external/IPT_13_PRC_San_Joaquin.shp
```

## Próximos Pasos (procesado / análisis)

1. Generar índices (NDVI) a partir de `sentinel2_B04.tif` y `sentinel2_B08.tif` → mover resultados a `processed/`.
2. Derivar pendientes y orientaciones del DEM (`srtm_dem_32719.tif`).
3. Integrar atributos socio-demográficos con uso de suelo (join espacial manzanas ↔ zonas PRC).
4. Carga de capas consolidadas a PostGIS (contenedor Docker `postgis`).

## Notas de Reproducibilidad

- Repetir la descarga con otra comuna generará un nuevo conjunto filtrado, sobrescribiendo archivos existentes (mantener control de versiones si se comparan comunas).
- Para análisis multi-comunal se recomienda mover resultados a `processed/<comuna>/` antes de descargar la siguiente.

## Licencias y Fuentes

- OSM: Datos abiertos bajo ODbL.
- INE Censo 2017: Uso académico (ver términos INE Chile).
- SRTM: Dominio público (USGS/NASA).
- Sentinel-2: Copernicus Programme (libre uso con atribución).
- MINVU: Información pública de planificación (ver catálogo MINVU).

## Metadatos

Archivo `metadata.txt` registra: comuna, fecha de descarga ISO8601, fuentes detectadas y listado de archivos finales presente tras la ejecución del script.

ESTO LO AGREGUE YOOOO:
#### 4.8 Ingesta mínima de fuentes base

La bandera `--ingest-minimum` carga en PostGIS las fuentes originales mínimas (límite oficial, manzanas censales, uso_suelo_minvu consolidado, microdatos censo) y cataloga los rasters base (DEM y bandas Sentinel) sin mover píxeles a la base.

Acciones:
- Vectoriales → tablas (`comuna_boundaries_oficial`, `manzanas_censales`, `uso_suelo_minvu`).
- Microdatos censo → tabla `censo_microdatos` (primeras columnas para ligereza).
- Rasters base → filas en `{schema}.raster_catalog` con `source_group='raw'`.

Comando recomendado (añade índices y reproyección):
```powershell
python scripts/process_data.py --ingest-minimum --srid 32719 --index
```
Luego ejecutar derivados y productos y cargarlos al esquema de procesados:
```powershell
python scripts/process_data.py --dem-derivatives --ndvi --join-censo --join-uso-suelo --metrics --unify-uso-suelo --network-metrics --srid 32719
python scripts/process_data.py --ingest-processed --processed-schema processed_data
```
##### Verificación PostGIS de la ingesta mínima

Listar tablas cargadas en el esquema `raw_data`:
```powershell
docker compose exec postgis psql -U geouser -d geodatabase -c "SELECT table_name FROM information_schema.tables WHERE table_schema='raw_data' ORDER BY table_name;"
```

Verificar SRID de geometrías principales:
```powershell
docker compose exec postgis psql -U geouser -d geodatabase -c "SELECT 'comuna_boundaries_oficial' AS tabla, Find_SRID('raw_data','comuna_boundaries_oficial','geometry') UNION ALL SELECT 'manzanas_censales', Find_SRID('raw_data','manzanas_censales','geometry') UNION ALL SELECT 'uso_suelo_minvu', Find_SRID('raw_data','uso_suelo_minvu','geometry');"
```

Conteos básicos:
```powershell
docker compose exec postgis psql -U geouser -d geodatabase -c "SELECT COUNT(*) AS manzanas FROM raw_data.manzanas_censales;"
docker compose exec postgis psql -U geouser -d geodatabase -c "SELECT COUNT(*) AS microdatos FROM raw_data.censo_microdatos;"
docker compose exec postgis psql -U geouser -d geodatabase -c "SELECT COUNT(*) AS uso_suelo FROM raw_data.uso_suelo_minvu;"
```

Rasters base catalogados (metadatos):
```powershell
docker compose exec postgis psql -U geouser -d geodatabase -c "SELECT filename, crs, width, height, band_count FROM raw_data.raster_catalog ORDER BY filename;"
```

Si se ejecuta nuevamente `--ingest-minimum` no debería duplicar entradas en `raster_catalog` (usa PRIMARY KEY sobre filename). Para comprobar idempotencia:
```powershell
docker compose exec postgis psql -U geouser -d geodatabase -c "SELECT filename, source_group FROM raw_data.raster_catalog;"
```

Pipeline completo (mínima + derivados + catalogación processed):
```powershell
python scripts/process_data.py --ingest-minimum --srid 32719 --index
python scripts/process_data.py --dem-derivatives --ndvi --join-censo --join-uso-suelo --metrics --unify-uso-suelo --network-metrics --srid 32719
python scripts/process_data.py --ingest-processed --processed-schema processed_data
```