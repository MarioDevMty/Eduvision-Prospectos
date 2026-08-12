from enum import Enum


class UserRole(str, Enum):
    CURATOR = "CURADOR"
    ADMIN = "ADMIN"
    SUPERADMIN = "SUPERADMIN"


class RecordStatus(str, Enum):
    REVIEW_REQUIRED = "REQUIERE_REVISION"
    PENDING = "PENDIENTE"
    INCOMPLETE = "INCOMPLETO"
    VALIDATED = "VALIDADO"
    DISCARDED = "DESCARTADO"