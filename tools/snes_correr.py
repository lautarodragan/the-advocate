#!/usr/bin/env python3
"""Corre la ROM en un core de libretro y guarda lo que dibuja.

El reemplazo de `rom/screenshot.sh`. Aquél levanta un servidor X, arranca
mednafen, duerme unos segundos de reloj, le manda teclas con xdotool, le saca
una foto a la pantalla entera y después la recorta. Acá no hay nada de eso:
`retro_run()` avanza un cuadro exacto, la cruceta se contesta cuadro por cuadro
y el framebuffer sale del callback ya en 256x224.

La diferencia que importa no es la velocidad sino que **la prueba deja de
depender del reloj**. Cuántos cuadros llegaba a emular mednafen en N segundos
dependía de la carga de la máquina; acá N cuadros son N cuadros. Eso es lo que
hacía que la tanda repartida en procesos pudiera dar rojos falsos.

Las teclas se mantienen apretadas desde que termina el arranque hasta el final,
que es lo que hacía screenshot.sh y lo que la referencia modela: camina hasta
chocar contra la pared.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from retro import Consola, CORE

# Cuántos cuadros se le dan a la ROM antes de apretar nada y de empezar a
# contar. Desde el 2026-09-05 el arranque de la ROM dura siempre lo mismo
# —BOOT_CUADROS en main.s más tres—, así que con este número el cuadro N de la
# captura muestra el tick N de la referencia, en cualquier mapa. Antes cada
# receta llevaba un número medido a mano que se corría con cada cambio de
# código o de datos.
#
# Eran 67 hasta el 2026-09-06. Subió a 115 cuando el cartucho pasó a llevar
# varios temas: el banco de muestras es uno solo para todos y creció, y subirlo
# al SPC700 va byte a byte con acuse. El porqué del 112 de BOOT_CUADROS está
# en main.s.
ARRANQUE = 115

# Cuánto se corre de más después de los cuadros que dice el plan. La ROM llega
# uno o dos cuadros después de `pasos x 8` —el pad se lee una vez por cuadro y
# el primero se pierde, y según la dirección la cámara termina de acomodarse un
# cuadro más tarde—, así que el plan solo se queda corto. Ocho es una celda
# entera: alcanza de sobra y sigue siendo un número exacto de cuadros, no una
# holgura de reloj. Medido en el mapa 73: right y up llegan en +1, left y down
# en +2.
MARGEN = 8

# Cuántos cuadros seguidos idénticos cuentan como "la pantalla se quedó quieta".
QUIETO = 4

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


def simbolos(rom):
    """La tabla que `w65.py` deja al lado de la ROM. Sin ella no hay reloj de
    ticks: una ROM armada a mano no tiene por qué tenerla."""
    try:
        with open(rom + ".sym") as handle:
            return dict(linea.split() for linea in handle if linea.strip())
    except OSError:
        return {}


class Reloj:
    """El tiempo del juego, contado en **ticks** y no en cuadros de hardware.

    Un tick es una vuelta del lazo principal de la ROM, o sea un paso de lógica
    de RM2k: el `while (Game_Clock::NextGameTimeStep())` de easyrpg, donde la
    lógica va a DEFAULT_FPS y el dibujo a lo que la máquina aguante. La
    referencia cuenta ticks —una llamada a `Interprete.cuadro()` cada uno— así
    que la comparación tiene que mirar el mismo reloj.

    Antes esto contaba cuadros de hardware y daba lo mismo, porque una vuelta
    entraba siempre en un cuadro. Dejó de dar lo mismo cuando aparecieron los
    eventos paralelos: al entrar a Lashe City las dos primeras vueltas miden 370
    y 386 líneas de las 262 que hay, así que la ROM se atrasa dos cuadros y la
    captura mostraba dos ticks antes de lo que se le pedía. **El atraso no es un
    error de cuentas**: la ROM computa la misma secuencia de estados, sólo que
    más tarde, igual que RPG_RT en una máquina lenta. Lo que hay que separar es
    el reloj del juego del reloj de pared, y eso es esto; cuánto se atrasó lo
    dice `cuadros_perdidos`, que es la otra pregunta.

    `retro_run()` no sabe de ticks —avanza un cuadro y no recibe nada— así que
    se avanza de a un cuadro preguntándole a la ROM en cuál va. Leerlo es
    barato: `ram()` devuelve un puntero a la memoria del core, no una copia.
    """

    # Si una vuelta no termina nunca, avanzar por ticks colgaría el arnés.
    CUADROS_POR_TICK = 60

    # El cuadro N de la referencia es el tick **N+1** de la ROM, y el número no
    # se muestrea: se fija. Medido en los mapas 6 y 7, que no pierden ningún
    # cuadro, `vueltas` vale 1 justo cuando termina el arranque, que es donde la
    # referencia pone su cuadro 0. Muestrearlo era el error de la primera
    # versión: en el mapa 8 los cuadros que se pierden caen **adentro** de la
    # ventana del arranque, así que la muestra daba 0 y todo quedaba corrido uno.
    TICK_DEL_CUADRO_CERO = 1

    def __init__(self, consola, rom, contador=True):
        self.consola = consola
        if consola.cuadro is None:
            # Todavía no corrió ni un cuadro, así que el reset tampoco: la RAM
            # es la basura con que arranca el emulador —snes9x la llena de
            # $55— y el contador leería 21845. Pasa con `--arranque 0`, que es
            # como corre `snes-espera`.
            consola.correr(1)
        self.direccion = None
        # Los cuadros corridos, para el respaldo: **bsnes no expone la WRAM**
        # —`retro_get_memory_data` devuelve nulo— así que ahí no hay contador
        # que leer y se cuentan cuadros, que es lo que se hacía antes y sigue
        # valiendo mientras la ROM no se atrase. Los casos que cruzan
        # emuladores corren mapas livianos justamente por eso.
        self.corridos = 0
        # Con `contador` en falso se cuentan cuadros de hardware aunque la ROM
        # tenga el símbolo. Es lo que hace falta para mirar la **pantalla de
        # título**: ahí `vueltas` no avanza —es el reloj del juego, y el título
        # no es el juego, así que una ROM con título corre el mapa igual que
        # una sin él y las dos referencias siguen siendo comparables— de modo
        # que esperar a que llegue a un cuadro no termina nunca.
        direccion = simbolos(rom).get("vueltas") if contador else None
        if direccion is not None:
            try:
                self.direccion = int(direccion)
                self.tick()
            except (ValueError, RuntimeError):
                self.direccion = None

    def hay(self):
        """Si esta ROM lleva el contador."""
        return self.direccion is not None

    def tick(self):
        """Cuántas vueltas dio el lazo principal."""
        if self.direccion is None:
            return 0
        b = self.consola.ram(self.direccion, 2)
        return b[0] | (b[1] << 8)

    def cuadro(self):
        """En qué cuadro **de la referencia** está la ROM."""
        if self.direccion is None:
            return self.corridos
        return self.tick() - self.TICK_DEL_CUADRO_CERO

    def paso(self):
        """Un cuadro de hardware."""
        self.consola.correr(1)
        self.corridos += 1

    def avanzar(self, hasta, antes=None):
        """Corre hasta que el juego llegue al cuadro `hasta` de la referencia.

        `antes(n)` se llama antes de cada cuadro de hardware con el número de
        cuadro de la referencia que la ROM está por correr, y es donde se
        aprieta el pad: la ROM lo lee una vez por vuelta, así que si la vuelta
        se estira el botón se sostiene los cuadros que haga falta y el flanco
        sigue siendo uno solo.
        """
        tope = (hasta + 2) * self.CUADROS_POR_TICK
        while self.cuadro() < hasta:
            if antes is not None:
                antes(self.cuadro() + 1)
            self.paso()
            tope -= 1
            if tope <= 0:
                raise RuntimeError(
                    "la ROM no llegó al cuadro %d: se colgó o va lentísima"
                    % hasta)


def cuadros_perdidos(consola, rom):
    """Cuántos cuadros perdió el lazo principal de la ROM, leído de su WRAM.

    La ROM los cuenta en `cuadros_perdidos` —ver `contar_perdidos` en main.s—
    y la dirección sale de la tabla de símbolos que w65.py deja al lado de la
    ROM, `<rom>.sym`. Sin tabla no se dice nada: una ROM armada a mano no
    tiene por qué tenerla. Es un dato en la salida, no una aserción: los
    saltos de mapa pierden cuadros hoy, y la comparación ya los cobra.
    """
    try:
        with open(rom + ".sym") as handle:
            simbolos = dict(linea.split() for linea in handle if linea.strip())
        direccion = int(simbolos["cuadros_perdidos"])
    except (OSError, KeyError, ValueError):
        return ""
    try:
        perdidos = consola.ram(direccion, 1)[0]
    except RuntimeError:
        return ""
    return ", %d cuadro(s) perdido(s)" % perdidos if perdidos else ""


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("rom")
    parser.add_argument("-o", "--output", required=True,
                        help="dónde va el PNG. Con varias direcciones tiene "
                             "que llevar un {} donde va la dirección")
    parser.add_argument("--walk", nargs="+", default=["none"],
                        help="las direcciones a correr; `none` es sin apretar "
                             "nada")
    parser.add_argument("--cuadros", type=int, default=480,
                        help="cuántos cuadros con la cruceta apretada")
    parser.add_argument("--arranque", type=int, default=ARRANQUE,
                        help="cuántos cuadros antes de apretar nada")
    parser.add_argument("--teclas", nargs="*", default=None, metavar="BOTON",
                        help="una sola corrida manteniendo estos botones. Es "
                             "la forma de pedir dos a la vez —`right down`— "
                             "que --walk no cubre. Sin botones, no aprieta "
                             "nada")
    parser.add_argument("--avance", type=int, default=None, metavar="PX",
                        help="capturar a mitad de camino, cuando el héroe lleva "
                             "andados estos pixeles. Los cuadros salen de la "
                             "cuenta, no de un número suelto")
    parser.add_argument("--plan", help="el archivo que escribe snes_expect.py "
                        "con --plan: por dirección, cuántas celdas camina el "
                        "héroe y cuántos cuadros le lleva. Con esto los "
                        "cuadros salen de la referencia y no de un número "
                        "elegido a ojo, y --cuadros pasa a ser sólo el tope")
    parser.add_argument("--margen", type=int, default=MARGEN,
                        help="cuadros de más sobre lo que dice el plan")
    parser.add_argument("--quieto", type=int, default=QUIETO,
                        help="cuántos cuadros idénticos seguidos cuentan como "
                             "pantalla quieta")
    parser.add_argument("--apretar-a", type=int, nargs="+", default=None,
                        metavar="N",
                        help="apretar A en estos cuadros, un cuadro cada vez, "
                             "que es lo que cierra una ventana de mensaje. Los "
                             "números se cuentan desde que termina el "
                             "arranque, igual que los de la referencia, y son "
                             "los mismos que se le pasan a snes_expect.py con "
                             "--apretar-a")
    parser.add_argument("--toques", nargs="*", metavar="BOTON:CUADRO",
                        help="toques sueltos: el botón se aprieta en ese "
                             "cuadro y se suelta en el siguiente. Es lo que "
                             "hace falta para caminar un menú, que mira "
                             "flancos y no estados, y que por eso no se puede "
                             "recorrer con --teclas")
    parser.add_argument("--toques-hardware", nargs="*", metavar="BOTON:CUADRO",
                        help="como --toques, pero el cuadro se cuenta en "
                             "cuadros de hardware desde --arranque y no en "
                             "ticks. Es para apretar adentro de una pantalla "
                             "que congela el reloj del juego —la de ranuras "
                             "abierta por el save point— mientras la captura "
                             "sigue esperando un tick: los toques por tick no "
                             "pueden caer ahí, porque ahí no hay ticks")
    parser.add_argument("--sin-contador", action="store_true",
                        help="cuenta cuadros de hardware en vez de leer\n"
                             "`vueltas` de la WRAM. Hace falta para la\n"
                             "pantalla de título, donde el reloj del juego no\n"
                             "corre: sin esto el arnés espera para siempre a\n"
                             "que la ROM llegue a un cuadro que nunca va a\n"
                             "contar.")
    parser.add_argument("--core", default=CORE,
                        help="el .so del core de libretro. Andan los tres "
                             "que hay instalados y dibujan lo mismo a 15 bits; "
                             "el default es snes9x porque es 23 veces más "
                             "rápido")
    args = parser.parse_args()

    # Los toques: un botón apretado en un cuadro y soltado en el siguiente. Es
    # lo que hace falta para caminar un menú —bajar dos veces y elegir— y no lo
    # cubre `--teclas`, que sostiene: los menús miran **flancos**, así que
    # sostener abajo mueve el cursor una sola vez.
    #
    # Los de `--toques-hardware` van en cuadros de hardware desde el arranque:
    # `reloj.corridos` los cuenta. Es la única forma de apretar adentro de la
    # pantalla de ranuras del save point, donde `vueltas` no avanza y por lo
    # tanto un toque por tick no cae nunca. Valen en los dos caminos de abajo:
    # con `--teclas`/`--toques`, y con `--apretar-a`, que es el de las escenas.
    cuando, cuando_hw = {}, {}
    for lista, donde, flag in ((args.toques, cuando, "--toques"),
                               (args.toques_hardware, cuando_hw,
                                "--toques-hardware")):
        for toque in lista or ():
            boton, _, cuadro = toque.partition(":")
            if not cuadro.isdigit():
                sys.exit("%s quiere BOTON:CUADRO, y vino %r" % (flag, toque))
            donde.setdefault(int(cuadro), []).append(boton)

    if args.teclas is not None or args.toques or args.toques_hardware:
        consola = Consola(args.rom, core=args.core)
        consola.correr(args.arranque)
        reloj = Reloj(consola, args.rom, not args.sin_contador)
        sostenidos = tuple(args.teclas or ())

        def antes(n):
            consola.apretar(*(sostenidos + tuple(cuando.get(n, ()))
                              + tuple(cuando_hw.get(reloj.corridos, ()))))

        if sostenidos:
            consola.apretar(*sostenidos)
        reloj.avanzar(args.cuadros, antes if cuando or cuando_hw else None)
        consola.imagen().save(args.output)
        print("captura -> %s: %s, %d cuadros (%d de arranque)%s"
              % (args.output,
                 " ".join(sostenidos + tuple(args.toques or ())
                          + tuple(args.toques_hardware or ()))
                 or "sin apretar nada",
                 args.arranque + args.cuadros, args.arranque,
                 cuadros_perdidos(consola, args.rom)))
        return

    # El número N es el cuadro en que la referencia cierra el mensaje **y lo
    # dibuja cerrado**. La ROM dibuja lo que armó la vuelta anterior —es
    # RETRASO_DE_PANTALLA, el mismo +1 de la caminata— así que para que su
    # cuadro N salga cerrado el flanco tiene que caer en la vuelta N-1: el pad
    # se aprieta un cuadro antes. Con los cuadros quietos que miraba
    # `snes-cerrar` esto no se veía; se vio en la apertura, con el droide
    # caminando después del cuarto mensaje un cuadro atrás de la referencia.
    presiones = {n - RETRASO_DE_PANTALLA for n in args.apretar_a or ()}

    def correr_con_a(consola, reloj, ticks, apretados):
        """Corre hasta el tick `ticks`, apretando A en los que diga --apretar-a.

        Cada uno es un toque: se aprieta en ese tick y se suelta en el
        siguiente. La ROM cierra el mensaje con el flanco —`pad_a` contra
        `pad_a_ant`, que es el `IsTriggered` de RM2k— así que sostenerlo no
        dispararía nada más, pero tampoco dejaría que el toque siguiente fuera
        un flanco; la referencia modela esos mismos flancos, uno por número.

        Los números son **ticks** y no cuadros: si una vuelta de la ROM se pasa
        del cuadro, el botón se sostiene los cuadros que dure esa vuelta y la
        ROM lo lee una sola vez igual. Mientras nada se atrase los dos números
        son el mismo, que es por lo que esto no mueve ningún caso verde.

        Devuelve desde qué tick la pantalla dejó de cambiar.
        """
        quieto_desde, anterior = None, [None]

        def antes(n):
            de_hardware = tuple(cuando_hw.get(reloj.corridos, ()))
            if n in presiones:
                consola.apretar(*(apretados + ("a",) + de_hardware))
            else:
                consola.apretar(*(apretados + de_hardware))

        # El mismo tope que `Reloj.avanzar`, y por la misma razón: una ROM que
        # no llegue nunca al tick pedido tiene que fallar, no quedarse dando
        # vueltas. Acá faltaba, y el 2026-09-10 costó caro: una captura de la
        # pantalla de título —donde `vueltas` no avanza y el tick pedido no
        # llega jamás— se quedó **una hora** comiéndose un núcleo entero y 42
        # GiB de la máquina de taro, hasta que él la vio en `ps`. Con el tope
        # habría cortado a los dos minutos diciendo qué pasaba.
        tope = (ticks + 2) * reloj.CUADROS_POR_TICK
        while reloj.cuadro() < ticks:
            antes(reloj.cuadro() + 1)
            reloj.paso()
            actual = consola.cuadro[0]
            if actual != anterior[0]:
                quieto_desde = reloj.cuadro()
            anterior[0] = actual
            tope -= 1
            if tope <= 0:
                raise RuntimeError(
                    "la ROM no llegó al tick %d: se colgó, va lentísima, o su "
                    "reloj no corre —la pantalla de título no cuenta "
                    "`vueltas`, y para eso está --sin-contador—" % ticks)
        return quieto_desde

    # El plan dice, por dirección, cuántos cuadros dura la caminata. Sale de la
    # misma referencia contra la que se compara, así que la prueba pasa de
    # "dormí 45 segundos, seguro alcanza" a "corré exactamente los cuadros que
    # esta caminata dura". El de arranque no sale de ahí y sigue siendo fijo,
    # pero eso no es una holgura del reloj: 180 cuadros son 180 cuadros en
    # cualquier máquina, y cuestan un milisegundo de CPU.
    plan = {}
    if args.plan:
        for linea in open(args.plan):
            if linea.split():
                direccion, _pasos, cuadros = linea.split()
                plan[direccion] = int(cuadros)

    for walk in args.walk:
        destino = args.output.format(walk) if "{}" in args.output else args.output
        # Una consola nueva por dirección: arrancar de cero es parte de lo que
        # se está comparando, y reusar una traería el estado de la caminata
        # anterior.
        consola = Consola(args.rom, core=args.core)
        del_plan = walk in plan
        if args.avance is not None:
            del_plan = False
            cuadros = args.avance // 2 + RETRASO_DE_PANTALLA
        elif del_plan:
            cuadros = plan[walk] + args.margen
        else:
            cuadros = args.cuadros
        consola.correr(args.arranque)
        reloj = Reloj(consola, args.rom, not args.sin_contador)
        if walk != "none":
            consola.apretar(walk)

        # Se corren los cuadros de a uno para poder mirar desde qué cuadro la
        # pantalla ya no cambia más. El que se compara es siempre el último, o
        # sea un número exacto y fijo: esto no elige el cuadro, sólo informa.
        # Si eligiera, la prueba dependería de una heurística.
        #
        # Y se busca el último tramo quieto, no el primero: caminando el mapa 52
        # hacia arriba hay tres tramos de cinco cuadros o más sin que cambie
        # nada —en el 97, en el 103 y en el 161— y sólo el último es el héroe
        # que llegó. Los otros dos son la ROM que se queda un momento a mitad de
        # camino; ese mapa es de 1000x80 y no entra en la ventana del PPU, así
        # que va redibujando mientras se scrollea. Quedarse con el primer tramo
        # informaba "quieta en el 97" cuando la caminata dura 160.
        quieto_desde = correr_con_a(consola, reloj, cuadros,
                                    () if walk == "none" else (walk,))

        consola.imagen().save(destino)
        aviso = ""
        if del_plan and quieto_desde is not None and plan[walk]:
            # El plan dice cuántos cuadros tendría que durar la caminata, y la
            # pantalla deja de cambiar cuando el héroe llegó. Los dos números
            # tienen que dar casi lo mismo. Es lo más cerca que estamos hoy de
            # medir la *velocidad* del héroe: las comparaciones sólo miran dónde
            # termina, nunca cuánto tardó en llegar. Es un dato, no una
            # aserción; para que lo fuera habría que comparar contra la
            # referencia a mitad de camino, que todavía no se hace.
            aviso = ", quieta desde el %d (el plan dice %d)" % (quieto_desde,
                                                                plan[walk])
        print("captura -> %s: %s, %d cuadros%s (%d de arranque)%s%s"
              % (destino, walk, cuadros,
                 " = plan %d + margen %d" % (plan[walk], args.margen)
                 if del_plan else "", args.arranque, aviso,
                 cuadros_perdidos(consola, args.rom)))


if __name__ == "__main__":
    main()
