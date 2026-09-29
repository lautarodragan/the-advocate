"""El oro del grupo: `ChangeGold` y la rama que lo pregunta.

No se muestra en ningún lado —el menú de RM2k no existe acá— así que lo único
que lo hace comprobable es la rama de `ConditionalBranch` que lo compara. Las
dos cosas se hicieron juntas por eso.

Las reglas salen de `Game_Party::GainGold` y de
`Game_Interpreter::CommandConditionalBranch` caso 3:

    GainGold(n)   oro = recortar(oro + n, 0, 999999)
    la rama       con la polaridad en 0 es `oro >= x`, y si no `oro <= x`

**Y las dos comparaciones no son una la negación de la otra**: en la igualdad se
cumplen las dos. Es lo que hace que la ROM las calcule por separado en vez de
dar vuelta un bit, y lo que estas pruebas cuidan.
"""

ORO_MAX = 999999


def test_arranca_en_cero(partida):
    assert partida().oro() == 0, "el oro arranca con basura de la RAM"


def test_el_tope_es_el_de_rm2k(partida):
    una = partida()
    assert una.simbolos["GOLD_MAX"] == ORO_MAX, \
        "el tope que la ROM lleva no es el de `MaxGoldValue()`"


def test_la_escena_del_despertar_le_da_cien(partida):
    """El caso del juego: el evento 4 del mapa 7 hace `ChangeGold [0, 0, 100]`.

    Es la escena en la que Talan se despierta, la misma que prende el switch 24
    y arranca el cronómetro. Sirve de banco porque es la única suma de oro que
    hay en los mapas de la demo.
    """
    una = partida(switch=[23])
    una.ir_al_mapa(7, 10, 7)
    for _ in range(400):
        if una.oro() == 100:
            break
        if una.byte("msg_open"):
            una.tocar_ticks("a")
        else:
            una.correr(1)
    assert una.oro() == 100, \
        "después de la escena del despertar el oro es %d y tendría que ser 100" \
        % una.oro()


def test_el_peaje_cobra_si_alcanza_y_no_da_la_vuelta_si_no(partida):
    """El peaje del mapa 8: `DetourOfficer` pregunta `oro >= 500` y resta 500.

    Es el único lugar del juego que usa las dos mitades a la vez, así que sirve
    para las dos: con 500 justos la rama se cumple —`>=` incluye la igualdad, y
    es donde una implementación que diera vuelta un bit se equivocaría— y el
    oro queda en cero; con menos, no cobra y **no da la vuelta**, que sin el
    recorte de `GainGold` daría más de dieciséis millones.
    """
    for antes, despues in ((500, 0), (700, 200), (499, 499), (0, 0)):
        una = partida(switch=[24])
        una.ir_al_mapa(8, 62, 33)
        una.poner_byte("hero_dir", una.simbolos["DIR_UP"])
        una.poner_oro(antes)
        for _ in range(30):
            if una.oro() != antes:
                break
            una.tocar_ticks("a")
            for _ in range(40):
                if una.oro() != antes:
                    break
                if una.byte("msg_open"):
                    una.tocar_ticks("a")
                else:
                    una.correr(1)
        assert una.oro() == despues, \
            "con %d de oro el peaje dejó %d y tendría que dejar %d" \
            % (antes, una.oro(), despues)
