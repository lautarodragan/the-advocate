"""Que el tema que la ROM dice estar tocando tenga sus muestras en la ARAM.

Esto es la otra mitad de la red, y acá se ve por qué hace falta: **el silencio
no cambia un pixel**. Las pruebas `_golden` comparan la pantalla cuadro por
cuadro y dan cero igual con la música muda, así que un tema
que suena contra un directorio de silencios pasa entero por delante de ella sin
que nada se ponga rojo. El defecto de la pantalla de título vivió un día por
eso, y encima tapado: con archivos de MSU-1 al lado de la ROM la pista suena y
el SPC700 no toca nada, así que el único camino roto era justamente el que
siempre tiene que andar.

Lo que se pregunta es lo mismo que mira `song_ensure` en runtime/paquete_de_audio.s: para cada
muestra que el stream del tema escribe en SRCN —`tema_muestras`, leída del
cartucho—, que `FAR_ARAM_OF` diga dónde está. Una muestra que no está apunta al
bloque de silencio, o sea una nota que no se oye.

La pantalla de título es el caso interesante y no un caso cualquiera: su tema
sale de `title_music` del LDB y **no entra en el paquete de audio de ningún
mapa**, porque los paquetes se arman con los temas que las páginas de cada mapa
pueden prender. O sea que es el único tema de la ROM que depende de que
`song_ensure` lo cargue en caliente, y por eso es el que delata el camino.
"""

from consola import EMPEZAR, SEGUIR, en_la_rom, en_la_wram


def test_el_tema_del_titulo_tiene_sus_muestras_en_la_aram(partida):
    """La pantalla de título, sin MSU-1: el tema arranca y sus muestras están.

    Es el caso que cobra el defecto del 2026-09-12. Con él puesto la ROM decía
    estar tocando `Fantasia_Of_The_Wind` —`tema_actual` con el tema del título
    y `music_apagada` en cero— y las muestras que ese tema pide seguían sin
    subir, así que las ocho voces atacaban el silencio.

    No hace falta apagar el MSU-1 para probar esto, aunque `release` lleve sus
    pistas: la consola de las pruebas no se las deja ver al core —ver
    `retro.Console` y `test_msu.py`—, así que `msu_detect` no encuentra la
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
        "silencio. Lo tenía que subir `song_ensure` al ver que el paquete "
        "del mapa no las traía"
        % (faltan, sorted(una.muestras_del_tema(tema))))


def test_entrar_al_juego_devuelve_las_muestras_del_tema_del_mapa(con_musica):
    """Y al salir del título, el tema del mapa recupera las suyas.

    Es la otra punta del mismo camino: subir el tema del título **desaloja** lo
    que había, porque la ARAM no alcanza para todo y `package_load` acomoda
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


def test_el_presupuesto_de_cada_muestra_es_el_de_su_peor_paquete():
    """Todos los temas con todas sus muestras, y cada muestra limitada sólo
    por los paquetes donde está.

    Es la opción A del paso 6 de `workflow/tasks/todo/la-calidad-de-la-musica.md`,
    y la única prueba de este archivo que **no** le pregunta a una ROM
    corriendo: se le pide a `build_all` el reparto con tres temas y la
    ARAM achicada a mano, para que el paquete de dos de ellos no entre sin
    recortar y el del tercero sí.

    Lo que reemplaza: hasta el 2026-09-26 el banco entero tenía que entrar en
    la ARAM, y los temas que no cabían dejaban de aportar programas —una nota
    cuyo programa no está en el banco **no llega al stream**—. Así sonaban
    diecinueve de los treinta y dos del `release`, y de `Gaden` quedaban dos
    canales de siete. Ahora no se recorta a nadie: todas las notas llegan, y
    lo que se paga es la tasa de las muestras de los paquetes llenos.

    Y la herencia: un paquete tiene que entrar también con el tema que puede
    venir sonando, **sin sus efectos** —ésos esperan al próximo `PlayBGM`—.
    """
    from audio import snes_music

    nombres = ["escape_newyork", "evilrhys", "Fantasia_Of_The_Wind"]
    leidos = [snes_music.read_song(n) for n in nombres]
    teclas = snes_music.most_used_zones(leidos)
    claves = [snes_music.song_keys(t, teclas) for t in leidos]
    nativo = {k: len(snes_music._sample(k, snes_music.NATIVE).data)
              for k in set().union(*claves)}
    apretados = claves[0] | claves[1]
    solo_del_tercero = claves[2] - apretados
    assert solo_del_tercero, (
        "el tercer tema no tiene muestras propias, así que no hay con qué ver "
        "que un paquete con lugar no pague por uno lleno")

    # La ARAM se mide, no se escribe: la mitad de lo que ocuparían enteras
    # las muestras de los dos primeros, más el directorio. Un número fijo
    # acá se desfasaría con el soundfont y la prueba dejaría de apretar.
    libre = sum(nativo[k] for k in apretados) // 2
    assert libre > sum(nativo[k] for k in claves[2]), (
        "el tercer tema entero no entra en la ARAM achicada: la prueba no "
        "distinguiría un paquete con lugar de uno lleno")
    viejo = snes_music.ARAM_END
    try:
        snes_music.ARAM_END = (snes_music.SAMPLES_ADDR + libre
                               + 4 * len(nativo) + len(snes_music.SILENCE))
        _d, _v, temas, banco = snes_music.build_all(
            nombres, packages=[("lleno", [0, 1], []), ("holgado", [2], [])],
            inheritance=[("holgado", 0)])
    finally:
        snes_music.ARAM_END = viejo

    assert [t["nombre"] for t in temas] == nombres
    for tema in temas:
        assert tema["resumen"]["notas"] == 1.0, (
            "a %s le faltan notas (%.3f): todos los temas aportan sus "
            "muestras al banco" % (tema["nombre"], tema["resumen"]["notas"]))

    # Las muestras que toca cada tema: una clave puede tener copias —ver
    # `snes_music.copies`—, así que se pregunta por las suyas.
    def suyas(tema):
        return set(banco.assignment[tema].values())

    lleno = suyas(0) | suyas(1)
    assert banco.takes(lleno) <= banco.free, (
        "el paquete de los dos primeros ocupa %d B y hay %d"
        % (banco.takes(lleno), banco.free))
    assert banco.takes(lleno) < sum(nativo[k] for k in apretados), (
        "el paquete lleno no recortó nada: la ARAM no se achicó")
    assert banco.takes(suyas(0) | suyas(2)) <= banco.free, (
        "el paquete del tercero no entra con el primero sonando")
    # Y ninguna muestra del tercero paga el paquete lleno, ni las que
    # comparte con los otros dos: ésas son copias —ver
    # `test_un_programa_no_paga_un_paquete_donde_no_suena`—. Lo que sí
    # puede recortarlas es la herencia, que es un grupo donde el tercero
    # está: con el primero sonando, entran los dos.
    for k in sorted(claves[2]):
        suya = banco.assignment[2][k]
        assert banco.limited_by.get(suya) != "lleno", (
            "la muestra %s del tercero la limita el paquete lleno, donde no "
            "está" % (k,))


def test_un_programa_no_paga_un_paquete_donde_no_suena():
    """Un tema que comparte un programa con el de un paquete lleno no queda
    limitado por ese paquete: el suyo es otra muestra, una copia.

    Es el mapa 3 del juego. Hasta el 2026-09-26 había una muestra por
    programa en todo el cartucho y cada una tenía el presupuesto de su peor
    paquete, así que los 43 KB de efectos del mapa 3 dejaban la batería de
    `evilrhys` —el tema del mapa— y la de **todos** los temas a 10 kHz, y el
    oboe a 7. `snes_music.copies` le da al tema de afuera su propia muestra.

    Acá, sin ROM: `evilrhys` en un paquete con la ARAM achicada a la mitad
    de lo que ocuparían sus muestras enteras, y `lufsorr` —que comparte con
    él el bombo y el arpa— en otro donde entra entero. Con la regla de antes
    el bombo y el arpa de `lufsorr` salían recortados como los de
    `evilrhys`.
    """
    from audio import snes_music

    nombres = ["evilrhys", "lufsorr"]
    leidos = [snes_music.read_song(n) for n in nombres]
    teclas = snes_music.most_used_zones(leidos)
    claves = [snes_music.song_keys(t, teclas) for t in leidos]
    nativo = {k: len(snes_music._sample(k, snes_music.NATIVE).data)
              for k in set().union(*claves)}
    compartidas = claves[0] & claves[1]
    assert compartidas, (
        "los dos temas no comparten ninguna muestra: la prueba no mira nada")

    libre = sum(nativo[k] for k in claves[0]) // 2
    assert libre > sum(nativo[k] for k in claves[1]), (
        "el segundo tema entero no entra en la ARAM achicada")
    viejo = snes_music.ARAM_END
    try:
        snes_music.ARAM_END = (snes_music.SAMPLES_ADDR + libre
                               + 4 * (len(nativo) + len(compartidas))
                               + len(snes_music.SILENCE))
        _d, _v, _temas, banco = snes_music.build_all(
            nombres, packages=[("lleno", [0], []), ("holgado", [1], [])])
    finally:
        snes_music.ARAM_END = viejo

    recortadas = []
    for k in sorted(compartidas):
        del_lleno = banco.keys.index(banco.assignment[0][k])
        del_otro = banco.keys.index(banco.assignment[1][k])
        assert len(banco.voices[del_lleno].data) < nativo[k], (
            "la muestra %s de `evilrhys` no se recortó: la ARAM no se "
            "achicó lo suficiente" % (k,))
        if len(banco.voices[del_otro].data) < nativo[k]:
            recortadas.append("%s (%d de %d B, la limita %s)" % (
                k, len(banco.voices[del_otro].data), nativo[k],
                banco.limited_by.get(banco.keys[del_otro], "nadie")))
    assert not recortadas, (
        "`lufsorr` paga el paquete lleno de `evilrhys`, donde no está: %s"
        % ", ".join(recortadas))


def test_cada_paquete_entra_entero_aunque_la_aram_quede_partida(partida):
    """Saltos entre los mapas de paquete más lleno, con la música callada
    antes de cada uno: el paquete de llegada tiene que quedar entero.

    Sin nada sonando no hay muestras que no se puedan mover, y cada paquete
    entra solo —lo garantiza el conversor—. Lo que podía dejar algo afuera
    es que las muestras que el paquete nuevo comparte con el anterior se
    quedan donde estaban, y con el presupuesto por paquete cada uno llena la
    ARAM casi entera: los huecos que dejaban alcanzaban para que no entrara
    una muestra, y pasaba en cinco de estos trece saltos. `package_load_done`
    decide primero dónde va cada una y, si algo no entra, vuelve a acomodar
    todo desde cero antes de subir nada. Es también lo que pasa al volver de
    una pelea, que calla la música antes de cargar el paquete del mapa.
    """
    una = partida(titulo=EMPEZAR)
    faltas = []
    for mapa in (18, 2, 19, 3, 26, 9, 121, 2, 18, 3, 19, 26, 2):
        if mapa not in una.mapas:
            continue
        una.poner_byte("music_apagada", 1)
        una.ir_al_mapa(mapa, 5, 5, cuadros=60)
        temas, efectos = una.muestras_del_paquete(una.mapas.index(mapa))
        quiere = set(efectos)
        for tema in temas:
            quiere |= set(una.muestras_del_tema(tema))
        faltan = sorted(quiere - una.muestras_en_la_aram())
        if faltan:
            faltas.append("mapa %d: %s de %d" % (mapa, faltan, len(quiere)))
    assert not faltas, (
        "paquetes que llegaron incompletos con la música callada: %s"
        % "; ".join(faltas))


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
                en_la_wram(s["PKG_PARTIAL"]), 1)[0]:
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


def test_un_tema_que_suena_para_irse_va_aparte_del_paquete():
    """Un `PlayBGM` seguido de un salto a otro mapa, sin efectos ni ramas en
    el medio, es **de salida**: el tema no tiene que caber con los efectos
    del mapa. Es `lufsorr` en el mapa 3, que suena al final de la secuencia
    de efectos, cuando ya no queda ninguno, y el mapa se deja enseguida.

    Se compilan páginas a mano, sin ROM: la de salida, una con un efecto en
    el medio, una que salta al mismo mapa, una que no salta, y un tema que
    sale en una página y en otra no. Sólo el primero cuenta: un tema es de
    salida en el mapa si **todos** sus `PlayBGM` de ahí lo son.
    """
    from rpgmaker import lcf
    from port import events

    def pagina(*comandos):
        return events._Commands(lcf.handwritten_commands(
            {"event_commands": list(comandos)}))

    def tema(nombre):
        return {"code": "PlayBGM", "parameters": [0, 100, 100, 50],
                "string": nombre}

    efecto = {"code": "PlaySound", "parameters": [100, 100, 50],
              "string": "Thunder9"}
    esperar = {"code": "Wait", "parameters": [10]}
    switch = {"code": "ControlSwitches", "parameters": [0, 15, 15, 0]}
    al_4 = {"code": "Teleport", "parameters": [4, 9, 9]}
    al_3 = {"code": "Teleport", "parameters": [3, 9, 9]}
    indice = {3: 0, 4: 1}.get

    temas = events.Songs()
    temas.current_map = 0
    for comandos in ([tema("sale"), esperar, switch, al_4],
                     [tema("suena"), efecto, al_4],
                     [tema("vuelve"), esperar, al_3],
                     [tema("queda"), esperar],
                     [tema("dos_veces"), al_4],
                     [tema("dos_veces"), esperar]):
        assert events.compile_page(pagina(*comandos), indice,
                                   songs=temas) is not None, (
            "la página %r no compiló: la prueba no mira nada" % (comandos,))
    de_salida = {temas.names[t] for t in temas.exit_songs(0)}
    assert de_salida == {"sale"}, (
        "de salida en el mapa: %s, y sólo tenía que serlo `sale`"
        % sorted(de_salida))


def test_el_tema_de_salida_sube_solo(partida):
    """El `PlayBGM` de un tema de salida que no está en la ARAM lo sube **a
    él solo**, y el paquete queda anotado como incompleto.

    El caso es el final del mapa 3: el tema del mapa, con sus efectos, y
    después `lufsorr`, que es de salida ahí y no entra al lado —si entrara,
    el caso no ejercitaría nada, y se pide antes—. Rearmar el paquete con él
    adelante, que es lo que hace `song_ensure` con un tema que falta, no
    entraría: se acomodaría todo desde cero y se subiría la ARAM entera.
    Así se sube lo suyo. El paquete queda incompleto para que, si la página
    no se fuera del mapa, el próximo `PlayBGM` lo complete.
    """
    una = partida(caso="tema-de-salida")
    s = una.simbolos
    mapa = una.mapas.index(3)
    salida = una.temas_de_salida(mapa)
    assert salida, "el mapa 3 no tiene temas de salida: el caso no mira nada"
    lufsorr = salida[0]
    temas, efectos = una.muestras_del_paquete(mapa)
    del_paquete = set(efectos)
    for tema in temas:
        del_paquete |= set(una.muestras_del_tema(tema))
    suyas = set(una.muestras_del_tema(lufsorr))
    antes = None
    for _ in range(900):
        una.correr(1)
        if una.mapa() != 3 or una.byte("music_apagada"):
            continue
        sonando = una.palabra("tema_actual")
        if sonando != lufsorr:
            # El tema del mapa: el paquete entero, y lo de salida afuera.
            antes = una.muestras_en_la_aram()
            continue
        break
    else:
        raise AssertionError("el caso no llegó a prender el tema de salida")
    assert antes is not None, "el tema del mapa no llegó a sonar"
    assert not del_paquete - antes, (
        "con el tema del mapa sonando al paquete le faltan %s"
        % sorted(del_paquete - antes))
    assert suyas - antes, (
        "el tema de salida ya estaba entero en la ARAM al lado del paquete: "
        "el caso no ejercita la subida")
    ahora = una.muestras_en_la_aram()
    assert not suyas - ahora, (
        "el tema de salida suena sin las muestras %s" % sorted(suyas - ahora))
    assert una.consola.ram(en_la_wram(s["PKG_PARTIAL"]), 1)[0], (
        "el tema de salida se subió solo y el paquete no quedó anotado como "
        "incompleto")


def test_el_tema_aparte_sube_con_los_efectos_del_paquete(partida):
    """El `PlayBGM` de un tema aparte sube **el tema con los efectos del
    paquete**, sin los otros temas, y el paquete queda incompleto.

    El caso es el basural del 38: `golden_axe-turtlevillage2`, que es del
    paquete, y después `vswar`, que es aparte ahí —ver `separate_songs` en
    tools/audio/snes_music.py— y no entra al lado de `golden_axe`: si
    entrara, el caso no ejercitaría nada, y se pide antes. Con `vswar`
    sonando tienen que estar sus muestras y las de los efectos del paquete
    —los cofres del basural suenan durante la escena—, y el paquete queda
    incompleto para que el próximo `PlayBGM` lo complete. Con la ROM
    tratándolo como uno de salida, los efectos faltan.
    """
    una = partida(caso="tema-aparte")
    mapa = una.mapas.index(38)
    aparte = una.temas_aparte(mapa)
    assert aparte, "el mapa 38 no tiene temas aparte: el caso no mira nada"
    vswar = aparte[0]
    temas, efectos = una.muestras_del_paquete(mapa)
    assert vswar not in temas, "vswar está también entre los temas del 38"
    del_paquete = set()
    for tema in temas:
        del_paquete |= set(una.muestras_del_tema(tema))
    suyas = set(una.muestras_del_tema(vswar))
    antes = None
    for _ in range(900):
        una.correr(1)
        if una.mapa() != 38 or una.byte("music_apagada"):
            continue
        if una.palabra("tema_actual") != vswar:
            antes = una.muestras_en_la_aram()
            continue
        break
    else:
        raise AssertionError("el caso no llegó a prender el tema aparte")
    assert antes is not None, "el tema del paquete no llegó a sonar"
    assert suyas - antes, (
        "el tema aparte ya estaba entero en la ARAM al lado del paquete: el "
        "caso no ejercita la subida")
    ahora = una.muestras_en_la_aram()
    assert not suyas - ahora, (
        "el tema aparte suena sin las muestras %s" % sorted(suyas - ahora))
    assert not set(efectos) - ahora, (
        "con el tema aparte sonando faltan los efectos del paquete %s"
        % sorted(set(efectos) - ahora))
    assert del_paquete - suyas - ahora, (
        "los otros temas del paquete siguen enteros al lado del aparte: no "
        "se subió solo")
    assert una.consola.ram(en_la_wram(una.simbolos["PKG_PARTIAL"]), 1)[0], (
        "el tema aparte se subió sin los otros temas y el paquete no quedó "
        "anotado como incompleto")


def test_los_efectos_comparten_lugares_del_directorio():
    """Los efectos no le quitan entradas del directorio del SPC700 a la
    música.

    El SRCN es de un byte, así que el directorio llega a 255 entradas. Hasta
    el 2026-09-26 cada efecto del cartucho tenía la suya —92 en `release`,
    `se_usual`—, y `snes_music.copies` paraba por llenarlo: las muestras
    que un paquete limitaba seguían limitando a los temas de afuera. Desde ese
    día los efectos comparten los `SE_LUGARES` del final —dos efectos que
    nunca van en el mismo paquete pueden ir al mismo lugar, ver
    `snes_music.effect_places`—, y lo que liberan es para las copias.

    Hasta el 2026-09-27 esta prueba pedía además que el directorio no se
    llenara, o sea que las copias terminaran porque ninguna sumaba. Con el
    camino principal del mundo en `release` (el hito 4 de
    `workflow/tasks/*/el-mundo-y-lo-que-sigue.md`) se llena: hay más temas, y
    la segunda tanda de copias —las que no le bajan la tasa a nadie— para por
    falta de entradas, que su docstring acepta. Es un límite de lo que se
    puede mejorar la música, no una muestra que falte.

    Se lee todo del cartucho: que los efectos ocupen menos entradas que las
    de siempre, que ningún paquete tenga dos efectos en el mismo lugar —se
    pisarían en la ARAM— y que los lugares no sean más que los efectos del
    paquete más cargado.
    """
    from audio import snes_music
    import tanda

    release = tanda.cartucho()
    s = release.simbolos
    with open(release.sfc, "rb") as archivo:
        rom = archivo.read()
    assert s["MUESTRAS_N"] <= snes_music.DIRECTORY_MAX, s["MUESTRAS_N"]
    assert s["SE_LUGARES"] < snes_music.se_usual(), (
        "los efectos ocupan %d entradas del directorio, tantas como cuando "
        "cada uno tenía la suya: no comparten" % s["SE_LUGARES"])
    assert s["MUESTRAS_N"] == s["SE_PRIMERA"] + s["SE_LUGARES"]
    lugar = rom[en_la_rom(s["efecto_lugar"]):
                en_la_rom(s["efecto_lugar"]) + s["EFECTOS_N"]]

    base = en_la_rom(s["paquetes"])
    mas_cargado, pisados = 0, []
    for p in range(s["PAQUETES_N"]):
        salto = base + 2 * p
        cursor = base + (rom[salto] | rom[salto + 1] << 8)
        while rom[cursor] != 0xFF:          # los temas
            cursor += 1
        cursor += 1
        efectos = []
        while rom[cursor] != 0xFF:
            efectos.append(rom[cursor])
            cursor += 1
        efectos = sorted(set(efectos))
        mas_cargado = max(mas_cargado, len(efectos))
        lugares = [lugar[e] for e in efectos]
        if len(set(lugares)) < len(lugares):
            pisados.append("paquete %d: efectos %s en los lugares %s"
                           % (p, efectos, lugares))
    assert not pisados, (
        "efectos del mismo paquete en el mismo lugar del directorio: %s"
        % "; ".join(pisados))
    assert s["SE_LUGARES"] == mas_cargado, (
        "los efectos ocupan %d lugares del directorio y el paquete más "
        "cargado trae %d" % (s["SE_LUGARES"], mas_cargado))


def test_un_efecto_no_suena_con_la_muestra_de_otro(partida):
    """Un lugar del directorio lo comparten efectos de paquetes distintos, y
    `sound_play` no toca un efecto si el anotado en su lugar es otro.

    Es el caso de un efecto que se pide en un mapa cuyo paquete no lo trae
    —el de un evento común, que no es de ningún mapa—: su lugar tiene la
    muestra de un vecino, y sin la pregunta sonaría ésa. En el juego no hay
    una página que lo haga, así que se lo fuerza: `Success2` en el mapa 10,
    con `FAR_EFECTO_EN` cambiado a otro efecto justo al llegar. El control,
    sin cambiarlo, tiene que sonar.
    """
    def suena(cambiar):
        una = partida(caso="efecto-de-calidad")
        s = una.simbolos
        cambiado = False
        for _ in range(200):
            una.correr(1)
            if una.mapa() != 10:
                continue
            if cambiar and not cambiado:
                lugares = max(1, s["SE_LUGARES"])
                direccion = en_la_wram(s["FAR_EFECTO_EN"])
                anotados = una.consola.ram(direccion, lugares)
                una.consola.write_ram(
                    direccion,
                    [(e + 1) % s["EFECTOS_N"] if e != 0xFF else e
                     for e in anotados])
                cambiado = True
            for voz in ("SE_FRAMES", "SE2_FRAMES"):
                if any(una.consola.ram(en_la_wram(s[voz]), 2)):
                    return True
        return False

    assert suena(False), (
        "Success2 no sonó en el mapa 10 sin tocar nada: el caso no mira nada")
    assert not suena(True), (
        "con otro efecto anotado en su lugar, Success2 sonó igual: "
        "`sound_play` no mira `FAR_EFECTO_EN` y tocaría la muestra del "
        "vecino")
