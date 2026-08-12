from __future__ import annotations

from database.connection import get_connection
from services.normalization import normalize_text


def get_import_batch_snapshot(
    campus_references: list[dict],
) -> list[dict]:
    """
    Verifica directamente contra SQLite el estado actual
    de los planteles involucrados en una importación.

    campus_references espera:
    [
        {
            "organization_name": "...",
            "campus_name": "..."
        }
    ]

    No modifica ningún dato.
    """

    results = []

    seen = set()

    with get_connection() as connection:

        for reference in campus_references:

            organization_name = str(
                reference.get(
                    "organization_name",
                    ""
                )
                or ""
            ).strip()

            campus_name = str(
                reference.get(
                    "campus_name",
                    ""
                )
                or ""
            ).strip()

            if (
                not organization_name
                or not campus_name
            ):
                continue

            normalized_organization = normalize_text(
                organization_name
            )

            normalized_campus = normalize_text(
                campus_name
            )

            unique_key = (
                normalized_organization,
                normalized_campus,
            )

            if unique_key in seen:
                continue

            seen.add(
                unique_key
            )

            # ---------------------------------------------
            # ORGANIZACIÓN
            # ---------------------------------------------

            organization = connection.execute(
                """
                SELECT
                    id,
                    official_name
                FROM organizations
                WHERE normalized_name = ?
                LIMIT 1
                """,
                (
                    normalized_organization,
                ),
            ).fetchone()

            if organization is None:

                results.append(
                    {
                        "organization":
                            organization_name,

                        "campus":
                            campus_name,

                        "exists":
                            False,

                        "campus_id":
                            None,

                        "contacts":
                            0,

                        "phones":
                            0,

                        "emails":
                            0,

                        "status":
                            "ORGANIZACION_NO_ENCONTRADA",
                    }
                )

                continue

            # ---------------------------------------------
            # PLANTEL
            # ---------------------------------------------

            campus = connection.execute(
                """
                SELECT
                    id,
                    campus_name,
                    status
                FROM campuses
                WHERE organization_id = ?
                  AND normalized_name = ?
                ORDER BY
                    CASE
                        WHEN status = 'BAJA'
                        THEN 1 ELSE 0
                    END,
                    id DESC
                LIMIT 1
                """,
                (
                    organization["id"],
                    normalized_campus,
                ),
            ).fetchone()

            if campus is None:

                results.append(
                    {
                        "organization":
                            organization[
                                "official_name"
                            ],

                        "campus":
                            campus_name,

                        "exists":
                            False,

                        "campus_id":
                            None,

                        "contacts":
                            0,

                        "phones":
                            0,

                        "emails":
                            0,

                        "status":
                            "PLANTEL_NO_ENCONTRADO",
                    }
                )

                continue

            campus_id = campus[
                "id"
            ]

            # ---------------------------------------------
            # CONTACTOS
            # ---------------------------------------------

            contact_count = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM contacts
                WHERE campus_id = ?
                  AND status <> 'BAJA'
                """,
                (
                    campus_id,
                ),
            ).fetchone()["total"]

            # ---------------------------------------------
            # TELÉFONOS INSTITUCIONALES
            # ---------------------------------------------

            phone_count = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM phones
                WHERE entity_type = 'CAMPUS'
                  AND entity_id = ?
                  AND status = 'ACTIVO'
                """,
                (
                    campus_id,
                ),
            ).fetchone()["total"]

            # ---------------------------------------------
            # CORREOS INSTITUCIONALES
            # ---------------------------------------------

            email_count = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM emails
                WHERE entity_type = 'CAMPUS'
                  AND entity_id = ?
                  AND status = 'ACTIVO'
                """,
                (
                    campus_id,
                ),
            ).fetchone()["total"]

            results.append(
                {
                    "organization":
                        organization[
                            "official_name"
                        ],

                    "campus":
                        campus[
                            "campus_name"
                        ],

                    "exists":
                        True,

                    "campus_id":
                        campus_id,

                    "contacts":
                        contact_count,

                    "phones":
                        phone_count,

                    "emails":
                        email_count,

                    "status":
                        campus[
                            "status"
                        ],
                }
            )

    return results


def summarize_import_actions(
    import_results: list[dict],
) -> dict:
    """
    Resume las acciones informadas por el motor
    de importación.

    Estos números describen lo ocurrido durante
    el lote.
    """

    summary = {
        "rows": len(
            import_results
        ),

        "processed": 0,
        "not_imported": 0,

        "campuses_created": 0,
        "contacts_created": 0,
        "contacts_existing": 0,
        "contacts_pending": 0,
        "errors": 0,
    }

    for item in import_results:

        imported = item.get(
            "imported",
            False,
        )

        action = item.get(
            "action",
            "",
        )

        if imported:
            summary[
                "processed"
            ] += 1
        else:
            summary[
                "not_imported"
            ] += 1

        if action == (
            "PLANTEL_Y_CONTACTO_CREADOS"
        ):

            summary[
                "campuses_created"
            ] += 1

            summary[
                "contacts_created"
            ] += 1

        elif action in {
            "PLANTEL_CREADO",
            "PLANTEL_CREADO_SIN_CONTACTO",
        }:

            summary[
                "campuses_created"
            ] += 1

        elif action == "CONTACTO_CREADO":

            summary[
                "contacts_created"
            ] += 1

        elif action == "CONTACTO_EXISTENTE":

            summary[
                "contacts_existing"
            ] += 1

        elif action == (
            "PLANTEL_PROCESADO_CONTACTO_PENDIENTE"
        ):

            summary[
                "contacts_pending"
            ] += 1

        elif action == "ERROR":

            summary[
                "errors"
            ] += 1

    return summary