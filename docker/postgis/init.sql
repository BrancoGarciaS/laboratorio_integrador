-- Crear extensiones espaciales
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS postgis_raster;
CREATE EXTENSION IF NOT EXISTS pgrouting;
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;
CREATE EXTENSION IF NOT EXISTS postgis_tiger_geocoder;
CREATE EXTENSION IF NOT EXISTS address_standardizer;

-- Crear esquemas
CREATE SCHEMA IF NOT EXISTS raw_data;
CREATE SCHEMA IF NOT EXISTS processed;
CREATE SCHEMA IF NOT EXISTS analysis;

-- Tabla de metadatos del proyecto
CREATE TABLE IF NOT EXISTS public.project_metadata (
    id SERIAL PRIMARY KEY,
    key VARCHAR(255) UNIQUE NOT NULL,
    value TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insertar metadatos iniciales
INSERT INTO project_metadata (key, value) VALUES
    ('project_name', 'Laboratorio Integrador'),
    ('version', '1.0.0'),
    ('created_date', CURRENT_DATE::TEXT),
    ('srid', '32719'); -- UTM Zone 19S para Chile

-- Función para actualizar timestamp
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger para actualización automática
CREATE TRIGGER update_project_metadata_updated_at
    BEFORE UPDATE ON project_metadata
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- Tabla de log de procesos
CREATE TABLE IF NOT EXISTS public.process_log (
    id SERIAL PRIMARY KEY,
    process_name VARCHAR(255),
    status VARCHAR(50),
    message TEXT,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    created_by VARCHAR(100) DEFAULT CURRENT_USER
);

-- Vista de información espacial
CREATE OR REPLACE VIEW spatial_info AS
SELECT
    f_table_schema as schema,
    f_table_name as table_name,
    f_geometry_column as geom_column,
    coord_dimension,
    srid,
    type
FROM geometry_columns
ORDER BY f_table_schema, f_table_name;

-- Mensaje de confirmación
DO $$
BEGIN
    RAISE NOTICE 'PostGIS configurado exitosamente!';
    RAISE NOTICE 'Versión: %', PostGIS_Version();
END $$;
