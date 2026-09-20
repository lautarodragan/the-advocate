"""Nombres de los códigos de comando de evento de RPG Maker 2000.

La tabla es `event_codes.json`, que sale de liblcf y no se edita a mano; de
dónde y con qué comando está en `tools/rpgmaker/README.md`. Acá sólo se la
carga, con las claves de vuelta a número —JSON sólo tiene claves de texto—.

Los códigos que no estén en la tabla se exportan como número pelado.
"""

import json
import os

TABLA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "event_codes.json")

with open(TABLA, encoding="utf-8") as _handle:
    EVENT_CODES = {int(codigo): nombre
                   for codigo, nombre in json.load(_handle).items()}

del _handle
