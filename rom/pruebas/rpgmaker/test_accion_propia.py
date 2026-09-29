"""La tecla de acción también mira la celda del propio héroe.

`Game_Player::CheckActionEvent` prueba dos celdas y **cada una pide la capa
contraria**:

    CheckEventTriggerHere   la celda del héroe,   GetLayer() != Layers_same
    CheckEventTriggerThere  la de adelante,       GetLayer() == Layers_same

No es simetría de adorno: un evento de la capa del héroe le cierra el paso, así
que nunca podría pararse encima; y uno de otra capa no lo frena, así que se le
camina por arriba.

La puerta que sale del pad de Talan es `TalDoorTop`, evento 3 del mapa 7, de
acción y **capa 2**, y se abre parándose encima y apretando A. Sin esto, del
pad no se puede salir.
"""


MAPA, DESTINO = 7, 8
PUERTA = (9, 12)        # TalDoorTop, capa 2: el héroe se para ahí
ABAJO = (9, 13)         # TalDoorBottom, capa del héroe: cierra el paso
LISTO = 24              # el switch que activa la página con el script


def test_pararse_encima_de_la_puerta_y_apretar_a_la_abre(partida):
    una = partida(switch=[LISTO])
    una.ir_al_mapa(MAPA, *PUERTA)
    for _ in range(25):
        if una.mapa() == DESTINO:
            break
        una.tocar_ticks("a")
        for _ in range(90):
            if una.mapa() == DESTINO or una.byte("msg_open"):
                break
            una.correr(1)
    assert una.mapa() == DESTINO, \
        "la puerta del pad no se abrió: sigue en el mapa %s. Es de acción y " \
        "capa 2, así que la dispara la celda propia y no la de adelante" \
        % una.mapa()


def test_de_frente_no_la_dispara(partida):
    """Y la de adelante **no** tiene que dispararla: ésa pide la capa del héroe.

    Es la otra mitad de la regla, y sin ella la primera pasaría también en un
    mundo donde la tecla de acción mirara las dos celdas sin filtrar por capa.
    El héroe se para en (9,14) —no puede en (9,13), que lo bloquea el
    `TalDoorBottom`— y mira hacia arriba.
    """
    una = partida(switch=[LISTO])
    una.ir_al_mapa(MAPA, ABAJO[0], ABAJO[1] + 1)
    una.poner_byte("hero_dir", una.simbolos["DIR_UP"])
    for _ in range(6):
        una.tocar_ticks("a")
        una.correr(30)
    assert una.mapa() == MAPA, \
        "se disparó algo mirando de frente a un evento que no es de la capa " \
        "del héroe"
