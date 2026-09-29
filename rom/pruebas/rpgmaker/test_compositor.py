"""El compositor de texto con un largo de renglón que no puede ser.

Ésta es la red que faltó dos veces. Un cuadro de texto trae, por renglón, un
byte con cuántos caracteres tiene, y ese byte sale del cartucho.
`compose_char` escribe en `texto_buf` con
un desplazamiento que sale de la columna, así que un largo mayor que
`MENSAJE_COLS` escribe **fuera del buffer**, y lo que hay del otro lado es la
tabla del HDMA de la ventana, la imagen de OAM y `vq_n`, el contador de la cola
de poses. Con `vq_n` alto, `vram_drain` sube bloques de 128 bytes a direcciones
cualquiera de la VRAM y la pantalla se hace basura unos cuadros después, en
cualquier otro lado. Es lo que taro reportó dos veces —la fábrica de Delcentric
el 2026-09-13 y la cinemática de los Neon Vipers el 2026-09-14— y las dos veces
la causa de fondo fue un puntero mal sumado, no el compositor.

Por eso el largo se inventa **desde afuera** en vez de armar un cartucho con un
mensaje roto: lo que se quiere medir no es cómo llegó el largo malo, sino que un
largo malo —venga de donde venga— corte el renglón en vez de romper la pantalla.
"""

# Un largo que no puede existir: el tope real son 39 columnas. Con 70 se pasan
# 31, y alcanzan para llegar hasta la cola de VRAM: la columna 64 escribe una
# palabra en `texto_buf` + 2534, y `vq_n` cae justo en el 2535 —el buffer mide
# 1968—.
LARGO_INVENTADO = 70

# Cuántos ticks se le dan a componer el renglón. `MSG_CHARS` caracteres por
# vuelta, así que setenta entran en unas quince; treinta es margen.
TICKS = 30


def _componer(p, largo, ticks=TICKS):
    """Pone al compositor a armar un renglón de `largo` caracteres y lo deja
    correr.

    Es el estado en el que `message_tick` se deja a sí mismo después de leer el
    byte de largo del cartucho, salteando esa lectura: `msg_cebada` en 1 dice
    que el fondo del renglón ya está en el buffer, así que lo próximo que hace
    es componer. `msg_ptr` apunta al bloque de textos, que es ROM legible: qué
    caracteres salgan de ahí no importa, importa dónde se escriben.
    """
    mensajes = p.simbolos["mensajes"]
    p.consola.write_ram(p.simbolos["msg_ptr"],
                        [mensajes & 0xFF, (mensajes >> 8) & 0xFF,
                         (mensajes >> 16) & 0xFF])
    for nombre, valor in (("msg_lineas", 1), ("msg_linea", 0),
                          ("msg_col", 0), ("msg_largo", largo),
                          ("msg_cebada", 1), ("msg_subir", 0),
                          ("msg_estado", 1)):
        p.poner_byte(nombre, valor)
    for _ in range(ticks):
        p.correr(1)
    return p


def _cola_de_la_ram(p):
    """Todo lo que vive entre el final de `texto_buf` y el final de la cola de
    VRAM, que es exactamente lo que un desborde del compositor pisa."""
    desde = p.simbolos["hdma_sc"]
    hasta = (p.simbolos["vq_n"] + 1
             + p.simbolos["VQ_MAX"] * p.simbolos["VQ_STRIDE"])
    return bytes(p.consola.ram(desde, hasta - desde)), desde


def test_un_largo_inventado_no_escribe_fuera_del_buffer(partida):
    """El caso que rompía la pantalla, medido por diferencia.

    Se corre dos veces lo mismo y sólo cambia el largo: una con 39, que es lo
    máximo legal, y otra con 70. Si el tope funciona, la segunda dibuja las
    mismas 39 columnas, se come los 31 bytes que sobran sin escribirlos, y **la
    RAM de la otra punta queda idéntica**. Comparar contra la primera corrida en
    vez de contra una lista de direcciones es lo que hace que la prueba no
    dependa de qué caracteres salgan del cartucho ni de dónde esté cada
    variable.

    Comprobado en rojo sacándole el tope a `message_tick`: **207 bytes
    distintos**, desde `hdma_sc` hasta adentro de `vq`.

    Las dos partidas no se pueden tener vivas a la vez —el núcleo de libretro es
    uno solo y arrancar la segunda resetea la primera— así que la foto de la
    primera se saca antes de empezar la otra.
    """
    legal = partida()
    antes, desde = _cola_de_la_ram(
        _componer(legal, legal.simbolos["MENSAJE_COLS"]))
    despues, _ = _cola_de_la_ram(_componer(partida(), LARGO_INVENTADO))
    distintos = [desde + i for i in range(len(antes))
                 if antes[i] != despues[i]]
    assert not distintos, (
        "un renglón de %d caracteres escribió %d bytes fuera de `texto_buf`, "
        "encima del HDMA de la ventana, de la imagen de OAM y de la cola de "
        "VRAM: %s..." % (LARGO_INVENTADO, len(distintos), distintos[:8]))


def test_el_renglon_cortado_igual_consume_sus_bytes(partida):
    """El tope corta el dibujo, no la lectura.

    Es la mitad que un tope ingenuo se lleva puesta: si el compositor dejara de
    leer en la columna 39, el puntero quedaría treinta y un bytes atrás y el
    renglón que sigue arrancaría del medio de éste, o sea que el tope
    convertiría un renglón feo en el mensaje entero corrido. Se mide con
    `msg_ptr`, que al terminar el renglón tiene que haber avanzado los setenta
    caracteres.
    """
    p = partida()
    mensajes = p.simbolos["mensajes"]
    _componer(p, LARGO_INVENTADO)
    bajo, alto, banco = p.consola.ram(p.simbolos["msg_ptr"], 3)
    ptr = (banco << 16) | (alto << 8) | bajo
    assert ptr - mensajes == LARGO_INVENTADO, (
        "el compositor tiene que consumir los %d caracteres del renglón aunque "
        "sólo dibuje %d: avanzó %d"
        % (LARGO_INVENTADO, p.simbolos["MENSAJE_COLS"], ptr - mensajes))
