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

Y el cartucho **no entra en la clave**: la regla es de taro, del 2026-09-21, y
dice que *la decisión versionada es siempre la del ROM jugable, `abl`*. Lo
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
nombre puesto. Medido el 2026-09-21: los tres cartuchos de prueba y `abl`
emiten los mismos 29 archivos byte por byte.

Y una cosa que el formato deja abierta a propósito. El rumbo es que qué mapas
entran, dónde arranca la ROM y con qué grupo dejen de ser argumentos sueltos de
una receta y pasen a ser **una descripción** que el que reparte paletas pueda
leer. Una clave que nombra la situación del juego —el mapa, y mañana el
gráfico o el tema— no le estorba: el día que exista, lo que cambia es de dónde
sale la lista de situaciones, no cómo se identifica cada una.

Lo que **todavía no está acá**, y es lo que queda para más adelante: las
paletas de los personajes —que sí dependen del cartucho, porque quién le paga
la entrada al cronómetro lo decide `npcs_dibujables` mirando el mapa entero—,
las voces que se caen de un MIDI, las muestras recortadas, las animaciones
dibujadas a otro tamaño y `DECORAR_TRANSLUCIDO`.
"""

import argparse
import collections
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


# --- las animaciones de batalla, que se dibujan a otro tamaño ---------------

# Igual que los mapas: versionadas acá, y cada cartucho deja las suyas al lado
# de su ROM. La clave es **el número de animación de RM2k**, que es del juego:
# el mismo 82 en cualquier cartucho que la muestre.
DIRECTORIO_ANIM = os.path.join("parches", "animaciones")
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
        "# --check` —y la tanda— fallan si quedó viejo. Ver tools/port/parches.py.",
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
    `<destino>/parches/animaciones/`.

    Devuelve cuántos archivos escribió y cuántos bytes ocupan.
    """
    carpeta = os.path.join(destino, EN_BUILD_ANIM)
    os.makedirs(carpeta, exist_ok=True)
    bytes_ = 0
    for datos in animaciones:
        contenido = texto_animacion(datos)
        with open(os.path.join(carpeta, "%04d.toml" % datos["animacion"]),
                  "w") as f:
            f.write(contenido)
        bytes_ += len(contenido.encode("utf-8"))
    return len(animaciones), bytes_


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
)


def versionados(raiz, clase=None):
    """Los que tienen parche versionado, o sea los del ROM jugable.

    Sin `clase`, los mapas: es lo que pedían los llamadores cuando ésta era la
    única clase que había.
    """
    carpeta = os.path.join(raiz, (clase or CLASES[0]).directorio)
    if not os.path.isdir(carpeta):
        return []
    return sorted(int(n[:-5]) for n in os.listdir(carpeta)
                  if n.endswith(".toml"))


def revisar(raiz, builds, jugable="abl"):
    """Los parches de los builds contra los versionados: (quejas, propios).

    `builds` son directorios de cartuchos armados, y se miran **todos**. Lo que
    no está versionado no es una queja: es una situación que `abl` no tiene
    —un mapa que no lleva, una animación que no muestra—, así que el cartucho
    de prueba decidió solo y eso no se versiona; sale en `propios`, que es
    información sobre cuánto se parecen los cartuchos al juego y no un error.

    Lo que **sí** está versionado se compara contra lo commiteado en cada
    cartucho que lo lleve. Para las dos clases de hoy eso no puede dar distinto
    —ni las fusiones de las capas ni el tamaño de una animación miran el
    cartucho— y por eso da queja: si diera, lo que se rompió es esa
    independencia, y conviene enterarse ahí y no en la fase 2.

    `propios` va por clase: `{"mapa": {7: ["chico"]}, ...}`, con la clave de
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
                if cartucho == jugable:
                    # Lo que el ROM jugable convierte **tiene** que estar
                    # versionado: si no, el juego pierde algo en algún lado y
                    # no queda escrito. En un cartucho de prueba, en cambio, es
                    # lo normal y no se dice nada.
                    quejas.append(
                        "%s %d entró en «%s», el ROM jugable, y no tiene "
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
                    "cambió de %s %d es esto:\n    %s\n"
                    "  Si el cambio es el que se buscaba, `just parches` y al "
                    "commit; si no, algo movió lo que se ve."
                    % (os.path.relpath(versionado, raiz), cartucho,
                       clase.articulo, cual, "\n    ".join(cambios)))
    for cual in sorted(tengo - vistos):
        quejas.append(
            "%s %d tiene parche versionado y ninguno de los cartuchos armados "
            "lo convierte: o el juego dejó de llevarlo —y entonces sobra el "
            "archivo— o falta armar el cartucho que lo tiene."
            % (clase.articulo, cual))
    return quejas, propios


def main(argv=None):
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "builds", nargs="+",
        help="los directorios de los cartuchos armados. Sin --check tiene que "
             "ser el del ROM jugable y nada más: lo versionado es lo que "
             "decide `abl`")
    parser.add_argument("--check", action="store_true",
                        help="no escribe: falla si lo versionado quedó viejo")
    args = parser.parse_args(argv)
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
                print("  y %d que sólo existe(n) en los cartuchos de prueba, "
                      "que deciden solos: %s"
                      % (len(mios), ", ".join(str(m) for m in sorted(mios))))
        return
    if len(builds) != 1:
        sys.exit("lo versionado es lo que decide **un** ROM, el jugable: "
                 "pasame `rom/build/abl` y no %d cartuchos" % len(builds))
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
    for nombre in sorted(os.listdir(carpeta) if os.path.isdir(carpeta) else []):
        if not nombre.endswith(".toml"):
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
