"""El esquema del formato lo publica Ditto, y lo publicado no se queda viejo.

`data/` omite todo campo que valga su default y guarda los enums por nombre, así
que leerlo pide saber los defaults y las tablas. Eso lo tiene Ditto, que lo
escribe con `ditto schema` —es `just esquema`—, y `tools/rpgmaker/ditto_schema.py`
lo lee. Hasta el 2026-09-20 el camino era el contrario: un generador le sacaba
esos datos al código de Rust de Ditto **con expresiones regulares**, y de paso
leía `9 * 256` como 9.

Eso mueve el problema en vez de resolverlo si el JSON commiteado se puede
quedar viejo, que es lo que cuida el primer caso —el mismo trato que
`test_protocolo.py` le da a los dos bytecodes—. El generador es un binario que
se instala con `just herramientas` y se usa desde el PATH; lo generado está
commiteado, así que **compilar la ROM no necesita ni eso**, y por eso el resto
de los casos leen el archivo y no la herramienta.
"""

import json
import os
import subprocess
import sys

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(REPO, "tools"))

import pytest  # noqa: E402

from rpgmaker.ditto_schema import CAMPOS, ENUMS, ESQUEMA  # noqa: E402


def test_el_esquema_publicado_esta_al_dia():
    """Regenerarlo no cambia nada: si no, el árbol tiene dos verdades."""
    hecho = subprocess.run(["ditto", "schema"], capture_output=True, text=True)
    if hecho.returncode != 0:
        pytest.fail("`ditto schema` no pudo correr —¿falta `just herramientas`?"
                    "—:\n%s" % hecho.stderr)
    with open(ESQUEMA, encoding="utf-8") as handle:
        assert hecho.stdout == handle.read(), (
            "tools/rpgmaker/ditto_schema.json quedó viejo: `just esquema`")


def test_el_esquema_trae_lo_que_el_lector_le_pide():
    """Las cinco cosas de cada campo, que son las que `lcf.py` desempaca."""
    assert CAMPOS and ENUMS
    for struct, campos in CAMPOS.items():
        assert campos, struct
        for campo, valor in campos.items():
            assert len(valor) == 5, (struct, campo)
            chunk, _default, enum, siempre, anidado = valor
            assert chunk is None or isinstance(chunk, int)
            assert enum is None or enum in ENUMS
            assert isinstance(siempre, bool)
            assert anidado is None or anidado in CAMPOS


def test_los_defaults_que_ya_costaron_un_bug():
    """Los tres que este repo pagó, fijados por número.

    `max_hp` es el que originó a Ditto —un enemigo moría de un golpe porque el
    default escrito a mano decía 1—; `skill_id` es el que la migración arregló;
    y `pan_speed` es el que el generador viejo leía mal, porque en la CSV está
    escrito `2 << 3` y la expresión regular paraba en el primer número.
    """
    assert CAMPOS["Enemy"]["max_hp"][1] == 10
    assert CAMPOS["Learning"]["skill_id"][1] == 1
    assert CAMPOS["SavePartyLocation"]["pan_speed"][1] == 16


def test_los_enums_vuelven_del_nombre_al_numero():
    """Los tres que el conversor lee en cada mapa."""
    assert ENUMS["EventPageTrigger"]["auto_start"] == 3
    assert ENUMS["EventPageLayers"]["same"] == 1
    assert ENUMS["EventCommandCode"]["ShowMessage"] == 10110


def test_el_json_es_el_que_el_modulo_lee():
    """Que nadie haya escrito el esquema a mano adentro del `.py`."""
    with open(ESQUEMA, encoding="utf-8") as handle:
        crudo = json.load(handle)
    assert set(crudo["fields"]) == set(CAMPOS)
    assert crudo["enums"] == ENUMS
