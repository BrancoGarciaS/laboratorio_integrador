FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema necesarias para rasterio, geopandas, etc.
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    libexpat1 \
    libgdal-dev \
    gdal-bin \
    libproj-dev \
    libgeos-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5000

CMD ["streamlit", "run", "main.py", "--server.port=5000", "--server.address=0.0.0.0"]
