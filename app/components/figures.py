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


def show_single_image():
    st.subheader("🖼️ Visualizador de Imágenes de Modelos")

    images = list_images()

    if not images:
        st.warning("No se encontraron imágenes en outputs/figures")
        return

    filenames = [img.name for img in images]

    selected = st.selectbox(
        "Seleccione una imagen:",
        filenames
    )

    img_path = BASE_FIGURE / selected

    image = Image.open(img_path)

    st.image(image, caption=selected, use_container_width=True)


def show_gallery(columns=3):
    st.subheader("🧩 Galería de Imágenes")

    images = list_images()

    if not images:
        st.warning("No hay imágenes para mostrar")
        return

    rows = [images[i:i + columns] for i in range(0, len(images), columns)]

    for row in rows:
        cols = st.columns(columns)
        for col, img in zip(cols, row):
            with col:
                image = Image.open(img)
                st.image(image, caption=img.name, use_container_width=True)

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
    st.image(image, caption=image_name, use_container_width=True)
