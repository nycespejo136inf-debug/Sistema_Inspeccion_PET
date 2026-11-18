
from analisis import analizar_imagen
import os

# Imágenes de referencia
imagenes = [
    os.path.join(
        "dataset_preformas",
        "conforme",
        "preforma_conforme_01.jpg"
    ),
    os.path.join(
        "dataset_preformas",
        "con_anomalia",
        "preforma_anomalia_01.png"
    )
]

for ruta in imagenes:

    print("\n-----------------------------")
    print("PROCESANDO:", ruta)

    if not os.path.exists(ruta):
        print("No se encontró la imagen")
        continue

    resultado = analizar_imagen(ruta)

    print("Ancho:", resultado["ancho"])
    print("Alto:", resultado["alto"])

    print(
        "Densidad de bordes:",
        resultado["densidad_bordes"], "%"
    )

    print(
        "Imagen procesada:",
        resultado["imagen_procesada"]
    )

    print("Estado:", resultado["estado"])
