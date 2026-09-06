"""Una partida de la ROM corriendo, para hacerle preguntas sobre su estado.

Esto **no compara pixeles**. La tanda de `rom/hitos.txt` compara la pantalla
contra la referencia de Python, cuadro por cuadro; acá se le pregunta a la ROM
en qué mapa está, qué switch tiene prendido o qué evento está corriendo. Son
dos redes distintas y se complementan: la de pixeles dice "la pantalla es
exactamente ésta", ésta dice "y además llegaste adonde tenías que llegar".

Lo que hace posible preguntar es que `w65.py --simbolos` deja al lado de la ROM
la tabla de símbolos que sale del `main.s` de verdad, con las direcciones de la
RAM **y** las constantes del ensamblador:

    mapa_actual 90
    BOOT_CUADROS 112
    FLAG_AUTO 2

Por eso acá no hay ninguna dirección escrita a mano. Si alguien renombra una
variable en `main.s`, el test falla diciendo qué símbolo falta, que es
exactamente lo que se quiere: ruidoso y en el lugar. Una constante copiada a
mano se desfasaría en silencio y leería la dirección de al lado.
"""

import os
import re
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "tools"))

import retro                                            # noqa: E402
from snes_correr import RETRASO_DE_PANTALLA             # noqa: E402

# El mismo que usa el justfile por omisión. Se puede pisar con NUCLEO para
# correr las pruebas contra otro core.
NUCLEO = os.environ.get(
    "NUCLEO", "/usr/lib/libretro/snes9x_libretro.so")

# El grupo por omisión, igual que `grupo` en el justfile.
GRUPO = os.environ.get("GRUPO", "10")


class SimboloDesconocido(KeyError):
    """Se pidió un símbolo que la ROM no tiene."""


class Simbolos:
    """La tabla que deja `w65.py --simbolos`, leída por nombre."""

    def __init__(self, ruta):
        self.ruta = ruta
        with open(ruta) as archivo:
            self.tabla = dict(linea.split() for linea in archivo
                              if linea.strip())

    def __getitem__(self, nombre):
        try:
            return int(self.tabla[nombre])
        except KeyError:
            raise SimboloDesconocido(
                "la ROM no tiene el símbolo %r (mirá %s). Si lo renombraste en "
                "main.s, renombralo también acá: la tabla se genera del "
                "assembler, así que un nombre que no está es un nombre que ya "
                "no existe." % (nombre, self.ruta)) from None


class Partida:
    """La ROM corriendo, con el arranque ya pasado.

    `correr` avanza cuadros apretando A donde se le diga, con la misma
    convención que `snes_correr.py` —un toque por número, apretado un cuadro
    antes por `RETRASO_DE_PANTALLA`— para que una lista de toques sirva igual
    en un caso de pixeles y en una prueba de estado.
    """

    def __init__(self, sfc, simbolos, mapas):
        self.simbolos = simbolos
        # Los ids de mapa de RM2k en el orden de la tabla de la ROM, que es lo
        # que `mapa_actual` indexa. Sale del `mapdata.inc` generado y no de
        # rehacer la convención de "el de --map-id primero": ya está escrita
        # dos veces —conversor y referencia— y una tercera copia sería una
        # tercera manera de equivocarse igual en los tres lados.
        self.mapas = mapas
        self.consola = retro.Consola(sfc, NUCLEO)
        self.cuadro = 0
        # El arranque, que lo dice la ROM y no un número copiado: mientras
        # sube el banco de muestras a la ARAM el mapa está congelado.
        #
        # Y el contador **no** lo cuenta: los números de `apretar_a` se cuentan
        # desde el primer cuadro de juego, que es como los cuenta `--arranque`
        # en `snes_correr.py`. Contándolo, cada toque caía ciento quince
        # cuadros antes de tiempo y la escena no avanzaba.
        self.consola.correr(self.simbolos["BOOT_CUADROS"] + 3)

    def correr(self, cuadros, apretar_a=()):
        """Avanza `cuadros` cuadros. `apretar_a` son toques de A, por número."""
        presiones = {n - RETRASO_DE_PANTALLA for n in apretar_a}
        for _ in range(cuadros):
            self.cuadro += 1
            if self.cuadro in presiones:
                self.consola.apretar("a")
            elif self.cuadro - 1 in presiones:
                self.consola.apretar()
            self.consola.correr(1)
        return self

    # --- las preguntas -----------------------------------------------------
    #
    # Cada símbolo se nombra en un solo lugar, acá. Un test dice `.mapa()`, no
    # `"mapa_actual"`, así que renombrar la variable en `main.s` se arregla en
    # una línea y no en veinte.

    def byte(self, nombre):
        return self.consola.ram(self.simbolos[nombre], 1)[0]

    def palabra(self, nombre):
        bajo, alto = self.consola.ram(self.simbolos[nombre], 2)
        return bajo | (alto << 8)

    def mapa(self):
        """En qué mapa de RM2k está parada la partida."""
        indice = self.byte("mapa_actual")
        if indice >= len(self.mapas):
            raise AssertionError(
                "la ROM dice estar en el mapa índice %d y su tabla tiene %d: "
                "%s" % (indice, len(self.mapas), self.mapas))
        return self.mapas[indice]

    def switch(self, numero):
        """Si el switch está prendido. Es el mismo bitmap que lee la ROM."""
        octeto = self.consola.ram(self.simbolos["switches"] + numero // 8, 1)
        return bool(octeto[0] & (1 << (numero % 8)))

    def corriendo_una_pagina(self):
        return bool(self.byte("ev_activo"))

    def cuadros_perdidos(self):
        """Cuántos cuadros no le alcanzaron al lazo principal. No es una
        aserción por sí solo —un teletransporte pierde algunos— pero un salto
        grande dice que algo se volvió caro."""
        return self.byte("cuadros_perdidos")


def armar(map_id, mapas=(), switch=(), con_ventana=True, destino=None,
          rama=()):
    """Convierte, ensambla y devuelve (ROM, símbolos, ids de mapa en orden).

    Los mismos dos comandos que corre el justfile, para que una ROM de prueba
    no sea nunca una ROM armada a mano: ver "Trampas del entorno" en CLAUDE.md.
    """
    destino = destino or os.path.join(RAIZ, "rom", "build", "pruebas")
    os.makedirs(destino, exist_ok=True)
    inc = os.path.join(destino, "mapdata.inc")
    sfc = os.path.join(destino, "prueba.sfc")

    convertir = [sys.executable, os.path.join(RAIZ, "tools", "snes_convert.py"),
                 "--grupo", GRUPO, "--map-id", str(map_id)]
    if mapas:
        convertir += ["--mapas"] + [str(m) for m in mapas]
    if switch:
        convertir += ["--switch"] + [str(s) for s in switch]
    if rama:
        convertir += ["--rama-de-prueba"] + [str(n) for n in rama]
    if con_ventana:
        convertir.append("--con-ventana")
    convertir += ["-o", inc]
    subprocess.run(convertir, check=True, capture_output=True, cwd=RAIZ)

    subprocess.run([sys.executable, os.path.join(RAIZ, "tools", "w65.py"),
                    os.path.join(RAIZ, "rom", "src", "main.s"),
                    "-I", destino, "-o", sfc, "--simbolos", sfc + ".sym"],
                   check=True, capture_output=True, cwd=RAIZ)

    return sfc, Simbolos(sfc + ".sym"), mapas_de(inc)


def mapas_de(inc):
    """El orden de la tabla de mapas, leído del `mapdata.inc` generado.

    El conversor deja un comentario por entrada —`--- 4: mapa 5 'Core
    Retrospective' ---`— y de ahí sale, en vez de rehacer la convención.
    """
    with open(inc) as archivo:
        texto = archivo.read()
    orden = {}
    for indice, map_id in re.findall(r"^; --- (\d+): mapa (\d+) ", texto,
                                     re.MULTILINE):
        orden[int(indice)] = int(map_id)
    if not orden:
        raise AssertionError("no encontré la tabla de mapas en %s" % inc)
    return [orden[i] for i in range(len(orden))]
