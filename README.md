# 🗺️ Laboratorio Integrador 1 - Análisis geoespacial de San Joaquín


## 📋 Descripción

Proyecto integrador que combina todas las tecnologías y métodos aprendidos en las primeras 7 clases del curso de Geoinformática. Este laboratorio requiere desarrollar un análisis territorial completo de una comuna chilena, incluyendo procesamiento de datos espaciales, geoestadística, machine learning y visualización interactiva.

## 👥 Información del Equipo

| Integrante | Rol | GitHub |
|------------|-----|--------|
| Branco García | Ingeniero y ciencista de datos geoespaciales | [@BrancoGarciaS] |
| Aracely Castro | Analista geoestadística y desarrolladora web | [@AracelyU] |

**Comuna seleccionada:** San Joaquín
**Repositorio del equipo:** [github.com/BrancoGarciaS/laboratorio_integrador](https://github.com/BrancoGarciaS/laboratorio_integrador)
**Repositorio del curso:** [github.com/franciscoparrao/geoinformatica.git](https://github.com/franciscoparrao/geoinformatica.git)

## 🚀 Quick Start

### Prerrequisitos

- Docker Desktop instalado (versión 4.0+)
- Python 3.10 o superior
- Git
- Mínimo 8GB RAM disponible
- 20GB de espacio en disco

### Resumen de todos los comandos a ejecutar:

Para evitar leer todo el README, puede ejecutar los siguientes comandos directamente:

```bash
# Clonar repositorio
git clone https://github.com/BrancoGarciaS/laboratorio_integrador.git 
cd laboratorio_integrador

# Ejecutar script de configuración
chmod +x setup.sh
./setup.sh

# Configurar variables de entorno
cp .env.example .env

# Levantar servicios Docker
docker compose up -d

# Crear ambiente virtual
python -m venv venv
```
```powershell
# Activar (en Powershell)
./venv/Scripts/Activate.ps1

# Verificar versión de Python dentro del entorno
python --version

# Instalar dependencias del proyecto (host)
pip install -r requirements.txt

# Descargar los datos requeridos
python scripts/download_data.py --comuna "San Joaquín" --year 2024 --sources all

# Procesar los datos requeridos
python scripts/process_data.py
```

Finalmente, si es que se quiere bajar los servicios Docker, se debe ejecutar lo siguiente:

```powershell
docker compose down 
```

### Instalación Rápida

```bash
# 1. Clonar el repositorio
git clone https://github.com/BrancoGarciaS/laboratorio_integrador.git
cd laboratorio_integrador

# 2. Ejecutar script de configuración
chmod +x setup.sh
./setup.sh

# 3. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus valores

# 4. Levantar servicios Docker
docker compose up -d

# 5. Verificar instalación
docker-compose ps
```

### Acceso a Servicios

| Servicio | URL | Credenciales |
|----------|-----|--------------|
| Jupyter Lab | http://localhost:8888 | Token en .env |
| PostGIS | localhost:5432 | geouser/geopass |
| Web App | http://localhost:5000 | - |
| PgAdmin | http://localhost:5050 | admin@geoinformatica.cl/admin |

## 📁 Estructura del Proyecto

```
laboratorio_integrador/
├── 📄 README.md                 # Este archivo
├── 📋 requirements.txt          # Dependencias Python
├── 🐳 docker-compose.yml        # Configuración Docker
├── 🔒 .env                      # Variables de entorno (no subir!)
├── 📝 .gitignore               # Archivos ignorados
│
├── 🐳 docker/                  # Configuraciones Docker
│   ├── jupyter/                # Imagen personalizada Jupyter
│   ├── postgis/                # Inicialización PostGIS
│   └── web/                    # Aplicación web
│
├── 💾 data/                    # Datos del proyecto
│   ├── raw/                    # Datos originales sin procesar
│   ├── processed/              # Datos procesados y limpios
│   └── external/               # Datos de fuentes externas
│
├── 📓 notebooks/               # Análisis en Jupyter
│   ├── 01_data_acquisition.ipynb
│   ├── 02_exploratory_analysis.ipynb
│   ├── 03_geostatistics.ipynb
│   ├── 04_machine_learning.ipynb
│   └── 05_results_synthesis.ipynb
│
├── 🐍 scripts/                 # Scripts Python reutilizables
│   ├── download_data.py       # Descarga automatizada
│   ├── process_data.py        # Procesamiento
│   ├── spatial_analysis.py    # Análisis espacial
│   └── utils.py              # Funciones auxiliares
│
├── 🌐 app/                    # Aplicación web Streamlit
│   ├── main.py               # Aplicación principal
│   ├── pages/                # Páginas del dashboard
│   └── components/           # Componentes reutilizables
│
├── 📊 outputs/                # Resultados generados
│   ├── figures/              # Gráficos y mapas
│   ├── models/               # Modelos ML entrenados
│   └── reports/              # Informes y documentos
│
└── 📚 docs/                   # Documentación
    ├── guia_usuario.md       # Manual de usuario
    ├── arquitectura.md       # Arquitectura técnica
    └── api_reference.md      # Referencia API
```

## 🛠️ Configuración Detallada

### 1. Configuración del Entorno Python

```bash
# Crear ambiente virtual
python -m venv venv
```

Activación según tu shell / SO:

PowerShell (Windows):
```powershell
# Si ves error de ExecutionPolicy, primero:
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

# Activar
./venv/Scripts/Activate.ps1
```

CMD (Windows clásico):
```cmd
venv\Scripts\activate.bat
```

Git Bash (Windows):
```bash
source venv/Scripts/activate  # Nota: En Windows la carpeta es Scripts, no bin
```

Linux / macOS:
```bash
source venv/bin/activate
```

Verificar versión de Python dentro del entorno:
```powershell
python --version
```

Instalar dependencias del proyecto (host):
```powershell
pip install -r requirements.txt
```

Si el comando `python` falla en PowerShell, prueba:
```powershell
py -3 -m venv venv
py -3 --version
```

Desactivar el entorno:
```powershell
deactivate
```

Problemas comunes:
- ExecutionPolicy bloquea Activate.ps1: aplicar `Set-ExecutionPolicy` como arriba.
- Usaste `source venv/bin/activate` en Windows: reemplazar por ruta `Scripts`.
- Carpeta `venv` corrupta: borrar `venv/` y recrear.
- Múltiples instalaciones de Python: confirmar con `where python` (PowerShell) o `Get-Command python`.
```

### 2. Configuración de PostGIS

```bash
# Conectarse a la base de datos (servicio 'postgis')
docker compose exec postgis psql -U geouser -d geodatabase

# Verificar extensiones
\dx

# Debe mostrar:
# - postgis
# - postgis_topology
# - postgis_raster
# - pgrouting (si está instalado)
```

### 3. Descarga de Datos

Estas instrucciones se pueden ver más en detalle en el archivo `README.md` de la carpeta `data/`:

```powershell
# Ejecutar script (desde la raíz del proyecto)
python scripts/download_data.py --comuna "San Joaquín" --year 2024 --sources all

# Descargar limites administrativos, manzanas censales y censo

python scripts/download_data.py --comuna "San Joaquín" --year 2024 --sources ine

# Descargar DEM

python scripts/download_data.py --comuna "San Joaquín" --year 2024 --sources srtm

# Descargar Sentinel-2

python scripts/download_data.py --comuna "San Joaquín" --year 2024 --sources sentinel

# Descargar red vial

python scripts/download_data.py --comuna "San Joaquín" --year 2024 --sources osm

# Descargar uso de suelo

python scripts/download_data.py --comuna "San Joaquín" --year 2024 --sources minv

# Opciones:
# --comuna     (obligatorio)
# --sources    osm | ine | all (default: all)
```

### 4. Procesamiento de datos

Estas instrucciones se pueden ver más en detalle en el archivo `README.md` de la carpeta `data/`:

Para el procesamiento de datos, se debe ejecutar el siguiente comando:

```powershell
python scripts/process_data.py
```

## 📊 Flujo de Trabajo

### Fase 1: Preparación de Datos (Semana 1)

- [ ] Seleccionar comuna de estudio
- [ ] Configurar ambiente de desarrollo
- [ ] Descargar datos de múltiples fuentes
- [ ] Cargar datos en PostGIS
- [ ] Validar calidad de datos

### Fase 2: Análisis Espacial (Semana 2)

- [ ] Análisis exploratorio (ESDA)
- [ ] Calcular autocorrelación espacial
- [ ] Identificar hot spots y clusters
- [ ] Crear visualizaciones temáticas
- [ ] Análisis geoestadístico

### Fase 3: Machine Learning y Aplicación (Semana 3)

- [ ] Feature engineering espacial
- [ ] Entrenar modelos predictivos
- [ ] Validación espacial
- [ ] Desarrollar aplicación web
- [ ] Documentar resultados

## 🔬 Análisis Incluidos

### 1. Análisis Exploratorio de Datos Espaciales (ESDA)
- Estadísticas descriptivas espaciales
- Mapas de distribución
- Análisis de patrones

### 2. Autocorrelación Espacial
- Índice de Moran Global
- LISA (Local Indicators of Spatial Association)
- Getis-Ord G*

### 3. Geoestadística
- Semivariogramas
- Kriging ordinario
- Validación cruzada

### 4. Machine Learning Geoespacial
- Random Forest espacial
- XGBoost con features geográficos
- Validación espacial (no random!)

### 5. Visualización Interactiva
- Dashboard Streamlit
- Mapas interactivos con Folium
- Gráficos dinámicos con Plotly

## 🌐 Aplicación Web

### Ejecutar la aplicación

```bash
# Desarrollo
streamlit run app/main.py

# Producción con Docker
docker-compose up web
```

### Características principales

- 🗺️ Mapa interactivo con múltiples capas
- 📈 Gráficos dinámicos de estadísticas
- 🤖 Panel de predicciones ML
- 💾 Descarga de resultados
- 📱 Diseño responsive

## 📝 Notebooks

### 1. `01_data_acquisition.ipynb`
Descarga y carga inicial de datos desde múltiples fuentes.

### 2. `02_exploratory_analysis.ipynb`
ESDA completo con visualizaciones y estadísticas.

### 3. `03_geostatistics.ipynb`
Análisis geoestadístico y interpolación espacial.

### 4. `04_machine_learning.ipynb`
Modelos predictivos con validación espacial.

### 5. `05_results_synthesis.ipynb`
Síntesis de resultados y conclusiones.

## 🧪 Testing

```bash
# Ejecutar tests unitarios
pytest tests/

# Ejecutar con coverage
pytest --cov=scripts tests/

# Verificar calidad del código
flake8 scripts/ app/
black --check scripts/ app/
```

## 📈 Monitoreo y Logs

```bash
# Ver logs de todos los servicios
docker-compose logs -f

# Logs de un servicio específico
docker-compose logs -f postgis

# Estado de los contenedores
docker stats
```

## 🐛 Troubleshooting

### Problema: Puerto en uso
```bash
# Verificar puertos en uso
sudo lsof -i :8888
sudo lsof -i :5432

# Matar proceso
kill -9 [PID]
```

### Problema: Falta de memoria Docker
```bash
# Aumentar memoria en Docker Desktop
# Settings -> Resources -> Memory -> 8GB mínimo
```

### Problema: Error de permisos
```bash
# Linux/Mac
sudo chown -R $USER:$USER .

# Dar permisos de ejecución
chmod +x scripts/*.py
```

## 📚 Recursos y Referencias

### Documentación Oficial
- [GeoPandas](https://geopandas.org)
- [PySAL](https://pysal.org)
- [OSMnx](https://osmnx.readthedocs.io)
- [Streamlit](https://docs.streamlit.io)
- [PostGIS](https://postgis.net/docs/)

### Fuentes de Datos
- [IDE Chile](https://www.ide.cl)
- [INE Chile](https://www.ine.cl)
- [OpenStreetMap](https://www.openstreetmap.org)
- [Google Earth Engine](https://earthengine.google.com)
- [Sentinel Hub](https://www.sentinel-hub.com)

### Tutoriales Recomendados
- [Automating GIS Processes](https://automating-gis-processes.github.io)
- [Geographic Data Science](https://geographicdata.science)
- [Spatial Thoughts](https://spatialthoughts.com)

## 👨‍💻 Desarrollo

### Convenciones de código

- Python: PEP 8
- Commits: Conventional Commits
- Branches: `feature/nombre`, `fix/nombre`, `docs/nombre`

### Flujo de Git

```bash
# Crear rama para nueva característica
git checkout -b feature/analisis-clustering

# Hacer cambios y commit
git add .
git commit -m "feat: agregar análisis de clustering DBSCAN"

# Push y crear PR
git push origin feature/analisis-clustering
```

## 📊 Métricas del Proyecto

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Docker](https://img.shields.io/badge/Docker-Compose-blue)
![PostGIS](https://img.shields.io/badge/PostGIS-3.3-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

### Estadísticas de código

- Líneas de código Python: [XXX]
- Notebooks Jupyter: 5
- Tests escritos: [XX]
- Coverage: [XX]%

## 📄 Licencia

Este proyecto fue desarrollado como parte del curso de Geoinformática en USACH.

## 🙏 Agradecimientos

- Prof. Francisco Parra O. por la guía y enseñanza
- Compañeros de curso por el feedback
- Comunidad Open Source por las herramientas

## 📧 Contacto

Para consultas sobre el proyecto:
- Email: [tu-email@usach.cl]
- GitHub Issues: [github.com/franciscoparrao/geoinformatica/issues](https://github.com/franciscoparrao/geoinformatica/issues)
- Repositorio: [github.com/franciscoparrao/geoinformatica](https://github.com/franciscoparrao/geoinformatica)

---

**Última actualización:** $(date)

**Estado del proyecto:** 🚧 En desarrollo

```mermaid
graph LR
    A[Datos Raw] --> B[Procesamiento]
    B --> C[PostGIS]
    C --> D[Análisis Espacial]
    D --> E[Machine Learning]
    E --> F[Web App]
    F --> G[Usuario Final]
```