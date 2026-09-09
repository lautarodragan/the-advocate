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

import glob
import hashlib
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

    `correr` avanza **ticks** apretando A donde se le diga, con la misma
    convención que `snes_correr.py` —un toque por número, apretado un tick
    antes por `RETRASO_DE_PANTALLA`— para que una lista de toques sirva igual
    en un caso de pixeles y en una prueba de estado.

    Un tick es una vuelta del lazo principal, o sea un paso de lógica de RM2k.
    Normalmente es un cuadro de hardware, y se separan cuando una vuelta se
    pasa del cuadro: al entrar a Lashe City las dos primeras miden 370 y 386
    líneas de las 262 que hay. La ROM lleva la cuenta en `vueltas` y acá se la
    pregunta, en vez de suponer que un cuadro es un tick. Ver `Reloj` en
    `tools/snes_correr.py`.
    """

    def __init__(self, sfc, simbolos, mapas, switches=()):
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
        self.consola.correr(self.simbolos["BOOT_CUADROS"])
        # Los switches se escriben **antes del primer cuadro de juego**, no
        # después: mientras dura el arranque el mapa está congelado y no corre
        # ninguna página, así que acá el estado inicial llega a tiempo para
        # todas. Escribiéndolo tres cuadros más tarde ya era tarde para la
        # página de prueba, que corre en el primero.
        if switches:
            self.prender(*switches)
        self.consola.correr(3)

    def reiniciar(self):
        """El botón de reset: la SRAM del cartucho sobrevive y la WRAM no.

        Es la única forma honesta de probar que una partida guardada se carga:
        volver a arrancar la consola de verdad, con el mismo cartucho, y mirar
        dónde queda parada. Escribirle la RAM a mano probaría otra cosa.
        """
        self.consola.reset()
        self.cuadro = 0
        self.consola.correr(self.simbolos["BOOT_CUADROS"])
        self.consola.correr(3)
        return self

    def sram(self, direccion=0, largo=None):
        """La SRAM del cartucho, que es lo que un frontend vuelca a un `.srm`."""
        return self.consola.sram(direccion, largo)

    def correr(self, cuadros, apretar_a=()):
        """Avanza `cuadros` **ticks**. `apretar_a` son toques de A, por número.

        El botón se sostiene mientras dure el tick: la ROM lee el pad una vez
        por vuelta, así que si la vuelta se estira sigue siendo un solo flanco.
        """
        presiones = {n - RETRASO_DE_PANTALLA for n in apretar_a}
        objetivo = self.cuadro + cuadros
        tope = (cuadros + 1) * 60
        while self.cuadro < objetivo:
            if self.cuadro + 1 in presiones:
                self.consola.apretar("a")
            else:
                self.consola.apretar()
            self._un_cuadro()
            tope -= 1
            if tope <= 0:
                raise RuntimeError("la ROM no llegó al tick %d" % objetivo)
        return self

    def _un_cuadro(self):
        """Un cuadro de hardware, y el reloj del juego al día."""
        self.consola.correr(1)
        # El cuadro 0 es el tick 1: ver `TICK_DEL_CUADRO_CERO` en snes_correr.
        self.cuadro = self.palabra("vueltas") - 1

    def _un_tick(self):
        """Cuadros hasta que el juego avance una vuelta."""
        antes = self.cuadro
        for _ in range(60):
            self._un_cuadro()
            if self.cuadro > antes:
                return
        raise RuntimeError("la ROM no avanzó ningún tick en 60 cuadros")

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

    def tocar(self, *botones):
        """Un toque de los botones que se le digan: un cuadro apretados y uno
        suelto, que es el flanco que la ROM mira.

        `correr(..., apretar_a=...)` sólo sabe de A porque eso es todo lo que la
        tanda de pixeles sabe apretar. Acá hacen falta las direcciones y B: el
        cursor de `ShowChoice` se mueve con ellos, y ése es justamente el camino
        que la tanda no puede ejercitar.
        """
        self.consola.apretar(*botones)
        self._un_tick()
        self.consola.apretar()
        self._un_tick()
        return self

    def poner_byte(self, nombre, valor):
        """Escribe un byte de la RAM de la ROM, por nombre de símbolo.

        Es para poner a la partida en un estado al que llegar jugando costaría
        media hora: `saltos_restantes` bajo, por ejemplo, que es lo que deja una
        partida larga. Lo que se escribe acá **no** es una aserción: se escribe
        el estado y después se le pregunta a la ROM qué hace con él.
        """
        self.consola.escribir_ram(self.simbolos[nombre], [valor])
        return self

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

    def prender(self, *numeros):
        """Prende switches escribiendo el bitmap, como si el juego los hubiera
        prendido antes.

        Reemplaza al `--switch` del conversor, que los prendía desde una página
        de prueba inventada, y es mejor por dos razones. La primera es que **la
        ROM deja de depender de la prueba**: es la misma para todas, así que se
        arma una vez.

        La segunda importa más. Esa página tenía el número de evento más alto
        de la tabla, y el barrido de eventos va de menor a mayor, así que corría
        **después** que las del mapa: un switch que decide lo que hace una
        página del mapa llegaba tarde. Acá se escribe antes del primer cuadro de
        juego, así que llega siempre a tiempo. Es lo que hacía imposible probar
        la rama de `ConditionalBranch` que sí corre.

        El `refresco` es lo que hace `OP_SWITCH` después de tocar el bitmap: sin
        él la ROM no vuelve a mirar qué página está activa hasta que algo más lo
        pida.
        """
        base = self.simbolos["switches"]
        for numero in numeros:
            direccion = base + numero // 8
            octeto = self.consola.ram(direccion, 1)[0] | (1 << (numero % 8))
            self.consola.escribir_ram(direccion, [octeto])
        self.consola.escribir_ram(self.simbolos["refresco"], [1])
        return self

    def ir_al_mapa(self, map_id, x, y, cuadros=90):
        """Teletransporta a la partida, como lo haría una puerta del juego.

        No hay atajo acá: se le pide a la ROM el mismo fundido que pide una
        puerta —`empezar_fundido` con `FUNDIDO_PUERTA`— y la carga del mapa la
        hace ella, por su camino. Lo único que se escribe desde afuera es el
        pedido: a dónde, a qué celda, y la bandera.

        Es lo que permite que una sola ROM sirva para pruebas que arrancan en
        mapas distintos. Cuesta los cuadros del fundido, así que una prueba con
        una lista de toques de A afinada al cuadro conviene que arranque en el
        mapa que la ROM carga sola.
        """
        if map_id not in self.mapas:
            raise AssertionError(
                "el mapa %d no está en esta ROM; lleva %s" % (map_id, self.mapas))
        self.consola.escribir_ram(self.simbolos["fundido_mapa"],
                                  [self.mapas.index(map_id)])
        for nombre, valor in (("entrada_x", x), ("entrada_y", y)):
            self.consola.escribir_ram(self.simbolos[nombre],
                                      [valor & 0xFF, valor >> 8])
        # `empezar_fundido`, desde afuera: qué fundido es, que hay uno, y el
        # reloj, que son **vueltas del lazo** —ticks— desde el 2026-09-08. Con
        # `boot_cuadros`, que es lo que decía antes, la resta daba cualquier
        # cosa y el fundido no terminaba nunca: la partida se quedaba en el
        # mapa de arranque y catorce pruebas fallaban sin decir por qué.
        self.consola.escribir_ram(self.simbolos["fundido_que"],
                                  [self.simbolos["FUNDIDO_PUERTA"]])
        self.consola.escribir_ram(self.simbolos["fundido"], [1])
        self.consola.escribir_ram(self.simbolos["fundido_base"],
                                  [self.palabra("vueltas") & 0xFF])
        self.correr(cuadros)
        return self

    def corriendo_una_pagina(self):
        return bool(self.byte("ev_activo"))

    def cuadros_perdidos(self):
        """Cuántos cuadros no le alcanzaron al lazo principal. No es una
        aserción por sí solo —un teletransporte pierde algunos— pero un salto
        grande dice que algo se volvió caro."""
        return self.byte("cuadros_perdidos")


def huella():
    """De qué depende una ROM de prueba, además de sus mapas.

    Todo lo que participa de armarla: el fuente de la ROM, el conversor, el
    ensamblador y el modelo. Si nada de eso cambió, la ROM que está en disco
    sigue siendo la que se habría armado, y armarla otra vez son tres segundos
    tirados en cada corrida.

    Se mira el contenido y no la fecha: `git checkout` de ida y vuelta deja
    fechas nuevas con el mismo contenido, y ahí rearmar no sirve para nada.
    """
    h = hashlib.sha256()
    partes = [os.path.join(RAIZ, "rom", "src", "main.s")]
    partes += sorted(glob.glob(os.path.join(RAIZ, "tools", "*.py")))
    for ruta in partes:
        with open(ruta, "rb") as archivo:
            h.update(archivo.read())
    return h.hexdigest()[:16]


def armar(map_id, mapas=(), con_ventana=True, destino=None, rama=(),
          descartar=False, guardar=0):
    """Convierte, ensambla y devuelve (ROM, símbolos, ids de mapa en orden).

    Los mismos dos comandos que corre el justfile, para que una ROM de prueba
    no sea nunca una ROM armada a mano: ver "Trampas del entorno" en CLAUDE.md.

    Se saltea si ya está hecha y nada de lo que la arma cambió; ver `huella`.
    El estado inicial —los switches— ya no se hornea en la ROM sino que se
    escribe en la RAM, así que dos pruebas que piden los mismos mapas comparten
    el mismo cartucho.
    """
    destino = destino or os.path.join(RAIZ, "rom", "build", "pruebas")
    os.makedirs(destino, exist_ok=True)
    inc = os.path.join(destino, "mapdata.inc")
    sfc = os.path.join(destino, "prueba.sfc")
    sello = os.path.join(destino, "huella.txt")

    actual = huella()
    if os.path.exists(sfc) and os.path.exists(inc):
        try:
            with open(sello) as archivo:
                if archivo.read().strip() == actual:
                    return sfc, Simbolos(sfc + ".sym"), mapas_de(inc)
        except OSError:
            pass

    convertir = [sys.executable, os.path.join(RAIZ, "tools", "snes_convert.py"),
                 "--grupo", GRUPO, "--map-id", str(map_id)]
    if mapas:
        convertir += ["--mapas"] + [str(m) for m in mapas]
    if rama:
        convertir += ["--rama-de-prueba"] + [str(n) for n in rama]
    if guardar:
        # La página de prueba espera `guardar` ticks y recién ahí guarda la
        # partida. La espera es lo que le deja a la prueba mover el mundo antes
        # —irse a otro mapa, por ejemplo— para que lo guardado no sea el estado
        # del arranque; ver `pagina_de_prueba`.
        convertir += ["--guardar-de-prueba", "--pagina-de-prueba", str(guardar)]
    if con_ventana:
        convertir.append("--con-ventana")
    if descartar:
        # Esta ROM descarta algún evento que cambia de gráfico y el conversor
        # corta si no se le dice que siga; ver `aviso_de_descarte`. Se pide por
        # ROM y no para todas: el corte es la red que avisó del evento 30 del
        # mapa 2, y apagarla en todas la dejaría sin cubrir nada.
        convertir.append("--descartar-eventos")
    convertir += ["-o", inc]
    subprocess.run(convertir, check=True, capture_output=True, cwd=RAIZ)

    subprocess.run([sys.executable, os.path.join(RAIZ, "tools", "w65.py"),
                    os.path.join(RAIZ, "rom", "src", "main.s"),
                    "-I", destino, "-o", sfc, "--simbolos", sfc + ".sym"],
                   check=True, capture_output=True, cwd=RAIZ)
    with open(sello, "w") as archivo:
        archivo.write(actual)

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
