from __future__ import annotations

import json

import pandas as pd

from database.connection import get_connection


def value_to_text(value) -> str:
    """
    Convierte un valor a texto seguro para almacenarlo.
    """

    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    return str(value).strip()


def row_to_dict(row: pd.Series) -> dict:
    """
    Convierte una fila de pandas en un diccionario
    serializable como JSON.
    """

    return {
        str(key): value_to_text(value)
        for key, value in row.items()
    }


def pending_row_exists(
    source_filename: str,
    source_sheet: str,
    source_row: int,
    organization_name: str,
    campus_name: str,
) -> bool:
    """
    Evita registrar dos veces el mismo pendiente
    durante una reimportación.
    """

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id
            FROM import_staging
            WHERE source_filename = ?
              AND source_sheet = ?
              AND source_row = ?
              AND organization_name = ?
              AND campus_name = ?
              AND status = 'PENDIENTE'
            LIMIT 1
            """,
            (
                source_filename,
                source_sheet,
                source_row,
                organization_name,
                campus_name,
            ),
        ).fetchone()

    return row is not None


def save_pending_import_row(
    row: pd.Series,
    source_filename: str,
    source_sheet: str,
    source_row: int,
    reason: str,
    review_type: str,
    user_id: int,
) -> int:
    """
    Guarda una fila que requiere revisión humana.

    Devuelve:
        id > 0  -> registro creado
        0       -> ya existía como pendiente
    """

    data = row_to_dict(row)

    organization_name = data.get(
        "organization_name",
        "",
    )

    campus_name = data.get(
        "campus_name",
        "",
    )

    contact_name = data.get(
        "contact_name",
        "",
    )

    if pending_row_exists(
        source_filename=source_filename,
        source_sheet=source_sheet,
        source_row=source_row,
        organization_name=organization_name,
        campus_name=campus_name,
    ):
        return 0

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO import_staging (
                source_filename,
                source_sheet,
                source_row,
                organization_name,
                campus_name,
                contact_name,
                row_data,
                reason,
                review_type,
                status,
                created_by
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?,
                'PENDIENTE', ?
            )
            """,
            (
                source_filename,
                source_sheet,
                source_row,
                organization_name,
                campus_name,
                contact_name,
                json.dumps(
                    data,
                    ensure_ascii=False,
                ),
                reason,
                review_type,
                user_id,
            ),
        )

        connection.commit()

        return int(cursor.lastrowid)


def get_pending_import_rows() -> list[dict]:
    """
    Devuelve todos los registros pendientes de revisión.
    """

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                s.id,
                s.source_filename,
                s.source_sheet,
                s.source_row,
                s.organization_name,
                s.campus_name,
                s.contact_name,
                s.reason,
                s.review_type,
                s.status,
                s.created_at,
                u.full_name AS created_by_name

            FROM import_staging s

            LEFT JOIN users u
                ON u.id = s.created_by

            WHERE s.status = 'PENDIENTE'

            ORDER BY
                s.created_at ASC,
                s.id ASC
            """
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


def get_staging_detail(
    staging_id: int,
) -> dict | None:
    """
    Obtiene un registro completo de staging.
    """

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                s.*,
                creator.full_name AS created_by_name,
                resolver.full_name AS resolved_by_name

            FROM import_staging s

            LEFT JOIN users creator
                ON creator.id = s.created_by

            LEFT JOIN users resolver
                ON resolver.id = s.resolved_by

            WHERE s.id = ?

            LIMIT 1
            """,
            (staging_id,),
        ).fetchone()

    if row is None:
        return None

    result = dict(row)

    try:
        result["data"] = json.loads(
            result.get(
                "row_data",
                "{}",
            )
        )

    except (
        json.JSONDecodeError,
        TypeError,
    ):
        result["data"] = {}

    return result


def resolve_staging_row(
    staging_id: int,
    user_id: int,
) -> None:
    """
    Marca el registro como resuelto.
    """

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE import_staging

            SET
                status = 'RESUELTO',
                resolved_by = ?,
                resolved_at = CURRENT_TIMESTAMP

            WHERE id = ?
            """,
            (
                user_id,
                staging_id,
            ),
        )

        connection.commit()


def discard_staging_row(
    staging_id: int,
    user_id: int,
) -> None:
    """
    Marca un registro como descartado.

    No existe eliminación física.
    """

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE import_staging

            SET
                status = 'DESCARTADO',
                resolved_by = ?,
                resolved_at = CURRENT_TIMESTAMP

            WHERE id = ?
            """,
            (
                user_id,
                staging_id,
            ),
        )

        connection.commit()