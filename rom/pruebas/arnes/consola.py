"""Una partida de la ROM corriendo, para hacerle preguntas sobre su estado.

Esto **no compara pixeles**. Las pruebas `_golden` comparan la pantalla contra
las capturas congeladas de `pruebas/golden/`, cuadro por cuadro; acá se le
pregunta a la ROM en qué mapa está, qué switch tiene prendido o qué evento está
corriendo. Son
dos redes distintas y se complementan: la de pixeles dice "la pantalla es
exactamente ésta", ésta dice "y además llegaste adonde tenías que llegar".

Lo que hace posible preguntar es que `tools/ensamblado/ensamblar.py` deja al lado de la ROM
la tabla de símbolos que sale de `runtime/` de verdad, con las direcciones de la
RAM **y** las constantes del ensamblador:

    mapa_actual 90
    BOOT_CUADROS 40
    FLAG_AUTO 2

Por eso acá no hay ninguna dirección escrita a mano. Si alguien renombra una
variable en `runtime/`, el test falla diciendo qué símbolo falta, que es
exactamente lo que se quiere: ruidoso y en el lugar. Una constante copiada a
mano se desfasaría en silencio y leería la dirección de al lado.
"""

import os
import re

import lugares                                  # antes que nada
from common import settings
from common import project
from emulator import retro
from ensamblado import bancos

RAIZ = project.root()
# Lo que las pruebas dejan para mirar. Lo toman de acá los pedazos del arnés
# que no importan de las herramientas.
SNAPSHOTS = lugares.SNAPSHOTS

# El mismo que usa el justfile por omisión. Se puede pisar con NUCLEO para
# correr las pruebas contra otro core.
NUCLEO = os.environ.get(
    "NUCLEO", "/usr/lib/libretro/snes9x_libretro.so")

# El cuadro que se ve en pantalla muestra el estado de la vuelta ANTERIOR del
# lazo principal: `flush_video` sube el OAM que armó `build_oam` la vuelta
# pasada, y por eso está al principio del lazo y no al final. De ahí sale este
# +1, que no es un ajuste sino una consecuencia del orden del lazo, en runtime/arranque.s.
#
# Con eso, para ver al héroe con N pixeles de avance hay que correr N/2 + 1
# cuadros desde que se aprieta: se mueve WALK_SPEED = 2 por cuadro. Medido en el
# mapa 73 a 40, 60 y 80 px: exacto da 0, y errarle por un cuadro para cualquier
# lado da unos 25000 pixeles de diferencia.
RETRASO_DE_PANTALLA = 1

# Los bytes de WRAM de la consola.
WRAM = 0x20000

# Cómo cuentan `muestras_en_la_aram` y `muestras_del_paquete` a un efecto de
# sonido: este número más el del efecto. Una entrada del directorio no alcanza
# para nombrarlo, porque varios efectos comparten lugar —ver
# `lugares_de_efectos` en snes_music.py—, y ninguna entrada llega a 256, así
# que no se confunde con una muestra de la música.
EFECTO = 0x100

# La marca de una ranura con partida. **No sale de la tabla de símbolos porque
# la ROM no la tiene como símbolo**: `ranura_llena` la compara con cuatro
# `cmp #` inmediatos, y `guardar_partida` la escribe igual. Sale del archivo
# de proyecto, de donde la saca el conversor. Lo que sí es símbolo es dónde
# va, `SRAM_MAGIA`.
MAGIA = settings.ascii("rom", "sram_signature", length=4).encode()


class SimboloDesconocido(KeyError):
    """Se pidió un símbolo que la ROM no tiene."""


class Simbolos:
    """La tabla que deja `tools/ensamblado/ensamblar.py`, leída por nombre."""

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
                "runtime/, renombralo también acá: la tabla se genera del "
                "assembler, así que un nombre que no está es un nombre que ya "
                "no existe." % (nombre, self.ruta)) from None


# Cuántos cuadros se le dan a la pantalla de título para llegar a su lazo antes
# de apretarle nada. No es un número medido al filo: es aire de sobra para los
# 33 KB que sube a la VRAM, y la pantalla se queda quieta hasta que alguien
# aprieta, así que pasarse no cuesta nada.
TITULO_AIRE = 30

# Las dos opciones del menú del título: "Begin the Story" y "Resume the
# Story", que abre la pantalla de ranuras y carga.
EMPEZAR, SEGUIR = 0, 1


def toques_de(pares, flag):
    """Los `BOTON:CUADRO` de una lista de toques, a {cuadro: (botones,)}.

    El número está en el reloj que diga cada lista —ver `Partida.correr`—; acá
    sólo se parte el par.
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

    `correr` avanza **ticks** apretando A donde se le diga: un toque por
    número, apretado un tick antes por `RETRASO_DE_PANTALLA`. Es la misma
    convención en un caso de pixeles y en una prueba de estado, así que una
    lista de toques sirve igual en los dos.

    Un tick es una vuelta del lazo principal, o sea un paso de lógica de RM2k.
    Normalmente es un cuadro de hardware, y se separan cuando una vuelta se
    pasa del cuadro: al entrar a Lashe City las dos primeras miden 370 y 386
    líneas de las 262 que hay. La ROM lleva la cuenta en `vueltas` y acá se la
    pregunta, en vez de suponer que un cuadro es un tick.
    """

    def __init__(self, sfc, simbolos, mapas, switches=(), titulo=None,
                 nucleo=None, caso=0, salta=False, pila=False, msu=False):
        self.simbolos = simbolos
        # El cartucho, para las tablas que no están en la RAM sino en la ROM:
        # ver `muestras_del_tema`.
        self.sfc = sfc
        # Los ids de mapa de RM2k en el orden de la tabla de la ROM, que es lo
        # que `mapa_actual` indexa. Sale del `mapdata.inc` generado y no de
        # rehacer la convención de "el de --map-id primero": ya está escrita
        # en el conversor, y una segunda copia sería una segunda manera de
        # equivocarse igual en los dos lados.
        self.mapas = mapas
        # `nucleo` es para correr la **misma** partida en dos cores y
        # comparar las dos pantallas entre sí: ver `pruebas/rpgmaker/test_cores.py`.
        # Sin él vale el de siempre, que es snes9x.
        # `msu` deja que el core encuentre las pistas al lado de la ROM: sólo
        # lo pide `video.py`, para que el video suene como la ROM que se juega.
        # Ver `retro.Console`.
        self.consola = retro.Console(sfc, nucleo or NUCLEO, msu=msu)
        # `pila` es sólo para `pruebas/rpgmaker/test_pila.py`, y va acá
        # porque acá es el único momento en que la marca llega antes del primer
        # cuadro: una línea después la ROM ya corrió el `reset`. Apagado por
        # omisión porque marcar es **inicializar memoria**, y `test_cores.py`
        # vive de que la ROM no dependa de la que no está inicializada.
        if pila:
            marcar_la_pila(self.consola)
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
        # desde el primer cuadro de juego. Contándolo, cada toque caía ciento
        # quince cuadros antes de tiempo y la escena no avanzaba.
        self.consola.run(self.simbolos["BOOT_CUADROS"])
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
        self.consola.run(3)
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
                self.consola.run(1)
            if not self.byte("fundido"):
                raise AssertionError(
                    "el caso %d empieza con un Teleport y la ROM no está "
                    "fundiendo después del primer tick" % caso)
            self._esperar_la_llegada()
        # Los cuadros de hardware corridos desde que terminó el arranque. Es el
        # reloj de los toques de `toques_hardware`, y es otro que el de los
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
            self.consola.run(1)
        else:
            raise RuntimeError("el Teleport del caso no terminó de fundir")
        apagado = self.palabra("vueltas")
        while self.palabra("vueltas") <= apagado:
            self.consola.run(1)
        self.llegada = self.palabra("vueltas") - antes

    def _bajar_y_elegir(self, cuantas):
        """`cuantas` toques de abajo y después A.

        Los botones se sueltan entre toque y toque porque estos menús miran
        **flancos**: sostener abajo no baja un renglón por cuadro, que es el
        `Input::IsTriggered` de RM2k y lo que la tanda comprueba en pixeles.
        """
        for _ in range(cuantas):
            self.consola.hold("down")
            self.consola.run(2)
            self.consola.hold()
            self.consola.run(2)
        self.consola.hold("a")
        self.consola.run(2)
        self.consola.hold()
        self.consola.run(2)

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
        self.consola.run(TITULO_AIRE)
        self._bajar_y_elegir(opcion)
        if opcion:
            self.consola.run(TITULO_AIRE)
            self._bajar_y_elegir(ranura)

    def esperar_la_pantalla_de_ranuras(self, tope=120):
        """Cuadros de hardware hasta que la pantalla de ranuras esté a la vista.

        Se mira `menu_abierto`, que la ROM pone para esto: mientras la pantalla
        se ve `vueltas` no avanza, así que esperar por ticks se colgaría.
        """
        for _ in range(tope):
            if self.byte("menu_abierto"):
                return self
            self.consola.run(1)
        raise RuntimeError(
            "la pantalla de ranuras no se abrió en %d cuadros" % tope)

    def abrir_ranuras_desde_el_titulo(self):
        """Resetea la consola, pasa el título por "Resume the Story" y se
        queda **con la pantalla de ranuras a la vista**, para mirarla.

        Es `reiniciar(SEGUIR)` cortado antes de elegir: lo que la pantalla
        muestra de cada ranura —el nombre y las caras del grupo guardado— sólo
        se puede comprobar con una partida guardada de verdad.
        """
        self._resetear()
        self.consola.run(TITULO_AIRE)
        self._bajar_y_elegir(1)
        self.consola.run(TITULO_AIRE)
        return self.esperar_la_pantalla_de_ranuras()

    def poner_grupo(self, *actores):
        """El grupo, por ids de actor, escrito en la RAM como lo dejaría un
        `ChangePartyMembers`. Es lo que la partida guarda y la pantalla de
        ranuras muestra."""
        largo = self.simbolos["GRUPO_MAX"]
        assert len(actores) <= largo
        self.consola.write_ram(self.simbolos["grupo"],
                               list(actores) + [0] * (largo - len(actores)))
        self.consola.write_ram(self.simbolos["grupo_n"],
                               [len(actores), 0])
        return self

    def imagen(self):
        """La pantalla, como la dibuja el emulador."""
        return self.consola.image()

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
        self.consola.run(TITULO_AIRE)
        if cancelar:
            self.consola.hold("b")
            self.consola.run(2)
            self.consola.hold()
        else:
            self._bajar_y_elegir(ranura)
        # Y unos ticks de aire: que la página siga y el mapa vuelva.
        self.correr(10)
        return self

    def guardar_por_el_menu(self, ranura=0):
        """Guarda en `ranura` como el jugador: B abre el menú de pausa, se baja
        hasta Save, y en la pantalla de ranuras se elige; después B cierra el
        menú. Hace falta que el héroe tenga el control, o el menú no se abre.

        **El permiso de guardar se habilita desde afuera**, y es a propósito:
        la apertura lo prohíbe con `ChangeSaveAccess` y en la ROM que se juega
        no hay otra forma de llegar a guardar temprano. Es preparación, como
        prender un switch: lo que se prueba después es que la partida vuelva,
        no el permiso —ése lo cobran las pruebas del menú—.
        """
        acceso = self.simbolos["FAR_ACCESO"]
        permiso = self.consola.ram(acceso, 1)[0]
        self.consola.write_ram(
            acceso, [permiso & ~self.simbolos["ACCESO_SIN_GUARDAR"] & 0xFF])
        self.consola.hold("b")
        self.consola.run(2)
        self.consola.hold()
        for _ in range(120):
            if self.byte("menu_abierto"):
                break
            self.consola.run(1)
        else:
            raise RuntimeError("B no abrió el menú de pausa: ¿el héroe tenía "
                               "el control?")
        self.consola.run(TITULO_AIRE)
        self._bajar_y_elegir(self.simbolos["MENU_GUARDAR"])
        # La pantalla de ranuras, arriba del menú: el menú sigue abierto
        # abajo, así que no hay bandera que esperar, y se le da el aire del
        # título, que sube más.
        self.consola.run(TITULO_AIRE)
        self._bajar_y_elegir(ranura)
        self.consola.run(TITULO_AIRE)
        self.consola.hold("b")
        self.consola.run(2)
        self.consola.hold()
        for _ in range(120):
            if not self.byte("menu_abierto"):
                break
            self.consola.run(1)
        else:
            raise RuntimeError("B no cerró el menú de pausa")
        self.correr(10)
        return self

    def _resetear(self):
        """El botón de reset y el arranque, con los relojes de la prueba en
        cero. `llegada` es la del `Teleport` del caso **antes** del reset:
        restada a un `vueltas` que arranca de nuevo, un `correr(10)` corría
        ochenta ticks.

        **La WRAM se pisa antes**, con el `$55` con que snes9x la enciende:
        el reset del core la deja como estaba —igual que el de la consola—, así
        que un valor que la carga no repusiera seguía ahí y la prueba de "viaja
        en la partida" pasaba igual. La ROM no la limpia entera al arrancar:
        inicializa variable por variable. Así lo que sobrevive es lo que vino
        de la SRAM o lo que el arranque escribió, como al prender la consola.
        """
        self.consola.write_ram(0, bytes([0x55]) * WRAM)
        self.consola.reset()
        self.cuadro = 0
        self.llegada = 0
        self.hardware = 0
        self.consola.run(self.simbolos["BOOT_CUADROS"])

    def reiniciar(self, opcion=None, ranura=0):
        """El botón de reset: la SRAM del cartucho sobrevive y la WRAM no.

        Es la única forma honesta de probar que una partida guardada se carga:
        volver a arrancar la consola de verdad, con el mismo cartucho, y mirar
        dónde queda parada. Escribirle la RAM a mano probaría otra cosa.

        Con pantalla de título hay que volver a elegir, y `opcion` dice qué:
        sin ella es "Resume the Story" en la ranura `ranura`, que es lo que
        hace un cartucho sin título al arrancar —cargar la partida solo—. Así
        una prueba de "viaja en la partida" dice lo mismo en los dos.
        """
        self._resetear()
        elegir = opcion
        if elegir is None and self.titulo is not None:
            elegir = SEGUIR
        if elegir is not None:
            self.pasar_el_titulo(elegir, ranura)
        # Empezar de nuevo desde el título arranca con la WRAM limpia, y la
        # página de prueba se elige otra vez como al encender. Cargar no:
        # la variable vuelve con la partida, y sin título el arranque carga
        # la partida solo.
        if elegir == EMPEZAR:
            self._elegir_el_caso()
        self.consola.run(3)
        return self

    def _elegir_el_caso(self):
        """Escribe la variable que elige la página de prueba, con el refresco
        que la hace mirar. El 0 es el que no pide nada."""
        if self.caso:
            self.consola.write_ram(
                self.simbolos["FAR_VARIABLES"]
                + 2 * self.simbolos["CASO_RANURA"],
                [self.caso & 0xFF, self.caso >> 8])
            self.consola.write_ram(self.simbolos["refresco"], [1])

    def sram(self, direccion=0, largo=None):
        """La SRAM del cartucho, que es lo que un frontend vuelca a un `.srm`."""
        return self.consola.sram(direccion, largo)

    def poner_sram(self, direccion, datos):
        """Escribe la SRAM del cartucho, como si trajera el `.srm` de otro
        build."""
        self.consola.write_sram(direccion, datos)

    def magia(self, ranura=0):
        """Los cuatro bytes de la marca de la ranura, en la SRAM."""
        return self.sram(self.simbolos["SRAM_MAGIA"]
                         + ranura * self.simbolos["SRAM_STRIDE"], 4)

    def hay_partida(self, ranura=0):
        """Si la ranura tiene una partida guardada: si lleva la marca."""
        return self.magia(ranura) == MAGIA

    def correr(self, cuadros, apretar_a=(), sosteniendo=(), toques=(),
               toques_hardware=(), tocar=()):
        """Avanza `cuadros` **ticks**. `apretar_a` son toques de A, por número.

        El botón se sostiene mientras dure el tick: la ROM lee el pad una vez
        por vuelta, así que si la vuelta se estira sigue siendo un solo flanco.

        `sosteniendo` son los que quedan apretados **todos** los cuadros. Hace
        falta porque esto suelta el pad en cada vuelta: un `consola.hold(...)` de afuera se
        perdía en el primer cuadro, y `KeyInputProc` sin espera leía cero.

        Los otros tres son listas de `BOTON:CUADRO`, y cada uno cuenta
        su número en otro reloj. Ninguno es un capricho:

            toques            en ticks, sin corrimiento. Es el que camina un
                              menú: los menús miran **flancos**, así que
                              sostener abajo mueve el cursor una sola vez
                              —hasta los 23 cuadros, cuando empieza la
                              repetición de `flechas_repetir`—.
            tocar             en ticks, un tick antes por `RETRASO_DE_PANTALLA`,
                              igual que `apretar_a`. Existe porque la forma de
                              `KeyInputProc` que espera la cruceta necesita un
                              flanco de dirección a mitad de una escena.
            toques_hardware   en **cuadros de hardware** desde el arranque. Es
                              el único que puede apretar adentro de una
                              pantalla que congela el reloj del juego —la de
                              ranuras del save point—: ahí no hay ticks en los
                              que caer.

        Que una lista se ignore calladita es cómo se dejó un caso en verde que no
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
            self.consola.hold(*botones)
            self._un_cuadro()
            tope -= 1
            if tope <= 0:
                raise RuntimeError("la ROM no llegó al tick %d" % objetivo)
        return self

    def _un_cuadro(self):
        """Un cuadro de hardware, y el reloj del juego al día."""
        self.consola.run(1)
        self.hardware += 1
        # El cuadro 0 es el tick 1.
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
    # `"mapa_actual"`, así que renombrar la variable en `runtime/` se arregla en
    # una línea y no en veinte.

    def byte(self, nombre):
        return self.consola.ram(self.simbolos[nombre], 1)[0]

    def palabra(self, nombre):
        bajo, alto = self.consola.ram(self.simbolos[nombre], 2)
        return bajo | (alto << 8)

    # Hay dos toques, y el nombre dice con qué reloj cuenta cada uno. Afuera
    # de ellos quedan dos a propósito: `Grabador.tocar_cuadros` en
    # `test_fundido_de_pelea.py`, que es este mismo toque pero fotografiando
    # cada cuadro, y `_tocar_cuadros` en `test_pila.py`, que no tiene
    # `Partida` y aprieta un cuadro solo.

    def tocar_ticks(self, *botones):
        """Un toque en ticks: un tick apretados y uno suelto, que es el flanco
        que la ROM mira.

        Es el toque del mapa: el de ahora, sin agendar —las listas de `correr`
        los ponen en un tick dado de antemano—, para ir tocando a medida que
        se mira el estado —el cursor de `ShowChoice`, un mensaje—. **No sirve
        con una pantalla que congela el reloj** —el menú, la tienda, la pelea,
        el título—: ahí `vueltas` no avanza y el segundo tick no llega nunca.
        Para ésas está `tocar_cuadros`.
        """
        self.consola.hold(*botones)
        self._un_tick()
        self.consola.hold()
        self._un_tick()
        return self

    def tocar_cuadros(self, boton, aire=4):
        """Un toque en cuadros de hardware: dos cuadros apretado y `aire`
        sueltos.

        Es el de las pantallas que congelan el reloj del juego —el menú de
        pausa y lo que se abre desde él, la tienda, la pelea, la pantalla de
        ranuras—. Hasta el 2026-09-26 la pelea tenía el suyo, que dejaba
        apretado tantos cuadros como de aire; se unificó con éste porque
        ninguna de las pruebas que lo usaban cambió de resultado, y ninguna
        compara contra una golden.
        """
        self.consola.hold(boton)
        self.consola.run(2)
        self.consola.hold()
        self.consola.run(aire)
        return self

    def sostener(self, ticks, *botones):
        """Los botones apretados durante `ticks` vueltas; quedan apretados
        hasta `soltar` o hasta lo próximo que apriete.

        Es la caminata con el pad, contada desde ahora y no agendada como las
        listas de `correr`. Lo que se pregunta después es lo que la ROM tenía
        con el botón todavía apretado en la última vuelta.
        """
        self.consola.hold(*botones)
        for _ in range(ticks):
            self._un_tick()
        return self

    def soltar(self):
        self.consola.hold()
        return self

    def velocidad_del_heroe(self):
        """La velocidad de RM2k del héroe, de 1 a 6, leída de la RAM lejana."""
        return self.consola.ram(self.simbolos["FAR_HERO_VEL"], 1)[0]

    def poner_velocidad_del_heroe(self, velocidad):
        """Lo que una ruta con 28 o 29 le deja al héroe, sin correr la ruta."""
        self.consola.write_ram(self.simbolos["FAR_HERO_VEL"], [velocidad])
        return self

    def poner_byte(self, nombre, valor):
        """Escribe un byte de la RAM de la ROM, por nombre de símbolo.

        Es para poner a la partida en un estado al que llegar jugando costaría
        media hora: `saltos_restantes` bajo, por ejemplo, que es lo que deja una
        partida larga. Lo que se escribe acá **no** es una aserción: se escribe
        el estado y después se le pregunta a la ROM qué hace con él.
        """
        self.consola.write_ram(self.simbolos[nombre], [valor])
        return self

    def heroe(self):
        """La celda donde está el héroe, (x, y). A mitad de un paso es la de
        los pixeles, o sea la de salida hasta que llega."""
        return (self.palabra("hero_x") // 16, self.palabra("hero_y") // 16)

    def evento(self, indice):
        """La celda (x, y) donde la ROM tiene ahora al evento `indice` de su
        tabla: desde cero, en el orden de los ids del mapa."""
        base = self.simbolos["ev_pos_buf"] + indice * self.simbolos["EV_STRIDE"]
        b = self.consola.ram(base, 4)
        return (b[0] | (b[1] << 8), b[2] | (b[3] << 8))

    def oro(self):
        b = self.consola.ram(self.simbolos["oro"], 3)
        return b[0] | (b[1] << 8) | (b[2] << 16)

    def poner_oro(self, cuanto):
        self.consola.write_ram(self.simbolos["oro"],
                               [cuanto & 0xFF, (cuanto >> 8) & 0xFF,
                                (cuanto >> 16) & 0xFF])
        return self

    # Los HP y los SP **de la partida**: `FAR_HP` y `FAR_SP`, una palabra por
    # número de actor. Es lo que guarda la SRAM, lo que dibuja el menú y lo que
    # tocan `FullHeal` y la posada. Los de adentro de una pelea son otros —uno
    # por puesto de combatiente, `Pelea.hp_del_combatiente`— y llegan acá
    # recién cuando `modo_fin` los copia al terminar.

    def hp(self, actor):
        return self._palabra_del_actor("FAR_HP", actor)

    def poner_hp(self, actor, valor):
        return self._poner_palabra_del_actor("FAR_HP", actor, valor)

    def sp(self, actor):
        return self._palabra_del_actor("FAR_SP", actor)

    def poner_sp(self, actor, valor):
        return self._poner_palabra_del_actor("FAR_SP", actor, valor)

    def _palabra_del_actor(self, tabla, actor):
        bajo, alto = self.consola.ram(self.simbolos[tabla] + 2 * actor, 2)
        return bajo | (alto << 8)

    def _poner_palabra_del_actor(self, tabla, actor, valor):
        self.consola.write_ram(self.simbolos[tabla] + 2 * actor,
                               [valor & 0xFF, valor >> 8])
        return self

    def equipo(self, actor):
        """Las cinco ranuras de equipo del actor, leídas de `FAR_EQUIPO`."""
        datos = self.consola.ram(self.simbolos["FAR_EQUIPO"] + actor * 10, 10)
        return [datos[2 * r] | (datos[2 * r + 1] << 8) for r in range(5)]

    def celdas_mal_dibujadas(self):
        """Las celdas de la ventana que no coinciden con lo que dibuja un
        `fill_window` en el mismo lugar, y la foto de antes.

        Teletransporta a la partida a la celda donde ya está, que es lo que
        hace que la ROM rearme la ventana entera por su propio camino —y por
        eso **repara** lo que encuentre: adentro de una jugada, lo que venga
        después ya no lo ve—. Vale sólo con la cámara quieta y el pan de
        vuelta en cero: si no, el teletransporte la deja en otro lado y la
        comparación no compararía lo mismo. Eso se cobra acá.
        """
        antes = self.ventana()
        camara = (self.palabra("camara_x"), self.palabra("camara_y"))
        self.ir_al_mapa(self.mapa(), self.palabra("tile_x"),
                        self.palabra("tile_y"))
        self.correr(10)
        assert (self.palabra("camara_x"), self.palabra("camara_y")) == camara, (
            "el teletransporte dejó la cámara en %s y antes estaba en %s: la "
            "referencia no sirve" % ((self.palabra("camara_x"),
                                      self.palabra("camara_y")), camara))
        despues = self.ventana()
        return [c for c in antes if antes[c] != despues[c]], antes

    def mapa(self):
        """En qué mapa de RM2k está parada la partida."""
        indice = self.palabra("mapa_actual")
        if indice >= len(self.mapas):
            raise AssertionError(
                "la ROM dice estar en el mapa índice %d y su tabla tiene %d: "
                "%s" % (indice, len(self.mapas), self.mapas))
        return self.mapas[indice]

    def ventana(self):
        """Qué celda del mapa hay dibujada en cada lugar de la pantalla.

        La ventana del tilemap es un toro: la celda `(mx, my)` del mapa vive
        siempre en la ranura `(mx mod 64, my mod 32)` de la VRAM. Así que para
        saber si lo dibujado corresponde con el mapa no alcanza con mirar la
        pantalla —dos filas corridas se ven como un mapa plausible—: hay que ir
        a la VRAM y preguntarle a cada ranura qué celda dice tener.

        Devuelve `{(mx, my): (fondo, encima)}` de las celdas que la pantalla
        toca y que caen adentro del mapa. Lo de afuera de la vista queda
        afuera a propósito: ahí el streaming pisa ranuras que nadie mira, y
        cobrarlas sería cobrar algo que no se ve.
        """
        win_col = self.palabra("win_col")
        win_row = self.palabra("win_row")
        ancho = self.palabra("mapa_cw")
        alto = self.palabra("mapa_ch")
        cols, filas = self.simbolos["WINDOW_COLS"], self.simbolos["WINDOW_ROWS"]
        # Las dos pantallas de 32x32 del tilemap no son contiguas: la de la
        # derecha vive 1024 palabras más adelante, que es como las escribe
        # `push_strips`. Dónde está el del fondo depende del reparto del mapa,
        # y la ROM lo deja en `FAR_VRAM_MAPA`.
        bajo, alto_ = self.consola.ram(
            en_la_wram(self.simbolos["FAR_VRAM_MAPA"]), 2)
        fondo = self.consola.vram(bajo | (alto_ << 8), 32 * 32 * 2)
        encima = self.consola.vram(self.simbolos["VRAM_ABOVE_MAP"], 32 * 32 * 2)
        visto = {}
        for my in range(win_row, win_row + self.simbolos["VIEW_ROWS"]):
            if my >= alto:
                break
            for mx in range(win_col, win_col + self.simbolos["VIEW_COLS"]):
                if mx >= ancho:
                    break
                ranura = (my % filas) * 32 + (mx % 32)
                if (mx % cols) >= 32:
                    ranura += 1024
                visto[(mx, my)] = (fondo[ranura], encima[ranura])
        return visto

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
            self.consola.write_ram(direccion, [octeto])
        self.consola.write_ram(self.simbolos["refresco"], [1])
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
            self.consola.write_ram(direccion, [octeto & 0xFF])
        self.consola.write_ram(self.simbolos["refresco"], [1])
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
        self.consola.write_ram(self.simbolos["fundido_mapa"],
                               [indice & 0xFF, indice >> 8])
        for nombre, valor in (("entrada_x", x), ("entrada_y", y)):
            self.consola.write_ram(self.simbolos[nombre],
                                   [valor & 0xFF, valor >> 8])
        # `empezar_fundido`, desde afuera: qué fundido es, que hay uno, y el
        # reloj, que son **vueltas del lazo** —ticks— desde el 2026-09-08. Con
        # `boot_cuadros`, que es lo que decía antes, la resta daba cualquier
        # cosa y el fundido no terminaba nunca: la partida se quedaba en el
        # mapa de arranque y catorce pruebas fallaban sin decir por qué.
        self.consola.write_ram(self.simbolos["fundido_que"],
                               [self.simbolos["FUNDIDO_PUERTA"]])
        self.consola.write_ram(self.simbolos["fundido"], [1])
        self.consola.write_ram(self.simbolos["fundido_base"],
                               [self.palabra("vueltas") & 0xFF])
        # Y la pantalla se destiñe, que es lo único que este salto hace y una
        # puerta de verdad no.
        #
        # El tinte **sobrevive al cambio de mapa**, y con razón: es lo que hace
        # RM2k. Pero saltar acá no es cruzar una
        # puerta: es aparecer en un mapa al que la partida no llegó jugando, sin
        # haber corrido las páginas que en el juego habrían dejado la pantalla
        # como corresponde. Con el mapa de arranque de las demos, que tiñe de
        # azul en su cinemática, eso dejaba el mapa entero azul y parecía el
        # defecto que uno estaba buscando: costó una hora el 2026-09-13. Con
        # `tinte=False` se conserva, para una prueba que quiera justamente
        # mirar que sobrevive.
        if tinte:
            for nombre in ("tinte_r", "tinte_g", "tinte_b", "tinte_s"):
                self.consola.write_ram(self.simbolos[nombre],
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
        self._resetear()
        self.consola.run(TITULO_AIRE)
        return self

    def muestras_en_la_aram(self):
        """Qué muestras dice la ROM tener subidas al SPC700.

        Es `FAR_ARAM_DE`, una palabra por muestra con dónde quedó cada una en
        la ARAM, o cero si no está: la lee `paquete_cargar` y la escribe
        `colocar_muestra`. Un número que **no** está acá es una muestra cuya
        entrada del directorio del SPC700 apunta al silencio, o sea una nota
        que no suena.

        Las entradas desde `SE_PRIMERA` son lugares que comparten los
        efectos, así que la entrada sola no dice cuál está: de ésas sale el
        efecto anotado en `FAR_EFECTO_EN`, como `EFECTO + su número`, que es
        como los cuenta `muestras_del_paquete`.
        """
        s = self.simbolos
        n = s["MUESTRAS_N"]
        crudo = self.consola.ram(en_la_wram(s["FAR_ARAM_DE"]), 2 * n)
        anotados = self.consola.ram(en_la_wram(s["FAR_EFECTO_EN"]),
                                    max(1, s["SE_LUGARES"]))
        return {i if i < s["SE_PRIMERA"]
                else EFECTO + anotados[i - s["SE_PRIMERA"]]
                for i in range(n) if crudo[2 * i] | (crudo[2 * i + 1] << 8)}

    def muestras_del_tema(self, indice):
        """Qué muestras necesita el tema, leídas de `tema_muestras` **en el
        cartucho**.

        Es la misma tabla que mira `tema_asegurar`, y se lee de la ROM en vez
        de recalcularla con `snes_music.muestras_del_tema`: recalcularla
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

    def muestras_del_paquete(self, indice):
        """(los temas, las muestras de sus efectos) del paquete de audio
        `indice` —el de un mapa, en el orden de la tabla de mapas—, leídos de
        `paquetes` en el cartucho, que es lo que recorre `paquete_cargar_ya`:
        un índice de desplazamientos de dos bytes y detrás, por paquete,
        cuatro listas cerradas con $FF. La tercera, los temas de salida, la
        da `temas_de_salida`, y la cuarta `temas_aparte`: ésos no tienen por
        qué estar. Los efectos van
        como `EFECTO + su número`: ver `muestras_en_la_aram`."""
        temas, efectos = self._listas_del_paquete(indice)[:2]
        return temas, [EFECTO + e for e in efectos]

    def temas_de_salida(self, indice):
        """Los temas de salida del paquete `indice`: los que el mapa prende
        sólo para irse, que se suben si hay lugar. Ver `extra_de_salida` en
        runtime/paquete_de_audio.s."""
        return self._listas_del_paquete(indice)[2]

    def temas_aparte(self, indice):
        """Los temas aparte del paquete `indice`: los que su `PlayBGM` sube
        solos con los efectos del paquete. Ver `extra_aparte` en
        runtime/paquete_de_audio.s."""
        return self._listas_del_paquete(indice)[3]

    def _listas_del_paquete(self, indice):
        with open(self.sfc, "rb") as archivo:
            rom = archivo.read()
        base = en_la_rom(self.simbolos["paquetes"])
        salto = base + 2 * indice
        lista = base + (rom[salto] | (rom[salto + 1] << 8))
        partes = []
        for _ in range(4):
            parte = []
            while rom[lista] != 0xFF:
                parte.append(rom[lista])
                lista += 1
            partes.append(parte)
            lista += 1
        return tuple(partes)

    def stream_del_tema(self, indice):
        """(dirección del stream, sus sonidos) del tema, leídos **del
        cartucho** con las mismas tablas que usa `music_start_ya`: `tema_lo`,
        `tema_hi` y `tema_bk`, y `tema_sonidos` dentro de `musica_sonidos`."""
        s = self.simbolos
        with open(self.sfc, "rb") as archivo:
            rom = archivo.read()
        lo, hi, bk = (rom[en_la_rom(s[t] + indice)]
                      for t in ("tema_lo", "tema_hi", "tema_bk"))
        base = en_la_rom(s["tema_sonidos"] + 2 * indice)
        desde = en_la_rom(s["musica_sonidos"]) + (rom[base] | rom[base + 1] << 8)
        sonidos = [tuple(rom[desde + 6 * i:desde + 6 * i + 6])
                   for i in range(256)]
        return lo | hi << 8 | bk << 16, sonidos

    def escrituras_del_tema(self, indice):
        """Lo que el stream del tema le escribe al DSP, (cuadro, registro,
        valor), una vuelta: sus bytes en el cartucho, decodificados con
        `snes_music.decodificar`, que es el modelo de `music_frame`."""
        from audio import snes_music
        direccion, sonidos = self.stream_del_tema(indice)
        with open(self.sfc, "rb") as archivo:
            rom = archivo.read()
        return snes_music.decodificar(DelCartucho(rom, direccion), sonidos)

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


# --- la pila, marcada para poder medirla ------------------------------------
#
# La pila arranca en `$1FFF` —el `ldx #$1FFF` / `txs` del `reset`— y crece hacia
# abajo, hacia la BSS. Lo que se le reserva es `bancos.PILA`, así que el byte más
# bajo que le toca es `TOPE_DE_LA_PILA - PILA`. Los dos números salen del mapa de
# memoria y no están copiados: si `PILA` cambia, la medición cambia con él.
TOPE_DE_LA_PILA = 0x2000


def marca_de(direccion):
    """El centinela que le toca a ese byte de la pila.

    **Cambia con la dirección a propósito.** Con un valor único, un `pha` que
    empujara justo ese valor dejaría el byte igual y la medición diría que la
    pila no llegó ahí; con uno distinto por dirección, un valor empujado puede
    esconder **un** byte y no una tirada entera.
    """
    return (0xA5 ^ direccion) & 0xFF


def marcar_la_pila(consola):
    """Llena la zona de la pila con los centinelas.

    Se llama **antes del primer `retro_run`**, que es lo que hace que esto mida
    desde el `reset` sin costarle un byte a la ROM: el core ya cargó el cartucho
    pero todavía no ejecutó una instrucción, así que todo lo que aparezca abajo
    de `$2000` lo escribió la ROM.
    """
    fondo = TOPE_DE_LA_PILA - bancos.PILA
    consola.write_ram(fondo, bytes(marca_de(fondo + i)
                                   for i in range(bancos.PILA)))


def hondura_de_la_pila(consola):
    """Cuántos bytes bajó la pila: el byte más bajo que dejó de ser su marca.

    Es una marca de agua, no una foto: nadie repone los centinelas, así que lo
    que se lee al final de la partida es lo más honda que la pila estuvo en toda
    la corrida, no dónde está ahora.

    Cero quiere decir que la pila no bajó **ni un byte**, o sea que la marca no
    llegó, no que la ROM no use la pila. Quien mida tiene que cobrar eso: es la
    forma de que esta medición pase en vacío.
    """
    fondo = TOPE_DE_LA_PILA - bancos.PILA
    crudo = consola.ram(fondo, bancos.PILA)
    for i, byte in enumerate(crudo):
        if byte != marca_de(fondo + i):
            return TOPE_DE_LA_PILA - (fondo + i)
    return 0


def en_la_wram(direccion):
    """De una dirección larga del banco $7E al desplazamiento que pide
    `retro.Console.ram`.

    Las de la RAM lejana están escritas de las dos maneras en `runtime/ram_lejana.s` —unas
    con el banco adelante (`$7E3100`) y otras sin él (`$2600`)—, así que el
    símbolo se enmascara en vez de suponerse.
    """
    return direccion & 0x1FFFF


def indice_del_tema(una, nombre):
    """El índice del tema en el cartucho, leído de la cabecera del
    `musicdata.inc` que se armó con él: `; Temas: a, b, …`, en el orden de
    `Temas`."""
    inc = os.path.join(os.path.dirname(una.sfc), "musicdata.inc")
    with open(inc) as archivo:
        for linea in archivo:
            if linea.startswith("; Temas: "):
                nombres = linea[len("; Temas: "):].strip().split(", ")
                break
        else:
            raise AssertionError("no encontré la lista de temas en %s" % inc)
    assert nombre in nombres, (
        "el cartucho no lleva %s: el conversor no le pidió el tema al mapa"
        % nombre)
    return nombres.index(nombre)


class DelCartucho:
    """Los bytes del cartucho desde `direccion`, como una secuencia. En LoROM
    el byte que sigue a $xxFFFF está en $(xx+1)8000, que en el archivo es el
    siguiente, así que alcanza con el desplazamiento: es el salto de banco de
    `advance` en runtime/musica.s, visto desde el archivo."""

    def __init__(self, rom, direccion):
        self.rom, self.base = rom, en_la_rom(direccion)

    def __getitem__(self, i):
        return self.rom[self.base + i]


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
