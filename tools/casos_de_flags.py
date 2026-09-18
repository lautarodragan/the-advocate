#!/usr/bin/env python3
"""De los flags de caso a `--comandos-de-prueba`, y la prueba de que es lo mismo.

Es la herramienta de la mudanza del paso 9d, corte 3, y se va con los flags:
recibe líneas de comandos del conversor —una por renglón, como lista JSON—,
escribe cada caso como la página de RM2k que es, y arma el cartucho de las
dos maneras. El criterio es que los dos `mapdata.inc` salgan **idénticos**.

    python3 tools/casos_de_flags.py REGISTRO.jsonl --casos DIR --trabajo DIR

Las líneas de comandos se juntan corriendo la tanda con un `sitecustomize`
que anota el `sys.argv` de cada `snes_convert.py`.
"""

import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys

import eventos
import lcf
import snes_convert
from ditto_schema import CAMPOS, ENUMS
from render_map import REPO

NOMBRE_DE_CODIGO = {v: k for k, v in
                    ENUMS[CAMPOS["EventCommand"]["code"][2]].items()}


def comando_json(cmd):
    """Un comando como lo escribe Ditto en `data/`: el código por nombre y los
    campos que valen su default, afuera."""
    salida = {"code": NOMBRE_DE_CODIGO[cmd.code]}
    if cmd.indent:
        salida["indent"] = cmd.indent
    if cmd.parameters:
        salida["parameters"] = list(cmd.parameters)
    if cmd.string:
        salida["string"] = cmd.string
    return salida


def pagina_json(comandos):
    """La página entera como texto, un comando por renglón como en `data/`."""
    renglones = [json.dumps(comando_json(c), ensure_ascii=False)
                 for c in comandos]
    return ('{\n  "event_commands": [\n    '
            + ",\n    ".join(renglones) + "\n  ]\n}\n")


def sin_flags_de_caso(tokens, parser):
    """Los tokens del cartucho: sin los flags de caso ni sus valores, y sin
    `-o`, que pone quien arma."""
    salida = []
    saltando = False
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.startswith("-") and t in parser._option_string_actions:
            dest = parser._option_string_actions[t].dest
            saltando = dest in snes_convert.FLAGS_DE_CASO or dest == "output"
        if not saltando:
            salida.append(t)
        i += 1
    return salida


def comandos_de(caso, grupo, id_de, grafico_de):
    kw = snes_convert.argumentos_de_caso(caso, grupo)
    kw["mensaje"] = caso.mensaje_de_prueba
    caso_d = eventos._sin_omisiones(kw)
    if caso.fondo_de_prueba:
        caso_d["fondo"] = caso.fondo_de_prueba
    comandos = eventos._comandos_de_prueba(caso_d, id_de, grafico_de)
    apagar = comandos.pop(0)
    assert (apagar.code, apagar.parameters) == (
        eventos.CONTROL_SWITCHES,
        [eventos.SWITCH_UNICO, eventos.SWITCH_DE_PRUEBA,
         eventos.SWITCH_DE_PRUEBA, eventos.SWITCH_ON])
    return comandos


def traducir(argv, parser, casos_dir):
    """(argv con archivos, [rutas de los casos]) para una línea con flags."""
    cartucho, tramos = snes_convert.partir_en_casos(argv)
    args = parser.parse_args(cartucho)
    casos = snes_convert.casos_de_prueba(parser, args, tramos)
    grupo = args.grupo or lcf.Database(
        os.path.join(args.game_dir, "RPG_RT.ldb")).party
    inicial = snes_convert.orden_de_mapas(args)[args.inicial]
    del_mapa = lcf.Map(os.path.join(args.game_dir,
                                    "Map%04d.lmu" % inicial)).events

    def id_de(blanco):
        return del_mapa[blanco - 1].id if 0 < blanco <= len(del_mapa) \
            else None

    pares = []

    def grafico_de(indice):
        # La tabla de gráficos del mapa como la numera el conversor: las
        # asociaciones de todos los mapas, las órdenes 34 de las páginas del
        # inicial y los de `--grafico-de-prueba`. Sólo se arma si hace falta,
        # porque pide compilar las páginas del mapa.
        if not pares:
            todos = snes_convert.orden_de_mapas(args)
            snes_convert.args_game_dir[0] = args.game_dir
            eventos.indexar_variables(args.game_dir)
            eventos.indexar_animaciones(args.game_dir)
            eventos.indexar_comunes(args.game_dir)
            eventos.indexar_audio_de_batalla(args.game_dir)
            eventos.indexar_actores(args.game_dir)
            asociaciones = eventos.asociaciones_de(
                [lcf.Map(os.path.join(args.game_dir, "Map%04d.lmu" % m))
                 for m in todos])
            _m, del_juego, _a, _g = snes_convert.eventos_movibles(
                lcf.Map(os.path.join(args.game_dir, "Map%04d.lmu" % inicial)),
                {m: i for i, m in enumerate(todos)}.get, asociaciones)
            pares.extend(del_juego)
            for par in snes_convert.graficos_de_prueba(args.grafico_de_prueba):
                if par not in pares:
                    pares.append(par)
        return pares[indice]

    rutas = []
    for caso in casos:
        texto = pagina_json(comandos_de(caso, grupo, id_de, grafico_de))
        ruta = os.path.join(casos_dir, "%s.json" % hashlib.sha256(
            texto.encode()).hexdigest()[:12])
        with open(ruta, "w", encoding="utf-8") as archivo:
            archivo.write(texto)
        rutas.append(ruta)

    nuevo = sin_flags_de_caso(cartucho, parser)
    # El caso 0 es el de antes del primer `--caso` si lo había: ver
    # `casos_de_prueba`. Si no, el primer `--caso` pasó a ser el 0.
    primero_suelto = snes_convert.pide_pagina_de_prueba(args)
    for k, ruta in enumerate(rutas):
        if k or not primero_suelto:
            nuevo.append("--caso")
        nuevo += ["--comandos-de-prueba", ruta]
    return nuevo, rutas


def convertir(argv, destino):
    os.makedirs(destino, exist_ok=True)
    inc = os.path.join(destino, "mapdata.inc")
    r = subprocess.run([sys.executable,
                        os.path.join(REPO, "tools", "snes_convert.py"),
                        "-o", inc] + argv,
                       capture_output=True, text=True, cwd=REPO)
    if r.returncode:
        return None, r.stderr[-2000:]
    with open(inc, "rb") as archivo:
        return archivo.read(), None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("registro")
    p.add_argument("--casos", required=True)
    p.add_argument("--trabajo", required=True)
    p.add_argument("-j", type=int, default=8)
    a = p.parse_args()
    os.makedirs(a.casos, exist_ok=True)
    parser = snes_convert.parser_de_flags()
    lineas = []
    with open(a.registro) as archivo:
        for renglon in archivo:
            argv = json.loads(renglon)
            if argv not in lineas:
                lineas.append(argv)
    trabajos = []
    for n, argv in enumerate(lineas):
        cartucho, tramos = snes_convert.partir_en_casos(argv)
        if not snes_convert.casos_de_prueba(
                parser, parser.parse_args(cartucho), tramos):
            continue
        nuevo, rutas = traducir(argv, parser, a.casos)
        # La misma línea sin su `-o`, que pone `convertir`.
        viejo = list(argv)
        if "-o" in viejo:
            salida = viejo.index("-o")
            del viejo[salida:salida + 2]
        # Y lo que armó esa misma línea cuando se anotó, si todavía está: es
        # lo que dice que los flags siguen dando lo mismo que antes.
        antes = argv[argv.index("-o") + 1] if "-o" in argv else None
        trabajos.append((n, viejo, nuevo, rutas, antes))

    def correr(trabajo):
        n, viejo, nuevo, rutas, antes = trabajo
        base = os.path.join(a.trabajo, "%03d" % n)
        uno, err1 = convertir(viejo, os.path.join(base, "flags"))
        dos, err2 = convertir(nuevo, os.path.join(base, "archivo"))
        previo = None
        if antes and os.path.exists(antes):
            with open(antes, "rb") as archivo:
                previo = archivo.read()
        return n, viejo, nuevo, rutas, uno, dos, err1, err2, previo

    iguales = distintos = 0
    with concurrent.futures.ThreadPoolExecutor(a.j) as pool:
        for n, viejo, nuevo, rutas, uno, dos, err1, err2, previo in pool.map(
                correr, trabajos):
            if previo is not None and previo != uno:
                print("CAMBIÓ CON FLAGS %03d %s" % (n, json.dumps(viejo)))
            if err1 or err2 or uno != dos:
                distintos += 1
                print("DISTINTO %03d %s" % (n, json.dumps(viejo)))
                print("   ->     %s" % json.dumps(nuevo))
                if err1:
                    print("   flags: " + err1)
                if err2:
                    print("   archivo: " + err2)
            else:
                iguales += 1
                print("igual %03d %s" % (n, " ".join(os.path.basename(r)
                                                    for r in rutas)))
            sys.stdout.flush()
    print("%d iguales, %d distintos" % (iguales, distintos))
    return 1 if distintos else 0


if __name__ == "__main__":
    sys.exit(main())
