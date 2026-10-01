"""`InputNumber`: los dígitos debajo del mensaje, y la variable que escriben.

Es la puerta de Drust Camp —mapa 68, evento 10, que se dispara al pisarla—,
la única de las dos del juego que está en un cartucho:

    VOICE  "What's the password?"
    InputNumber: seis dígitos, a la variable 143
    si la 143 es 35421: "Fine... come on in." y salta al 201, Net's Droid
                        Emporium
    si no: el héroe da un paso atrás

En RM2k el número va **en la ventana del mensaje**, en la línea de abajo de
su texto, y el mensaje no espera la A: la A es la que entra el número. Los
dígitos arrancan en cero con el cursor en el último; arriba y abajo cambian el
dígito, izquierda y derecha mueven el cursor, y las dos cosas dan la vuelta
(`Window_NumberInput::Update` en easyrpg).

Y de paso cobra lo otro que la puerta pedía: **comparar contra 35421**, que no
entra en un word con signo. La variable es de dieciséis bits, así que el
número se guarda **saturado** en 65535: 100957, que es 35421 más 65536, no
abre la puerta.
"""

from arnes.consola import en_la_wram
from arnes.datos import ranuras_de_variable

DRUST_CAMP = 68
LA_TIENDA_DE_NET = 201
LA_PUERTA = (0, 3)
LA_CLAVE = 143
SEIS = 6


def abierto(una):
    """Si los dígitos están en pantalla y la ROM ya mira el pad: la ventana
    abierta, la línea de los dígitos compuesta y nada componiéndose."""
    return (una.byte("pick_active") == una.simbolos["PICK_NUMBER"]
            and una.byte("msg_open") and una.byte("pick_cancel")
            and not una.byte("msg_state"))


def esperar(una, condicion, que, tope=300):
    for _ in range(tope):
        if condicion(una):
            return una
        una.correr(1)
    raise AssertionError(que)


def en_la_puerta(partida):
    """Una partida que pisó la puerta, con los dígitos ya abiertos."""
    una = partida()
    x, y = LA_PUERTA
    una.ir_al_mapa(DRUST_CAMP, x + 1, y)
    una.sostener(20, "left")
    una.soltar()
    return esperar(una, abierto,
                   "los dígitos no se abrieron: la puerta no disparó, o su "
                   "página no compiló")


def linea(una):
    """Lo que dice la línea de los dígitos, con el cursor: `> ` y blancos."""
    base = en_la_wram(una.simbolos["NUMBER_LINE"])
    largo = una.consola.ram(base, 1)[0]
    letras = una.consola.ram(base + 1, largo)
    return "".join(chr(32 + c) for c in letras)


def tocar(una, boton):
    una.tocar_ticks(boton)
    return esperar(una, abierto, "la línea no se volvió a componer")


def escribir(una, numero):
    """Entra `numero` dígito por dígito, de izquierda a derecha, como lo haría
    alguien con la cruceta, y aprieta A."""
    tocar(una, "right")         # del último, la derecha da la vuelta al primero
    for k, digito in enumerate("%0*d" % (SEIS, numero)):
        assert una.byte("pick_sel") == k
        for _ in range(int(digito)):
            tocar(una, "up")
        tocar(una, "right")
    una.tocar_ticks("a")


def clave(una):
    return una.variable(ranuras_de_variable()[LA_CLAVE]) & 0xFFFF


def test_los_digitos_arrancan_en_cero_con_el_cursor_en_el_ultimo(partida):
    una = en_la_puerta(partida)
    assert una.byte("pick_n") == SEIS
    assert linea(una) == " 0 0 0 0 0>0"
    # Abajo da la vuelta de 0 a 9, y la izquierda mueve el cursor.
    tocar(una, "down")
    tocar(una, "left")
    tocar(una, "up")
    assert linea(una) == " 0 0 0 0>1 9"


def test_la_clave_abre_la_puerta(partida):
    una = en_la_puerta(partida)
    escribir(una, 35421)
    assert clave(una) == 35421
    for _ in range(600):
        if una.mapa() == LA_TIENDA_DE_NET:
            break
        if una.byte("msg_open"):
            una.tocar_ticks("a")
        una.correr(1)
    assert una.mapa() == LA_TIENDA_DE_NET, (
        "con 35421 la rama no abrió la puerta: la comparación contra más de "
        "32767 no compiló, o comparó otra cosa")


def test_un_numero_que_no_entra_se_satura_y_no_abre(partida):
    una = en_la_puerta(partida)
    escribir(una, 35421 + 65536)
    assert clave(una) == 0xFFFF, (
        "100957 no quedó saturado en 65535: %d" % clave(una))
    una.correr(120)
    assert una.mapa() == DRUST_CAMP, (
        "100957 abrió la puerta: el número dio la vuelta y quedó en 35421")
