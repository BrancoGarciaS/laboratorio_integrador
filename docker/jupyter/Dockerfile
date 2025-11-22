FROM jupyter/scipy-notebook:python-3.11

USER root

# Instalar dependencias del sistema
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal-dev \
    libspatialindex-dev \
    libproj-dev \
    libgeos-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Configurar GDAL
ENV GDAL_CONFIG=/usr/bin/gdal-config
ENV PROJ_LIB=/usr/share/proj

USER $NB_UID

# Copiar requirements
COPY requirements.txt /tmp/

# Instalar librerías Python
RUN pip install --no-cache-dir -r /tmp/requirements.txt && \
    fix-permissions "${CONDA_DIR}" && \
    fix-permissions "/home/${NB_USER}"

# Instalar extensiones de JupyterLab
RUN jupyter labextension install @jupyter-widgets/jupyterlab-manager \
    jupyterlab-plotly \
    @jupyterlab/geojson-extension

WORKDIR /home/jovyan/work
