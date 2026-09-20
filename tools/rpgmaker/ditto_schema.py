"""Los nombres, los defaults y los enums del volcado a JSON, leídos de Ditto.

El dato está en `ditto_schema.json`, que lo escribe **Ditto**: `ditto schema`.
Acá no hay esquema, hay un lector. El porqué, y con qué se regenera, están en
`tools/rpgmaker/README.md`.

    CAMPOS[struct][campo] = (chunk, default, enum, siempre, anidado)
    ENUMS[enum][nombre] = número

`chunk` es el del binario, que ya no se lee pero sigue siendo cómo se nombran
algunas cosas desde afuera —los términos de la tienda—. `default` es lo que
vale un campo que el JSON no trae, y `None` es el default del tipo: una lista
vacía o un struct todo en default. `siempre` es el `PersistIfDefault` del
formato: el campo que el binario escribe aunque valga el default, y que por eso
un lector del binario siempre veía. `anidado` es el struct que el campo lleva
adentro, uno solo o una lista de ellos.
"""

import json
import os

ESQUEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "ditto_schema.json")

with open(ESQUEMA, encoding="utf-8") as _handle:
    _crudo = json.load(_handle)

CAMPOS = {
    struct: {campo: (d["chunk"], d["default"], d["enum"], d["persist"],
                     d["nested"])
             for campo, d in campos.items()}
    for struct, campos in _crudo["fields"].items()
}

ENUMS = _crudo["enums"]

del _crudo, _handle
