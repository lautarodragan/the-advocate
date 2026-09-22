"""La ventana del mapa contra la cámara: que lo dibujado sea lo que toca.

Esto no lo puede cobrar una golden, y por eso está acá y no en la tanda. La
ventana del tilemap es un toro —la celda `(mx, my)` vive siempre en la ranura
`(mx mod 64, my mod 32)`—, así que una fila que quedó sin redibujar se ve como
un mapa perfectamente plausible **corrido una o dos celdas**: los tiles son los
del vecino y no hay basura que delate nada. La colisión sigue saliendo de la
grilla del cartucho, que no se movió, y entonces se camina sobre paredes.

La comprobación es directa: se le pregunta a la VRAM qué celda tiene en cada
lugar de la pantalla —`Partida.ventana`— y se compara contra lo mismo llegando
por un teletransporte, que llena la ventana entera de cero con `fill_window`.
Si el streaming está bien, las dos fotos son idénticas; si se salteó una fila,
no.

Lo que lo destapó: taro jugando, el 2026-09-22, después de la cinemática de los
Neon Vipers. Y lo que lo causa está medido acá abajo, en
`test_la_camara_llega_a_dos_filas_por_vuelta`.
"""


def coherente(una):
    """Las celdas de la ventana que no coinciden con lo que dibuja un
    `fill_window` en el mismo lugar, y la foto de antes.

    Teletransporta a la partida a la celda donde ya está, que es lo que hace
    que la ROM rearme la ventana entera por su propio camino. Vale sólo con la
    cámara quieta y el pan de vuelta en cero: si no, el teletransporte la deja
    en otro lado y la comparación no compararía lo mismo. Eso se cobra acá.
    """
    antes = una.ventana()
    camara = (una.palabra("camara_x"), una.palabra("camara_y"))
    mapa = una.mapa()
    una.ir_al_mapa(mapa, una.palabra("tile_x"), una.palabra("tile_y"))
    una.correr(10)
    assert (una.palabra("camara_x"), una.palabra("camara_y")) == camara, (
        "el teletransporte dejó la cámara en %s y antes estaba en %s: la "
        "referencia no sirve" % ((una.palabra("camara_x"),
                                  una.palabra("camara_y")), camara))
    despues = una.ventana()
    return [c for c in antes if antes[c] != despues[c]], antes


def test_la_camara_llega_a_dos_filas_por_vuelta(partida):
    """El peor caso del juego son **dos** filas o columnas por vuelta.

    Se suman dos cosas en el mismo eje: el héroe a velocidad 6 camina 8 px por
    cuadro —`paso_medio_por_vel` llega a 64 octavos— y un `PanScreen` a
    velocidad 6 corre la cámara otros 8 —`2 << 6` dieciseisavos—. Son 16 px, o
    sea dos celdas de 8. El salto del héroe no llega: el más largo del juego es
    de 5 celdas en 11 cuadros, 7,3 px por cuadro.

    Está acá y no en un comentario porque es lo que hace que los dos casos de
    abajo sigan reproduciendo el error: si alguien les baja la velocidad, esto
    falla en vez de que los otros dos pasen sin probar nada.
    """
    for caso, eje in (("camara-veloz", "camara_y"), ("camara-veloz-x", "camara_x")):
        una = partida(caso=caso)
        peor = 0
        anterior = None
        for _ in range(60):
            una.correr(1)
            ahora = una.palabra(eje)
            if anterior is not None:
                peor = max(peor, abs(ahora - anterior))
            anterior = ahora
        assert peor >= 16, (
            "%s mueve la cámara %d px por vuelta como mucho, y para saltear "
            "una fila hacen falta más de 8: el caso dejó de reproducir"
            % (caso, peor))


def test_la_ventana_sigue_a_la_camara_que_baja_rapido(partida):
    """Una fila de 8 px que la cámara destapa y nadie redibuja queda mal para
    siempre: la ranura del toro no se vuelve a tocar hasta 32 filas después."""
    una = partida(caso="camara-veloz")
    una.correr(120)
    distintas, todas = coherente(una)
    assert not distintas, (
        "%d de las %d celdas que se ven tienen dibujada otra celda del mapa; "
        "las primeras: %s" % (len(distintas), len(todas), distintas[:6])
    )


def test_la_ventana_sigue_a_la_camara_que_va_a_la_derecha_rapido(partida):
    """Lo mismo por el otro eje: `MARGEN_COLS` tapa cuatro columnas de atraso,
    pero un pan sostenido las gasta en cuatro cuadros."""
    una = partida(caso="camara-veloz-x")
    una.correr(120)
    distintas, todas = coherente(una)
    assert not distintas, (
        "%d de las %d celdas que se ven tienen dibujada otra celda del mapa; "
        "las primeras: %s" % (len(distintas), len(todas), distintas[:6])
    )
