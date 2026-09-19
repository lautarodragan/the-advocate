"""La pantalla de título: que sus dos opciones hagan lo que dicen.

Lo que se ve —la imagen, el menú, el cursor— lo cobran los casos `titulo`
de `test_tanda_pantallas.py`, pixel por pixel. Lo que **no** puede cobrar es lo de acá: que elegir una opción u otra
deje la partida en estados distintos, porque las dos terminan mostrando el mismo
mapa y la diferencia está en la RAM.

El reparto es el de siempre: la tanda mira la pantalla y esto mira el estado.

La ROM de estas pruebas lleva `--con-titulo` y por eso es un cartucho propio,
`titulo`, que es el de pruebas con la pantalla delante: el
flag cambia el arranque —sin él la partida guardada se carga sola, con él espera
a que el menú lo decida— y ése es justamente el camino que hay que probar.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "tools"))
from eventos import SWITCH_DE_PRUEBA                    # noqa: E402

# Cuántos ticks espera la página de prueba antes de guardar, como en
# `test_guardar`: alcanzan para irse a otro mapa —el fundido son 90— y sobra.
ESPERA = 198

EMPEZAR, SEGUIR = 0, 1

# El mapa donde arranca el cartucho `titulo`, que es el de pruebas: el 6 y no
# el 4 del juego. Ver `pruebas/arnes/cartuchos.py`.
MAPA_DE_ARRANQUE = 6


def test_empezar_la_historia_arranca_en_el_mapa_inicial(partida):
    """'Begin the Story' entra al juego por el mapa de arranque de la ROM.

    Es el camino que no depende de que haya nada guardado, y el que confirma
    que salir del título repone la VRAM: el mapa se carga entero de nuevo,
    porque la imagen del título la había pisado.
    """
    una = partida(titulo=EMPEZAR)
    una.correr(1)
    assert una.mapa() == MAPA_DE_ARRANQUE, (
        "'Begin the Story' dejó la partida en el mapa %d y no en el de "
        "arranque" % una.mapa())


def test_el_reloj_del_juego_no_corre_en_el_titulo(partida):
    """`vueltas` arranca en cero después de elegir, no en los cuadros que la
    pantalla de título estuvo puesta.

    No es un detalle interno: es lo que hace que una ROM con título corra el
    mapa igual que una sin él, y por lo tanto que las dos referencias sigan
    siendo comparables. Si el reloj corriera, la animación del ChipSet entraría
    al mapa con otra fase y todos los cuadros de la tanda se moverían.
    """
    una = partida(titulo=EMPEZAR)
    assert una.palabra("vueltas") <= 3, (
        "el reloj del juego contó %d vueltas en la pantalla de título"
        % una.palabra("vueltas"))


def test_seguir_la_historia_carga_la_partida(partida):
    """'Resume the Story' carga la partida de la SRAM.

    Es la prueba que cierra el camino entero: se guarda, se **resetea la
    consola de verdad** —la SRAM sobrevive y la WRAM no— y se elige la segunda
    opción. Si el estado vuelve es porque salió del cartucho.

    Lo que distingue cargar de empezar de nuevo es el **switch**, y no el mapa:
    esta partida guarda sin moverse del mapa de arranque, así que las dos
    opciones terminan en el mismo lugar. Irse a otro mapa antes de guardar
    sería más contundente y hoy no se puede: ver
    `test_irse_de_mapa_antes_de_guardar_no_guarda`, acá abajo.
    """
    una = partida(titulo=EMPEZAR, caso="guardar-198-titulo")
    una.prender(7)
    una.guardar_en()
    assert una.sram(0x100, 4) == b"ABLS", "la partida no llegó a guardarse"

    una.reiniciar(SEGUIR)
    assert una.switch(7), (
        "'Resume the Story' no cargó la partida: el switch 7 no volvió")


@pytest.mark.xfail(strict=True, reason=(
    "la PÁGINA DE PRUEBA de guardado no llega a guardar si se cambia de mapa, "
    "y sólo con pantalla de título. Medido el 2026-09-10: quedándose en el "
    "mapa de arranque la SRAM tiene la magia a las ~350 vueltas; con un "
    "ir_al_mapa(6) en el medio no la tiene ni a las 891 —desde el 9f el "
    "arranque es el 6 y se va al 5—, o sea que no es "
    "cuestión de esperar más. Sin pantalla de título el mismo camino guarda a "
    "las 351. "
    "Lo que se descartó: no es el bug de página directa de partida_suma "
    "—sigue pasando con ése arreglado, y con ése arreglado cargar sí anda—. "
    "**Y desde el 2026-09-13 está medido que es de la página de prueba y no "
    "del juego**, que es lo que acá faltaba: "
    "`test_guardar_save_point.py` camina hasta el save point de verdad "
    "—`SaveByTalansPad0`, el evento de índice 66 del mapa 8, en (9,56); acá "
    "decía 'el evento 67', que es como lo numera el editor de RM2k, desde "
    "uno— y guarda con "
    "pantalla de título después de cambiar de mapa dos veces, y la partida "
    "vuelve del reset en el mapa 8 y en la misma celda. El mismo camino sin "
    "título guarda igual, o sea que la pantalla de título tampoco es la "
    "variable ahí. Así que lo que no llega a guardar es esta página —una "
    "automática con espera, que el doble cargar_mapa del menú reinicia— y es "
    "andamio: taro además confirmó ese día que el save point guarda en "
    "mednafen, en mesen y en la SNES de verdad. Desde el 2026-09-10 el "
    "síntoma es que la pantalla de ranuras no se abre nunca, que es lo mismo "
    "dicho por `guardar_en`. Está anotado en ESTADO.md"))
def test_irse_de_mapa_antes_de_guardar_no_guarda(partida):
    """El segundo defecto, escrito como prueba para que se sepa cuándo se
    arregló.

    Va con `strict`: el día que alguien toque el doble `cargar_mapa` y esto
    empiece a pasar, la prueba falla y obliga a sacar el xfail en vez de dejar
    una deuda que ya no existe.
    """
    una = partida(titulo=EMPEZAR, caso="guardar-198-titulo")
    una.ir_al_mapa(5, 39, 34)
    una.prender(7)
    una.guardar_en()
    assert una.sram(0x100, 4) == b"ABLS", "la partida no llegó a guardarse"


def test_empezar_ignora_la_partida_guardada(partida):
    """Y la primera opción no la carga, que es la mitad que se puede romper sin
    que nadie se entere.

    Con la ROM de antes de la pantalla de título el arranque cargaba la partida
    **siempre**, así que 'Begin the Story' habría devuelto al jugador el switch
    prendido. Elegir empezar de nuevo tiene que dejar el mundo como estaba.

    Se guarda **sin irse del mapa de arranque**, igual que
    `test_seguir_la_historia_carga_la_partida`, y por la misma razón: con
    título, la página de prueba no llega a guardar si se cambió de mapa —ver
    el `xfail` de acá arriba—. Hasta el 2026-09-10 esto se iba al mapa 6 y
    pasaba **en vacío**: `guardar_en` corría los ticks sin mirar si la partida
    se había guardado, la SRAM quedaba virgen y "empezar de nuevo no cargó
    nada" era cierto sin probar nada. Ahora `guardar_en` atraviesa la pantalla
    de ranuras y se cuelga si no se abre, que fue lo que lo delató; y la
    aserción sobre la SRAM está para que no vuelva a pasar.
    """
    una = partida(titulo=EMPEZAR, caso="guardar-198-titulo")
    una.prender(7)
    una.guardar_en()
    assert una.sram(0x100, 4) == b"ABLS", "la partida no llegó a guardarse"

    una.reiniciar(EMPEZAR)
    assert una.mapa() == MAPA_DE_ARRANQUE, (
        "'Begin the Story' cargó la partida guardada: quedó en el mapa %d"
        % una.mapa())
    assert not una.switch(7), (
        "el switch 7 de la partida guardada sobrevivió a empezar de nuevo")


def test_la_musica_viaja_en_la_partida(partida):
    """El tema que está sonando se guarda en la SRAM, como un switch.

    Lo prende un `PlayBGM` de un evento, así que es estado del mundo: sin
    guardarlo, una partida cargada arrancaría con el tema del mapa inicial de la
    ROM —el de la apertura— en vez de con el del lugar donde uno guardó.

    **Lo que se mira son los bytes de la SRAM y no el estado después de
    cargar**, y la razón vale la pena: al cargar, las páginas del mapa corren
    sus propios `PlayBGM` y reponen la música en un par de cuadros, así que un
    caso que mirara `tema_actual` después de cargar **pasa igual con el campo
    sacado de `partida_tabla`** —se comprobó, y pasa—. Mirar la SRAM no depende
    de eso: si el campo no se guarda, los bytes no están.

    La ROM lleva `--tema-de-arranque` porque los mapas de las pruebas no traen
    música propia.
    """
    una = partida(titulo=EMPEZAR, caso="guardar-198-titulo")
    assert not una.byte("music_apagada"), (
        "esta ROM tenía que arrancar con un tema sonando y arrancó callada: "
        "sin eso el caso no compara nada")
    una.guardar_en()
    assert una.sram(0x100, 4) == b"ABLS", "la partida no llegó a guardarse"

    # Las dos entradas de la música en `partida_tabla`, en su orden:
    # `music_apagada` y después `tema_actual`, que es de dos bytes con el alto
    # en cero. Están al final de la partida, **antes de las variables**, que
    # desde el 2026-09-10 siguen con VARIABLES_N palabras, de la velocidad
    # del héroe, un byte, del inventario, ITEMS_N bytes, de los permisos del
    # menú, un byte, del equipo, diez bytes por actor, desde el 2026-09-12 de
    # los HP, dos bytes por actor, y desde el 2026-09-13 de los SP, otros dos,
    # y del gráfico que un `ChangeSpriteAssociation` le haya puesto a cada
    # actor, un byte, que es lo que cierra la tabla.
    #
    # Esta resta es un duplicado de `partida_tabla` y lo sabe: agregarle un
    # campo a la partida la deja mal, y lo que se ve es este caso en rojo. Es
    # lo que pasó con los HP, y lo que volvió a pasar con los SP.
    largo = (una.simbolos["PARTIDA_BYTES"] - 2 * una.simbolos["VARIABLES_N"]
             - 1 - una.simbolos["ITEMS_N"] - 1
             - 10 * una.simbolos["ACTORES_N"]
             - 2 * una.simbolos["ACTORES_N"]
             - 2 * una.simbolos["ACTORES_N"]
             - una.simbolos["ACTORES_N"])
    cola = una.sram(0x106 + largo - 3, 3)
    assert cola[0] == una.byte("music_apagada"), (
        "la SRAM guardó music_apagada = %d y la consola lo tenía en %d"
        % (cola[0], una.byte("music_apagada")))
    assert cola[1] | (cola[2] << 8) == una.palabra("tema_actual"), (
        "la SRAM guardó el tema %d y estaba sonando el %d"
        % (cola[1] | (cola[2] << 8), una.palabra("tema_actual")))


def test_la_partida_cargada_arranca_con_su_musica(partida):
    """Y al cargar, la ROM la usa en vez del tema del mapa inicial.

    Es la otra mitad de lo de arriba: que el dato esté en la SRAM no alcanza si
    `music_boot` lo ignora. Se ensucia la WRAM antes de elegir porque **el reset
    de snes9x no la borra** —una consola de verdad enciende con basura ahí— y
    sin ensuciarla el estado viejo sobrevive solo y no se compara nada. Es la
    misma trampa que escondió el bug de página directa de `partida_suma`.
    """
    una = partida(titulo=EMPEZAR, caso="guardar-198-titulo")
    una.guardar_en()
    assert una.sram(0x100, 4) == b"ABLS", "la partida no llegó a guardarse"
    sonaba = una.palabra("tema_actual")

    una.consola.reset()
    una.cuadro = 0
    una.consola.correr(una.simbolos["BOOT_CUADROS"])
    una.poner_byte("tema_actual", (sonaba + 1) % una.simbolos["TEMA_TOTAL"])
    una.poner_byte("music_apagada", 1)
    una.pasar_el_titulo(SEGUIR)
    una.consola.correr(3)

    assert not una.byte("music_apagada"), (
        "la partida cargada arrancó callada y se había guardado con música")
    assert una.palabra("tema_actual") == sonaba, (
        "volvió sonando el tema %d en vez del %d que estaba guardado"
        % (una.palabra("tema_actual"), sonaba))


def test_la_pantalla_de_ranuras_carga_la_que_se_elige(partida):
    """Elegir la ranura 1 carga la 1, y elegir una vacía no carga nada.

    Es lo que distingue cuatro ranuras de una sola disfrazada de cuatro: si el
    número que elige el cursor no llegara hasta `cargar_partida`, la primera
    mitad de este caso pasaría igual —hay una partida y se carga— y sólo la
    segunda lo delataría. Por eso están las dos.
    """
    una = partida(titulo=EMPEZAR, caso="guardar-198-titulo")
    una.prender(7)
    una.guardar_en(1)                   # se elige la segunda en la pantalla
    base = una.simbolos["SRAM_MAGIA"] + una.simbolos["SRAM_STRIDE"]
    assert una.sram(base, 4) == b"ABLS", "no quedó nada en la ranura 1"

    # La ranura 1 tiene la partida: elegirla la carga.
    una.reiniciar(SEGUIR, ranura=1)
    assert una.switch(7), (
        "se eligió la ranura 1, que tenía una partida, y no se cargó")

    # Y la 0 está vacía: elegirla arranca de cero en vez de cargar la 1.
    una.reiniciar(SEGUIR, ranura=0)
    assert not una.switch(7), (
        "se eligió la ranura 0, que está vacía, y se cargó la partida de otra")


def test_el_cursor_de_guardar_arranca_en_la_ranura_en_uso(partida):
    """Con una partida cargada de la ranura 2, la pantalla de guardar abre con
    el cursor en la 2: es el `latest_slot` de `Scene_File::Start`, sin fechas.
    Elegir sin mover el cursor vuelve a escribir la misma ranura, que es lo que
    uno espera de "guardar" después de "continuar".

    Hace falta el título porque es la única forma de llegar con `ranura`
    puesta: la página de prueba corre una sola vez por partida, así que
    guardar dos veces seguidas en la misma sesión no se puede. Y después de
    cargar hay que **apagar `SWITCH_DE_PRUEBA`**: la página lo prende al
    arrancar, viaja en la partida, y con él puesto gana la página que la apaga.
    Medido: sin esto `ev_activo` queda en cero para siempre después de "Resume
    the Story". Es de la página inventada, no del juego.
    """
    una = partida(titulo=EMPEZAR, caso="guardar-198-titulo")
    una.prender(7)
    una.guardar_en(2)
    una.reiniciar(SEGUIR, ranura=2)
    assert una.byte("ranura") == 2, "no se cargó de la ranura 2"
    una.apagar(SWITCH_DE_PRUEBA)
    una.correr(ESPERA - 10)
    una.esperar_la_pantalla_de_ranuras()
    assert una.byte("titulo_sel") == 2, (
        "el cursor arrancó en la ranura %d y la partida vino de la 2"
        % una.byte("titulo_sel"))


def test_la_pantalla_de_ranuras_muestra_el_grupo_guardado(partida):
    """Una ranura con partida muestra el nombre del líder y las caras del
    grupo, como `Window_SaveFile` en RM2k, y **pixel por pixel** contra
    `titulo.render_ranuras` con ese mismo grupo.

    Es la única prueba de pixeles de la variante "llena": la tanda no puede
    llegar a ella porque la SRAM del emulador arranca virgen, y acá sí, porque
    primero se guarda. El grupo es Talan y DummyHero —los dos que pueden
    estar en el grupo con los mapas de esta ROM—: Talan tiene cara y nombre,
    DummyHero no tiene cara, así que se ven las dos cosas y un hueco.
    """
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "tools"))
    import lcf
    import titulo
    import ventana
    from render_map import GAME_DIR
    from tanda import quince_bits

    una = partida(titulo=EMPEZAR, caso="guardar-198-titulo")
    una.poner_grupo(14, 10)
    una.guardar_en(1)
    una.abrir_ranuras_desde_el_titulo()

    db = lcf.Database(os.path.join(GAME_DIR, "RPG_RT.ldb"))
    skin = ventana.skin(GAME_DIR, db.system_name)
    ranuras = una.simbolos["SRAM_RANURAS"]

    def comparar(elegida):
        captura = una.imagen().convert("RGB")
        esperada = titulo.render_ranuras(skin, db, ranuras, [False] * ranuras,
                                         elegida, 0, db.font_id,
                                         {1: [14, 10]}, GAME_DIR)
        distintos = sum(1 for x, y in zip(quince_bits(captura),
                                          quince_bits(esperada)) if x != y)
        if distintos:
            donde = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))), "rom", "shots")
            os.makedirs(donde, exist_ok=True)
            captura.save(os.path.join(
                donde, "prueba-ranuras-grupo-%d.png" % elegida))
            esperada.save(os.path.join(
                donde, "prueba-ranuras-grupo-%d.esperado.png" % elegida))
        assert distintos == 0, (
            "la pantalla de ranuras con la partida de Talan y el cursor en la "
            "%d difiere de la referencia en %d pixeles; están en "
            "rom/shots/prueba-ranuras-grupo-%d*.png"
            % (elegida, distintos, elegida))

    # Como se entra, y con el cursor sobre la fila de Talan: bajar el cursor
    # repinta la fila entera adentro del vblank, cara y nombre incluidos, y
    # eso es lo que se mira acá. Medido: contra una referencia sin grupo o
    # con otro actor son unos 400 pixeles, así que el cero no es vacío.
    comparar(0)
    una.consola.apretar("down")
    una.consola.correr(2)
    una.consola.apretar()
    una.consola.correr(2)
    comparar(1)
