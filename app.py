import time
from datetime import datetime
from flask import send_file
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image as RLImage
)
from xml.sax.saxutils import escape
from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash
)

from werkzeug.security import (
    check_password_hash,
    generate_password_hash
)

from werkzeug.utils import secure_filename

from database import (
    conectar,
    inicializar_bd,
    registrar_acceso
)

from analisis import analizar_imagen

import cv2
import os
import uuid


app = Flask(__name__)

app.secret_key = "cambiar_esta_clave_por_una_segura"


# ==========================================
# CONFIGURACIÓN DEL SISTEMA
# ==========================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CARPETA_IMAGENES = os.path.join(
    BASE_DIR, "static", "imagenes"
)

CARPETA_ANALISIS = os.path.join(
    BASE_DIR, "static", "analisis"
)

os.makedirs(CARPETA_IMAGENES, exist_ok=True)
os.makedirs(CARPETA_ANALISIS, exist_ok=True)
os.makedirs("reportes", exist_ok=True)

EXTENSIONES = {"jpg", "jpeg", "png", "bmp"}

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
# ==========================================
# CONTROL DE ARCHIVOS MAYORES A 10 MB
# ==========================================

@app.errorhandler(413)
def archivo_demasiado_grande(error):

    flash(
        "La imagen supera el límite permitido de 10 MB. "
        "Seleccione otra fotografía.",
        "error"
    )

    if usuario_requerido():
        return redirect(url_for("inspeccion"))

    return redirect(url_for("login"))

# ==========================================
# FUNCIONES GENERALES
# ==========================================

def archivo_permitido(nombre):

    return (
        "." in nombre
        and nombre.rsplit(".", 1)[1].lower() in EXTENSIONES
    )


def usuario_requerido():

    return "usuario" in session


def administrador_requerido():

    return session.get("rol") == "Administrador"


# ==========================================
# INICIO
# ==========================================

@app.route("/")
def inicio():

    if usuario_requerido():
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


# ==========================================
# INICIAR SESIÓN
# ==========================================

@app.route("/login", methods=["GET", "POST"])
def login():

    inicio_perf001 = time.perf_counter() if request.method == "POST" else None

    if request.method == "POST":

        usuario = request.form["usuario"].strip()
        password = request.form["password"]

        conexion = conectar()

        try:
            resultado = conexion.execute("""
                SELECT * FROM usuarios
                WHERE usuario = ?
            """, (usuario,)).fetchone()

        finally:
            conexion.close()

        if resultado and check_password_hash(
            resultado["password"], password
        ):

            session["usuario"] = resultado["usuario"]
            session["nombre"] = resultado["nombre"]
            session["rol"] = resultado["rol"]

            registrar_acceso(resultado["usuario"])

            # Guardar el inicio para medir hasta la carga del panel
            session["_perf001_inicio"] = inicio_perf001

            return redirect(url_for("dashboard"))

        flash("Usuario o contraseña incorrectos")

    return render_template("login.html")
# ==========================================
# PANEL PRINCIPAL
# ==========================================

@app.route("/dashboard")
def dashboard():

    if not usuario_requerido():
        return redirect(url_for("login"))

    conexion = conectar()

    try:

        total = conexion.execute("""
            SELECT COUNT(*) AS cantidad
            FROM inspecciones
        """).fetchone()["cantidad"]

        pendientes = conexion.execute("""
            SELECT COUNT(*) AS cantidad
            FROM inspecciones
            WHERE resultado IN (
                'Pendiente de análisis',
                'Pendiente de clasificación'
            )
        """).fetchone()["cantidad"]

        historial = conexion.execute("""
            SELECT *
            FROM inspecciones
            ORDER BY id DESC
            LIMIT 5
        """).fetchall()

    finally:
        conexion.close()

    respuesta = render_template(
        "dashboard.html",
        total=total,
        pendientes=pendientes,
        historial=historial
    )

    inicio = session.pop("_perf001_inicio", None)

    if inicio is not None:

        tiempo_ms = (time.perf_counter() - inicio) * 1000

        print("--------------------------------")
        print("PRUEBA PERF001")
        print("Inicio de sesión y carga del panel")
        print("Tiempo de respuesta:", round(tiempo_ms, 2), "ms")
        print("--------------------------------")

    return respuesta


# ==========================================
# MÓDULO DE INSPECCIÓN
# ==========================================


@app.route("/inspeccion", methods=["GET", "POST"])
def inspeccion():

    if not usuario_requerido():
        return redirect(url_for("login"))

    if request.method == "POST":
        inicio_perf002 = time.perf_counter()
        # 1. Comprobar que se haya enviado una imagen
        if "imagen" not in request.files:
            flash(
                "No se recibió ninguna imagen. Seleccione una fotografía.",
                "error"
            )
            return redirect(url_for("inspeccion"))

        archivo = request.files["imagen"]

        # 2. Comprobar que se haya seleccionado un archivo
        if not archivo.filename or not archivo.filename.strip():
            flash(
                "No seleccionó ninguna imagen. Intente nuevamente.",
                "error"
            )
            return redirect(url_for("inspeccion"))

        # 3. Validar formato
        if not archivo_permitido(archivo.filename):
            flash(
                "Formato no permitido. Utilice JPG, JPEG, PNG o BMP.",
                "error"
            )
            return redirect(url_for("inspeccion"))

        # 4. Generar nombre único
        extension = archivo.filename.rsplit(".", 1)[1].lower()

        nombre_archivo = secure_filename(
            str(uuid.uuid4()) + "." + extension
        )

        ruta = os.path.join(
            CARPETA_IMAGENES,
            nombre_archivo
        )

        # 5. Guardar imagen temporalmente
        archivo.save(ruta)
        tiempo_guardado = (
            time.perf_counter() - inicio_perf002
        ) * 1000

        inicio_perf003 = time.perf_counter()
        # 6. Comprobar que el archivo no esté vacío
        if not os.path.isfile(ruta) or os.path.getsize(ruta) == 0:

            if os.path.exists(ruta):
                os.remove(ruta)

            flash(
                "El archivo está vacío. Seleccione otra imagen.",
                "error"
            )
            return redirect(url_for("inspeccion"))

        # 7. Verificar que OpenCV pueda leer la imagen
        imagen = cv2.imread(ruta)
        if imagen is None:
            if os.path.exists(ruta):
                os.remove(ruta)

            flash(
                "La imagen está dañada o no se puede leer. "
                "Seleccione otra fotografía o capture una nueva.",
                "error"
            )
            return redirect(url_for("inspeccion"))

        # 8. Procesamiento con OpenCV
        try:

            datos_analisis = analizar_imagen(ruta)

            resultado = datos_analisis["estado"]
            densidad = datos_analisis["densidad_bordes"]
            tiempo_validacion = (
                time.perf_counter() - inicio_perf003
            ) * 1000

            print("--------------------------------")
            print("PRUEBA PERF002")
            print("Guardado de imagen:", round(tiempo_guardado, 2), "ms")
            print("--------------------------------")

            print("PRUEBA PERF003")
            print(
                "Validación y procesamiento:",
                round(tiempo_validacion, 2),
                "ms"
            )
            print("--------------------------------")
            print("--------------------------------")
            print("INSPECCIÓN PROCESADA")
            print("Usuario:", session["usuario"])
            print("Imagen:", nombre_archivo)
            print("Ancho:", datos_analisis["ancho"])
            print("Alto:", datos_analisis["alto"])
            print("Densidad de bordes:", densidad, "%")
            print("Resultado:", resultado)
            print("--------------------------------")

        except Exception as error:

            print("Error durante el análisis:", error)

            if os.path.exists(ruta):
                os.remove(ruta)

            mensaje = str(error)

            if "Imagen borrosa" in mensaje:
                flash(
                    "IMAGEN NO VÁLIDA: La fotografía está borrosa. "
                    "Capture o seleccione otra imagen.",
                    "error"
                )
            else:
                flash(
                    "No fue posible procesar la imagen. "
                    "Seleccione otra fotografía.",
                    "error"
                )

            return redirect(url_for("inspeccion"))

        # 9. Guardar resultado en MySQL
        conexion = conectar()

        try:

            conexion.execute("""
                INSERT INTO inspecciones
                (usuario, imagen, resultado)
                VALUES (?, ?, ?)
            """, (
                session["usuario"],
                nombre_archivo,
                resultado
            ))

            conexion.commit()

        except Exception as error:

            conexion.rollback()

            print("Error al guardar inspección:", error)

            if os.path.exists(ruta):
                os.remove(ruta)

            flash(
                "No se pudo guardar la inspección en la base de datos.",
                "error"
            )

            return redirect(url_for("inspeccion"))

        finally:

            conexion.close()

        # 10. Confirmación
        flash(
            "Imagen procesada correctamente. "
            "Densidad de bordes: " + str(densidad) + "%",
            "success"
        )

        return redirect(url_for("historial"))

    return render_template("inspeccion.html")


# ==========================================
# HISTORIAL DE INSPECCIONES
# ==========================================

@app.route("/historial")
def historial():

    if not usuario_requerido():
        return redirect(url_for("login"))

    conexion = conectar()

    try:

        registros = conexion.execute("""
            SELECT *
            FROM inspecciones
            ORDER BY id DESC
        """).fetchall()

    finally:

        conexion.close()

    return render_template(
        "historial.html",
        registros=registros
    )

# ==========================================
# MÓDULO DE REPORTES
# ==========================================

def obtener_datos_reporte(registro):

    nombre_imagen = os.path.basename(registro["imagen"])

    ruta_original = os.path.join(
        CARPETA_IMAGENES,
        nombre_imagen
    )

    datos = {
        "registro": registro,
        "densidad": None,
        "ruta_original": None,
        "ruta_procesada": None,
        "imagen_original_url": None,
        "imagen_procesada_url": None
    }

    if os.path.isfile(ruta_original):

        datos["ruta_original"] = ruta_original

        datos["imagen_original_url"] = url_for(
            "static",
            filename="imagenes/" + nombre_imagen
        )

        try:

            resultado_analisis = analizar_imagen(ruta_original)

            datos["densidad"] = resultado_analisis["densidad_bordes"]

            ruta_procesada = resultado_analisis["imagen_procesada"]

            if os.path.isfile(ruta_procesada):

                datos["ruta_procesada"] = ruta_procesada

                nombre_procesada = os.path.basename(ruta_procesada)

                datos["imagen_procesada_url"] = url_for(
                    "static",
                    filename="analisis/" + nombre_procesada
                )

        except Exception as error:

            print("No se pudo obtener el análisis para el reporte:", error)

    return datos


def generar_pdf_individual(datos):

    memoria = BytesIO()

    documento = SimpleDocTemplate(
        memoria,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm
    )

    estilos = getSampleStyleSheet()

    titulo = ParagraphStyle(
        "TituloReporte",
        parent=estilos["Title"],
        fontSize=19,
        textColor=colors.HexColor("#173b62"),
        alignment=TA_CENTER,
        spaceAfter=8
    )

    subtitulo = ParagraphStyle(
        "SubtituloReporte",
        parent=estilos["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#526477"),
        alignment=TA_CENTER,
        spaceAfter=20
    )

    normal = ParagraphStyle(
        "TextoReporte",
        parent=estilos["Normal"],
        fontSize=9,
        leading=14
    )

    registro = datos["registro"]

    elementos = []

    elementos.append(Paragraph(
        "EMPACAR S.A.",
        titulo
    ))

    elementos.append(Paragraph(
        "SISTEMA INTELIGENTE DE CONTROL DE CALIDAD PET",
        subtitulo
    ))

    elementos.append(Paragraph(
        "REPORTE INDIVIDUAL DE INSPECCIÓN",
        ParagraphStyle(
            "Seccion",
            parent=estilos["Heading2"],
            textColor=colors.HexColor("#173b62"),
            alignment=TA_CENTER
        )
    ))

    elementos.append(Spacer(1, 15))

    resultado = escape(str(registro["resultado"]))

    densidad = (
        str(datos["densidad"]) + " %"
        if datos["densidad"] is not None
        else "No disponible"
    )

    informacion = [
        ["Código de inspección", str(registro["id"])],
        ["Usuario responsable", escape(str(registro["usuario"]))],
        ["Fecha y hora", escape(str(registro["fecha"]))],
        ["Resultado registrado", resultado],
        ["Densidad de bordes", densidad],
        ["Imagen", escape(str(registro["imagen"]))]
    ]

    tabla = Table(
        informacion,
        colWidths=[5 * cm, 11 * cm]
    )

    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eaf2fb")),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#173b62")),
        ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#344b63")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dce4ec")),
        ("PADDING", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE")
    ]))

    elementos.append(tabla)
    elementos.append(Spacer(1, 22))

    elementos.append(Paragraph(
        "EVIDENCIA FOTOGRÁFICA",
        estilos["Heading2"]
    ))

    imagenes = []

    if datos["ruta_original"]:

        imagen_original = RLImage(
            datos["ruta_original"],
            width=7 * cm,
            height=5 * cm,
            kind="proportional"
        )

        imagenes.append([
            imagen_original,
            Paragraph("Imagen original", normal)
        ])

    if datos["ruta_procesada"]:

        imagen_procesada = RLImage(
            datos["ruta_procesada"],
            width=7 * cm,
            height=5 * cm,
            kind="proportional"
        )

        imagenes.append([
            imagen_procesada,
            Paragraph("Imagen procesada", normal)
        ])

    for imagen in imagenes:

        elementos.append(imagen[0])
        elementos.append(Paragraph(imagen[1].text, normal))
        elementos.append(Spacer(1, 12))

    elementos.append(Spacer(1, 15))

    elementos.append(Paragraph(
        "Documento generado por el Sistema Inteligente de Inspección PET - EMPACAR S.A.",
        normal
    ))

    documento.build(elementos)

    memoria.seek(0)

    return memoria


def generar_pdf_general(registros, resumen):

    memoria = BytesIO()

    documento = SimpleDocTemplate(
        memoria,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm
    )

    estilos = getSampleStyleSheet()

    elementos = []

    elementos.append(Paragraph(
        "EMPACAR S.A.",
        ParagraphStyle(
            "TituloGeneral",
            parent=estilos["Title"],
            fontSize=20,
            textColor=colors.HexColor("#173b62"),
            alignment=TA_CENTER
        )
    ))

    elementos.append(Paragraph(
        "REPORTE GENERAL DE INSPECCIONES PET",
        ParagraphStyle(
            "SubtituloGeneral",
            parent=estilos["Heading2"],
            textColor=colors.HexColor("#245b8e"),
            alignment=TA_CENTER
        )
    ))

    elementos.append(Spacer(1, 20))

    elementos.append(Paragraph(
        "RESUMEN GENERAL",
        estilos["Heading2"]
    ))

    datos_resumen = [
        ["Total de inspecciones", "Conformes", "Con anomalía", "Pendientes"],
        [
            str(resumen["total"]),
            str(resumen["conformes"]),
            str(resumen["anomalias"]),
            str(resumen["pendientes"])
        ]
    ]

    tabla_resumen = Table(
        datos_resumen,
        colWidths=[4 * cm, 4 * cm, 4 * cm, 4 * cm]
    )

    tabla_resumen.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173b62")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#eaf2fb")),
        ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#173b62")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.white),
        ("PADDING", (0, 0), (-1, -1), 9)
    ]))

    elementos.append(tabla_resumen)
    elementos.append(Spacer(1, 22))

    elementos.append(Paragraph(
        "DETALLE DE INSPECCIONES",
        estilos["Heading2"]
    ))

    encabezados = [
        "ID",
        "Usuario",
        "Imagen",
        "Resultado",
        "Fecha"
    ]

    datos_tabla = [encabezados]

    for registro in registros:

        datos_tabla.append([
            str(registro["id"]),
            Paragraph(escape(str(registro["usuario"])), estilos["Normal"]),
            Paragraph(escape(str(registro["imagen"])), estilos["Normal"]),
            Paragraph(escape(str(registro["resultado"])), estilos["Normal"]),
            Paragraph(escape(str(registro["fecha"])), estilos["Normal"])
        ])

    if not registros:

        datos_tabla.append([
            "-", "-", "-", "No hay inspecciones", "-"
        ])

    tabla_detalle = Table(
        datos_tabla,
        colWidths=[
            1.2 * cm,
            3 * cm,
            4 * cm,
            4 * cm,
            4 * cm
        ],
        repeatRows=1
    )

    tabla_detalle.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173b62")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dce4ec")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white,
            colors.HexColor("#f3f7fb")
        ]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 6)
    ]))

    elementos.append(tabla_detalle)

    documento.build(elementos)

    memoria.seek(0)

    return memoria


# ==========================================
# LISTADO PRINCIPAL DE REPORTES
# ==========================================

@app.route("/reportes")
def reportes():

    if not usuario_requerido():
        return redirect(url_for("login"))

    conexion = conectar()

    try:

        registros = conexion.execute("""
            SELECT *
            FROM inspecciones
            ORDER BY id DESC
        """).fetchall()

    finally:

        conexion.close()

    resumen = {
        "total": len(registros),
        "conformes": sum(
            1 for r in registros
            if str(r["resultado"]).lower() == "conforme"
        ),
        "anomalias": sum(
            1 for r in registros
            if str(r["resultado"]).lower() == "con anomalía"
        ),
        "pendientes": sum(
            1 for r in registros
            if "pendiente" in str(r["resultado"]).lower()
        )
    }

    return render_template(
        "reportes.html",
        registros=registros,
        resumen=resumen
    )


# ==========================================
# VISTA PREVIA DEL REPORTE INDIVIDUAL
# ==========================================

@app.route("/reporte_individual/<int:id>")
def reporte_individual(id):

    if not usuario_requerido():
        return redirect(url_for("login"))

    conexion = conectar()

    try:

        registro = conexion.execute("""
            SELECT *
            FROM inspecciones
            WHERE id = ?
        """, (id,)).fetchone()

    finally:

        conexion.close()

    if not registro:

        flash("No se encontró la inspección solicitada")
        return redirect(url_for("reportes"))

    datos = obtener_datos_reporte(registro)

    return render_template(
        "reporte_individual.html",
        datos=datos
    )


# ==========================================
# DESCARGAR PDF INDIVIDUAL
# ==========================================

@app.route("/reporte_individual/<int:id>/pdf")
def descargar_reporte_individual(id):

    if not usuario_requerido():
        return redirect(url_for("login"))

    conexion = conectar()

    try:

        registro = conexion.execute("""
            SELECT *
            FROM inspecciones
            WHERE id = ?
        """, (id,)).fetchone()

    finally:

        conexion.close()

    if not registro:

        flash("No se encontró la inspección solicitada")
        return redirect(url_for("reportes"))

    datos = obtener_datos_reporte(registro)

    pdf = generar_pdf_individual(datos)

    return send_file(
        pdf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"Reporte_Inspeccion_{id}.pdf"
    )


# ==========================================
# VISTA PREVIA DEL REPORTE GENERAL
# ==========================================

@app.route("/reporte_general")
def reporte_general():

    if not usuario_requerido():
        return redirect(url_for("login"))

    conexion = conectar()

    try:

        registros = conexion.execute("""
            SELECT *
            FROM inspecciones
            ORDER BY id DESC
        """).fetchall()

    finally:

        conexion.close()

    resumen = {
        "total": len(registros),
        "conformes": sum(
            1 for r in registros
            if str(r["resultado"]).lower() == "conforme"
        ),
        "anomalias": sum(
            1 for r in registros
            if str(r["resultado"]).lower() == "con anomalía"
        ),
        "pendientes": sum(
            1 for r in registros
            if "pendiente" in str(r["resultado"]).lower()
        )
    }

    return render_template(
        "reporte_general.html",
        registros=registros,
        resumen=resumen
    )


# ==========================================
# DESCARGAR PDF GENERAL
# ==========================================

@app.route("/reporte_general/pdf")
def descargar_reporte_general():

    if not usuario_requerido():
        return redirect(url_for("login"))

    conexion = conectar()

    try:

        registros = conexion.execute("""
            SELECT *
            FROM inspecciones
            ORDER BY id DESC
        """).fetchall()

    finally:

        conexion.close()

    resumen = {
        "total": len(registros),
        "conformes": sum(
            1 for r in registros
            if str(r["resultado"]).lower() == "conforme"
        ),
        "anomalias": sum(
            1 for r in registros
            if str(r["resultado"]).lower() == "con anomalía"
        ),
        "pendientes": sum(
            1 for r in registros
            if "pendiente" in str(r["resultado"]).lower()
        )
    }

    pdf = generar_pdf_general(registros, resumen)

    return send_file(
        pdf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="Reporte_General_Inspecciones_PET.pdf"
    )


# ==========================================
# ADMINISTRACIÓN DE USUARIOS
# ==========================================

@app.route("/usuarios")
def usuarios():

    if not usuario_requerido():
        return redirect(url_for("login"))

    if not administrador_requerido():
        flash("No tienes permiso para acceder")
        return redirect(url_for("dashboard"))

    conexion = conectar()

    try:

        registros = conexion.execute("""
            SELECT id, nombre, usuario, rol
            FROM usuarios
            ORDER BY id DESC
        """).fetchall()

    finally:

        conexion.close()

    return render_template(
        "usuarios.html",
        registros=registros
    )


# ==========================================
# CREAR NUEVO USUARIO
# ==========================================

@app.route("/crear_usuario", methods=["GET", "POST"])
def crear_usuario():

    if not usuario_requerido():
        return redirect(url_for("login"))

    if not administrador_requerido():
        flash("No tienes permiso para realizar esta acción")
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        nombre = request.form["nombre"].strip()
        usuario = request.form["usuario"].strip()
        password = request.form["password"]
        rol = request.form["rol"]

        if not nombre or not usuario or not password:
            flash("Completa todos los campos")
            return redirect(url_for("crear_usuario"))

        if len(password) < 8:
            flash("La contraseña debe tener al menos 8 caracteres")
            return redirect(url_for("crear_usuario"))

        if rol not in ["Administrador", "Operador"]:
            flash("Rol no válido")
            return redirect(url_for("crear_usuario"))

        conexion = conectar()

        try:

            existente = conexion.execute("""
                SELECT id FROM usuarios
                WHERE usuario = ?
            """, (usuario,)).fetchone()

            if existente:
                flash("Ese nombre de usuario ya existe")
                return redirect(url_for("crear_usuario"))

            conexion.execute("""
                INSERT INTO usuarios
                (nombre, usuario, password, rol)
                VALUES (?, ?, ?, ?)
            """, (
                nombre,
                usuario,
                generate_password_hash(password),
                rol
            ))

            conexion.commit()

            flash("Usuario creado correctamente")
            return redirect(url_for("usuarios"))

        except Exception as error:

            conexion.rollback()
            print("Error al crear usuario:", error)
            flash("No se pudo crear el usuario")

        finally:

            conexion.close()

    return render_template("crear_usuario.html")


# ==========================================
# HISTORIAL DE ACCESOS
# ==========================================

@app.route("/accesos")
def accesos():

    if not usuario_requerido():
        return redirect(url_for("login"))

    if not administrador_requerido():
        flash("No tienes permiso para acceder")
        return redirect(url_for("dashboard"))

    conexion = conectar()

    try:

        registros = conexion.execute("""
            SELECT id, usuario, fecha
            FROM accesos
            ORDER BY id DESC
        """).fetchall()

    finally:

        conexion.close()

    return render_template(
        "accesos.html",
        registros=registros
    )

# ==========================================
# REPORTES MENSUALES DE ACCESOS
# ==========================================

MESES = [
    "Enero", "Febrero", "Marzo", "Abril",
    "Mayo", "Junio", "Julio", "Agosto",
    "Septiembre", "Octubre", "Noviembre", "Diciembre"
]


def obtener_accesos_mensuales(mes, anio):

    conexion = conectar()

    try:

        registros = conexion.execute("""
            SELECT
                a.id,
                a.usuario,
                COALESCE(u.nombre, a.usuario) AS nombre,
                COALESCE(u.rol, 'Usuario no disponible') AS rol,
                a.fecha
            FROM accesos a
            LEFT JOIN usuarios u
                ON a.usuario = u.usuario
            WHERE MONTH(a.fecha) = ?
              AND YEAR(a.fecha) = ?
            ORDER BY a.fecha DESC
        """, (mes, anio)).fetchall()

    finally:
        conexion.close()

    return registros


@app.route("/reporte_accesos_mensual")
def reporte_accesos_mensual():

    if not usuario_requerido():
        return redirect(url_for("login"))

    if not administrador_requerido():
        flash("No tienes permiso para acceder")
        return redirect(url_for("dashboard"))

    mes_actual = datetime.now().month
    anio_actual = datetime.now().year

    try:
        mes = int(request.args.get("mes", mes_actual))
        anio = int(request.args.get("anio", anio_actual))

        if mes < 1 or mes > 12 or anio < 2000 or anio > anio_actual + 1:
            raise ValueError

    except (ValueError, TypeError):
        flash("Selecciona un mes y año válidos")
        return redirect(url_for("reporte_accesos_mensual"))

    registros = obtener_accesos_mensuales(mes, anio)

    return render_template(
        "reporte_accesos_mensual.html",
        registros=registros,
        mes=mes,
        anio=anio,
        nombre_mes=MESES[mes - 1]
    )


@app.route("/reporte_accesos_mensual/pdf")
def descargar_reporte_accesos_mensual():

    if not usuario_requerido():
        return redirect(url_for("login"))

    if not administrador_requerido():
        flash("No tienes permiso para acceder")
        return redirect(url_for("dashboard"))

    try:
        mes = int(request.args.get("mes"))
        anio = int(request.args.get("anio"))

        if mes < 1 or mes > 12 or anio < 2000 or anio > datetime.now().year + 1:
            raise ValueError

    except (ValueError, TypeError):
        flash("Selecciona un mes y año válidos")
        return redirect(url_for("reporte_accesos_mensual"))

    registros = obtener_accesos_mensuales(mes, anio)

    memoria = BytesIO()

    documento = SimpleDocTemplate(
        memoria,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm
    )

    estilos = getSampleStyleSheet()
    elementos = []

    titulo = ParagraphStyle(
        "TituloAccesos",
        parent=estilos["Title"],
        fontSize=19,
        textColor=colors.HexColor("#173b62"),
        alignment=TA_CENTER,
        spaceAfter=10
    )

    subtitulo = ParagraphStyle(
        "SubtituloAccesos",
        parent=estilos["Normal"],
        fontSize=11,
        alignment=TA_CENTER,
        spaceAfter=20
    )

    elementos.append(Paragraph("EMPACAR S.A.", titulo))

    elementos.append(Paragraph(
        "REPORTE MENSUAL DE ACCESOS AL SISTEMA",
        subtitulo
    ))

    elementos.append(Paragraph(
        f"Periodo: {MESES[mes - 1]} de {anio}",
        estilos["Heading2"]
    ))

    elementos.append(Spacer(1, 10))

    elementos.append(Paragraph(
        f"Total de ingresos registrados: <b>{len(registros)}</b>",
        estilos["Normal"]
    ))

    elementos.append(Spacer(1, 18))

    datos_tabla = [[
        "ID", "Usuario", "Nombre completo", "Rol", "Fecha y hora"
    ]]

    for registro in registros:

        datos_tabla.append([
            str(registro["id"]),
            Paragraph(escape(str(registro["usuario"])), estilos["Normal"]),
            Paragraph(escape(str(registro["nombre"])), estilos["Normal"]),
            Paragraph(escape(str(registro["rol"])), estilos["Normal"]),
            Paragraph(escape(str(registro["fecha"])), estilos["Normal"])
        ])

    if not registros:
        datos_tabla.append([
            "-", "-", "No existen ingresos registrados", "-", "-"
        ])

    tabla = Table(
        datos_tabla,
        colWidths=[
            1.1 * cm,
            3 * cm,
            4.2 * cm,
            3 * cm,
            4.5 * cm
        ],
        repeatRows=1
    )

    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173b62")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dce4ec")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white,
            colors.HexColor("#f3f7fb")
        ]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 7)
    ]))

    elementos.append(tabla)

    elementos.append(Spacer(1, 25))

    elementos.append(Paragraph(
        "Documento generado por el Sistema Inteligente "
        "de Inspección PET - EMPACAR S.A.",
        estilos["Normal"]
    ))

    documento.build(elementos)

    memoria.seek(0)

    return send_file(
        memoria,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"Reporte_Accesos_{anio}_{mes:02d}.pdf"
    )


# ==========================================
# CAMBIAR CONTRASEÑA
# ==========================================

@app.route("/cambiar_password", methods=["GET", "POST"])
def cambiar_password():

    if not usuario_requerido():
        return redirect(url_for("login"))

    if request.method == "POST":

        actual = request.form["actual"]
        nueva = request.form["nueva"]
        confirmar = request.form["confirmar"]

        conexion = conectar()

        try:

            usuario = conexion.execute("""
                SELECT password
                FROM usuarios
                WHERE usuario = ?
            """, (session["usuario"],)).fetchone()

            if not usuario or not check_password_hash(
                usuario["password"], actual
            ):

                flash("La contraseña actual es incorrecta")
                return redirect(url_for("cambiar_password"))

            if len(nueva) < 8:

                flash("La nueva contraseña debe tener al menos 8 caracteres")
                return redirect(url_for("cambiar_password"))

            if nueva != confirmar:

                flash("Las contraseñas nuevas no coinciden")
                return redirect(url_for("cambiar_password"))

            conexion.execute("""
                UPDATE usuarios
                SET password = ?
                WHERE usuario = ?
            """, (
                generate_password_hash(nueva),
                session["usuario"]
            ))

            conexion.commit()

            flash("Contraseña actualizada correctamente")
            return redirect(url_for("dashboard"))

        except Exception as error:

            conexion.rollback()
            print("Error al cambiar contraseña:", error)
            flash("No se pudo actualizar la contraseña")

        finally:

            conexion.close()

    return render_template("cambiar_password.html")


# ==========================================
# CERRAR SESIÓN
# ==========================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


# ==========================================
# EJECUTAR APLICACIÓN
# ==========================================

if __name__ == "__main__":

    inicializar_bd()

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )
