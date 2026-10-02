"""`\\V[n]` en un mensaje: el valor de la variable, escrito al abrirlo.

Es lo que hace `PendingMessage::DefaultCommandInserter` de easyrpg: el
número en decimal, con el menos si es negativo y sin relleno. La página
`variable-en-texto` deja la 40 en -1234, la 41 en 0 y la 42 en 7, y los
escribe en tres renglones: pegado a letras, dos en un renglón —con ceros
adelante y la `v` en minúscula—, y en el medio de una frase. La página
`variable-en-texto-escrita` dice lo mismo con los números a mano, y las dos
ventanas tienen que ser la misma imagen: el número va donde iba el escape y
lo que sigue se corre lo que mide el número, que es lo que cuenta el largo
del renglón.

En rojo, con el compilador de antes, la página no compila: `just
cartuchos` se niega con "the test page doesn't compile".
"""

from dibujo import pantalla_distinta, pixeles_distintos


def ventana(una):
    imagen = una.imagen().convert("RGB")
    return imagen.crop((0, una.simbolos["WINDOW_LINE"], imagen.width,
                        imagen.height))


def test_el_valor_de_la_variable_se_ve_como_escrito(partida):
    una = partida(caso="variable-en-texto")
    una.correr(60)
    con_variables = ventana(una)
    escrita = partida(caso="variable-en-texto-escrita")
    escrita.correr(60)
    esperada = ventana(escrita)
    distintos = pixeles_distintos(con_variables, esperada)
    donde = pantalla_distinta("variable-en-texto", con_variables, esperada,
                              distintos)
    assert distintos == 0, (
        "la ventana con \\V no se ve como la escrita a mano: %d pixeles "
        "distintos, en %s" % (distintos, donde))
