from zoneinfo import ZoneInfo
from datetime import time

FUSO_HORARIO = ZoneInfo("America/Fortaleza")

TOLERANCIA_MINUTOS = 5

HORARIOS_PADRAO = {
    "Entrada": time(8, 0, 0),
    "Saída": time(18, 0, 0)
}