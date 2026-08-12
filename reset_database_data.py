from database.connection import get_connection


CONFIRMATION_TEXT = "BORRAR DATOS"


def table_exists(
    connection,
    table_name: str,
) -> bool:

    row = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        LIMIT 1
        """,
        (
            table_name,
        ),
    ).fetchone()

    return row is not None


def reset_database_data() -> None:

    print()
    print("=" * 60)
    print("REINICIO DE DATOS - EDUVISION")
    print("=" * 60)
    print()

    print(
        "Se eliminarán los datos operativos, "
        "pero se conservarán usuarios y estructura."
    )

    print()

    confirmation = input(
        f'Escribe exactamente "{CONFIRMATION_TEXT}" para continuar: '
    )

    if confirmation != CONFIRMATION_TEXT:

        print()
        print("Operación cancelada.")
        return


    tables_to_clear = [
        "import_staging",
        "audit_log",
        "dynamic_values",
        "organization_aliases",
        "phones",
        "emails",
        "contacts",
        "campuses",
        "organizations",
    ]


    tables_to_reset_sequence = [
        "import_staging",
        "audit_log",
        "dynamic_values",
        "organization_aliases",
        "phones",
        "emails",
        "contacts",
        "campuses",
        "organizations",
    ]


    with get_connection() as connection:

        try:

            connection.execute(
                "BEGIN"
            )

            print()
            print("Tablas encontradas:")

            existing_tables = []

            for table_name in tables_to_clear:

                if table_exists(
                    connection,
                    table_name,
                ):

                    existing_tables.append(
                        table_name
                    )

                    print(
                        f"  OK  {table_name}"
                    )

                else:

                    print(
                        f"  NO EXISTE  {table_name}"
                    )


            print()
            print("Eliminando datos...")


            for table_name in existing_tables:

                connection.execute(
                    f"DELETE FROM {table_name}"
                )

                print(
                    f"  LIMPIA  {table_name}"
                )


            # -------------------------------------------------
            # REINICIAR AUTOINCREMENT
            # -------------------------------------------------

            if table_exists(
                connection,
                "sqlite_sequence",
            ):

                for table_name in (
                    tables_to_reset_sequence
                ):

                    connection.execute(
                        """
                        DELETE FROM sqlite_sequence
                        WHERE name = ?
                        """,
                        (
                            table_name,
                        ),
                    )


            connection.commit()

        except Exception:

            connection.rollback()
            raise


    print()
    print("=" * 60)
    print("RESET COMPLETADO")
    print("=" * 60)
    print()
    print(
        "Usuarios y estructura conservados."
    )
    print(
        "La base está lista para la carga definitiva."
    )


if __name__ == "__main__":

    reset_database_data()