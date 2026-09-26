"""Que el tema que la ROM dice estar tocando tenga sus muestras en la ARAM.

Esto es la otra mitad de la red, y acá se ve por qué hace falta: **el silencio
no cambia un pixel**. Las pruebas `_golden` comparan la pantalla cuadro por
cuadro y dan cero igual con la música muda, así que un tema
que suena contra un directorio de silencios pasa entero por delante de ella sin
que nada se ponga rojo. El defecto de la pantalla de título vivió un día por
eso, y encima tapado: con archivos de MSU-1 al lado de la ROM la pista suena y
el SPC700 no toca nada, así que el único camino roto era justamente el que
siempre tiene que andar.

Lo que se pregunta es lo mismo que mira `tema_asegurar` en rom/src/paquete_de_audio.s: para cada
muestra que el stream del tema escribe en SRCN —`tema_muestras`, leída del
cartucho—, que `FAR_ARAM_DE` diga dónde está. Una muestra que no está apunta al
bloque de silencio, o sea una nota que no se oye.

La pantalla de título es el caso interesante y no un caso cualquiera: su tema
sale de `title_music` del LDB y **no entra en el paquete de audio de ningún
mapa**, porque los paquetes se arman con los temas que las páginas de cada mapa
pueden prender. O sea que es el único tema de la ROM que depende de que
`tema_asegurar` lo cargue en caliente, y por eso es el que delata el camino.
"""

from consola import EMPEZAR, SEGUIR, en_la_wram


def test_el_tema_del_titulo_tiene_sus_muestras_en_la_aram(partida):
    """La pantalla de título, sin MSU-1: el tema arranca y sus muestras están.

    Es el caso que cobra el defecto del 2026-09-12. Con él puesto la ROM decía
    estar tocando `Fantasia_Of_The_Wind` —`tema_actual` con el tema del título
    y `music_apagada` en cero— y las muestras que ese tema pide seguían sin
    subir, así que las ocho voces atacaban el silencio.

    No hace falta apagar el MSU-1 para probar esto, aunque `release` lleve sus
    pistas: la consola de las pruebas no se las deja ver al core —ver
    `retro.Consola` y `test_msu.py`—, así que `msu_detectar` no encuentra la
    firma y `music_start` cae siempre por `sin_pista`, que es el camino que se
    quiere medir.
    """
    una = partida(titulo=EMPEZAR).quedarse_en_el_titulo()

    tema = una.simbolos["TEMA_TITULO"]
    assert tema != 0xFF, (
        "esta ROM no lleva tema de título, así que el caso no compara nada")
    assert una.palabra("tema_actual") == tema, (
        "la pantalla de título dice estar tocando el tema %d y el suyo es el "
        "%d" % (una.palabra("tema_actual"), tema))
    assert not una.byte("music_apagada"), (
        "la pantalla de título quedó callada: `music_start` no llegó a "
        "prender el tema")

    faltan = sorted(set(una.muestras_del_tema(tema))
                    - una.muestras_en_la_aram())
    assert not faltan, (
        "el tema del título dice estar sonando y le faltan en la ARAM las "
        "muestras %s de las %s que usa: son notas contra el bloque de "
        "silencio. Lo tenía que subir `tema_asegurar` al ver que el paquete "
        "del mapa no las traía"
        % (faltan, sorted(una.muestras_del_tema(tema))))


def test_entrar_al_juego_devuelve_las_muestras_del_tema_del_mapa(con_musica):
    """Y al salir del título, el tema del mapa recupera las suyas.

    Es la otra punta del mismo camino: subir el tema del título **desaloja** lo
    que había, porque la ARAM no alcanza para todo y `paquete_cargar` acomoda
    desde cero lo que el paquete nuevo quiere. Si volver al juego no rehiciera
    el paquete del mapa, el jugador entraría a la partida con el tema del mapa
    sonando mudo, que es el mismo defecto una pantalla más tarde.

    Los dos temas piden muestras distintas —se comprueba, porque si pidieran
    las mismas el caso pasaría sin mover nada—.

    Se entra al juego **cargando** una partida guardada con el tema de la
    apertura sonando: en `release` el mapa de arranque no trae tema, así que
    "Begin the Story" no tiene nada que reponer, y cargar también sale del
    título. Ver `con_musica` en conftest.py.
    """
    una = con_musica()
    una.guardar_por_el_menu()
    una.reiniciar(SEGUIR)
    # Un tick, para que el mapa arranque su tema.
    una.correr(1)

    del_mapa = una.palabra("tema_actual")
    assert not una.byte("music_apagada"), (
        "esta ROM tenía que entrar al juego con el tema del mapa sonando")
    assert del_mapa != una.simbolos["TEMA_TITULO"], (
        "el tema del mapa y el del título son el mismo: no hay desalojo que "
        "probar")

    suyas = set(una.muestras_del_tema(del_mapa))
    del_titulo = set(una.muestras_del_tema(una.simbolos["TEMA_TITULO"]))
    assert suyas - del_titulo, (
        "los dos temas usan las mismas muestras, así que entrar al juego no "
        "tiene nada que reponer")

    faltan = sorted(suyas - una.muestras_en_la_aram())
    assert not faltan, (
        "se entró al juego y al tema del mapa le faltan en la ARAM las "
        "muestras %s de las %s que usa" % (faltan, sorted(suyas)))


def test_un_tema_pierde_sus_muestras_pero_nunca_su_numero():
    """Y el del título se las queda antes que un mapa que nadie visite.

    Esta es la otra mitad del mismo defecto, y la única de este archivo que
    **no** le pregunta a una ROM corriendo: lo que se rompió vive en el
    conversor, y para verlo desde la consola haría falta un cartucho con los
    diecinueve temas de la demo, que son cuatro minutos de conversión por caso.
    Acá se le pide a `build_varios` el mismo reparto con tres temas y el límite
    de ARAM apretado a mano hasta donde el recorte se dispara.

    Lo que se rompió el 2026-09-12, al pasar la demo a 29 mapas: el banco
    compartido se llenó y el conversor sacó a ocho temas **de la lista entera**,
    entre ellos el del título —que va último porque agregarlo al final es lo
    único que no renumera el bytecode—. Con eso `TEMA_TITULO` salía `$FF` y la
    pantalla de título no intentaba ni arrancar música.

    Y el agravante, que es lo que hace que perder el número no sea lo mismo que
    perder las muestras: `Fantasia_Of_The_Wind` **tiene pista de MSU-1**. Una
    pista no gasta ni un byte de ARAM; lo único que necesita es que el tema
    tenga número. Sin número no hay nada que tocar ni con los archivos al lado.
    """
    from audio import snes_music

    nombres = ["escape_newyork", "evilrhys", "Fantasia_Of_The_Wind"]
    titulo = nombres.index("Fantasia_Of_The_Wind")

    # El tope se mide, no se escribe: es lo que ocupa el banco de los dos que
    # tienen que quedar —el del título primero, por la prioridad—, así que el
    # recorte se lleva exactamente a uno. Un número fijo acá se desfasaría con
    # el soundfont y la prueba dejaría de apretar nada.
    leidos = [snes_music.leer_tema(n) for n in nombres]
    quedan = [leidos[titulo], leidos[0]]
    tope = snes_music.Banco(
        set().union(*[t["melodicos"] for t in quedan]),
        set().union(*[t["golpes"] for t in quedan])).bytes

    viejo = snes_music.ARAM_LIBRE
    try:
        snes_music.ARAM_LIBRE = tope
        _driver, _voces, temas, _banco, afuera = snes_music.build_varios(
            nombres, prioridad=[titulo])
    finally:
        snes_music.ARAM_LIBRE = viejo

    assert [t["nombre"] for t in temas] == nombres, (
        "un tema se cayó de la lista por no entrar en el banco: sin número no "
        "hay `PlayBGM` que lo prenda ni pista de MSU-1 que tocar")
    assert afuera == ["evilrhys"], (
        "el banco apretado tenía que dejar afuera al de menor prioridad y "
        "dejó afuera a %s" % (afuera,))
    assert snes_music.muestras_del_tema(temas[titulo]), (
        "el tema del título quedó sin una sola muestra aunque tenía la "
        "prioridad: es la primera pantalla del juego y suena antes que "
        "cualquier mapa")


def test_un_tema_que_no_aporta_pierde_notas_y_la_ROM_lo_dice():
    """Y cuánto pierde tiene que estar dicho, porque es lo que se oye.

    Esto es lo que taro escuchó en la consola el 2026-09-13 y describió como
    que a la música *"le falta una voz"*: una nota cuyo programa de General MIDI
    no está en el banco compartido **no llega al stream** —`build_events` la
    saltea con un `continue`—, así que el canal entero desaparece. De `Gaden`,
    con siete canales, quedan dos.

    Lo que esta prueba fija no es el número sino que exista y que se mueva: el
    conversor imprimía "no aportan muestras al banco" y una lista de nombres, o
    sea la causa sin la consecuencia, y con eso la demo pasó de once a
    veintiún temas sin que nadie viera el costo.

    Y fija la otra mitad: que `--banco-entero` —el `tope` de `build_varios`— lo
    devuelva. Es el lever con el que se decide de oído entre los primeros temas
    perfectos y todos completos pero más chillones.

    **Ojo con medirlo con `perdido`**, que es el otro número del resumen —hasta
    el 2026-09-26, `coverage`—: ése mide polifonía, sobre las notas que sí
    tienen muestra, así que no ve lo que el banco se lleva; con él parecía que
    compartir no costaba nada. Son dos preguntas distintas y por eso van las
    dos.
    """
    from audio import snes_music

    nombres = ["escape_newyork", "evilrhys", "Fantasia_Of_The_Wind"]
    titulo = nombres.index("Fantasia_Of_The_Wind")

    # El mismo tope medido que la prueba de arriba: lo que ocupan los dos que
    # tienen que quedar, así que el recorte se lleva exactamente a `evilrhys`.
    leidos = [snes_music.leer_tema(n) for n in nombres]
    quedan = [leidos[titulo], leidos[0]]
    tope = snes_music.Banco(
        set().union(*[t["melodicos"] for t in quedan]),
        set().union(*[t["golpes"] for t in quedan])).bytes

    _d, _v, apretado, _b, afuera = snes_music.build_varios(
        nombres, prioridad=[titulo], tope=tope)
    assert afuera == ["evilrhys"], (
        "el banco apretado tenía que dejar afuera a evilrhys y dejó a %s"
        % (afuera,))

    recortado = apretado[nombres.index("evilrhys")]["resumen"]["notas"]
    assert recortado < 1.0, (
        "evilrhys no aporta ninguna muestra al banco y sin embargo el resumen "
        "dice que suenan todas sus notas (%.3f): si esto pasa, el conversor "
        "imprime un 100%% sobre un tema al que le faltan voces" % recortado)
    for i, nombre in enumerate(nombres):
        if nombre != "evilrhys":
            assert apretado[i]["resumen"]["notas"] == 1.0, (
                "%s sí aporta al banco, así que tienen que sonar todas sus "
                "notas" % nombre)

    _d, _v, enteros, _b, afuera = snes_music.build_varios(
        nombres, prioridad=[titulo], tope=1 << 30)
    assert not afuera, (
        "con el tope sacado no tenía que quedar ningún tema sin aportar, y "
        "quedaron %s" % (afuera,))
    assert enteros[nombres.index("evilrhys")]["resumen"]["notas"] == 1.0, (
        "con el tope sacado evilrhys tiene que recuperar todas sus notas, y "
        "quedó en %.3f" % enteros[nombres.index("evilrhys")]["resumen"]["notas"])


def test_el_paquete_que_no_entro_con_otro_tema_sonando_se_completa(partida):
    """Entrar a un mapa con el tema de otro sonando, y el `PlayBGM` de después.

    Las muestras del tema que suena no se mueven al cargar el paquete del mapa
    nuevo —la música sigue durante el fundido—, así que lo que el paquete
    trae entra en lo que queda al lado, y lo último de la lista, los efectos,
    puede no entrar. Es el paso del mapa 2 al 3 del juego: la página del
    ascensor salta al 3 y recién ahí vuelve a pedir el tema del 2, así que el
    3 se carga con él sonando y algunos de sus efectos quedaban afuera hasta
    el cambio de mapa siguiente, aunque la página del 3 prendiera enseguida
    su propio tema.

    El caso hace ese paso con el tema del 2 sonando y después prende
    el del 3. Se pide primero que el paquete haya quedado incompleto al
    llegar —si no, el caso no ejercita nada: pasaría también sin el arreglo,
    por ejemplo si el reparto de la ARAM cambia y todo entra—, y después que
    con el tema nuevo sonando estén todos los efectos del 3.
    """
    una = partida(caso="paquete-incompleto")
    s = una.simbolos
    tema_del_3 = None
    incompleto_al_llegar = False
    for _ in range(600):
        una.correr(1)
        if una.mapa() != 3:
            continue
        sonando = None if una.byte("music_apagada") else una.palabra("tema_actual")
        if tema_del_3 is None and sonando is not None:
            # El primero que suena en el 3 es el que venía del 2.
            tema_del_3 = sonando
        if sonando == tema_del_3 and una.consola.ram(
                en_la_wram(s["PAQ_INCOMPLETO"]), 1)[0]:
            incompleto_al_llegar = True
        if sonando is not None and sonando != tema_del_3:
            break
    else:
        raise AssertionError(
            "el caso no llegó a prender el tema del mapa 3 en 600 cuadros")
    assert incompleto_al_llegar, (
        "el paquete del mapa 3 entró entero con el tema del 2 sonando, así "
        "que el caso no ejercita el completado: buscar otro paso que no entre")

    _temas, efectos = una.muestras_del_paquete(una.mapas.index(3))
    faltan = sorted(set(efectos) - una.muestras_en_la_aram())
    assert not faltan, (
        "con el tema del mapa 3 sonando, a su paquete le siguen faltando los "
        "efectos %s de %s: el `PlayBGM` tenía que completar lo que no entró "
        "al llegar con el tema del 2" % (faltan, sorted(efectos)))
