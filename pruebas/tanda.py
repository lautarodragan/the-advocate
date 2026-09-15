"""El arnés de `rom/hitos.txt` adentro de pytest, contra las capturas congeladas.

Lo que hoy hace una receta de `just` en cinco procesos —convertir, ensamblar,
correr la referencia, correr el emulador, comparar— acá son dos llamadas:
`cartucho()` arma la ROM y `Partida` la corre. Lo que se compara no es la
referencia de Python sino el PNG congelado de `pruebas/golden/tanda/`, que **es
una captura del emulador** y por eso se compara en cero pixeles exactos, sin
máscara; el porqué está en el `LEEME.md` de ese directorio.

Tres cosas que este archivo hace y conviene tener a la vista:

* **El plan sale del congelado, no de la referencia.** Los 16 `plan-*.txt`
  dicen, por dirección, cuántas celdas camina el héroe y cuántos ticks vive la
  referencia; lo segundo es lo que dice cuánto correr el emulador. Con eso, un
  caso de caminata deja de necesitar que `snes_expect.py` corra antes.
* **El grupo es el 11 y no el 10.** Es el default de `grupo` en el justfile y no
  el de `consola.GRUPO`, que es el del juego de verdad. Con el 10 el líder es
  otro, el sprite es otro, y las goldens no dan.
* **El arranque de `Partida` es el mismo `--arranque 115` del corredor**:
  `BOOT_CUADROS` (112) más tres, y de ahí en más los dos cuentan ticks de
  `vueltas` con la misma convención —el cuadro N de la referencia es el tick
  N+1— y aprietan A un tick antes por `RETRASO_DE_PANTALLA`. O sea que para un
  caso de caminata con toques de A, `Partida.correr` **es** el lazo de
  `snes_correr.py`; no hay una segunda convención que mantener.
"""

import os
import subprocess
import sys

from consola import RAIZ, Partida, Simbolos, huella, mapas_de

sys.path.insert(0, os.path.join(RAIZ, "tools"))

import w65_bin                                           # noqa: E402

# Dónde viven las capturas congeladas y los planes.
GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden",
                      "tanda")

# El mismo default que `grupo` en el justfile: ver arriba.
GRUPO = os.environ.get("GRUPO_TANDA", "11")


def cartucho(nombre, *flags, grupo=None):
    """Convierte y ensambla; devuelve (ROM, símbolos, ids de mapa en orden).

    Es `consola.armar()` con los flags del conversor a la vista en vez de un
    parámetro por flag: los 47 casos de la tanda usan **cuarenta y un** flags
    distintos, y una firma con cuarenta y un argumentos opcionales es la misma
    lista escrita dos veces. Acá el caso dice exactamente lo que dice su receta.

    `grupo` es el único que no va como flag suelto, porque hay una receta que lo
    pisa: `batalla` lleva tres actores en pantalla y las demás uno.

    Se saltea si ya está hecha y no cambió nada de lo que la arma: la clave es
    `huella()` —los fuentes de la ROM, el ensamblador y las herramientas— más
    los flags. `nombre` es sólo para poder mirar el directorio; lo que decide
    si sirve es el sello.

    **Cada cartucho en su propio directorio**, y por eso `mapdata.inc` deja de
    ser estado global: dos casos con mapas distintos no se pisan, que es la
    trampa que `AGENTS.md` nombra.
    """
    destino = os.path.join(RAIZ, "rom", "build", "tanda", nombre)
    os.makedirs(destino, exist_ok=True)
    inc = os.path.join(destino, "mapdata.inc")
    sfc = os.path.join(destino, "prueba.sfc")
    sello = os.path.join(destino, "huella.txt")
    grupo = (grupo or GRUPO).split()
    actual = huella() + "\n" + repr(("--grupo", tuple(grupo)) + flags)

    if os.path.exists(sfc) and os.path.exists(inc):
        try:
            with open(sello) as archivo:
                if archivo.read().strip() == actual:
                    return sfc, Simbolos(sfc + ".sym"), mapas_de(inc)
        except OSError:
            pass

    convertir = ([sys.executable, os.path.join(RAIZ, "tools",
                                               "snes_convert.py"),
                  "--grupo"] + grupo + [str(f) for f in flags]
                 + ["-o", inc])
    subprocess.run(convertir, check=True, capture_output=True, cwd=RAIZ)
    subprocess.run([w65_bin.binario(),
                    os.path.join(RAIZ, "rom", "src", "main.s"),
                    "-I", destino, "-o", sfc, "--symbols", sfc + ".sym"],
                   check=True, capture_output=True, cwd=RAIZ)
    with open(sello, "w") as archivo:
        archivo.write(actual)
    return sfc, Simbolos(sfc + ".sym"), mapas_de(inc)


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


def partida(sfc, simbolos, mapas):
    """La ROM con el arranque ya pasado, lista para correr ticks.

    Una consola nueva por captura, igual que el corredor: arrancar de cero es
    parte de lo que se compara, y reusarla traería el estado de la corrida
    anterior.
    """
    return Partida(sfc, simbolos, mapas)


def cuadros_de_hardware(p, cuantos):
    """`cuantos` cuadros de hardware, sin mirar el reloj del juego.

    Es el `--sin-contador` del corredor, y hace falta donde `vueltas` no
    avanza: adentro de la pantalla de batalla y en la de título, que no son el
    juego. Un `Partida.correr` ahí no termina nunca, porque espera un tick que
    no va a llegar.
    """
    p.consola.apretar()
    p.consola.correr(cuantos)
    return p


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
