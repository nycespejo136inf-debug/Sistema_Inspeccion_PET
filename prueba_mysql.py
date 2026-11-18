
import mysql.connector

try:
    conexion = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root",
        password="",
        database="sistemapet1"
    )

    if conexion.is_connected():
        print("CONEXIÓN EXITOSA CON MYSQL")
        print("Base de datos: SistemaPET")

    conexion.close()

except mysql.connector.Error as error:
    print("ERROR DE CONEXIÓN:")
    print(error)
