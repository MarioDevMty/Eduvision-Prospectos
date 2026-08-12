from __future__ import annotations

from io import BytesIO

import pandas as pd


SUPPORTED_EXCEL_EXTENSIONS = {
    ".xlsx",
    ".xls",
}


def get_file_extension(
    filename: str,
) -> str:
    """
    Obtiene la extensión del archivo.
    """

    if "." not in filename:
        return ""

    return "." + filename.rsplit(".", 1)[-1].lower()


def validate_excel_file(
    filename: str,
) -> tuple[bool, str]:

    extension = get_file_extension(
        filename
    )

    if extension not in SUPPORTED_EXCEL_EXTENSIONS:

        return (
            False,
            "El archivo no corresponde a un formato Excel soportado.",
        )

    return True, ""


def get_excel_engine(
    filename: str,
) -> str:

    extension = get_file_extension(
        filename
    )

    if extension == ".xlsx":
        return "openpyxl"

    if extension == ".xls":
        return "xlrd"

    raise ValueError(
        "Formato Excel no soportado."
    )


def get_sheet_names(
    file_bytes: bytes,
    filename: str,
) -> list[str]:

    engine = get_excel_engine(
        filename
    )

    buffer = BytesIO(
        file_bytes
    )

    excel_file = pd.ExcelFile(
        buffer,
        engine=engine,
    )

    return excel_file.sheet_names


def read_excel_sheet(
    file_bytes: bytes,
    filename: str,
    sheet_name: str,
    header_row: int = 0,
) -> pd.DataFrame:
    """
    Lee una hoja específica del archivo.

    Importante:
    - conserva todas las columnas físicas;
    - conserva columnas aunque estén totalmente vacías;
    - no interpreta todavía el significado de los datos.
    """

    engine = get_excel_engine(
        filename
    )

    buffer = BytesIO(
        file_bytes
    )

    dataframe = pd.read_excel(
        buffer,
        sheet_name=sheet_name,
        header=header_row,
        engine=engine,
        dtype=object,
    )

    return clean_dataframe(
        dataframe
    )


def make_unique_columns(
    columns: list[str],
) -> list[str]:

    counts: dict[str, int] = {}

    result = []

    for column in columns:

        if column not in counts:

            counts[column] = 1
            result.append(column)

        else:

            counts[column] += 1

            result.append(
                f"{column}_{counts[column]}"
            )

    return result


def excel_value_to_text(
    value,
):
    """
    Convierte valores a texto seguro.

    Los vacíos permanecen como pd.NA.
    """

    if pd.isna(value):
        return pd.NA

    if isinstance(value, float):

        if value.is_integer():

            return str(
                int(value)
            )

    return str(
        value
    ).strip()


def clean_dataframe(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    Limpieza estructural segura.

    Reglas:
    - elimina filas completamente vacías;
    - NO elimina columnas completamente vacías;
    - conserva todos los encabezados físicos;
    - convierte los valores a texto seguro.
    """

    df = dataframe.copy()

    # -----------------------------------------------------
    # ELIMINAR SOLO FILAS TOTALMENTE VACÍAS
    # -----------------------------------------------------

    df = df.dropna(
        axis=0,
        how="all",
    )

    # IMPORTANTE:
    # NO eliminamos columnas totalmente vacías.
    #
    # Antes existía algo como:
    #
    # df = df.dropna(
    #     axis=1,
    #     how="all",
    # )
    #
    # Ese comportamiento se elimina porque una columna
    # vacía sigue representando un campo físico válido.

    # -----------------------------------------------------
    # LIMPIAR ENCABEZADOS
    # -----------------------------------------------------

    cleaned_columns = []

    for index, column in enumerate(
        df.columns
    ):

        column_name = str(
            column
        ).strip()

        if (
            not column_name
            or column_name.lower().startswith(
                "unnamed:"
            )
        ):

            column_name = (
                f"Columna_{index + 1}"
            )

        cleaned_columns.append(
            column_name
        )

    df.columns = make_unique_columns(
        cleaned_columns
    )

    # -----------------------------------------------------
    # CONVERTIR VALORES A TEXTO SEGURO
    # -----------------------------------------------------

    for column in df.columns:

        df[column] = (
            df[column]
            .map(
                excel_value_to_text
            )
            .astype("string")
        )

    df = df.reset_index(
        drop=True
    )

    return df


def dataframe_summary(
    dataframe: pd.DataFrame,
) -> dict:

    return {
        "rows": len(
            dataframe
        ),
        "columns": len(
            dataframe.columns
        ),
        "column_names": list(
            dataframe.columns
        ),
    }


def get_preview(
    dataframe: pd.DataFrame,
    rows: int = 20,
) -> pd.DataFrame:

    return dataframe.head(
        rows
    ).copy()


def dataframe_for_display(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    Devuelve una copia segura para st.dataframe.
    """

    display_df = (
        dataframe.copy()
    )

    for column in display_df.columns:

        display_df[column] = (
            display_df[column]
            .astype("string")
        )

    return display_df


# =========================================================
# PERFIL DE CAMPOS
# =========================================================

def is_meaningful_value(
    value,
) -> bool:
    """
    Determina si una celda contiene información real.

    Un campo puede existir físicamente aunque todas
    sus celdas resulten False aquí.
    """

    if value is None:
        return False

    try:

        if pd.isna(value):
            return False

    except (TypeError, ValueError):
        pass

    text = str(
        value
    ).strip()

    if not text:
        return False

    return True


def get_column_profile(
    dataframe: pd.DataFrame,
    column: str,
    sample_size: int = 3,
) -> dict:
    """
    Obtiene estadísticas de llenado para una columna.

    No interpreta qué significa el campo.
    """

    if column not in dataframe.columns:

        return {
            "column": column,
            "total_rows": 0,
            "filled_rows": 0,
            "empty_rows": 0,
            "fill_percentage": 0.0,
            "samples": [],
        }

    series = dataframe[
        column
    ]

    total_rows = len(
        series
    )

    meaningful_mask = (
        series.map(
            is_meaningful_value
        )
    )

    filled_rows = int(
        meaningful_mask.sum()
    )

    empty_rows = (
        total_rows
        -
        filled_rows
    )

    if total_rows > 0:

        fill_percentage = (
            filled_rows
            /
            total_rows
        ) * 100

    else:

        fill_percentage = 0.0

    samples = (
        series[
            meaningful_mask
        ]
        .astype("string")
        .head(
            sample_size
        )
        .tolist()
    )

    return {
        "column":
            column,

        "total_rows":
            total_rows,

        "filled_rows":
            filled_rows,

        "empty_rows":
            empty_rows,

        "fill_percentage":
            round(
                fill_percentage,
                1,
            ),

        "samples":
            samples,
    }


def get_dataframe_profile(
    dataframe: pd.DataFrame,
    sample_size: int = 3,
) -> list[dict]:
    """
    Obtiene el perfil de todas las columnas físicas
    del archivo, tengan o no contenido.
    """

    profiles = []

    for column in dataframe.columns:

        profiles.append(
            get_column_profile(
                dataframe=dataframe,
                column=column,
                sample_size=sample_size,
            )
        )

    return profiles