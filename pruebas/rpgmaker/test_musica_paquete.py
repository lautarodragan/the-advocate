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


def test_el_presupuesto_de_cada_muestra_es_el_de_su_peor_paquete():
    """Todos los temas con todas sus muestras, y cada muestra limitada sólo
    por los paquetes donde está.

    Es la opción A del paso 6 de `workflow/tasks/todo/la-calidad-de-la-musica.md`,
    y la única prueba de este archivo que **no** le pregunta a una ROM
    corriendo: se le pide a `build_varios` el reparto con tres temas y la
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
    leidos = [snes_music.leer_tema(n) for n in nombres]
    teclas = snes_music.zonas_mas_usadas(leidos)
    claves = [snes_music.claves_del_tema(t, teclas) for t in leidos]
    nativo = {k: len(snes_music._muestra(k, snes_music.NATIVA).data)
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
    viejo = snes_music.ARAM_FIN
    try:
        snes_music.ARAM_FIN = (snes_music.SAMPLES_ADDR + libre
                               + 4 * len(nativo) + len(snes_music.SILENCIO))
        _d, _v, temas, banco = snes_music.build_varios(
            nombres, paquetes=[("lleno", [0, 1], []), ("holgado", [2], [])],
            herencia=[("holgado", 0)])
    finally:
        snes_music.ARAM_FIN = viejo

    assert [t["nombre"] for t in temas] == nombres
    for tema in temas:
        assert tema["resumen"]["notas"] == 1.0, (
            "a %s le faltan notas (%.3f): todos los temas aportan sus "
            "muestras al banco" % (tema["nombre"], tema["resumen"]["notas"]))
    assert banco.ocupa(apretados) <= banco.libre, (
        "el paquete de los dos primeros ocupa %d B y hay %d"
        % (banco.ocupa(apretados), banco.libre))
    assert banco.ocupa(apretados) < sum(nativo[k] for k in apretados), (
        "el paquete lleno no recortó nada: la ARAM no se achicó")
    assert banco.ocupa(claves[0] | claves[2]) <= banco.libre, (
        "el paquete del tercero no entra con el primero sonando")
    for k in solo_del_tercero:
        i = banco.claves.index(k)
        assert len(banco.voces[i].data) == nativo[k], (
            "la muestra %s sólo está en el paquete con lugar y aun así se "
            "recortó (%d de %d B): pagó por el paquete lleno"
            % (k, len(banco.voces[i].data), nativo[k]))


def test_cada_paquete_entra_entero_aunque_la_aram_quede_partida(partida):
    """Saltos entre los mapas de paquete más lleno, con la música callada
    antes de cada uno: el paquete de llegada tiene que quedar entero.

    Sin nada sonando no hay muestras que no se puedan mover, y cada paquete
    entra solo —lo garantiza el conversor—. Lo que podía dejar algo afuera
    es que las muestras que el paquete nuevo comparte con el anterior se
    quedan donde estaban, y con el presupuesto por paquete cada uno llena la
    ARAM casi entera: los huecos que dejaban alcanzaban para que no entrara
    una muestra, y pasaba en cinco de estos trece saltos. `paquete_cargar_ya`
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
