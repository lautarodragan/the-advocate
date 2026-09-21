#!/usr/bin/env python3
"""Los parches: lo que el conversor **decide perder** al pasar el juego a la SNES.

Al pasar de RPG Maker a la consola hay dos clases de transformación y sólo una
es un parche. El horneado de eventos opacos, el reuso de tiles espejados o
`separar_del_heroe` no piden criterio y no cambian lo que se ve: son
optimizaciones y no están acá. Fusionar dos colores porque la CGRAM no da para
los dos, en cambio, **pierde algo y alguien eligió qué**, y eso es un parche.

Hasta hoy esas decisiones se tomaban solas y no dejaban rastro: si un cambio
hacía que un mapa perdiera dos colores más, la única forma de enterarse era
mirar la ROM. Acá salen escritas, se versionan, y la tanda falla si lo
commiteado no coincide —lo mismo que `just protocolo --check` hace con los
opcodes—. El punto es que **el diff avise**: es lo que las goldens hacen con
los pixeles, para las decisiones.

Lo que se escribe es **el estado deseado y no un informe**, porque la fase 2
—ya decidida— es que el conversor lea estos archivos en vez de volver a
decidir. Por eso cada fusión se escribe como "este color se va a este otro" y
en el orden en que se aplicaron: replayar la lista reconstruye el mapeo entero,
que es exactamente lo que devuelve `asignador.merge_least_visible`.

Un ejemplo de cómo se leería de vuelta, que es lo que guió el formato::

    mapping = {}
    for f in parches.leer(RAIZ, 7)["capas"]["fondo"]["fusiones"]:
        de, a = tuple(f["de"]), tuple(f["a"])
        for viejo, actual in mapping.items():
            if actual == de:
                mapping[viejo] = a
        mapping[de] = a

La clave
--------

Un archivo por mapa, ``parches/mapas/<id>.toml``, y adentro una sección por
capa. **El id del mapa es del juego y no del cartucho**: no se mueve cuando
cambia la lista de mapas de la ROM, ni cuando cambia el orden interno del
conversor, ni cuando cambia el algoritmo del asignador. Los colores se escriben
por su valor —RGB de 15 bits, que es la profundidad real de la consola— y no
por su índice en ninguna paleta, por lo mismo: el índice se corre con cualquier
cosa y el valor identifica al color para siempre.

Y el cartucho **no entra en la clave**, que es la decisión que más se pensó.
Las fusiones de las capas dependen del mapa y de su ChipSet y de nada más —es
la misma razón por la que `capas_convertidas` las puede cachear en disco con
una clave que no sabe qué cartucho se está armando—, así que meter el cartucho
adentro repetiría la misma decisión tres veces y dejaría tres lugares donde
editarla en la fase 2. Que eso sea cierto **no se supone**: cada cartucho
escribe su copia en `rom/build/<cartucho>/parches/` y `--check` compara todas
contra la única versionada, así que si alguna vez un cartucho decidiera
distinto, la tanda lo dice con el nombre del cartucho puesto.

Lo que **todavía no está acá**, y es lo que queda para más adelante: las
paletas de los personajes —que sí dependen del cartucho, porque quién le paga
la entrada al cronómetro lo decide `npcs_dibujables` mirando el mapa entero—,
las voces que se caen de un MIDI, las muestras recortadas, las animaciones
dibujadas a otro tamaño y `DECORAR_TRANSLUCIDO`.
"""

import argparse
import os
import sys
import tomllib

# Dónde viven los versionados, relativo a la raíz del repo.
DIRECTORIO = os.path.join("parches", "mapas")

# Dónde los deja cada cartucho al armarse, relativo al directorio del build.
EN_BUILD = os.path.join("parches", "mapas")


def ruta(raiz, map_id):
    return os.path.join(raiz, DIRECTORIO, "%04d.toml" % map_id)


def _color(c):
    return "[%d, %d, %d]" % tuple(c)


def texto(map_id, nombre, resumen):
    """El archivo de un mapa, tal cual va a disco.

    `resumen` es el que deja `_convert_layers` en `mapa["resumen"]`.
    """
    fusiones = resumen.get("fusiones", {"fondo": [], "encima": []})
    lineas = [
        "# Las decisiones artísticas del mapa %d: qué se pierde al pasarlo a la"
        % map_id,
        "# SNES. Lo escribe el conversor y lo regenera `just parches`, que es lo",
        "# que hay que correr cuando un cambio lo mueve; `just parches --check`",
        "# —y la tanda— fallan si quedó viejo. Ver tools/port/parches.py.",
        "",
        "mapa = %d" % map_id,
        "nombre = %s" % _cadena(nombre),
    ]
    for capa, cuantos in (("fondo", resumen.get("presupuesto")),
                          ("encima", None)):
        lineas += ["", "[capas.%s]" % capa]
        if capa == "fondo":
            lineas += [
                "# Cuántos colores distintos traía el dibujo y cuántas entradas",
                "# de CGRAM le dejó la capa de encima.",
                "colores = %d" % resumen["colores"],
                "presupuesto = %d" % cuantos,
            ]
        lineas += [
            "# Cada fusión manda el color `de` al color `a`, en RGB de 15 bits,",
            "# y `pixeles` es cuántos movía cuando se decidió. Van **en orden**:",
            "# aplicarlas de arriba a abajo reconstruye el mapeo entero.",
        ]
        propias = fusiones.get(capa, [])
        if not propias:
            lineas.append("fusiones = []")
            continue
        lineas.append("fusiones = [")
        for victima, destino, pixeles in propias:
            lineas.append("  { de = %s, a = %s, pixeles = %d },"
                          % (_color(victima), _color(destino), pixeles))
        lineas.append("]")
    return "\n".join(lineas) + "\n"


def _cadena(valor):
    return '"%s"' % str(valor).replace("\\", "\\\\").replace('"', '\\"')


def escribir(destino, mapas):
    """Los parches de los mapas de un cartucho, en `<destino>/parches/mapas/`.

    `mapas` son los que devuelve `main()` del conversor. Devuelve cuántos
    archivos escribió y cuántos bytes ocupan.
    """
    carpeta = os.path.join(destino, EN_BUILD)
    os.makedirs(carpeta, exist_ok=True)
    bytes_ = 0
    for mapa in mapas:
        contenido = texto(mapa["id"], mapa["nombre"], mapa["resumen"])
        with open(os.path.join(carpeta, "%04d.toml" % mapa["id"]), "w") as f:
            f.write(contenido)
        bytes_ += len(contenido.encode("utf-8"))
    return len(mapas), bytes_


# --- la verificación --------------------------------------------------------

def _leer(ruta_):
    with open(ruta_, "rb") as f:
        return tomllib.load(f)


def _fusiones(doc, capa):
    return [(tuple(f["de"]), tuple(f["a"]), f["pixeles"])
            for f in doc.get("capas", {}).get(capa, {}).get("fusiones", [])]


def diferencias(viejo, nuevo):
    """Qué decisión cambió entre dos parches ya parseados, en castellano.

    No es un diff de texto: un archivo que difiere sólo en un comentario no
    dice nada, y uno al que le cambió una fusión tiene que decir **cuál**. Es
    lo único que hace útil a la verificación: "el archivo difiere" manda a
    correr `diff` y a adivinar si el cambio importa.
    """
    salida = []
    for capa in ("fondo", "encima"):
        antes, ahora = _fusiones(viejo, capa), _fusiones(nuevo, capa)
        for campo in ("colores", "presupuesto"):
            a = viejo.get("capas", {}).get(capa, {}).get(campo)
            b = nuevo.get("capas", {}).get(capa, {}).get(campo)
            if a != b:
                salida.append("capa %s: %s pasó de %s a %s"
                              % (capa, campo, a, b))
        if len(antes) != len(ahora):
            salida.append("capa %s: fusionaba %d color(es) y ahora fusiona %d"
                          % (capa, len(antes), len(ahora)))
        for i, (a, b) in enumerate(zip(antes, ahora)):
            if a[:2] != b[:2]:
                salida.append(
                    "capa %s: la fusión %d mandaba %s a %s y ahora manda %s a %s"
                    % (capa, i, _color(a[0]), _color(a[1]),
                       _color(b[0]), _color(b[1])))
            elif a[2] != b[2]:
                salida.append(
                    "capa %s: la fusión %d de %s movía %d pixel(es) y ahora "
                    "mueve %d" % (capa, i, _color(a[0]), a[2], b[2]))
        sobran = ahora[len(antes):] if len(ahora) > len(antes) else []
        faltan = antes[len(ahora):] if len(antes) > len(ahora) else []
        for v, d, _p in sobran:
            salida.append("capa %s: fusiona de más %s -> %s"
                          % (capa, _color(v), _color(d)))
        for v, d, _p in faltan:
            salida.append("capa %s: ya no fusiona %s -> %s"
                          % (capa, _color(v), _color(d)))
    return salida


def revisar(raiz, builds):
    """Los parches de los builds contra los versionados. Lista de quejas.

    `builds` son directorios de cartuchos armados —los que tienen adentro
    `parches/mapas/`—. Se comparan **todos**, y no sólo uno: que dos cartuchos
    decidan lo mismo para el mismo mapa es lo que sostiene que el cartucho no
    entre en la clave, y acá se mide en vez de suponerse.
    """
    quejas = []
    emitidos = {}
    for build in builds:
        carpeta = os.path.join(build, EN_BUILD)
        if not os.path.isdir(carpeta):
            continue
        cartucho = os.path.basename(os.path.normpath(build))
        for nombre in sorted(os.listdir(carpeta)):
            if not nombre.endswith(".toml"):
                continue
            doc = _leer(os.path.join(carpeta, nombre))
            map_id = doc["mapa"]
            antes = emitidos.get(map_id)
            if antes is not None and diferencias(antes[1], doc):
                quejas.append(
                    "el mapa %d sale distinto en los cartuchos «%s» y «%s», "
                    "así que la decisión depende del cartucho y este formato "
                    "no la puede guardar:\n    %s"
                    % (map_id, antes[0], cartucho,
                       "\n    ".join(diferencias(antes[1], doc))))
            if antes is not None:
                # Contra lo versionado se compara **una vez por mapa**: los
                # tres cartuchos decidieron lo mismo —lo acaba de comprobar el
                # bloque de arriba—, así que repetir la queja sólo tapa a las
                # de los otros mapas.
                continue
            emitidos[map_id] = (cartucho, doc)
            versionado = ruta(raiz, map_id)
            if not os.path.exists(versionado):
                quejas.append(
                    "el mapa %d no tiene parche versionado y el cartucho «%s» "
                    "decide sobre él: falta %s. Corré `just parches`."
                    % (map_id, cartucho, os.path.relpath(versionado, raiz)))
                continue
            cambios = diferencias(_leer(versionado), doc)
            if cambios:
                quejas.append(
                    "%s quedó viejo (lo dice el cartucho «%s»):\n    %s\n"
                    "  Si el cambio es el que se buscaba, `just parches` y al "
                    "commit; si no, algo movió lo que se ve."
                    % (os.path.relpath(versionado, raiz), cartucho,
                       "\n    ".join(cambios)))
    carpeta = os.path.join(raiz, DIRECTORIO)
    sobrantes = sorted(
        int(n[:-5]) for n in os.listdir(carpeta) if n.endswith(".toml")
    ) if os.path.isdir(carpeta) else []
    for map_id in sobrantes:
        if map_id not in emitidos:
            quejas.append(
                "el mapa %d tiene parche versionado y ningún cartucho lo "
                "convierte: o sobra el archivo, o falta el mapa en algún "
                "cartucho." % map_id)
    return quejas


def main(argv=None):
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("builds", nargs="+",
                        help="los directorios de los cartuchos armados")
    parser.add_argument("--check", action="store_true",
                        help="no escribe: falla si lo versionado quedó viejo")
    args = parser.parse_args(argv)
    builds = []
    for build in args.builds:
        if os.path.isdir(os.path.join(build, EN_BUILD)):
            builds.append(build)
        else:
            builds += [os.path.join(build, n) for n in sorted(os.listdir(build))
                       if os.path.isdir(os.path.join(build, n, EN_BUILD))]
    if not builds:
        sys.exit("no encontré ningún cartucho armado con parches adentro: %s"
                 % ", ".join(args.builds))
    if args.check:
        quejas = revisar(raiz, builds)
        for queja in quejas:
            print("  " + queja, file=sys.stderr)
        if quejas:
            sys.exit("%d parche(s) no coinciden con lo que decide el conversor"
                     % len(quejas))
        print("los parches de %d cartucho(s) coinciden con lo versionado"
              % len(builds))
        return
    destino = os.path.join(raiz, DIRECTORIO)
    os.makedirs(destino, exist_ok=True)
    vistos, bytes_ = set(), 0
    for build in builds:
        carpeta = os.path.join(build, EN_BUILD)
        for nombre in sorted(os.listdir(carpeta)):
            if not nombre.endswith(".toml") or nombre in vistos:
                continue
            with open(os.path.join(carpeta, nombre)) as f:
                contenido = f.read()
            with open(os.path.join(destino, nombre), "w") as f:
                f.write(contenido)
            vistos.add(nombre)
            bytes_ += len(contenido.encode("utf-8"))
    for nombre in sorted(os.listdir(destino)):
        if nombre.endswith(".toml") and nombre not in vistos:
            os.remove(os.path.join(destino, nombre))
            print("  %s: ningún cartucho convierte ese mapa, lo saco" % nombre)
    print("%d parche(s) en %s, %d B" % (len(vistos), DIRECTORIO, bytes_))


if __name__ == "__main__":
    main()
