"""Una partida de la ROM corriendo, para hacerle preguntas sobre su estado.

Esto **no compara pixeles**. La tanda de `pruebas/*/test_tanda*.py` compara la pantalla
contra la referencia de Python, cuadro por cuadro; acá se le pregunta a la ROM
en qué mapa está, qué switch tiene prendido o qué evento está corriendo. Son
dos redes distintas y se complementan: la de pixeles dice "la pantalla es
exactamente ésta", ésta dice "y además llegaste adonde tenías que llegar".

Lo que hace posible preguntar es que `tools/ensamblar.py` deja al lado de la ROM
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
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "tools"))

import retro                                            # noqa: E402

# El mismo que usa el justfile por omisión. Se puede pisar con NUCLEO para
# correr las pruebas contra otro core.
NUCLEO = os.environ.get(
    "NUCLEO", "/usr/lib/libretro/snes9x_libretro.so")

# El cuadro que se ve en pantalla muestra el estado de la vuelta ANTERIOR del
# lazo principal: `flush_video` sube el OAM que armó `build_oam` la vuelta
# pasada, y por eso está al principio del lazo y no al final. De ahí sale este
# +1, que no es un ajuste sino una consecuencia del orden de main.s.
#
# Con eso, para ver al héroe con N pixeles de avance hay que correr N/2 + 1
# cuadros desde que se aprieta: se mueve WALK_SPEED = 2 por cuadro. Medido en el
# mapa 73 a 40, 60 y 80 px: exacto da 0, y errarle por un cuadro para cualquier
# lado da unos 25000 pixeles de diferencia.
RETRASO_DE_PANTALLA = 1


class SimboloDesconocido(KeyError):
    """Se pidió un símbolo que la ROM no tiene."""


class Simbolos:
    """La tabla que deja `tools/ensamblar.py`, leída por nombre."""

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

# La primera opción del menú del título, "Begin the Story". La segunda carga.
EMPEZAR = 0


def toques_de(pares, flag):
    """Los `BOTON:CUADRO` del corredor, a {cuadro: (botones,)}.

    Es el mismo formato que `--toques`, `--tocar` y `--toques-hardware` leen en
    `snes_correr.py`, y a propósito: mientras las recetas y las pruebas
    convivan, un caso mudado tiene que poder copiar su lista tal cual. El
    número está en el reloj que diga cada flag; acá sólo se parte el par.
    """
    cuando = {}
    for toque in pares or ():
        boton, _, cuadro = str(toque).partition(":")
        if not cuadro.isdigit():
            raise ValueError("%s quiere BOTON:CUADRO, y vino %r" % (flag,
                                                                    toque))
        cuando.setdefault(int(cuadro), []).append(boton)
    return {n: tuple(botones) for n, botones in cuando.items()}


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

    def __init__(self, sfc, simbolos, mapas, switches=(), titulo=None,
                 nucleo=None, caso=0, salta=False):
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
        # `nucleo` es para correr la **misma** partida en dos cores y
        # comparar las dos pantallas entre sí: ver `pruebas/rpgmaker/test_cores.py`.
        # Sin él vale el de siempre, que es snes9x.
        self.consola = retro.Consola(sfc, nucleo or NUCLEO)
        self.cuadro = 0
        self.hardware = 0
        # Cuántas vueltas del lazo quedaron antes del primer tick de la
        # prueba: cero, salvo que el caso arranque con un `Teleport`. Ver
        # `_esperar_la_llegada`.
        self.llegada = 0
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
        # Y el caso de prueba, por lo mismo: la página que lo corre es
        # automática y se elige en el primer cuadro. El 0 es el que no pide
        # nada, así que un cartucho de un solo caso no necesita esto. Ver
        # `--caso` en snes_convert.py.
        self.caso = caso
        self._elegir_el_caso()
        self.consola.correr(3)
        # Un caso que empieza con un `Teleport` —así elige dónde arranca desde
        # el paso 9e— sale en el primer tick y está fundiendo acá. Lo dice
        # quien armó el cartucho, que leyó el caso: mirar si hay un fundido
        # no alcanza, porque hay mapas cuya cinemática funde sola al entrar
        # —el 4 de `apertura`— y ahí la prueba cuenta desde el arranque.
        if salta:
            # El primer tick no cae siempre en el mismo cuadro: en el
            # cartucho de pruebas, con cuarenta mapas y todos los casos, la
            # primera vuelta del lazo termina tres cuadros más tarde que en
            # uno de un mapa. Se espera a que haya corrido.
            for _ in range(60):
                if self.palabra("vueltas"):
                    break
                self.consola.correr(1)
            if not self.byte("fundido"):
                raise AssertionError(
                    "el caso %d empieza con un Teleport y la ROM no está "
                    "fundiendo después del primer tick" % caso)
            self._esperar_la_llegada()
        # Los cuadros de hardware corridos desde que terminó el arranque, que
        # es donde `snes_correr.py` pone su `reloj.corridos` en cero. Es el
        # reloj de los toques de `--toques-hardware`, y es otro que el de los
        # ticks: adentro de una pantalla que congela el juego —la de ranuras
        # del save point— `vueltas` no avanza y éste sí, así que es el único
        # que puede decir cuándo apretar ahí.
        self.hardware = 0

    def _esperar_la_llegada(self):
        """Corre hasta que el `Teleport` del caso llega, y cuenta desde ahí.

        Los dos relojes de la prueba —ticks y cuadros de hardware— arrancan
        en la llegada, así que una prueba cuenta igual que si la ROM hubiera
        arrancado en ese mapa. Lo que cuesta llegar **no se escribe en ningún
        lado**, se mira: en ticks el fundido dura siempre lo mismo, pero en
        cuadros de hardware va de 74 a 139 según lo que haya que cargar
        adentro del negro, medido en el paso 9e. Un número fijo servía para
        uno de los dos relojes y mentía en el otro.

        La llegada es la vuelta **siguiente** a la que apaga el fundido: en
        ésa el mundo corre por primera vez en el mapa nuevo, que es lo que en
        una partida que arranca ahí es el tick 1.
        """
        antes = self.palabra("vueltas")
        for _ in range(600):
            if not self.byte("fundido"):
                break
            self.consola.correr(1)
        else:
            raise RuntimeError("el Teleport del caso no terminó de fundir")
        apagado = self.palabra("vueltas")
        while self.palabra("vueltas") <= apagado:
            self.consola.correr(1)
        self.llegada = self.palabra("vueltas") - antes

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
        # Empezar de nuevo desde el título arranca con la WRAM limpia, y la
        # página de prueba se elige otra vez como al encender. Cargar no:
        # la variable vuelve con la partida, y sin título el arranque carga
        # la partida solo.
        if elegir == EMPEZAR:
            self._elegir_el_caso()
        self.consola.correr(3)
        return self

    def _elegir_el_caso(self):
        """Escribe la variable que elige la página de prueba, con el refresco
        que la hace mirar. El 0 es el que no pide nada."""
        if self.caso:
            self.consola.escribir_ram(
                self.simbolos["FAR_VARIABLES"]
                + 2 * self.simbolos["CASO_RANURA"],
                [self.caso & 0xFF, self.caso >> 8])
            self.consola.escribir_ram(self.simbolos["refresco"], [1])

    def sram(self, direccion=0, largo=None):
        """La SRAM del cartucho, que es lo que un frontend vuelca a un `.srm`."""
        return self.consola.sram(direccion, largo)

    def correr(self, cuadros, apretar_a=(), sosteniendo=(), toques=(),
               toques_hardware=(), tocar=()):
        """Avanza `cuadros` **ticks**. `apretar_a` son toques de A, por número.

        El botón se sostiene mientras dure el tick: la ROM lee el pad una vez
        por vuelta, así que si la vuelta se estira sigue siendo un solo flanco.

        `sosteniendo` son los que quedan apretados **todos** los cuadros, que
        es lo que hace `--teclas` en `snes_correr.py`. Hace falta porque esto
        suelta el pad en cada vuelta: un `consola.apretar(...)` de afuera se
        perdía en el primer cuadro, y `KeyInputProc` sin espera leía cero.

        Los otros tres son los `BOTON:CUADRO` del corredor, y cada uno cuenta
        su número en otro reloj. Ninguno es un capricho:

            toques            en ticks, sin corrimiento. Es `--toques`, el que
                              camina un menú: los menús miran **flancos**, así
                              que sostener abajo mueve el cursor una sola vez.
            tocar             en ticks, un tick antes por `RETRASO_DE_PANTALLA`,
                              igual que `apretar_a`. Es `--tocar`, y existe
                              porque la forma de `KeyInputProc` que espera la
                              cruceta necesita un flanco de dirección a mitad
                              de una escena.
            toques_hardware   en **cuadros de hardware** desde el arranque. Es
                              `--toques-hardware`, y es el único que puede
                              apretar adentro de una pantalla que congela el
                              reloj del juego —la de ranuras del save point—:
                              ahí no hay ticks en los que caer.

        Que un flag se ignore calladito es cómo se dejó un caso en verde que no
        apretaba nada, así que los cuatro caminos valen a la vez.
        """
        presiones = {n - RETRASO_DE_PANTALLA for n in apretar_a}
        por_tick = toques_de(toques, "toques")
        por_hardware = toques_de(toques_hardware, "toques_hardware")
        con_retraso = {n - RETRASO_DE_PANTALLA: botones
                       for n, botones in toques_de(tocar, "tocar").items()}
        sosteniendo = tuple(sosteniendo)
        objetivo = self.cuadro + cuadros
        tope = (cuadros + 1) * 60
        while self.cuadro < objetivo:
            n = self.cuadro + 1
            botones = (sosteniendo + por_tick.get(n, ())
                       + con_retraso.get(n, ())
                       + por_hardware.get(self.hardware, ())
                       + (("a",) if n in presiones else ()))
            self.consola.apretar(*botones)
            self._un_cuadro()
            tope -= 1
            if tope <= 0:
                raise RuntimeError("la ROM no llegó al tick %d" % objetivo)
        return self

    def _un_cuadro(self):
        """Un cuadro de hardware, y el reloj del juego al día."""
        self.consola.correr(1)
        self.hardware += 1
        # El cuadro 0 es el tick 1: ver `TICK_DEL_CUADRO_CERO` en snes_correr.
        self.cuadro = self.palabra("vueltas") - 1 - self.llegada

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

        Reemplazó al `--switch` que tenía el conversor, que los prendía desde
        una página de prueba inventada, y es mejor por dos razones. La primera es que **la
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
