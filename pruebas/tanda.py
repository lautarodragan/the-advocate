"""El arnés de la tanda de regresión, contra las capturas congeladas.

Lo que hasta el 2026-09-16 era una receta de `just` por caso, en cinco procesos
—convertir, ensamblar, correr la referencia, correr el emulador, comparar— acá
son dos llamadas: `cartucho()` arma la ROM y `Partida` la corre. Y lo que se
compara ya no es una referencia de Python sino el PNG congelado de
`pruebas/golden/tanda/`, que **es una captura del emulador** y por eso se compara
en cero pixeles exactos, sin máscara; el porqué está en el `LEEME.md` de ese
directorio.

Tres cosas que este archivo hace y conviene tener a la vista:

* **El plan sale del congelado, no de la referencia.** Los 16 `plan-*.txt`
  dicen, por dirección, cuántas celdas camina el héroe y cuántos ticks duraba la
  caminata; lo segundo es lo que dice cuánto correr el emulador. Los escribió la
  referencia cuando existía, y por eso están congelados: son lo último que queda
  de ella, y lo que hizo que un caso de caminata dejara de necesitarla.
* **El grupo es el 11 y no el 10.** Es el default de `grupo` en el justfile y no
  el del juego de verdad, y lo arma la página de prueba: el caso por omisión de
  `cartucho` es `grupo-11`, y cada caso propio trae el suyo. Con el 10 el líder
  es otro, el sprite es otro, y las goldens no dan.
* **El arranque de `Partida` es el mismo `--arranque 115` del corredor**:
  `BOOT_CUADROS` (112) más tres, y de ahí en más los dos cuentan ticks de
  `vueltas` con la misma convención —el cuadro N de la referencia es el tick
  N+1— y aprietan A un tick antes por `RETRASO_DE_PANTALLA`. O sea que para un
  caso de caminata con toques de A, `Partida.correr` **es** el lazo de
  `snes_correr.py`; no hay una segunda convención que mantener.
"""

import glob
import hashlib
import os
import subprocess
import sys

from consola import (NUCLEO, RAIZ, RETRASO_DE_PANTALLA, Partida, Simbolos,
                     flags_de_casos, huella, mapas_de, toques_de)

sys.path.insert(0, os.path.join(RAIZ, "tools"))

import retro                                             # noqa: E402
import ensamblar                                         # noqa: E402
from snes_correr import ARRANQUE                         # noqa: E402

# Dónde viven las capturas congeladas y los planes.
GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden",
                      "tanda")

# El caso de los cartuchos que no traen uno propio: la página que arma el grupo
# con el 11, que es el default de `grupo` en el justfile. Ver arriba.
GRUPO_11 = "grupo-11"


def cartucho(nombre, *flags, caso=GRUPO_11):
    """Convierte y ensambla; devuelve (ROM, símbolos, ids de mapa en orden).

    Es `consola.armar()` con los flags del conversor a la vista en vez de un
    parámetro por flag: una firma con un argumento opcional por flag es la
    misma lista escrita dos veces. Lo que hace la página no va en flags sino
    en `caso`.

    `caso` es la página de prueba, por su nombre en `pruebas/casos/` —o una
    tupla de nombres, para un cartucho con varias—, y no va como flag suelto
    porque lo que importa de ella es el contenido, que entra en la clave. Arma
    también el grupo, así que un caso lleva el suyo; sin caso, el cartucho
    arranca con el del juego.

    Se saltea si ya está hecha y no cambió nada de lo que la arma: la clave es
    `huella()` —los fuentes de la ROM, el ensamblador y las herramientas— más
    los flags y lo que dice el caso.

    **Cada cartucho en su propio directorio**, y por eso `mapdata.inc` deja de
    ser estado global: dos casos con mapas distintos no se pisan, que es la
    trampa que `AGENTS.md` nombra.

    **Quién es "su propio" lo decide el hash de (caso, flags), no el nombre.**
    Con un directorio por caso son unos 5 MB por cartucho y ~170 casos, o sea
    casi un giga de ROMs casi iguales; con el hash, dos casos que arman
    exactamente la misma ROM comparten el build sin que nadie los empareje a
    mano. `nombre` queda de prefijo para poder mirar el directorio y saber de
    quién es, y el que gana es el primero que lo pida: lo que identifica al
    directorio es lo que viene después del guión.

    Lo que **no** entra en el hash es `huella()`, a propósito: si entrara,
    tocar un fuente de la ROM estrenaría un directorio por caso en vez de
    reusar el suyo, y el disco crecería con cada cambio. Va en el sello, que es
    lo que decide si lo que hay adentro sirve.
    """
    tanda = os.path.join(RAIZ, "rom", "build", "tanda")
    de_casos, contenido = flags_de_casos(caso)
    clave = hashlib.sha256(
        repr((contenido, flags)).encode()).hexdigest()[:12]
    existentes = glob.glob(os.path.join(tanda, "*-" + clave))
    destino = existentes[0] if existentes else os.path.join(
        tanda, "%s-%s" % (nombre, clave))
    os.makedirs(destino, exist_ok=True)
    inc = os.path.join(destino, "mapdata.inc")
    sfc = os.path.join(destino, "prueba.sfc")
    sello = os.path.join(destino, "huella.txt")
    actual = huella() + "\n" + repr((contenido, flags))
    SALTAN[sfc] = tuple(salta_al_empezar(texto) for _nombre, texto in contenido)

    if os.path.exists(sfc) and os.path.exists(inc):
        try:
            with open(sello) as archivo:
                if archivo.read().strip() == actual:
                    return sfc, Simbolos(sfc + ".sym"), mapas_de(inc)
        except OSError:
            pass

    # Los casos van al final: detrás de un `--caso`, cualquier flag del
    # cartucho sería de ese caso, y el conversor lo rechaza.
    convertir = ([sys.executable, os.path.join(RAIZ, "tools",
                                               "snes_convert.py"), "-o", inc]
                 + [str(f) for f in flags] + de_casos)
    subprocess.run(convertir, check=True, capture_output=True, cwd=RAIZ)
    # El mismo envoltorio que usan las recetas: `ca65` + `ld65`.
    ensamblar.ensamblar(os.path.join(RAIZ, "rom", "src", "main.s"),
                        destino, sfc, sfc + ".sym")
    with open(sello, "w") as archivo:
        archivo.write(actual)
    return sfc, Simbolos(sfc + ".sym"), mapas_de(inc)


# Qué casos de cada cartucho arrancan con un `Teleport`, por ruta de la ROM y
# en el orden de sus páginas. Lo llena `cartucho` y lo lee `partida`, que así
# sabe que tiene que esperar la llegada: ver `Partida._esperar_la_llegada`. Va
# aparte y no en lo que devuelve `cartucho` porque cada prueba desarma esa
# tupla, y agregarle un campo es tocarlas a todas para algo que casi ninguna
# mira.
SALTAN = {}


def salta_al_empezar(texto):
    """Si el caso —el JSON de su archivo— empieza con un `Teleport`."""
    import json
    comandos = json.loads(texto).get("event_commands") or [{}]
    return comandos[0].get("code") == "Teleport"


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


def partida(sfc, simbolos, mapas, nucleo=None, caso=0):
    """La ROM con el arranque ya pasado, lista para correr ticks.

    Una consola nueva por captura, igual que el corredor: arrancar de cero es
    parte de lo que se compara, y reusarla traería el estado de la corrida
    anterior.

    `nucleo` pisa el core; lo usa `test_cores.py`, que corre la misma partida
    en snes9x y en bsnes. `caso` elige la página de prueba en un cartucho que
    lleva varias: ver `--caso` en snes_convert.py.
    """
    saltan = SALTAN.get(sfc, ())
    return Partida(sfc, simbolos, mapas, nucleo=nucleo, caso=caso,
                   salta=caso < len(saltan) and saltan[caso])


def consola_cruda(sfc, arranque=ARRANQUE):
    """La ROM con el arranque pasado y **sin reloj de juego**.

    Es el `--sin-contador` del corredor: hace falta donde `vueltas` no avanza
    —la pantalla de título, la de ranuras, el menú de pausa, la de batalla—,
    que no son el juego. Ahí un `Partida.correr` no termina nunca, porque
    espera un tick que no va a llegar.

    No devuelve una `Partida` a propósito: `Partida` *es* el reloj de ticks, y
    una que no pueda contarlos sería una que miente sobre lo que sabe. Lo que
    se devuelve es la consola pelada, que es todo lo que estos casos usan.
    """
    consola = retro.Consola(sfc, NUCLEO)
    consola.correr(arranque)
    return consola


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
