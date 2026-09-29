"""El arnés de la tanda de regresión, contra las capturas congeladas.

`partida(caso)` busca el caso en los cartuchos de prueba y lo corre, y `golden`
compara la pantalla contra el PNG congelado de `pruebas/golden/tanda/`, que **es
una captura del emulador** y por eso se compara en cero pixeles exactos, sin
máscara; el porqué está en el `LEEME.md` de ese directorio.

**Acá no se arma nada.** Los cartuchos los arma `tools/assembly/cartridges.py`, una
vez, antes de la tanda —`just pruebas` lo corre primero—, y el arnés sólo sabe
buscar un caso por su nombre y decir en qué cartucho y en qué página está. Si
el cartucho es de otros fuentes, se niega a correr: ver `Cartucho`.

Tres cosas que este archivo hace y conviene tener a la vista:

* **El plan está congelado.** Los `plan-*.txt` dicen, por dirección, cuántas
  celdas camina el héroe y cuántos ticks duraba la caminata; lo segundo es lo
  que dice cuánto correr el emulador. Los escribió la referencia de Python que
  hubo hasta el 2026-09-16, y por eso no se regeneran: no queda nada que los
  sepa calcular.
* **El grupo es el 11 y no el 10.** Es el del banco de pruebas y no el del
  juego de verdad, y lo arma la página de prueba: `grupo-11`, o
  `grupo-11-en-<mapa>` para el mismo grupo en otro lugar. Con el 10 el líder
  es otro, el sprite es otro, y las goldens no dan.
* **El arranque de `Partida` es el `--arranque 115` del corredor**, que era
  `tools/snes_correr.py` y es con lo que se sacaron las goldens: `BOOT_FRAMES`
  más tres, y de ahí en más se cuentan ticks de `ticks` con la misma
  convención —el cuadro N de aquella referencia es el tick N+1— y se aprieta A un
  tick antes por `RETRASO_DE_PANTALLA`. O sea que para un caso de caminata con
  toques de A, `Partida.correr` **es** el lazo de aquel corredor, y por eso las
  goldens que sacó siguen valiendo. El corredor se borró el 2026-09-19; cuando
  este archivo o una prueba lo nombran, es para decir qué convención copian.
"""

import os

from consola import (EMPEZAR, NUCLEO, RETRASO_DE_PANTALLA, Partida,
                     Simbolos, en_la_rom, mapas_de, marcar_la_pila, toques_de)

from emulator import retro

import lugares
from assembly import cartridges

# Dónde viven las capturas congeladas y los planes.
GOLDEN = os.path.join(lugares.GOLDENS, "tanda")


class Cartucho:
    """Uno de los cartuchos que dejó `tools/assembly/cartridges.py`, ya leído.

    **Se niega a servir uno viejo.** Si los fuentes, las herramientas o los
    casos cambiaron desde que se armó, la tanda correría contra una ROM que
    no es la del árbol y daría verde o rojo por algo que ya no existe; así que
    dice qué correr y corta. Es la misma cuenta con que `cartridges.py` decide
    si rearmar, así que los dos no pueden estar en desacuerdo.
    """

    def __init__(self, nombre):
        self.nombre = nombre
        self.dir = cartridges.directory(nombre)
        self.sfc = cartridges.rom_of(nombre)
        viejo = cartridges.stale(nombre)
        if viejo:
            raise AssertionError(
                "el cartucho de prueba %r %s. Las pruebas no arman nada: "
                "corré `just cartuchos` —o `just pruebas`, que lo corre "
                "primero—." % (nombre, viejo))
        self.simbolos = Simbolos(self.sfc + ".sym")
        self.mapas = mapas_de(os.path.join(self.dir, "mapdata.inc"))
        self.casos, self.saltan = cartridges.manifest(nombre)
        # Lo que se elige en la pantalla de título si nadie pide otra cosa:
        # "Begin the Story", que en la ROM que se juega es por donde se entra
        # a cualquier caso. None si el cartucho no tiene título.
        self.titulo = (None if cartridges.without_title(nombre) else EMPEZAR)


# El mapa 2 solo: el Linkage Block entero. Sus dos cuartos parecen dos mapas
# jugando pero son el mismo, y se cruzan con teletransportes internos. Ver
# `test_puerta_misma.py`. Lo usan también las peleas contra el droide.
LINKAGE = "en-2"


_CARGADOS = {}


def cartucho(nombre=cartridges.RELEASE):
    """El cartucho `nombre`, leído una vez por corrida."""
    if nombre not in _CARGADOS:
        _CARGADOS[nombre] = Cartucho(nombre)
    return _CARGADOS[nombre]


def rom(caso, en=None):
    """(el cartucho, la página) donde está el caso.

    Sin `en`, `release` si lo lleva, y si no el único que lo lleve: los chicos
    existen por lo que no entra en el grande, y cada caso vive en uno. Un caso
    que está en dos se pide con `en`.
    """
    nombres = [en] if en else cartridges.where_is(caso)
    if not nombres:
        raise AssertionError(
            "ningún cartucho de prueba lleva el caso %r: ¿existe "
            "pruebas/casos/%s.json?" % (caso, caso))
    uno = cartucho(nombres[0])
    if caso not in uno.casos:
        raise AssertionError("el cartucho %r no lleva el caso %r"
                             % (uno.nombre, caso))
    return uno, uno.casos.index(caso)


def partida(caso, nucleo=None, en=None, switches=(), titulo=None, pila=False,
            msu=False):
    """El caso corriendo, con el arranque ya pasado y, si empieza con un
    `Teleport`, con la llegada ya esperada.

    Una consola nueva por captura, igual que el corredor: arrancar de cero es
    parte de lo que se compara, y reusarla traería el estado de la corrida
    anterior.

    `nucleo` pisa el core; lo usa `test_cores.py`, que corre la misma partida
    en snes9x y en bsnes. `en` elige el cartucho: ver `rom`. `pila` marca la
    zona de la pila antes del primer cuadro, y lo usa una sola prueba: ver
    `consola.marcar_la_pila`. `msu` deja sonar las pistas de MSU-1: lo pide
    sólo `video.py`, ver `Partida`.

    En un cartucho con pantalla de título, `titulo` dice qué se elige ahí, y
    sin él es "Begin the Story": el caso se elige después, como al encender
    uno sin título. Medido al juntar `release` con `test-main`: pasar por el
    título no mueve ninguna golden.
    """
    if caso is None and (en or cartridges.RELEASE) == cartridges.RELEASE:
        # Sin caso, en `release`: la partida de verdad **sin el mapa de
        # debug**, `REAL_GAME`, que es la página 0 de la entrega
        # limpia. Con el mapa, la página 0 lleva a él —ver `FIRST_CASE` en
        # cartridges.py— y esto la elige por su número, como a cualquier caso:
        # así las pruebas que juegan desde el título siguen mirando el
        # arranque del juego, con la misma ROM que se entrega. Pasar por la
        # puerta del comienzo normal no daría lo mismo: llegar al 4 con un
        # `Teleport` corre la rampa del fundido y el tinte —ver
        # `CINEMATICAS` en test_escenas_golden.py—. La puerta la cruza el
        # recorrido de la apertura.
        uno, k = rom(cartridges.REAL_GAME, en)
        salta = uno.saltan[k]
    elif caso is None:
        # Sin caso, en otro cartucho: la ROM como arranca, la página 0.
        uno, k, salta = cartucho(en), 0, False
    else:
        uno, k = rom(caso, en)
        salta = uno.saltan[k]
    if titulo is None:
        titulo = uno.titulo
    return Partida(uno.sfc, uno.simbolos, uno.mapas, switches=switches,
                   titulo=titulo, nucleo=nucleo, caso=k, salta=salta,
                   pila=pila, msu=msu)


def consola_cruda(caso, en=None, pila=False):
    """La ROM con el arranque pasado y **sin reloj de juego**.

    Es el `--sin-contador` del corredor: hace falta donde `ticks` no avanza
    —la pantalla de ranuras, el menú de pausa, la de batalla—, que no son el
    juego. Ahí un `Partida.correr` no termina nunca, porque espera un tick que
    no va a llegar.

    Es la consola de una `Partida` recién arrancada, que ya eligió su caso y
    esperó la llegada si salta: los cuadros de hardware que siguen se cuentan
    desde ahí, igual que los contaba el corredor desde el arranque de un
    cartucho que empezaba en ese mapa. No devuelve la `Partida` a propósito:
    `Partida` *es* el reloj de ticks, y una que no pueda contarlos sería una
    que miente sobre lo que sabe.
    """
    return partida(caso, en=en, pila=pila).consola


def encender(en, cuadros, pila=False):
    """La ROM del cartucho `en`, recién encendida y con `cuadros` corridos.

    Sin caso y sin arranque: es para lo que se mira antes de que haya juego
    —la pantalla de título—, donde el arranque de `Partida` todavía no
    terminó. Corre la página 0, la de siempre.
    """
    consola = retro.Console(cartucho(en).sfc, NUCLEO)
    if pila:
        marcar_la_pila(consola)
    consola.run(cuadros)
    return consola


def cuadro_de_texto(cartucho, renglon):
    """Dónde cayó, en el cartucho, el cuadro de texto que dice ese renglón.

    Devuelve `(desplazamiento, byte del archivo, largo)`: el desplazamiento es
    en bytes desde el principio del bloque —el operando de `OP_MESSAGE` es eso
    dividido `events.MESSAGES_STEP`—, y el byte del archivo es dónde arranca
    el cuadro adentro del
    `.sfc`. Con los dos se puede preguntar lo que ninguna golden ve: si el
    cuadro cruza un borde de banco, y si su desplazamiento pasa de los 16 bits
    del operando. Ver `test_texto`.

    Se lee del cartucho y no del conversor a propósito: lo que la prueba
    quiere saber es dónde quedó el cuadro **en la ROM que se corre**, y el
    `.sym` más los bytes son las dos cosas que la ROM misma usa.

    El bloque se recorre desde el principio, cuadro por cuadro, con el formato
    que emite `events.message_bytes` y que lee `msg_start`: un byte de
    cabecera con los renglones en los tres bits de abajo, y cada renglón con
    su largo delante. Cada cuadro arranca en un múltiplo del paso, así que
    entre uno y otro puede haber relleno, y se saltea. Se para al primer byte
    que no puede ser una cabecera, que es lo que hay detrás del último cuadro.
    """
    from port.events import MESSAGES_STEP
    base = cartucho.simbolos["messages"]
    archivo = en_la_rom(base)
    with open(cartucho.sfc, "rb") as sfc:
        datos = sfc.read()
    encontrados, desplazamiento = [], 0
    while desplazamiento < 0x10000 * MESSAGES_STEP:
        cabecera = datos[archivo + desplazamiento]
        cuantos, largo = cabecera & 0x07, 1
        if not 1 <= cuantos <= 4:
            break
        renglones = []
        for _ in range(cuantos):
            cuenta = datos[archivo + desplazamiento + largo]
            largo += 1
            renglones.append("".join(
                chr(b + 32) for b in
                datos[archivo + desplazamiento + largo:
                      archivo + desplazamiento + largo + cuenta]))
            largo += cuenta
        if renglon in renglones:
            encontrados.append((desplazamiento,
                                archivo + desplazamiento, largo))
        desplazamiento += largo
        desplazamiento += -desplazamiento % MESSAGES_STEP
    assert len(encontrados) == 1, (
        "el bloque de textos del cartucho %r tiene %d cuadros con el renglón "
        "%r y la prueba necesita uno solo para saber de cuál habla"
        % (cartucho.nombre, len(encontrados), renglon))
    return encontrados[0]


def plan(nombre):
    """El plan congelado: por dirección, cuántos ticks dura la caminata.

    El archivo lleva `<dirección> <celdas> <ticks>` por línea. Los ticks son
    lo que se corre; las celdas, lo que tiene que haber caminado: ver
    `celdas_del_plan`.

    El margen que el corredor suma sobre el plan es **cero** en los casos que
    lo usan, así que acá no hay margen: el plan dice el número exacto.
    """
    return {direccion: ticks
            for direccion, (_celdas, ticks) in _plan(nombre).items()}


def celdas_del_plan(nombre):
    """El plan congelado: por dirección, cuántas celdas camina el héroe.

    Es lo que dice si una caminata caminó: `varios-18-down` fotografió
    durante días lo mismo que `varios-18-none` —una página automática no
    dejaba moverse al héroe— y la golden lo defendía, porque había congelado
    eso.
    """
    return {direccion: celdas
            for direccion, (celdas, _ticks) in _plan(nombre).items()}


def _plan(nombre):
    lineas = {}
    with open(os.path.join(GOLDEN, "plan-%s.txt" % nombre)) as archivo:
        for linea in archivo:
            if linea.split():
                direccion, celdas, cuadros = linea.split()
                lineas[direccion] = (int(celdas), int(cuadros))
    return lineas


def ticks_de_avance(pixeles):
    """En qué tick el héroe lleva andados `pixeles`, que es el `--avance`.

    El héroe se mueve `WALK_SPEED` = 2 pixeles por tick, y el cuadro que se ve
    muestra el estado de la vuelta anterior —`RETRASO_DE_PANTALLA`—, así que
    para verlo con N pixeles andados hay que correr N/2 + 1 ticks desde que se
    aprieta. No es una holgura: errarle por un cuadro para cualquier lado da
    unos 25.000 pixeles de diferencia, medido en el mapa 73.
    """
    return pixeles // 2 + RETRASO_DE_PANTALLA


def correr_hardware(consola, cuantos, toques=(), toques_hardware=(),
                    sosteniendo=()):
    """`cuantos` cuadros de hardware, con los toques que se le digan.

    Los dos diccionarios de toques **cuentan con un cuadro de diferencia**, y
    está copiado a propósito del corredor: con `--sin-contador` el
    corredor pone su reloj a contar cuadros, así que `--toques` cae en el
    cuadro `n-1` —el lazo pregunta por `cuadro() + 1`— y `--toques-hardware` en
    el `n`, porque ése lee `reloj.corridos` directo. Dos flags que parecen el
    mismo y no lo son.

    Medido: **ninguna golden distingue los dos**, o sea que hoy se podrían
    unificar sin que nada se ponga rojo. Se deja igual porque lo que congela
    una golden es la salida y no la convención, y un caso nuevo que caiga justo
    en el borde sí las distinguiría.
    """
    por_tick = toques_de(toques, "toques")
    por_hardware = toques_de(toques_hardware, "toques_hardware")
    sosteniendo = tuple(sosteniendo)
    for corridos in range(cuantos):
        consola.hold(*(sosteniendo + por_tick.get(corridos + 1, ())
                       + por_hardware.get(corridos, ())))
        consola.run(1)
    return consola


def quince_bits(imagen):
    """La imagen a 15 bits, que es lo que la consola puede mostrar."""
    return [(r >> 3, g >> 3, b >> 3)
            for r, g, b in imagen.convert("RGB").get_flattened_data()]


# Las goldens que dieron verde en la prueba en curso, con un hash de sus
# pixeles. La vacía y la mira `conftest._capturas_distintas`.
CAPTURAS = []


def golden(nombre, imagen):
    """La captura contra su congelada, y tienen que ser **idénticas**.

    Cero pixeles, sin máscara: las dos son capturas del mismo emulador, así que
    el descarte de sprites del PPU es el mismo de los dos lados. Ver el
    `LEEME.md` del congelado.

    Cuando difieren, la captura queda en `pruebas/snapshots/tanda/`, con el
    mismo nombre que su golden en `pruebas/golden/tanda/`, para poder mirarlas
    lado a lado. **No se pisa la golden**: cambiarla es un acto deliberado y
    va a git con su porqué. Y cuando coinciden, se borra la captura que haya
    quedado de una corrida anterior: así ese directorio tiene sólo lo que está
    en rojo ahora, y no lo que estuvo alguna vez.
    """
    rojo = os.path.join(lugares.SNAPSHOTS, "tanda")
    donde = os.path.join(rojo, "%s.png" % nombre)
    ruta = os.path.join(GOLDEN, "%s.png" % nombre)
    if not os.path.exists(ruta):
        raise AssertionError("no hay golden para %r: %s" % (nombre, ruta))
    from PIL import Image
    esperada = Image.open(ruta).convert("RGB")
    actual = imagen.convert("RGB")
    if esperada.size != actual.size:
        raise AssertionError("%r mide %s y su golden %s"
                             % (nombre, actual.size, esperada.size))
    # El caso verde se contesta con los bytes crudos, que es una comparación y
    # no 57.344; contar cuántos difieren sólo hace falta para el mensaje.
    if actual.tobytes() == esperada.tobytes():
        CAPTURAS.append((nombre, hash(esperada.tobytes())))
        if os.path.exists(donde):
            os.remove(donde)
    else:
        distintos = sum(1 for a, b in zip(actual.getdata(), esperada.getdata())
                        if a != b)
        os.makedirs(rojo, exist_ok=True)
        actual.save(donde)
        total = esperada.size[0] * esperada.size[1]
        raise AssertionError(
            "%r difiere de su golden en %d de %d pixeles (%.2f%%). La captura "
            "quedó en %s y la golden es %s. Si el cambio es a propósito, "
            "mirala y reemplazá la golden; si no, la ROM cambió lo que dibuja."
            % (nombre, distintos, total, 100.0 * distintos / total, donde,
               ruta))
