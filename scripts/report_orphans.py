#!/usr/bin/env python3
"""Reporte de microdatos huérfanos (sin geometría de manzana).

Uso:
  python scripts/report_orphans.py --output data/processed/orphans_microdatos.csv

Genera un CSV con los registros de raw_data.censo_microdatos cuyo manzent
no tiene correspondencia en raw_data.manzanas_censales.
"""
import os
import argparse
import pandas as pd
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

def get_engine():
    user = os.getenv('POSTGRES_USER')
    pwd = os.getenv('POSTGRES_PASSWORD')
    host = os.getenv('POSTGRES_HOST', 'localhost')
    port = os.getenv('POSTGRES_PORT', '5432')
    db = os.getenv('POSTGRES_DB')
    return create_engine(f'postgresql://{user}:{pwd}@{host}:{port}/{db}')


def fetch_orphans(engine):
    sql = text("""
        SELECT c.*
        FROM raw_data.censo_microdatos c
        LEFT JOIN raw_data.manzanas_censales m ON c.manzent = m.manzent
        WHERE m.manzent IS NULL
    """)
    with engine.begin() as conn:
        df = pd.read_sql(sql, conn)
    return df


def main():
    parser = argparse.ArgumentParser(description='Generar reporte de microdatos huérfanos')
    parser.add_argument('--output', type=str, default='data/processed/orphans_microdatos.csv', help='Ruta de salida CSV')
    args = parser.parse_args()

    engine = get_engine()
    df = fetch_orphans(engine)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)

    print(f"Huérfanos encontrados: {len(df)}")
    print(f"Guardado CSV en: {out_path}")
    if len(df):
        print("Primeras filas:")
        print(df.head())

if __name__ == '__main__':
    main()
