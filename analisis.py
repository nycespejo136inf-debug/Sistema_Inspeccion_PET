
import cv2
import os

# Carpeta donde se guardarán las imágenes procesadas
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CARPETA_ANALISIS = os.path.join(
    BASE_DIR, "static", "analisis"
)

os.makedirs(CARPETA_ANALISIS, exist_ok=True)

# Umbral preliminar de clasificación
UMBRAL_BORDES = 6.0

# Umbral mínimo de nitidez
UMBRAL_NITIDEZ = 100.0


def validar_nitidez(imagen):
    """
    Calcula el nivel de nitidez de una imagen.
    Un valor bajo puede indicar que está borrosa.
    """

    gris = cv2.cvtColor(
        imagen,
        cv2.COLOR_BGR2GRAY
    )

    nitidez = cv2.Laplacian(
        gris,
        cv2.CV_64F
    ).var()

    return round(nitidez, 2)


def analizar_imagen(ruta_imagen):
    """
    Procesa una imagen de una preforma PET
    y realiza una clasificación preliminar.
    """

    # 1. Cargar imagen
    imagen = cv2.imread(ruta_imagen)

    if imagen is None:
        raise ValueError("No se pudo leer la imagen")

    # 2. Validar nitidez antes del análisis
    nitidez = validar_nitidez(imagen)

    print("Nivel de nitidez:", nitidez)

    if nitidez < UMBRAL_NITIDEZ:
        raise ValueError(
            f"Imagen borrosa. Nivel de nitidez: {nitidez}. "
            "Toma otra fotografía con mejor enfoque."
        )

    # 3. Obtener dimensiones
    alto, ancho = imagen.shape[:2]

    # 4. Redimensionar si es demasiado grande
    if ancho > 1200:

        escala = 1200 / ancho
        nuevo_ancho = 1200
        nuevo_alto = int(alto * escala)

        imagen = cv2.resize(
            imagen,
            (nuevo_ancho, nuevo_alto)
        )

    # 5. Convertir a escala de grises
    gris = cv2.cvtColor(
        imagen,
        cv2.COLOR_BGR2GRAY
    )

    # 6. Mejorar contraste
    clahe = cv2.createCLAHE(
        clipLimit=2.0,
        tileGridSize=(8, 8)
    )

    contraste = clahe.apply(gris)

    # 7. Reducir ruido
    suavizada = cv2.GaussianBlur(
        contraste,
        (5, 5),
        0
    )

    # 8. Detectar bordes
    bordes = cv2.Canny(
        suavizada,
        50,
        150
    )

    # 9. Calcular densidad de bordes
    pixeles_borde = cv2.countNonZero(bordes)

    total_pixeles = (
        bordes.shape[0] * bordes.shape[1]
    )

    densidad_bordes = (
        pixeles_borde / total_pixeles
    ) * 100

    densidad_bordes = round(
        densidad_bordes, 2
    )

    # 10. Clasificación preliminar
    if densidad_bordes >= UMBRAL_BORDES:
        estado = "Con Anomalía"
    else:
        estado = "Conforme"

    # 11. Guardar imagen procesada
    nombre = os.path.splitext(
        os.path.basename(ruta_imagen)
    )[0]

    ruta_salida = os.path.join(
        CARPETA_ANALISIS,
        nombre + "_bordes.jpg"
    )

    cv2.imwrite(ruta_salida, bordes)

    # 12. Devolver información
    return {
        "ancho": ancho,
        "alto": alto,
        "densidad_bordes": densidad_bordes,
        "nitidez": nitidez,
        "imagen_procesada": ruta_salida,
        "estado": estado
    }
