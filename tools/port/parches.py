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
que es exactamente lo que devuelve `asignador.merge_least_visible`. Y por eso
una animación escribe el rectángulo al que se dibuja y no cuánto se achicó: el
porcentaje es para leer y el rectángulo es para aplicar.

Dos ejemplos de cómo se leería de vuelta, que es lo que guió el formato. El
mapeo de colores de una capa::

    mapping = {}
    for f in parches.leer(RAIZ, 7)["capas"]["fondo"]["fusiones"]:
        de, a = tuple(f["de"]), tuple(f["a"])
        for viejo, actual in mapping.items():
            if actual == de:
                mapping[viejo] = a
        mapping[de] = a

Y el tamaño al que se dibuja una animación de batalla, que es una sola línea
porque la decisión es un rectángulo::

    ta, tal = parches.leer_animacion(RAIZ, 82)["tamano"]

La clave
--------

Un archivo por situación del juego: ``parches/auto/mapas/<id>.toml`` para las
capas de un mapa, con una sección por capa, y
``parches/auto/animaciones/<n>.toml`` para las animaciones de batalla. **El id
del mapa es del juego y no del cartucho**: no se mueve cuando cambia la lista
de mapas de la ROM, ni cuando cambia el orden interno del conversor, ni cuando
cambia el algoritmo del asignador. Los colores se escriben por su valor —RGB de
15 bits, que es la profundidad real de la consola— y no por su índice en
ninguna paleta, por lo mismo: el índice se corre con cualquier cosa y el valor
identifica al color para siempre.

Y el cartucho **no entra en la clave**: la regla es de taro, del 2026-09-21, y
dice que *la decisión versionada es siempre la del ROM jugable*, hoy `release`. Lo
versionado es lo que perdió **el juego**, que es lo único que le importa a
alguien que mire el repo; un cartucho de prueba la reusa cuando aplica, y
cuando no aplica decide por su cuenta y eso no se versiona. Por eso acá están
los 29 mapas de `abl` y no los 40 que arman los cartuchos de prueba: los once
que sobran son situaciones que sólo existen en la tanda.

Lo que pasa **cuando la decisión de `abl` no se puede aplicar** en un cartucho
de prueba es, entonces, un camino previsto y no una excepción: ese cartucho
decide solo, escribe lo que decidió al lado de su ROM —en
`rom/build/<cartucho>/parches/`, que no se versiona— y `--check` no le pide
nada. En esta clase de decisión, encima, la pregunta no se llega a hacer: las
fusiones de las capas dependen del mapa y de su ChipSet y de nada más —es la
misma razón por la que `capas_convertidas` las puede cachear con una clave que
no sabe qué cartucho se está armando—. Que eso sea cierto **no se supone**:
`--check` compara contra lo versionado **todos** los cartuchos que lleven un
mapa versionado, así que si alguno decidiera distinto, la tanda lo dice con su
nombre puesto. Medido el 2026-09-21: los tres cartuchos de prueba de entonces y `abl`
emiten los mismos 29 archivos byte por byte.

Y una cosa que el formato deja abierta a propósito. El rumbo es que qué mapas
entran, dónde arranca la ROM y con qué grupo dejen de ser argumentos sueltos de
una receta y pasen a ser **una descripción** que el que reparte paletas pueda
leer. Una clave que nombra la situación del juego —el mapa, y mañana el
gráfico o el tema— no le estorba: el día que exista, lo que cambia es de dónde
sale la lista de situaciones, no cómo se identifica cada una.

Las animaciones de batalla
--------------------------

La segunda clase que dejó de decidirse en silencio, y la más barata de las que
quedaban: **a qué tamaño se dibuja cada animación**. Una que no entra en la
caja de la consola se achica entera, con su proporción, y eso se ve —la 82 de
la intro mide 536x416 en RM2k y se dibuja en 64x49, el 11%—.

Su clave es **el número de animación de RM2k**, y alcanza sola porque el
tamaño sale de `animacion.tamano`, que mira la caja que la animación ocupa en
RM2k y la caja de la consola, que es **una sola para toda la ROM** —el porqué
está en `animacion.py`: que no dependa del mapa es lo que deja que los
`ShowBattleAnimation` de todos los mapas compartan los cuadros ya
convertidos—. Ni el cartucho ni el mapa entran, y no se supone: lo mismo que
con las capas, `--check` compara todos los cartuchos que muestren una
animación versionada, y
`test_el_tamano_de_cada_animacion_versionada_sale_de_su_caja_y_de_nada_mas`
rehace la cuenta desde lo escrito.

Lo que **sí** depende del mapa es otra cosa y no está acá: si la animación se
dibuja, que es lo que decide `animacion_de_mapa` cuando el mapa ya se llevó
las ocho paletas de sprite. Es otra decisión —y otra clase—, y meterla en este
archivo sería volver a mezclar el cartucho con el juego.

Los battlers
------------

La tercera, del 2026-09-21: desde que la escena de la pelea se compone en la
consola, cada battler tiene **quince colores y el transparente**, y cuáles se
pierden es una decisión nueva. Se escribe la paleta que quedó y cuántas
fusiones hicieron falta —ver `texto_battler`—, con la clave del battler:
su imagen y su tono, que es lo que `escena.clave` arma. No mira la tropa ni el
cartucho: la reducción es del dibujo ya achicado y de nada más.

Lo que **todavía no está acá**, y es lo que queda para más adelante: las
paletas de los personajes —que sí dependen del cartucho, porque quién le paga
la entrada al cronómetro lo decide `npcs_dibujables` mirando el mapa entero—,
las voces que se caen de un MIDI, las muestras recortadas, los quince colores
a los que se reduce cada animación y `DECORAR_TRANSLUCIDO`.
"""

import argparse
import collections
import os
import sys
import tomllib

# Corrido como script, deja `tools/` en el camino de los imports en vez de la
# carpeta de este archivo; y desde el PATH, si el directorio actual es otro
# checkout, corre el de ahí: ver `comun/ejecutable.py`.
if __name__ == "__main__":
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    from comun import ejecutable
    ejecutable.usar_el_del_checkout(__file__)

# Dónde viven los versionados, relativo a la raíz del repo.
DIRECTORIO = os.path.join("parches", "auto", "mapas")

# Dónde los deja cada cartucho al armarse, relativo al directorio del build.
EN_BUILD = DIRECTORIO


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
        "# —y la tanda— fallan si quedó viejo. Ver `rm2k-snes-patches`.",
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


def _vaciar(carpeta):
    """La carpeta de una clase en el build, creada y sin los `.toml` de la
    corrida anterior. Sin esto, un cartucho que deja de llevar un mapa o una
    animación seguía teniendo su parche viejo al lado de la ROM, y
    `revisar` lo contaba como convertido: al sacar los mapas de prueba de
    `release`, el `0052.toml` que había quedado hacía caer `test_parches`."""
    os.makedirs(carpeta, exist_ok=True)
    for viejo in os.listdir(carpeta):
        if viejo.endswith(".toml"):
            os.remove(os.path.join(carpeta, viejo))
    return carpeta


def escribir(destino, mapas):
    """Los parches de los mapas de un cartucho, en
    `<destino>/parches/auto/mapas/`.

    `mapas` son los que devuelve `main()` del conversor. Devuelve cuántos
    archivos escribió y cuántos bytes ocupan.
    """
    carpeta = _vaciar(os.path.join(destino, EN_BUILD))
    bytes_ = 0
    for mapa in mapas:
        contenido = texto(mapa["id"], mapa["nombre"], mapa["resumen"])
        with open(os.path.join(carpeta, "%04d.toml" % mapa["id"]), "w") as f:
            f.write(contenido)
        bytes_ += len(contenido.encode("utf-8"))
    return len(mapas), bytes_


# --- las animaciones de batalla, que se dibujan a otro tamaño ---------------

# Igual que los mapas: versionadas acá, y cada cartucho deja las suyas al lado
# de su ROM. La clave es **el número de animación de RM2k**, que es del juego:
# el mismo 82 en cualquier cartucho que la muestre.
DIRECTORIO_ANIM = os.path.join("parches", "auto", "animaciones")
EN_BUILD_ANIM = DIRECTORIO_ANIM


def ruta_animacion(raiz, numero):
    return os.path.join(raiz, DIRECTORIO_ANIM, "%04d.toml" % numero)


def texto_animacion(datos):
    """El archivo de una animación, tal cual va a disco.

    `datos` es lo que arma `snes_convert` con `animacion.informe` y el nombre
    que la animación tiene en el LDB.
    """
    ancho, alto = datos["original"]
    ta, tal = datos["caja"]
    return "\n".join([
        "# La decisión artística de la animación %d: **a qué tamaño se dibuja**"
        % datos["animacion"],
        "# en la consola. Lo escribe el conversor y lo regenera `just parches`,",
        "# que es lo que hay que correr cuando un cambio lo mueve; `just parches",
        "# --check` —y la tanda— fallan si quedó viejo. Ver `rm2k-snes-patches`.",
        "",
        "animacion = %d" % datos["animacion"],
        "nombre = %s" % _cadena(datos["nombre"]),
        "hoja = %s" % _cadena(datos["hoja"]),
        "",
        "# Lo decidido: el rectángulo, en pixeles de la consola, al que se",
        "# achica la animación entera para entrar en la caja de %d x %d. Es lo"
        % (datos["lado"], datos["lado"]),
        "# que la fase 2 va a leer en vez de volver a calcularlo.",
        "tamano = [%d, %d]" % (ta, tal),
        "",
        "# De qué venía: la unión de todas las celdas de todos sus cuadros en",
        "# pixeles de RM2k, y cuántos cuadros son. No se decide, se mide, y",
        "# está para que el diff diga por qué cambió el tamaño.",
        "original = [%d, %d]" % (ancho, alto),
        "cuadros = %d" % datos["cuadros"],
        "",
    ])


def escribir_animaciones(destino, animaciones):
    """Los parches de las animaciones de un cartucho, en
    `<destino>/parches/auto/animaciones/`.

    Devuelve cuántos archivos escribió y cuántos bytes ocupan.
    """
    carpeta = _vaciar(os.path.join(destino, EN_BUILD_ANIM))
    bytes_ = 0
    for datos in animaciones:
        contenido = texto_animacion(datos)
        with open(os.path.join(carpeta, "%04d.toml" % datos["animacion"]),
                  "w") as f:
            f.write(contenido)
        bytes_ += len(contenido.encode("utf-8"))
    return len(animaciones), bytes_


# --- los battlers, que se reducen a quince colores --------------------------

# La tercera clase, desde el 2026-09-21: con la escena de la pelea compuesta en
# la consola cada battler lleva **quince colores y el transparente**, y cuáles
# se pierden es una decisión que antes no existía —la escena horneada repartía
# 96 entre el fondo y todos los battlers juntos—. Ver tools/port/escena.py.
#
# La clave es **el battler**: la imagen de RM2k y su tono, `escena.clave`. Es
# del juego y no depende del cartucho ni de la tropa, porque la reducción mira
# el dibujo ya achicado y nada más.
DIRECTORIO_BAT = os.path.join("parches", "auto", "battlers")
EN_BUILD_BAT = DIRECTORIO_BAT


def _archivo(clave):
    """El nombre de archivo de una clave: los battlers de RM2k pueden tener
    espacios —`sentry drone`—, y un archivo con espacios en el repo es una
    molestia en cada comando que lo nombre."""
    return "%s.toml" % str(clave).replace(" ", "_")


def ruta_battler(raiz, clave):
    return os.path.join(raiz, DIRECTORIO_BAT, _archivo(clave))


def texto_battler(info):
    """El archivo de un battler, tal cual va a disco. `info` es el que devuelve
    `escena.battler`."""
    lineas = [
        "# La decisión artística del battler %s: **qué colores se pierden** al"
        % info["clave"],
        "# llevarlo a quince, que es lo que la escena de la pelea le deja a cada",
        "# uno. Lo escribe el conversor y lo regenera `just parches`, que es lo",
        "# que hay que correr cuando un cambio lo mueve; `just parches --check`",
        "# —y la tanda— fallan si quedó viejo. Ver `rm2k-snes-patches`.",
        "",
        "battler = %s" % _cadena(info["clave"]),
        "imagen = %s" % _cadena(info["imagen"]),
        "tono = %d" % info["tono"],
        "",
        "# De qué venía, ya achicado al 80%: el tamaño en pixeles de la escena y",
        "# cuántos colores distintos de 15 bits traía. No se decide, se mide.",
        "tamano = [%d, %d]" % (info["ancho"], info["alto"]),
        "colores = %d" % info["colores"],
        "",
        "# Lo que quedó, en el orden de la paleta: el índice 1 es el primero.",
        "paleta = [",
    ]
    for color in info["paleta"]:
        lineas.append("  %s," % _color(color))
    # **La forma mínima, a propósito**: la paleta que quedó y no la lista de
    # fusiones que llevó a ella. Un battler ya achicado trae cientos de colores
    # —los grises intermedios que deja el LANCZOS en cada borde— y la lista
    # medía 179 KB para los once de `abl`; lo que se ve es qué quince quedan, y
    # eso es lo que el diff tiene que mostrar. El día que la fase 2 quiera leer
    # esto en vez de decidir, la lista vuelve: es `info["fusiones"]`.
    lineas += [
        "]",
        "",
        "# Cuántas fusiones hicieron falta para llegar ahí, con",
        "# `asignador.merge_least_visible`: cada una manda al color que menos",
        "# se nota a su vecino más cercano.",
        "fusiones = %d" % len(info["fusiones"]),
    ]
    return "\n".join(lineas) + "\n"


def escribir_battlers(destino, battlers):
    """Los parches de los battlers de un cartucho, en
    `<destino>/parches/auto/battlers/`. Devuelve cuántos y cuántos bytes."""
    carpeta = _vaciar(os.path.join(destino, EN_BUILD_BAT))
    bytes_ = 0
    for info in battlers:
        contenido = texto_battler(info)
        with open(os.path.join(carpeta, _archivo(info["clave"])), "w") as f:
            f.write(contenido)
        bytes_ += len(contenido.encode("utf-8"))
    return len(battlers), bytes_


def leer_battler(raiz, clave):
    return _leer(ruta_battler(raiz, clave))


def diferencias_battler(viejo, nuevo):
    """Qué cambió entre dos parches de battler, en castellano: primero si se
    pierde otro color, después por qué."""
    salida = []
    antes = [tuple(c) for c in viejo.get("paleta", [])]
    ahora = [tuple(c) for c in nuevo.get("paleta", [])]
    for c in ahora:
        if c not in antes:
            salida.append("se queda con %s, que antes se fusionaba"
                          % _color(c))
    for c in antes:
        if c not in ahora:
            salida.append("pierde %s, que antes se quedaba" % _color(c))
    if not salida and antes != ahora:
        salida.append("los mismos colores en otro orden de paleta")
    for campo in ("tamano", "colores", "imagen", "tono"):
        if viejo.get(campo) != nuevo.get(campo):
            salida.append("%s pasó de %s a %s"
                          % (campo, viejo.get(campo), nuevo.get(campo)))
    if viejo.get("fusiones") != nuevo.get("fusiones"):
        salida.append("hacían falta %s fusiones y ahora %s"
                      % (viejo.get("fusiones"), nuevo.get("fusiones")))
    return salida


# --- lo que no es del juego -------------------------------------------------

# Quién pidió cada parche del cartucho, al lado de sus parches y **sin
# versionar**: lo escribe el conversor —ver `usos_de_los_parches` en
# snes_convert.py— y lo lee `de_prueba`. Hace falta desde que la ROM que se
# juega lleva también los mapas y las páginas de la tanda.
USOS = os.path.join("parches", "usos.json")


def escribir_usos(destino, usos):
    """`usos` es `{clave de la clase: {clave: [origen, ...]}}`; el origen es un
    id de mapa o `"caso"`."""
    import json
    with open(os.path.join(destino, USOS), "w") as f:
        json.dump({clase: {str(k): sorted(v, key=str)
                           for k, v in sorted(cuales.items(), key=str)}
                   for clase, cuales in usos.items()}, f, indent=1)


def mapas_de_prueba():
    """Los mapas que sólo existen por la tanda. Salen de `cartuchos.py`, que es
    donde se decide qué mapas lleva cada cartucho; acá no se escriben otra
    vez."""
    # `realpath`: corrido desde el PATH, `__file__` es el symlink.
    herramientas = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    if herramientas not in sys.path:
        sys.path.insert(0, herramientas)
    from ensamblado import cartuchos
    return set(cartuchos.MAPAS_DE_PRUEBA)


def de_prueba(build, clase, cual, prueba):
    """Si `cual` está en el cartucho `build` sólo por la tanda: un mapa de
    prueba, o una animación o un battler que sólo piden los mapas de prueba y
    las páginas de los casos. `prueba` es `mapas_de_prueba()`.

    Sin `usos.json`, o sin origen conocido, **no**: la duda va para el lado de
    pedir el parche, que es la queja que se ve.
    """
    if clase.clave == "mapa":
        return cual in prueba
    import json
    try:
        with open(os.path.join(build, USOS)) as f:
            origenes = json.load(f).get(clase.clave, {}).get(str(cual))
    except OSError:
        return False
    return bool(origenes) and all(o == "caso" or o in prueba
                                  for o in origenes)


# --- la verificación --------------------------------------------------------

def _leer(ruta_):
    with open(ruta_, "rb") as f:
        return tomllib.load(f)


def leer(raiz, map_id):
    """Lo decidido y versionado para un mapa, parseado.

    Es la puerta de entrada de la fase 2 y la usa la verificación, que es lo
    que la mantiene viva mientras la fase 2 no exista.
    """
    return _leer(ruta(raiz, map_id))


def leer_animacion(raiz, numero):
    """Lo decidido y versionado para una animación de batalla, parseado."""
    return _leer(ruta_animacion(raiz, numero))


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


def diferencias_animacion(viejo, nuevo):
    """Qué cambió entre dos parches de animación, en castellano.

    Lo que importa es la primera línea: **a qué tamaño se dibuja**. Las otras
    dos dicen por qué cambió —la animación mide otra cosa en RM2k, o tiene
    otros cuadros—, y pueden salir solas: que la caja no se mueva no quiere
    decir que la animación sea la misma.
    """
    salida = []
    if viejo.get("tamano") != nuevo.get("tamano"):
        salida.append("se dibujaba a %s y ahora se dibuja a %s"
                      % (_lados(viejo.get("tamano")),
                         _lados(nuevo.get("tamano"))))
    if viejo.get("original") != nuevo.get("original"):
        salida.append("venía de %s en RM2k y ahora viene de %s"
                      % (_lados(viejo.get("original")),
                         _lados(nuevo.get("original"))))
    if viejo.get("cuadros") != nuevo.get("cuadros"):
        salida.append("tenía %s cuadro(s) y ahora tiene %s"
                      % (viejo.get("cuadros"), nuevo.get("cuadros")))
    if viejo.get("hoja") != nuevo.get("hoja"):
        salida.append("salía de la hoja %r y ahora sale de %r"
                      % (viejo.get("hoja"), nuevo.get("hoja")))
    return salida


def _lados(par):
    return "%dx%d" % tuple(par) if par else "nada"


# Las clases de decisión que hay escritas, cada una con su directorio, la
# clave con que se identifica —que es siempre algo **del juego**— y cómo se
# cuenta qué cambió. Agregar una clase es agregar una fila acá y su `texto`:
# la verificación, el copiado a `parches/` y los mensajes salen de ésta.
Clase = collections.namedtuple(
    "Clase", "nombre articulo directorio clave leer diferencias")

CLASES = (
    Clase("mapa(s)", "el mapa", DIRECTORIO, "mapa", leer, diferencias),
    Clase("animación(es)", "la animación", DIRECTORIO_ANIM, "animacion",
          leer_animacion, diferencias_animacion),
    Clase("battler(s)", "el battler", DIRECTORIO_BAT, "battler",
          leer_battler, diferencias_battler),
)


def versionados(raiz, clase=None):
    """Los que tienen parche versionado, o sea los del ROM jugable.

    Sin `clase`, los mapas: es lo que pedían los llamadores cuando ésta era la
    única clase que había.
    """
    clase = clase or CLASES[0]
    carpeta = os.path.join(raiz, clase.directorio)
    if not os.path.isdir(carpeta):
        return []
    # La clave se lee de adentro del archivo y no del nombre: la de un battler
    # es un texto, y su nombre de archivo no lleva los espacios. Ver `_archivo`.
    return sorted(_leer(os.path.join(carpeta, n))[clase.clave]
                  for n in os.listdir(carpeta) if n.endswith(".toml"))


def revisar(raiz, builds, jugable="release"):
    """Los parches de los builds contra los versionados: (quejas, propios).

    `builds` son directorios de cartuchos armados, y se miran **todos**. Lo que
    no está versionado no es una queja: es una situación que `abl` no tiene
    —un mapa que no lleva, una animación que no muestra—, así que el cartucho
    de prueba decidió solo y eso no se versiona; sale en `propios`, que es
    información sobre cuánto se parecen los cartuchos al juego y no un error.
    Del ROM jugable, en cambio, todo tiene que estar versionado **salvo lo que
    lleva sólo por la tanda** —ver `de_prueba`—, que también sale en
    `propios`.

    Lo que **sí** está versionado se compara contra lo commiteado en cada
    cartucho que lo lleve. Para las dos clases de hoy eso no puede dar distinto
    —ni las fusiones de las capas ni el tamaño de una animación miran el
    cartucho— y por eso da queja: si diera, lo que se rompió es esa
    independencia, y conviene enterarse ahí y no en la fase 2.

    `propios` va por clase: `{"mapa": {7: ["test-special"]}, ...}`, con la clave de
    cada una.
    """
    quejas, propios = [], {}
    for clase in CLASES:
        suyas, mios = _revisar_clase(clase, raiz, builds, jugable)
        quejas += suyas
        if mios:
            propios[clase.clave] = mios
    return quejas, propios


def _revisar_clase(clase, raiz, builds, jugable):
    quejas, propios = [], {}
    prueba = mapas_de_prueba()
    tengo = set(versionados(raiz, clase))
    vistos = set()
    # Una queja por situación **y por juego de diferencias**: cuatro cartuchos
    # que llevan el mismo mapa dicen todos lo mismo, y repetirlo cuatro veces
    # tapa a las de los demás. Si uno decidiera distinto que los otros, sus
    # diferencias son otras y su queja sale igual, con su nombre.
    dichas = set()
    for build in builds:
        carpeta = os.path.join(build, clase.directorio)
        if not os.path.isdir(carpeta):
            continue
        cartucho = os.path.basename(os.path.normpath(build))
        for nombre in sorted(os.listdir(carpeta)):
            if not nombre.endswith(".toml"):
                continue
            doc = _leer(os.path.join(carpeta, nombre))
            cual = doc[clase.clave]
            if cual not in tengo:
                if cartucho == jugable and not de_prueba(build, clase, cual,
                                                          prueba):
                    # Lo que el ROM jugable convierte **tiene** que estar
                    # versionado: si no, el juego pierde algo en algún lado y
                    # no queda escrito. En un cartucho de prueba, en cambio, es
                    # lo normal y no se dice nada.
                    quejas.append(
                        "%s %s entró en «%s», el ROM jugable, y no tiene "
                        "parche versionado: corré `just parches`."
                        % (clase.articulo, cual, cartucho))
                else:
                    propios.setdefault(cual, []).append(cartucho)
                continue
            vistos.add(cual)
            versionado = os.path.join(raiz, clase.directorio, nombre)
            cambios = clase.diferencias(clase.leer(raiz, cual), doc)
            if cambios and (cual, tuple(cambios)) not in dichas:
                dichas.add((cual, tuple(cambios)))
                quejas.append(
                    "%s quedó viejo (lo dice el cartucho «%s»), y lo que "
                    "cambió de %s %s es esto:\n    %s\n"
                    "  Si el cambio es el que se buscaba, `just parches` y al "
                    "commit; si no, algo movió lo que se ve."
                    % (os.path.relpath(versionado, raiz), cartucho,
                       clase.articulo, cual, "\n    ".join(cambios)))
    for cual in sorted(tengo - vistos):
        quejas.append(
            "%s %s tiene parche versionado y ninguno de los cartuchos armados "
            "lo convierte: o el juego dejó de llevarlo —y entonces sobra el "
            "archivo— o falta armar el cartucho que lo tiene."
            % (clase.articulo, cual))
    return quejas, propios


def main(argv=None):
    # `realpath`: corrido desde el PATH, `__file__` es el symlink.
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.realpath(__file__))))
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "builds", nargs="*",
        help="los directorios de los cartuchos armados. Sin --check tiene que "
             "ser el del ROM jugable y nada más: lo versionado es lo que "
             "decide `abl`. Con --check y sin ninguno, los de todos los "
             "cartuchos de `cartuchos.py`")
    parser.add_argument("--check", action="store_true",
                        help="no escribe: falla si lo versionado quedó viejo")
    args = parser.parse_args(argv)
    if not args.builds and args.check:
        mapas_de_prueba()       # deja `tools/` en el camino de los imports
        from ensamblado import cartuchos
        args.builds = [cartuchos.directorio(n) for n in cartuchos.CARTUCHOS]
    builds = []
    for build in args.builds:
        if _tiene_parches(build):
            builds.append(build)
        else:
            builds += [os.path.join(build, n) for n in sorted(os.listdir(build))
                       if _tiene_parches(os.path.join(build, n))]
    if not builds:
        sys.exit("no encontré ningún cartucho armado con parches adentro: %s"
                 % ", ".join(args.builds))
    if args.check:
        quejas, propios = revisar(raiz, builds)
        for queja in quejas:
            print("  " + queja, file=sys.stderr)
        if quejas:
            sys.exit("%d parche(s) no coinciden con lo que decide el conversor"
                     % len(quejas))
        for clase in CLASES:
            print("los %d parche(s) de %s del juego coinciden con lo que "
                  "decidieron %d cartucho(s)"
                  % (len(versionados(raiz, clase)), clase.nombre, len(builds)))
            mios = propios.get(clase.clave)
            if mios:
                # No es una queja: son situaciones que `abl` no tiene, así que
                # el cartucho de prueba decidió solo y eso no se versiona. Se
                # imprime porque dice cuánto se parece la tanda al juego.
                print("  y %d que sólo existe(n) por la tanda, "
                      "que deciden solos: %s"
                      % (len(mios), ", ".join(str(m) for m in sorted(mios))))
        return
    if len(builds) != 1:
        sys.exit("lo versionado es lo que decide **un** ROM, el jugable: "
                 "pasame `rom/build/release` y no %d cartuchos" % len(builds))
    for clase in CLASES:
        _copiar(raiz, builds[0], clase)


def _tiene_parches(build):
    return any(os.path.isdir(os.path.join(build, c.directorio))
               for c in CLASES)


def _copiar(raiz, build, clase):
    """Lo que decidió el ROM jugable, a `parches/`, y afuera lo que ya no está."""
    destino = os.path.join(raiz, clase.directorio)
    os.makedirs(destino, exist_ok=True)
    carpeta = os.path.join(build, clase.directorio)
    vistos, bytes_ = set(), 0
    prueba = mapas_de_prueba()
    for nombre in sorted(os.listdir(carpeta) if os.path.isdir(carpeta) else []):
        if not nombre.endswith(".toml"):
            continue
        # Lo que el ROM jugable lleva sólo por la tanda no se versiona: ver
        # `de_prueba`.
        if de_prueba(build, clase, _leer(os.path.join(carpeta, nombre))[
                clase.clave], prueba):
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
            print("  %s: el juego ya no lo lleva, lo saco"
                  % os.path.join(clase.directorio, nombre))
    print("%d parche(s) en %s, %d B" % (len(vistos), clase.directorio, bytes_))


if __name__ == "__main__":
    main()
