from getpass import getpass

from services.smtp_service import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    test_smtp_connection,
)


def main():

    print()
    print("=" * 60)
    print("PRUEBA SMTP - EDUVISION")
    print("=" * 60)

    print()
    print(f"Servidor : {SMTP_HOST}")
    print(f"Puerto   : {SMTP_PORT}")
    print(f"Usuario  : {SMTP_USER}")
    print("Seguridad: STARTTLS")
    print()

    print(
        "Esta prueba NO enviará ningún correo."
    )

    print(
        "La contraseña no se guardará."
    )

    print()

    password = getpass(
        "Contraseña del correo: "
    )

    print()
    print("Probando conexión...")

    result = test_smtp_connection(
        password=password
    )

    print()

    if result["success"]:
        print("OK")
        print(result["message"])
    else:
        print("ERROR")
        print(result["message"])

    print()


if __name__ == "__main__":
    main()
    
    
    
