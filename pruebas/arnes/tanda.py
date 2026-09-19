"""El arnés de la tanda de regresión, contra las capturas congeladas.

Lo que hasta el 2026-09-16 era una receta de `just` por caso, en cinco procesos
—convertir, ensamblar, correr la referencia, correr el emulador, comparar— acá
es una llamada: `partida(caso)` busca el caso en los cartuchos de prueba y lo
corre. Y lo que se compara ya no es una referencia de Python sino el PNG
congelado de `pruebas/golden/tanda/`, que **es una captura del emulador** y por
eso se compara en cero pixeles exactos, sin máscara; el porqué está en el
`LEEME.md` de ese directorio.

**Acá no se arma nada.** Los cartuchos los arma `pruebas/arnes/cartuchos.py`, una
vez, antes de la tanda —`just pruebas` lo corre primero—, y el arnés sólo sabe
buscar un caso por su nombre y decir en qué cartucho y en qué página está. Si
el cartucho es de otros fuentes, se niega a correr: ver `Cartucho`.

Tres cosas que este archivo hace y conviene tener a la vista:

* **El plan sale del congelado, no de la referencia.** Los 16 `plan-*.txt`
  dicen, por dirección, cuántas celdas camina el héroe y cuántos ticks duraba la
  caminata; lo segundo es lo que dice cuánto correr el emulador. Los escribió la
  referencia cuando existía, y por eso están congelados: son lo último que queda
  de ella, y lo que hizo que un caso de caminata dejara de necesitarla.
* **El grupo es el 11 y no el 10.** Es el default de `grupo` en el justfile y no
  el del juego de verdad, y lo arma la página de prueba: `grupo-11`, o
  `grupo-11-en-<mapa>` para el mismo grupo en otro lugar. Con el 10 el líder
  es otro, el sprite es otro, y las goldens no dan.
* **El arranque de `Partida` es el mismo `--arranque 115` del corredor**:
  `BOOT_CUADROS` (112) más tres, y de ahí en más los dos cuentan ticks de
  `vueltas` con la misma convención —el cuadro N de la referencia es el tick
  N+1— y aprietan A un tick antes por `RETRASO_DE_PANTALLA`. O sea que para un
  caso de caminata con toques de A, `Partida.correr` **es** el lazo de
  `snes_correr.py`; no hay una segunda convención que mantener.
"""

import os
import sys

from consola import (NUCLEO, RAIZ, RETRASO_DE_PANTALLA, Partida, Simbolos,
                     mapas_de, toques_de)

sys.path.insert(0, os.path.join(RAIZ, "tools"))

import retro                                             # noqa: E402

import cartuchos                                         # noqa: E402

# Dónde viven las capturas congeladas y los planes.
GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "golden",
                      "tanda")


class Cartucho:
    """Uno de los cartuchos que dejó `pruebas/arnes/cartuchos.py`, ya leído.

    **Se niega a servir uno viejo.** Si los fuentes, las herramientas o los
    casos cambiaron desde que se armó, la tanda correría contra una ROM que
    no es la del árbol y daría verde o rojo por algo que ya no existe; así que
    dice qué correr y corta. Es la misma cuenta con que `cartuchos.py` decide
    si rearmar, así que los dos no pueden estar en desacuerdo.
    """

    def __init__(self, nombre):
        self.nombre = nombre
        self.dir = os.path.join(cartuchos.DESTINO, nombre)
        self.sfc = os.path.join(self.dir, "prueba.sfc")
        viejo = cartuchos.viejo(nombre)
        if viejo:
            raise AssertionError(
                "el cartucho de prueba %r %s. Las pruebas no arman nada: "
                "corré `just cartuchos` —o `just pruebas`, que lo corre "
                "primero—." % (nombre, viejo))
        self.simbolos = Simbolos(self.sfc + ".sym")
        self.mapas = mapas_de(os.path.join(self.dir, "mapdata.inc"))
        self.casos, self.saltan = cartuchos.manifiesto(nombre)


_CARGADOS = {}


def cartucho(nombre=cartuchos.PRUEBAS):
    """El cartucho `nombre`, leído una vez por corrida."""
    if nombre not in _CARGADOS:
        _CARGADOS[nombre] = Cartucho(nombre)
    return _CARGADOS[nombre]


def rom(caso, en=None):
    """(el cartucho, la página) donde está el caso.

    Sin `en`, el cartucho de pruebas si lo lleva, y si no el único que lo
    lleve: los chicos existen por lo que no entra en el grande, y cada caso
    vive en uno. Un caso que está en dos —los del cartucho del juego, que
    repite algunos a propósito— se pide con `en`.
    """
    nombres = [en] if en else cartuchos.donde_esta(caso)
    if not nombres:
        raise AssertionError(
            "ningún cartucho de prueba lleva el caso %r: ¿existe "
            "pruebas/casos/%s.json?" % (caso, caso))
    uno = cartucho(nombres[0])
    if caso not in uno.casos:
        raise AssertionError("el cartucho %r no lleva el caso %r"
                             % (uno.nombre, caso))
    return uno, uno.casos.index(caso)


def partida(caso, nucleo=None, en=None, switches=(), titulo=None):
    """El caso corriendo, con el arranque ya pasado y, si empieza con un
    `Teleport`, con la llegada ya esperada.

    Una consola nueva por captura, igual que el corredor: arrancar de cero es
    parte de lo que se compara, y reusarla traería el estado de la corrida
    anterior.

    `nucleo` pisa el core; lo usa `test_cores.py`, que corre la misma partida
    en snes9x y en bsnes. `en` elige el cartucho: ver `rom`.
    """
    uno, k = rom(caso, en)
    return Partida(uno.sfc, uno.simbolos, uno.mapas, switches=switches,
                   titulo=titulo, nucleo=nucleo, caso=k, salta=uno.saltan[k])


def consola_cruda(caso, en=None):
    """La ROM con el arranque pasado y **sin reloj de juego**.

    Es el `--sin-contador` del corredor: hace falta donde `vueltas` no avanza
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
    return partida(caso, en=en).consola


def encender(en, cuadros):
    """La ROM del cartucho `en`, recién encendida y con `cuadros` corridos.

    Sin caso y sin arranque: es para lo que se mira antes de que haya juego
    —la pantalla de título—, donde el arranque de `Partida` todavía no
    terminó. Corre la página 0, la de siempre.
    """
    consola = retro.Consola(cartucho(en).sfc, NUCLEO)
    consola.correr(cuadros)
    return consola


def plan(nombre):
    """El plan congelado: por dirección, cuántos ticks dura la caminata.

    El archivo lleva `<dirección> <celdas> <ticks>` por línea. Las celdas no se
    usan acá —son el dato que hacía falta para leer el plan con los ojos— y los
    ticks son lo que se corre.

    El margen que el corredor suma sobre el plan es **cero** en los casos que
    lo usan, así que acá no hay margen: el plan dice el número exacto.
    """
    ticks = {}
    with open(os.path.join(GOLDEN, "plan-%s.txt" % nombre)) as archivo:
        for linea in archivo:
            if linea.split():
                direccion, _celdas, cuadros = linea.split()
                ticks[direccion] = int(cuadros)
    return ticks


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
    está copiado a propósito de `snes_correr.py`: con `--sin-contador` el
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
        consola.apretar(*(sosteniendo + por_tick.get(corridos + 1, ())
                          + por_hardware.get(corridos, ())))
        consola.correr(1)
    return consola


def correr_ticks(consola, simbolos, ticks, sosteniendo=()):
    """El lazo de ticks de `Reloj.avanzar`, sobre una consola sin `Partida`.

    Hace falta para el único par de casos que arranca en el cuadro **cero**:
    la ROM con pantalla de título contra la misma sin ella. Ahí no se puede
    pasar un arranque fijo —la mitad del arranque es el título— así que el
    reloj se lee desde el primer cuadro. `Reloj` corre uno antes de mirar,
    porque con cero cuadros corridos la WRAM es todavía la basura con que el
    emulador enciende y el contador leería 21845.
    """
    consola.correr(1)
    sosteniendo = tuple(sosteniendo)
    if sosteniendo:
        consola.apretar(*sosteniendo)
    direccion = simbolos["vueltas"]
    tope = (ticks + 2) * 240
    while True:
        bajo, alto = consola.ram(direccion, 2)
        if (bajo | (alto << 8)) - 1 >= ticks:
            return consola
        consola.correr(1)
        tope -= 1
        if tope <= 0:
            raise RuntimeError("la ROM no llegó al tick %d" % ticks)


def quince_bits(imagen):
    """La imagen a 15 bits, que es lo que la consola puede mostrar."""
    return [(r >> 3, g >> 3, b >> 3)
            for r, g, b in imagen.convert("RGB").get_flattened_data()]


def golden(nombre, imagen):
    """La captura contra su congelada, y tienen que ser **idénticas**.

    Cero pixeles, sin máscara: las dos son capturas del mismo emulador, así que
    el descarte de sprites del PPU es el mismo de los dos lados. Ver el
    `LEEME.md` del congelado.

    Cuando difieren, la captura queda en `rom/build/tanda/rojo/` para poder
    mirarla al lado de la golden. **No se pisa la golden**: cambiarla es un acto
    deliberado y va a git con su porqué.
    """
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
    if actual.tobytes() != esperada.tobytes():
        distintos = sum(1 for a, b in zip(actual.getdata(), esperada.getdata())
                        if a != b)
        rojo = os.path.join(RAIZ, "rom", "build", "tanda", "rojo")
        os.makedirs(rojo, exist_ok=True)
        donde = os.path.join(rojo, "%s.png" % nombre)
        actual.save(donde)
        total = esperada.size[0] * esperada.size[1]
        raise AssertionError(
            "%r difiere de su golden en %d de %d pixeles (%.2f%%). La captura "
            "quedó en %s y la golden es %s. Si el cambio es a propósito, "
            "mirala y reemplazá la golden; si no, la ROM cambió lo que dibuja."
            % (nombre, distintos, total, 100.0 * distintos / total, donde,
               ruta))
