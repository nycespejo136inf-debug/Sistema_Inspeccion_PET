
import mysql.connector
from werkzeug.security import generate_password_hash


# ==========================================
# CONEXIÓN CON MYSQL
# ==========================================

def conectar():

    conexion = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root",
        password="",
        database="SistemaPET1"
    )

    return ConexionMySQL(conexion)


class ConexionMySQL:

    def __init__(self, conexion):
        self.conexion = conexion

    def execute(self, consulta, parametros=()):
        consulta = consulta.replace("?", "%s")
        cursor = self.conexion.cursor(dictionary=True)
        cursor.execute(consulta, parametros)
        return cursor

    def commit(self):
        self.conexion.commit()

    def rollback(self):
        self.conexion.rollback()

    def close(self):
        self.conexion.close()


# ==========================================
# INICIALIZAR BASE DE DATOS
# ==========================================

def inicializar_bd():

    conexion = conectar()

    try:

        # Tabla de usuarios
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INT AUTO_INCREMENT PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL,
                usuario VARCHAR(50) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                rol VARCHAR(50) NOT NULL
            )
        """)

        # Tabla de inspecciones
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS inspecciones (
                id INT AUTO_INCREMENT PRIMARY KEY,
                usuario VARCHAR(50) NOT NULL,
                imagen VARCHAR(255) NOT NULL,
                resultado VARCHAR(100) NOT NULL,
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Tabla de historial de accesos
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS accesos (
                id INT AUTO_INCREMENT PRIMARY KEY,
                usuario VARCHAR(50) NOT NULL,
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Usuarios iniciales
        usuarios = [
            (
                "Administrador",
                "admin",
                generate_password_hash("Admin123"),
                "Administrador"
            ),
            (
                "Operador",
                "operador",
                generate_password_hash("Operador123"),
                "Operador"
            )
        ]

        for usuario in usuarios:

            conexion.execute("""
                INSERT IGNORE INTO usuarios
                (nombre, usuario, password, rol)
                VALUES (?, ?, ?, ?)
            """, usuario)

        conexion.commit()

        print("Base de datos MySQL inicializada correctamente")

    except Exception as error:

        conexion.rollback()
        print("Error al inicializar la base de datos:", error)
        raise

    finally:

        conexion.close()


# ==========================================
# REGISTRAR INICIO DE SESIÓN
# ==========================================

def registrar_acceso(usuario):

    conexion = conectar()

    try:

        conexion.execute("""
            INSERT INTO accesos (usuario)
            VALUES (?)
        """, (usuario,))

        conexion.commit()

    except Exception as error:

        conexion.rollback()
        print("Error al registrar acceso:", error)
        raise

    finally:

        conexion.close()
