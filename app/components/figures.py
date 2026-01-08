import streamlit as st
from pathlib import Path
from PIL import Image

# Componente para cargar figuras como imagenes

# raíz del proyecto 
PROJECT_ROOT = Path(__file__).resolve().parents[2]

BASE_FIGURE = PROJECT_ROOT / "outputs" / "figures"

def list_images():
    exts = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp")

    return sorted(
        [p for p in BASE_FIGURE.glob("*") if p.suffix.lower() in exts]
    )

def load_image(image_name: str):
    """
    Carga una imagen específica ubicada en outputs/figures
    Parámetro:
        image_name (str): nombre del archivo (ej: "grafico1.png")
    """

    # construir ruta correctamente
    image_path = BASE_FIGURE / image_name

    # validar existencia
    if not image_path.exists():
        st.error(f"No se encontró la imagen: {image_name}")
        st.info(f"Busqué en: {image_path}")
        return

    # abrir y mostrar
    image = Image.open(image_path)
    st.image(image, caption=image_name, width=1100)
