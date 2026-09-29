"""La pantalla de título: que sus dos opciones hagan lo que dicen.

Lo que se ve —la imagen, el menú, el cursor— lo cobra `test_titulo_golden.py`,
pixel por pixel. Lo que **no** puede cobrar es lo de acá: que elegir una opción
u otra deje la partida en estados distintos, porque las dos terminan mostrando
el mismo mapa y la diferencia está en la RAM.

El reparto es el de siempre: la tanda mira la pantalla y esto mira el estado.

La ROM de estas pruebas es `release`, la que se juega, que es la que lleva la
pantalla de título: la pantalla cambia el arranque —sin ella la partida
guardada se carga sola, con ella espera a que el menú lo decida— y ése es
justamente el camino que hay que probar. Así que estas pruebas arrancan donde
arranca el jugador, y **guardan como él**: con el menú de pausa, en el mapa 5,
y no con una página de prueba —desde el 2026-09-25 `release` las lleva, pero
guardar desde una es otro camino que el del jugador—.
"""

import pytest

from consola import EMPEZAR, SEGUIR
import datos
from dibujo import comparar_pantalla


# El mapa donde arranca `release`: el 4, el del juego de verdad.
MAPA_DE_ARRANQUE = 4

# Dónde se guarda: el mapa 5, donde el héroe tiene el control apenas llega. En
# el de arranque no se puede: el 4 es el enrutador de la apertura, y mientras
# su página corre el menú de pausa no se abre.
PARA_GUARDAR = (5, 39, 34)


def con_el_control(partida):
    """La partida después de "Begin the Story", parada en el mapa 5 con el
    control, que es donde se puede guardar con el menú."""
    una = partida(titulo=EMPEZAR)
    una.ir_al_mapa(*PARA_GUARDAR)
    return una


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
    mapa igual que una sin él, y por lo tanto que las goldens sacadas sin
    título sigan valiendo a través de él. Si el reloj corriera, la animación
    del ChipSet entraría al mapa con otra fase y todos los cuadros de la tanda
    se moverían.
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

    Lo que distingue cargar de empezar de nuevo es el **switch** 7, que se
    prende antes de guardar: es estado que sólo puede volver de la SRAM.
    """
    una = con_el_control(partida)
    una.prender(7)
    una.guardar_por_el_menu()
    assert una.hay_partida(), "la partida no llegó a guardarse"

    una.reiniciar(SEGUIR)
    assert una.switch(7), (
        "'Resume the Story' no cargó la partida: el switch 7 no volvió")


def test_empezar_ignora_la_partida_guardada(partida):
    """Y la primera opción no la carga, que es la mitad que se puede romper sin
    que nadie se entere.

    Con la ROM de antes de la pantalla de título el arranque cargaba la partida
    **siempre**, así que 'Begin the Story' habría devuelto al jugador el switch
    prendido. Elegir empezar de nuevo tiene que dejar el mundo como estaba.

    **La aserción sobre la SRAM no sobra.** Hasta el 2026-09-10 este caso
    pasaba en vacío: guardar no llegaba a guardar, la SRAM quedaba virgen y
    "empezar de nuevo no cargó nada" era cierto sin probar nada. Sin mirar que
    la partida quedó escrita, el caso vuelve a poder pasar así.
    """
    una = con_el_control(partida)
    una.prender(7)
    una.guardar_por_el_menu()
    assert una.hay_partida(), "la partida no llegó a guardarse"

    una.reiniciar(EMPEZAR)
    assert una.mapa() == MAPA_DE_ARRANQUE, (
        "'Begin the Story' cargó la partida guardada: quedó en el mapa %d"
        % una.mapa())
    assert not una.switch(7), (
        "el switch 7 de la partida guardada sobrevivió a empezar de nuevo")


def test_la_musica_viaja_en_la_partida(con_musica):
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

    Se guarda al final de la apertura, que es donde hay música y control:
    ver `con_musica` en conftest.py.
    """
    una = con_musica()
    assert not una.byte("music_apagada"), (
        "esta ROM tenía que arrancar con un tema sonando y arrancó callada: "
        "sin eso el caso no compara nada")
    una.guardar_por_el_menu()
    assert una.hay_partida(), "la partida no llegó a guardarse"

    # Las dos entradas de la música en `partida_tabla`, en su orden:
    # `music_apagada` y después `tema_actual`, que es de dos bytes con el alto
    # en cero. Están al final de la partida, **antes de las variables**, que
    # siguen con VARIABLES_N palabras; después vienen la velocidad del héroe,
    # un byte; el inventario, ITEMS_N bytes; los permisos del menú, un byte;
    # el equipo, diez bytes por actor; los HP, dos bytes por actor, y los SP,
    # otros dos; el gráfico que un `ChangeSpriteAssociation` le haya puesto a
    # cada actor, un byte; las habilidades que sabe cada uno, HAB_BYTES; y la
    # experiencia y el nivel, cuatro bytes por cada actor que puede pelear,
    # que es lo que cierra la tabla.
    #
    # Esta resta es un duplicado de `partida_tabla` y lo sabe: agregarle un
    # campo a la partida la deja mal, y lo que se ve es este caso en rojo. Es
    # lo que pasó con los HP, y lo que volvió a pasar con los SP y con las
    # habilidades.
    largo = (una.simbolos["PARTIDA_BYTES"] - 2 * una.simbolos["VARIABLES_N"]
             - 1 - una.simbolos["ITEMS_N"] - 1
             - 10 * una.simbolos["ACTORES_N"]
             - 2 * una.simbolos["ACTORES_N"]
             - 2 * una.simbolos["ACTORES_N"]
             - una.simbolos["ACTORES_N"]
             - una.simbolos["HAB_BYTES"]
             - 4 * una.simbolos["EXP_K"])
    cola = una.sram(una.simbolos["SRAM_DATOS"] + largo - 3, 3)
    assert cola[0] == una.byte("music_apagada"), (
        "la SRAM guardó music_apagada = %d y la consola lo tenía en %d"
        % (cola[0], una.byte("music_apagada")))
    assert cola[1] | (cola[2] << 8) == una.palabra("tema_actual"), (
        "la SRAM guardó el tema %d y estaba sonando el %d"
        % (cola[1] | (cola[2] << 8), una.palabra("tema_actual")))


def test_la_partida_cargada_arranca_con_su_musica(con_musica):
    """Y al cargar, la ROM la usa en vez del tema del mapa inicial.

    Es la otra mitad de lo de arriba: que el dato esté en la SRAM no alcanza si
    `music_boot` lo ignora. Se ensucia la WRAM antes de elegir porque **el reset
    de snes9x no la borra** —una consola de verdad enciende con basura ahí— y
    sin ensuciarla el estado viejo sobrevive solo y no se compara nada. Es la
    misma trampa que escondió el bug de página directa de `partida_suma`.
    """
    una = con_musica()
    una.guardar_por_el_menu()
    assert una.hay_partida(), "la partida no llegó a guardarse"
    sonaba = una.palabra("tema_actual")

    una._resetear()
    una.poner_byte("tema_actual", (sonaba + 1) % una.simbolos["TEMA_TOTAL"])
    una.poner_byte("music_apagada", 1)
    una.pasar_el_titulo(SEGUIR)
    # Un tick y no unos cuadros: mientras se carga el mapa el título está
    # callado —`music_apagada` en 1, ver `titulo_lazo`— y la música de la
    # partida recién se repone en `music_boot`, con el mapa ya cargado.
    una.correr(1)

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
    una = con_el_control(partida)
    una.prender(7)
    una.guardar_por_el_menu(1)                   # se elige la segunda en la pantalla
    assert una.hay_partida(1), "no quedó nada en la ranura 1"

    # La ranura 1 tiene la partida: elegirla la carga.
    una.reiniciar(SEGUIR, ranura=1)
    assert una.switch(7), (
        "se eligió la ranura 1, que tenía una partida, y no se cargó")

    # Y la 0 está vacía: elegirla arranca de cero en vez de cargar la 1.
    una.reiniciar(SEGUIR, ranura=0)
    assert not una.switch(7), (
        "se eligió la ranura 0, que está vacía, y se cargó la partida de otra")


@pytest.mark.parametrize("ranura", range(4))
def test_cada_ranura_carga_lo_que_se_guardo_en_ella(partida, ranura):
    """Las cuatro, una por una: guardar en ella y cargarla desde el título.

    Hasta el 2026-09-21 las pruebas guardaban sólo en la 0 y la 1, y la cuarta
    no cargaba nunca —taro la encontró jugando—. La NMI escribía `boot_cuadros`
    en el banco de datos que tuviera el código interrumpido, y guardar corre con
    el banco en la SRAM: le sumaba uno a un byte que sólo cae adentro de la
    cuarta ranura, y la suma de control dejaba de dar. Ver `nmi_boot`.

    Sin el arreglo, la 3 de este caso da rojo y las otras tres no.
    """
    una = con_el_control(partida)
    una.prender(7)
    una.guardar_por_el_menu(ranura)
    una.reiniciar(SEGUIR, ranura=ranura)
    assert una.switch(7), (
        "se guardó en la ranura %d —la %da de la pantalla— y al elegirla desde "
        "el título no volvió la partida" % (ranura, ranura + 1))


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
    from port import titulo
    from rpgmaker.recursos import GAME_DIR

    una = con_el_control(partida)
    una.poner_grupo(14, 10)
    una.guardar_por_el_menu(1)
    una.abrir_ranuras_desde_el_titulo()

    db, skin = datos.base(), datos.skin()
    ranuras = una.simbolos["SRAM_RANURAS"]

    def comparar(elegida):
        esperada = titulo.render_ranuras(skin, db, ranuras, [False] * ranuras,
                                         elegida, 0, db.font_id,
                                         {1: [14, 10]}, GAME_DIR)
        comparar_pantalla(una, esperada, "ranuras-grupo-%d" % elegida,
                          "la pantalla de ranuras con la partida de Talan y "
                          "el cursor en la %d" % elegida)

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


def _suma(bytes_):
    return sum(bytes_) & 0xFFFF


def _de_otro_build(simbolos, guardado, como):
    """La ranura entera —desde `SRAM_MAGIA`— de una partida guardada por otro
    build, armada con los bytes de `guardado`, que son los de una de éste.

    El otro formato se simula corriendo todo dos bytes desde la mitad de la
    partida —una variable menos, que es lo que pasó al juntar `release` y
    `test-main`— y con **ceros detrás**: con ceros la suma de control cuadra
    igual, que es el caso en que antes cargaba corrupta.
    """
    mitad = len(guardado) // 2
    corrida = guardado[:mitad] + guardado[mitad + 2:] + bytes(2)
    magia = b"ABLS"
    if como == "sin-cabecera":
        # Un build de antes de que la partida llevara su formato: la suma y
        # los datos pegados, sin nada en el medio.
        return magia + _suma(corrida).to_bytes(2, "little") + corrida
    bytes_ = simbolos["PARTIDA_BYTES"]
    firma = simbolos["PARTIDA_FIRMA"]
    if como == "otro-largo":
        bytes_ -= 2
    else:
        firma ^= 0x0100
    relleno = bytes(simbolos["SRAM_DATOS"] - simbolos["SRAM_MAGIA"] - 10)
    return (magia + _suma(corrida).to_bytes(2, "little")
            + bytes_.to_bytes(2, "little") + firma.to_bytes(2, "little")
            + relleno + corrida)


@pytest.mark.parametrize("como", ["sin-cabecera", "otro-largo", "otra-firma"])
def test_una_partida_de_otro_build_se_ve_vacia_y_no_carga(partida, como):
    """Una partida de otro formato es "no hay partida": la pantalla de ranuras
    la muestra vacía, pixel por pixel, y elegirla empieza de cero.

    Vacía y no "corrupta" como en EasyRPG: el "Savegame corrupted" de su
    `Window_SaveFile` es un texto suyo, en inglés y escrito en el código, y no
    uno de los términos del LDB, que es de donde la ROM saca todo lo que
    dice. Y es lo que la ROM ya hacía con una ranura cuya suma no cuadra.

    `sin-cabecera` es la partida que existe de verdad: la de un build de
    antes de este cambio. Contra la ROM sin el cambio este caso da rojo en
    la comparación de pixeles —la ranura se ve con el grupo guardado— y,
    salteando esa, en el switch: la partida corrida carga.
    """
    from port import titulo
    from rpgmaker.recursos import GAME_DIR

    una = con_el_control(partida)
    una.poner_grupo(14, 10)
    una.prender(7)
    una.guardar_por_el_menu(1)
    s = una.simbolos
    base = s["SRAM_STRIDE"]
    guardado = una.sram(base + s["SRAM_DATOS"], s["PARTIDA_BYTES"])
    ranura = _de_otro_build(s, guardado, como)
    una.poner_sram(base + s["SRAM_MAGIA"],
                   ranura + bytes(s["SRAM_STRIDE"] - len(ranura)))
    una.abrir_ranuras_desde_el_titulo()

    db, skin = datos.base(), datos.skin()
    ranuras = s["SRAM_RANURAS"]
    esperada = titulo.render_ranuras(skin, db, ranuras, [False] * ranuras,
                                     0, 0, db.font_id, {}, GAME_DIR)
    comparar_pantalla(una, esperada, "ranuras-otro-build-%s" % como,
                      "la pantalla de ranuras con una partida de otro build "
                      "en la 1")

    # Y elegirla no carga nada ni se cuelga: arranca como "Begin the Story".
    una._bajar_y_elegir(1)
    una.consola.correr(3)
    una.correr(1)
    assert una.mapa() == MAPA_DE_ARRANQUE, (
        "elegir la partida de otro build dejó el juego en el mapa %d"
        % una.mapa())
    assert not una.switch(7), (
        "la partida de otro build cargó: el switch 7 volvió de la SRAM")
