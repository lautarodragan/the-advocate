"""Lo que las pruebas le preguntan al conversor, `rm2k-snes-convert`, sin
convertir nada: cómo le pregunta él al compilador de eventos, quién puede
liderar el grupo, qué le da a `wally` de un mapa.

Hasta el 2026-10-02 eran los módulos del conversor de Python
—`port/compiler.py`, `port/game_scan.py`— y las pruebas los llamaban de
adentro; con el conversor en Rust se le pregunta al binario, que es el que
decide cómo pregunta: si no, las pruebas sostendrían una copia de los
pedidos que el conversor ya no arma. Ver `src/queries.rs` en
`rm2k-snes-convert`.

El juego y el proyecto salen de `lugares`, igual que para los cartuchos.
"""

import functools
import json
import os
import subprocess
import tempfile

from common import environment

import events
import lugares

BINARIO = "rm2k-snes-convert"


def preguntar(pregunta, *args):
    """La respuesta de `rm2k-snes-convert <pregunta>`, ya leída."""
    hecho = subprocess.run(
        [BINARIO, pregunta, "--project", lugares.ABL]
        + environment.as_flags("game_dir", "rtp_dir", "soundfont", "cache")
        + [str(a) for a in args],
        capture_output=True, text=True)
    if hecho.returncode:
        raise SystemExit(hecho.stderr.strip()
                         or "%s %s salió con %d"
                         % (BINARIO, pregunta, hecho.returncode))
    return json.loads(hecho.stdout)


@functools.lru_cache(maxsize=None)
def _escaneo(mapas, archivos, extra):
    args = []
    if mapas is not None:
        args += ["--maps"] + list(mapas)
    for archivo in archivos:
        args += ["--test-commands", archivo]
    for variable in extra:
        args += ["--extra-variable", variable]
    return preguntar("scan", *args)


def escaneo(mapas=None, archivos=(), extra=()):
    """La primera llamada del compilador como la hace el conversor: los
    índices del juego entero y qué páginas de cada mapa compilan. Sin
    `mapas`, todos los del volcado; `archivos` son casos de
    `pruebas/casos/` cuyos comandos se suman como páginas de prueba, y
    `extra` variables de más."""
    return _escaneo(None if mapas is None else tuple(mapas), tuple(archivos),
                    tuple(sorted(extra)))


def ranuras(respuesta):
    """`({variable: ranura}, {(actor, habilidad): bit})` de un escaneo."""
    return ({v: s for v, s in respuesta["variables"]},
            {(a, h): s for a, h, s in respuesta["skills"]})


def entrada(respuesta, map_id):
    """Lo que el compilador contestó de un mapa."""
    for una in respuesta["maps"]:
        if una["id"] == map_id:
            return una
    raise KeyError("el mapa %d no está en la respuesta" % map_id)


def paginas_compiladas(respuesta, map_id):
    """{(evento, página): código} de las páginas de ese mapa que compilan,
    por índice, cada una compilada sola."""
    return {(e, p): bytes.fromhex(codigo)
            for e, p, codigo in entrada(respuesta, map_id)["compiled"]}


def _archivo_de(comandos):
    """Los comandos —`lcf.EventCommand`— en un archivo como los de
    `pruebas/casos/`, para pasárselos al conversor."""
    archivo = tempfile.NamedTemporaryFile(
        "w", suffix=".json", prefix="conversor-", delete=False,
        encoding="utf-8")
    with archivo:
        json.dump({"event_commands": [
            {"code": c.code, "indent": c.indent, "string": c.string,
             "parameters": list(c.parameters)} for c in comandos]}, archivo)
    return archivo.name


def compilar(mapas=(), casos=(), tropas=()):
    """La segunda llamada del compilador para un cartucho de `mapas` armado
    sin convertirlos: `casos` son `(mapa, comandos)`, cada uno una página
    compilada en ese mapa, y `tropas` las que el cartucho lleva."""
    archivos = []
    try:
        args = []
        if mapas:
            args += ["--maps"] + list(mapas)
        for mapa, comandos in casos:
            archivos.append(_archivo_de(comandos))
            args += ["--case", mapa, archivos[-1]]
        for tropa in tropas:
            args += ["--encounter-troop", tropa]
        return preguntar("compile", *args)
    finally:
        for archivo in archivos:
            os.remove(archivo)


def pagina_suelta(map_id, comandos, mapas=None):
    """`comandos` compilados como una página del evento 0 de `map_id`, en un
    cartucho de `mapas` —ese mapa solo, si no—: su código, o None."""
    codigo = compilar(mapas or [map_id], [(map_id, comandos)])["cases"][0]
    return None if codigo is None else bytes.fromhex(codigo)


def disparadores(tropa):
    """{página: disparador} de las páginas de esa tropa que entran en un
    cartucho, como `events.Trigger`: lo que la pelea lee para saber cuándo
    corre cada una."""
    respuesta = compilar(tropas=[tropa])
    for numero, suyas in respuesta["troop_pages"]["per_troop"]:
        if numero == tropa:
            return {pagina: events.Trigger(*t) for t, _en, pagina in suyas}
    return {}


def lideres(mapas, grupo):
    """Los actores que pueden quedar primeros del grupo en un cartucho de
    esos mapas, empezando con `grupo`."""
    return preguntar("leaders", "--maps", *mapas, "--party", *grupo)


def contexto_de_mapa(map_id):
    """Lo que el conversor le da a `wally` de un mapa además de sus
    decisiones: el volcado, dónde se buscan las imágenes, los archivos del
    proyecto y los nombres que les da a sus gráficos."""
    return preguntar("map-context", "--map", map_id)


def cajas():
    """Las cajas de texto que el conversor le da al compilador, rearmadas
    para la ventana, y la ventana: `{"window", "boxes"}`."""
    return preguntar("boxes")
