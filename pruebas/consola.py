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


# Cuántos cuadros se le dan a la pantalla de título para llegar a su lazo antes
# de apretarle nada. No es un número medido al filo: es aire de sobra para los
# 33 KB que sube a la VRAM, y la pantalla se queda quieta hasta que alguien
# aprieta, así que pasarse no cuesta nada.
TITULO_AIRE = 30


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

    def __init__(self, sfc, simbolos, mapas, switches=(), titulo=None):
        self.simbolos = simbolos
        # El cartucho, para las tablas que no están en la RAM sino en la ROM:
        # ver `muestras_del_tema`.
        self.sfc = sfc
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
        # Con pantalla de título el arranque no termina en el mapa sino en el
        # menú, y el primer cuadro de juego es el de después de elegir.
        self.titulo = titulo
        if titulo is not None:
            self.pasar_el_titulo(titulo)
        # Los switches se escriben **antes del primer cuadro de juego**, no
        # después: mientras dura el arranque el mapa está congelado y no corre
        # ninguna página, así que acá el estado inicial llega a tiempo para
        # todas. Escribiéndolo tres cuadros más tarde ya era tarde para la
        # página de prueba, que corre en el primero.
        if switches:
            self.prender(*switches)
        self.consola.correr(3)

    def _bajar_y_elegir(self, cuantas):
        """`cuantas` toques de abajo y después A.

        Los botones se sueltan entre toque y toque porque estos menús miran
        **flancos**: sostener abajo no baja un renglón por cuadro, que es el
        `Input::IsTriggered` de RM2k y lo que la tanda comprueba en pixeles.
        """
        for _ in range(cuantas):
            self.consola.apretar("down")
            self.consola.correr(2)
            self.consola.apretar()
            self.consola.correr(2)
        self.consola.apretar("a")
        self.consola.correr(2)
        self.consola.apretar()
        self.consola.correr(2)

    def pasar_el_titulo(self, opcion, ranura=0):
        """Elige `opcion` en el menú del título, y `ranura` si hace falta.

        La segunda opción —"Resume the Story"— abre **otra pantalla**, la de
        ranuras, así que elegirla son dos menús y no uno. `ranura` dice cuál se
        elige ahí; con la primera opción no se mira.
        """
        # Unos cuadros de aire primero: `pantalla_titulo` corre **después** de
        # que el arranque contó sus BOOT_CUADROS, y antes de llegar a su lazo
        # sube 33 KB a la VRAM con la pantalla apagada. Un toque en el cuadro
        # BOOT_CUADROS justo cae ahí y se pierde. La pantalla de ranuras sube
        # bastante menos, pero el aire no cuesta nada y se le da el mismo.
        self.consola.correr(TITULO_AIRE)
        self._bajar_y_elegir(opcion)
        if opcion:
            self.consola.correr(TITULO_AIRE)
            self._bajar_y_elegir(ranura)

    def esperar_la_pantalla_de_ranuras(self, tope=120):
        """Cuadros de hardware hasta que la pantalla de ranuras esté a la vista.

        Se mira `menu_abierto`, que la ROM pone para esto: mientras la pantalla
        se ve `vueltas` no avanza, así que esperar por ticks se colgaría.
        """
        for _ in range(tope):
            if self.byte("menu_abierto"):
                return self
            self.consola.correr(1)
        raise RuntimeError(
            "la pantalla de ranuras no se abrió en %d cuadros" % tope)

    def abrir_ranuras_desde_el_titulo(self):
        """Resetea la consola, pasa el título por "Resume the Story" y se
        queda **con la pantalla de ranuras a la vista**, para mirarla.

        Es `reiniciar(SEGUIR)` cortado antes de elegir: lo que la pantalla
        muestra de cada ranura —el nombre y las caras del grupo guardado— sólo
        se puede comprobar con una partida guardada de verdad, y eso una
        captura de `snes_correr.py` no lo tiene.
        """
        self.consola.reset()
        self.cuadro = 0
        self.consola.correr(self.simbolos["BOOT_CUADROS"])
        self.consola.correr(TITULO_AIRE)
        self._bajar_y_elegir(1)
        self.consola.correr(TITULO_AIRE)
        return self.esperar_la_pantalla_de_ranuras()

    def poner_grupo(self, *actores):
        """El grupo, por ids de actor, escrito en la RAM como lo dejaría un
        `ChangePartyMembers`. Es lo que la partida guarda y la pantalla de
        ranuras muestra."""
        largo = self.simbolos["GRUPO_MAX"]
        assert len(actores) <= largo
        self.consola.escribir_ram(self.simbolos["grupo"],
                                  list(actores) + [0] * (largo - len(actores)))
        self.consola.escribir_ram(self.simbolos["grupo_n"],
                                  [len(actores), 0])
        return self

    def imagen(self):
        """La pantalla, como la dibuja el emulador."""
        return self.consola.imagen()

    def guardar_en(self, ranura=0, espera=200, cancelar=False):
        """Corre hasta que la página de prueba abra la pantalla de ranuras, y
        elige `ranura` ahí —o cancela con B—.

        Es el camino del save point de verdad: `OpenSaveMenu` abre la pantalla
        adentro del intérprete y la página sigue cuando se cierra. La ranura
        no se escribe a mano: se baja el cursor y se aprieta A, como lo haría
        el jugador.

        La página abre la pantalla al tick `espera`, más o menos uno, contado
        desde el arranque y no desde acá: la prueba puede haber gastado ticks
        antes —`ir_al_mapa` son 90—. Se corre por ticks hasta unos cuantos
        antes y de ahí por cuadros de hardware hasta que la pantalla esté, que
        es lo que `esperar_la_pantalla_de_ranuras` mira.
        """
        if self.cuadro < espera - 10:
            self.correr(espera - 10 - self.cuadro)
        self.esperar_la_pantalla_de_ranuras()
        self.consola.correr(TITULO_AIRE)
        if cancelar:
            self.consola.apretar("b")
            self.consola.correr(2)
            self.consola.apretar()
        else:
            self._bajar_y_elegir(ranura)
        # Y unos ticks de aire: que la página siga y el mapa vuelva.
        self.correr(10)
        return self

    def reiniciar(self, opcion=None, ranura=0):
        """El botón de reset: la SRAM del cartucho sobrevive y la WRAM no.

        Es la única forma honesta de probar que una partida guardada se carga:
        volver a arrancar la consola de verdad, con el mismo cartucho, y mirar
        dónde queda parada. Escribirle la RAM a mano probaría otra cosa.

        Con pantalla de título hay que volver a elegir, y `opcion` dice qué:
        sin ella se repite la de la vez anterior.
        """
        self.consola.reset()
        self.cuadro = 0
        self.consola.correr(self.simbolos["BOOT_CUADROS"])
        elegir = self.titulo if opcion is None else opcion
        if elegir is not None:
            self.pasar_el_titulo(elegir, ranura)
        self.consola.correr(3)
        return self

    def sram(self, direccion=0, largo=None):
        """La SRAM del cartucho, que es lo que un frontend vuelca a un `.srm`."""
        return self.consola.sram(direccion, largo)

    def correr(self, cuadros, apretar_a=(), sosteniendo=()):
        """Avanza `cuadros` **ticks**. `apretar_a` son toques de A, por número.

        El botón se sostiene mientras dure el tick: la ROM lee el pad una vez
        por vuelta, así que si la vuelta se estira sigue siendo un solo flanco.

        `sosteniendo` son los que quedan apretados **todos** los cuadros, que
        es lo que hace `--teclas` en `snes_correr.py`. Hace falta porque esto
        suelta el pad en cada vuelta: un `consola.apretar(...)` de afuera se
        perdía en el primer cuadro, y `KeyInputProc` sin espera leía cero.
        """
        presiones = {n - RETRASO_DE_PANTALLA for n in apretar_a}
        sosteniendo = tuple(sosteniendo)
        objetivo = self.cuadro + cuadros
        tope = (cuadros + 1) * 60
        while self.cuadro < objetivo:
            if self.cuadro + 1 in presiones:
                self.consola.apretar("a", *sosteniendo)
            else:
                self.consola.apretar(*sosteniendo)
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

    def sostener(self, ticks, *botones):
        """Los botones apretados durante `ticks` vueltas, y después sueltos.

        Es la caminata con el pad: `correr` sólo sabe de A. Se lee el estado
        **antes** de soltar, así que lo que se pregunta después es lo que la
        ROM tenía con el botón todavía apretado en la última vuelta.
        """
        self.consola.apretar(*botones)
        for _ in range(ticks):
            self._un_tick()
        return self

    def soltar(self):
        self.consola.apretar()
        return self

    def velocidad_del_heroe(self):
        """La velocidad de RM2k del héroe, de 1 a 6, leída de la RAM lejana."""
        return self.consola.ram(self.simbolos["FAR_HERO_VEL"], 1)[0]

    def poner_velocidad_del_heroe(self, velocidad):
        """Lo que una ruta con 28 o 29 le deja al héroe, sin correr la ruta."""
        self.consola.escribir_ram(self.simbolos["FAR_HERO_VEL"], [velocidad])
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
        indice = self.palabra("mapa_actual")
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

    def apagar(self, *numeros):
        """Lo contrario de `prender`, con el mismo `refresco` detrás.

        Hace falta para volver a correr la página de prueba después de cargar
        una partida: la página prende `SWITCH_DE_PRUEBA` al arrancar, la
        partida se guarda con ese switch puesto, y al cargarla gana la página
        que lo mira y la apaga. Es un artefacto de la página inventada y no del
        juego, así que se deshace desde afuera.
        """
        base = self.simbolos["switches"]
        for numero in numeros:
            direccion = base + numero // 8
            octeto = self.consola.ram(direccion, 1)[0] & ~(1 << (numero % 8))
            self.consola.escribir_ram(direccion, [octeto & 0xFF])
        self.consola.escribir_ram(self.simbolos["refresco"], [1])
        return self

    def ir_al_mapa(self, map_id, x, y, cuadros=90, tinte=True):
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
        # Dos bytes: el índice de mapa es un word desde que el destino de
        # OP_TELEPORT lo es. Escribiendo uno solo, el alto se queda con lo que
        # hubiera antes y la ROM carga cualquier mapa.
        indice = self.mapas.index(map_id)
        self.consola.escribir_ram(self.simbolos["fundido_mapa"],
                                  [indice & 0xFF, indice >> 8])
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
        # Y la pantalla se destiñe, que es lo único que este salto hace y una
        # puerta de verdad no.
        #
        # El tinte **sobrevive al cambio de mapa**, y con razón: es lo que hace
        # RM2k y lo que la referencia modela. Pero saltar acá no es cruzar una
        # puerta: es aparecer en un mapa al que la partida no llegó jugando, sin
        # haber corrido las páginas que en el juego habrían dejado la pantalla
        # como corresponde. Con el mapa de arranque de las demos, que tiñe de
        # azul en su cinemática, eso dejaba el mapa entero azul y parecía el
        # defecto que uno estaba buscando: costó una hora el 2026-09-13, y
        # estuvo escrito como trampa en AGENTS.md hasta que esto lo hizo
        # innecesario. Con `tinte=False` se conserva, para una prueba que
        # quiera justamente mirar que sobrevive.
        if tinte:
            for nombre in ("tinte_r", "tinte_g", "tinte_b", "tinte_s"):
                self.consola.escribir_ram(self.simbolos[nombre],
                                          [self.simbolos["TINTE_NEUTRO"]])
        self.correr(cuadros)
        return self

    def variable(self, ranura):
        """El valor de la ranura, con signo, leído de la RAM lejana."""
        bajo, alto = self.consola.ram(self.simbolos["FAR_VARIABLES"]
                                      + ranura * 2, 2)
        valor = bajo | (alto << 8)
        return valor - 0x10000 if valor & 0x8000 else valor

    def quedarse_en_el_titulo(self):
        """Resetea y **se queda** en la pantalla de título, sin elegir nada.

        `pasar_el_titulo` la atraviesa; acá hace falta lo contrario, porque lo
        que se quiere mirar es el estado mientras la pantalla está puesta.
        """
        self.consola.reset()
        self.cuadro = 0
        self.consola.correr(self.simbolos["BOOT_CUADROS"])
        self.consola.correr(TITULO_AIRE)
        return self

    def muestras_en_la_aram(self):
        """Qué muestras dice la ROM tener subidas al SPC700.

        Es `FAR_ARAM_DE`, una palabra por muestra con dónde quedó cada una en
        la ARAM, o cero si no está: la lee `paquete_cargar` y la escribe
        `colocar_muestra`. Un número que **no** está acá es una muestra cuya
        entrada del directorio del SPC700 apunta al silencio, o sea una nota
        que no suena.
        """
        n = self.simbolos["MUESTRAS_N"]
        crudo = self.consola.ram(en_la_wram(self.simbolos["FAR_ARAM_DE"]),
                                 2 * n)
        return {i for i in range(n)
                if crudo[2 * i] | (crudo[2 * i + 1] << 8)}

    def muestras_del_tema(self, indice):
        """Qué muestras necesita el tema, leídas de `tema_muestras` **en el
        cartucho**.

        Es la misma tabla que mira `tema_asegurar`, y se lee de la ROM en vez
        de recalcularla con `snes_music.muestras_del_stream`: recalcularla
        sería una segunda manera de contestar la pregunta, y las dos se pueden
        equivocar igual. Un índice de desplazamientos de dos bytes por tema
        —`TEMA_TOTAL` de ellos— y detrás una lista por tema cerrada con $FF.
        """
        with open(self.sfc, "rb") as archivo:
            rom = archivo.read()
        base = en_la_rom(self.simbolos["tema_muestras"])
        if not 0 <= indice < self.simbolos["TEMA_TOTAL"]:
            raise AssertionError(
                "el tema %d no está en esta ROM, que lleva %d"
                % (indice, self.simbolos["TEMA_TOTAL"]))
        salto = base + 2 * indice
        lista = base + (rom[salto] | (rom[salto + 1] << 8))
        muestras = []
        while rom[lista] != 0xFF:
            muestras.append(rom[lista])
            lista += 1
        assert muestras, (
            "el tema %d dice no usar ninguna muestra: o la tabla se leyó mal "
            "o la ROM no lleva música" % indice)
        return muestras

    def acceso(self):
        """El byte de permisos: bit 0 guardar prohibido, bit 1 el menú
        prohibido, bit 7 el menú pedido."""
        return self.consola.ram(self.simbolos["FAR_ACCESO"], 1)[0]

    def menu_abierto(self):
        return bool(self.byte("menu_abierto"))

    def item(self, numero):
        """Cuántos hay del ítem, leído de la RAM lejana."""
        return self.consola.ram(self.simbolos["FAR_ITEMS"] + numero, 1)[0]

    def corriendo_una_pagina(self):
        return bool(self.byte("ev_activo"))

    def cuadros_perdidos(self):
        """Cuántos cuadros no le alcanzaron al lazo principal. No es una
        aserción por sí solo —un teletransporte pierde algunos— pero un salto
        grande dice que algo se volvió caro."""
        return self.byte("cuadros_perdidos")


def en_la_wram(direccion):
    """De una dirección larga del banco $7E al desplazamiento que pide
    `retro.Consola.ram`.

    Las de la RAM lejana están escritas de las dos maneras en `main.s` —unas
    con el banco adelante (`$7E3100`) y otras sin él (`$2600`)—, así que el
    símbolo se enmascara en vez de suponerse.
    """
    return direccion & 0x1FFFF


def en_la_rom(direccion):
    """De una dirección larga del cartucho al desplazamiento en el archivo.

    Es el mapeo LoROM y nada más: cada banco expone sus 32 KB desde $8000.
    """
    return ((direccion >> 16) * 0x8000) + (direccion & 0x7FFF)


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
          descartar=False, guardar=0, titulo=False, tema=None, variables=(),
          rama_var=(), items=(), acceso=(), tecla=(), espera=0, timer=False,
          batalla=0, game_over=False, encuentros=0, grupo=None):
    """Convierte, ensambla y devuelve (ROM, símbolos, ids de mapa en orden).

    Los mismos dos comandos que corre el justfile, para que una ROM de prueba
    no sea nunca una ROM armada a mano: ver "Trampas del entorno" en AGENTS.md.

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

    # La huella lleva **también los argumentos**, y no sólo los fuentes: dos
    # llamadas con mapas distintos y el mismo `destino` devolvían el cartucho de
    # la primera, en silencio. `conftest.partida()` no se lo come porque le da
    # un destino por combinación, pero llamar a `armar()` a mano sí: el
    # 2026-09-13 me hizo medir cuatro mapas y estar midiendo siempre el mismo.
    actual = huella() + "\n" + repr((
        map_id, tuple(mapas), con_ventana, tuple(rama), descartar, guardar,
        titulo, tema, tuple(variables), tuple(rama_var), tuple(items),
        tuple(acceso), tuple(tecla), espera, timer, batalla, game_over,
        encuentros, tuple(grupo or ())))
    if os.path.exists(sfc) and os.path.exists(inc):
        try:
            with open(sello) as archivo:
                if archivo.read().strip() == actual:
                    return sfc, Simbolos(sfc + ".sym"), mapas_de(inc)
        except OSError:
            pass

    convertir = [sys.executable, os.path.join(RAIZ, "tools", "snes_convert.py"),
                 "--grupo"] + [str(a) for a in (grupo or GRUPO.split())] + [
                 "--map-id", str(map_id)]
    if mapas:
        convertir += ["--mapas"] + [str(m) for m in mapas]
    if rama:
        convertir += ["--rama-de-prueba"] + [str(n) for n in rama]
    if variables:
        convertir += ["--vars-de-prueba"] + [str(n) for n in variables]
    if rama_var:
        convertir += ["--rama-var-de-prueba"] + [str(n) for n in rama_var]
    if items:
        convertir += ["--items-de-prueba"] + [str(n) for n in items]
    if acceso:
        convertir += ["--acceso-de-prueba"] + [str(n) for n in acceso]
    if tecla:
        # `KeyInputProc` en la página de prueba, con `espera` cuadros de espera
        # delante: la espera es lo que le deja a la prueba apretar algo antes
        # de que el comando lea, que si no lee en el primer cuadro de juego y
        # no hay forma de tener el pad puesto a tiempo.
        convertir += ["--tecla-de-prueba"] + [str(n) for n in tecla]
        convertir += ["--pagina-de-prueba", str(espera)]
    if batalla:
        # Una pelea contra esta tropa al final de la página de prueba, con la
        # derrota puesta en `BATALLA_PERDER`, o sea el Game Over de RM2k. La
        # espera de delante es lo que le deja a la prueba ponerle los HP del
        # grupo en cero antes de que la pelea se abra: con todos caídos,
        # `batalla_correr` devuelve derrota sin pelear —ver "nadie en pie" en
        # main.s— y ése es el camino que se quiere ejercitar.
        convertir += ["--batalla-de-prueba", str(batalla),
                      "--pagina-de-prueba", str(espera)]
        if game_over:
            convertir.append("--batalla-game-over")
    if encuentros:
        # Los encuentros al azar cada `encuentros` pasos, en vez de los del
        # árbol de mapas: sin esto una prueba tendría que caminar hasta que le
        # tocara, y en Rat Tracks B1 son ochenta pasos por encuentro.
        convertir += ["--encuentros-de-prueba", str(encuentros)]
    if guardar:
        # La página de prueba espera `guardar` ticks y recién ahí guarda la
        # partida. La espera es lo que le deja a la prueba mover el mundo antes
        # —irse a otro mapa, por ejemplo— para que lo guardado no sea el estado
        # del arranque; ver `pagina_de_prueba`.
        convertir += ["--guardar-de-prueba", "--pagina-de-prueba", str(guardar)]
    if con_ventana:
        convertir.append("--con-ventana")
    if timer:
        # El cronómetro, que es lo que las demos llevan: se lo pide `--con-timer`
        # y cuesta la paleta de los dígitos. Lo necesita la prueba de recorrido,
        # porque la cuenta atrás de diez minutos arranca en la casa de Talan y
        # sin esto el mapa que la para no tendría qué parar.
        convertir.append("--con-timer")
    if tema:
        # Que la ROM arranque con un tema sonando. Los mapas de estas pruebas
        # no traen música propia, así que sin esto no hay forma de comprobar
        # que el tema viaja en la partida guardada: `music_apagada` valdría 1
        # en los dos lados y la prueba pasaría sin probar nada.
        convertir += ["--tema-de-arranque", tema]
    if titulo:
        # La pantalla de título, que cambia el arranque: la ROM no carga la
        # partida sola y espera a que el menú lo decida. Va en su propio
        # cartucho justamente por eso.
        convertir.append("--con-titulo")
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
