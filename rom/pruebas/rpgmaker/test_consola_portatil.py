"""La portable console: los eventos comunes automáticos, el `CallEvent`
compartido y `\\V[n]`, en el sistema del juego que los usa a los tres.

El ítem 81, *Portable Console*, es de switch: prende el 710, y el 710 es el
switch del común 39, `NewMenuActivated`, que es **automático**. RM2k lo corre
apenas el intérprete de primer plano queda libre, en cualquier mapa
(`Game_Map::UpdateForegroundEvents`, easyrpg). El común es una máquina de
estados hecha con `Label`/`JumpToLabel` y `KeyInputProc`: elige el primer
personaje del grupo en su orden —prende el switch de ese personaje, 712 a
725—, izquierda y derecha cambian de personaje, arriba y abajo de rótulo
—856 "Skills", 857 "Tutorials"—, A abre la página del rótulo y B cierra la
consola. Llama al común 40 en cada vuelta, y para Talan al 21: compartidos,
no pegados.

Las imágenes no se ven: hoy entran las que el mapa lleva, y las de la
consola no las lleva ninguno —son de la tarea de las imágenes grandes—. Lo que
se mira es el estado que el común escribe, el héroe quieto mientras corre y,
de lo que se ve, el mensaje de Sern, que dice cuántas almas tiene con
`\\V[0173]`: contra el mismo mensaje escrito con el número a mano.

En rojo, con la ROM sin los comunes automáticos —`common_start` devolviendo
siempre cero—: el 710 se prende y nada más, así que ningún switch de
personaje.
"""

from dibujo import pantalla_distinta, pixeles_distintos
from consola import TITULO_AIRE
from menu import abrir

TALAN, SERN = 14, 28
CONSOLA = 710
SKILLS, TUTORIALES = 856, 857
DE_TALAN, DE_SERN = 715, 722


def ventana(una):
    """La franja de la ventana de mensajes, de su primera línea para abajo."""
    imagen = una.imagen().convert("RGB")
    return imagen.crop((0, una.simbolos["WINDOW_LINE"], imagen.width,
                        imagen.height))


def con_la_consola(partida):
    """La partida con Talan y Sern, después de usar la consola desde el menú:
    la ítem es la única del inventario, así que A sobre la primera."""
    una = partida(caso="consola-portatil")
    una.correr(30)
    una.poner_grupo(TALAN, SERN)
    abrir(una)
    una.tocar_cuadros("a", TITULO_AIRE)     # Items
    una.tocar_cuadros("a", 20)              # la consola
    assert not una.menu_abierto(), "usar la consola tenía que volver al mapa"
    assert una.switch(CONSOLA), "la consola no prendió su switch"
    una.correr(10)
    return una


def test_el_item_81_corre_el_comun_automatico(partida):
    una = con_la_consola(partida)
    assert una.corriendo_una_pagina(), "el común 39 no está corriendo"
    assert una.switch(SKILLS) and not una.switch(TUTORIALES), (
        "el común 39 no empezó: es el que prende el rótulo de Skills")
    assert una.switch(DE_TALAN), (
        "Talan es el primero del grupo en el orden del común, y su switch "
        "no se prendió")
    assert not una.switch(DE_SERN)


def test_las_flechas_recorren_personajes_y_rotulos(partida):
    """Derecha pasa al próximo del grupo —por el común 40, que apaga los de
    todos, y un salto hacia atrás a la etiqueta del siguiente—; abajo y arriba
    cambian de rótulo; izquierda no hace nada más que sonar."""
    una = con_la_consola(partida)
    una.tocar_ticks("right")
    una.correr(5)
    assert una.switch(DE_SERN) and not una.switch(DE_TALAN), (
        "derecha tenía que pasar de Talan a Sern")
    una.tocar_ticks("down")
    una.correr(5)
    assert una.switch(TUTORIALES) and not una.switch(SKILLS)
    una.tocar_ticks("up")
    una.correr(5)
    assert una.switch(SKILLS) and not una.switch(TUTORIALES)
    una.tocar_ticks("left")
    una.correr(5)
    assert una.switch(DE_SERN), "izquierda no cambia de personaje"


def test_el_heroe_no_camina_con_la_consola_abierta(partida):
    """Mientras corre un automático —del mapa o común— el héroe no camina:
    `IsAnyEventStarting`. Con B se cierra, y camina de nuevo."""
    una = con_la_consola(partida)
    antes = una.heroe()
    una.sostener(20, "up")
    una.soltar()
    una.correr(5)
    assert una.heroe() == antes, "el héroe caminó con la consola abierta"
    una.tocar_ticks("b")
    una.correr(5)
    assert not una.switch(CONSOLA), "B tenía que cerrar la consola"
    assert not una.corriendo_una_pagina()
    una.sostener(20, "up")
    una.soltar()
    una.correr(5)
    assert una.heroe() != antes, "cerrada la consola, el héroe no camina"


def test_el_mensaje_de_sern_dice_sus_almas(partida):
    """A sobre Skills de Sern abre el mensaje con `\\V[0173]`, que la página
    de prueba puso en 42: tiene que verse igual que el mismo mensaje con el
    42 escrito. Las dos partidas no conviven —el núcleo es uno—, así que la
    ventana de la primera se saca antes de arrancar la otra."""
    una = con_la_consola(partida)
    una.tocar_ticks("right")
    una.correr(5)
    assert una.switch(DE_SERN)
    una.tocar_ticks("a")
    una.correr(60)
    con_variable = ventana(una)
    escrita = partida(caso="consola-portatil-escrita")
    escrita.correr(60)
    esperada = ventana(escrita)
    distintos = pixeles_distintos(con_variable, esperada)
    donde = pantalla_distinta("consola-sern", con_variable, esperada,
                              distintos)
    assert distintos == 0, (
        "el mensaje de Sern no se ve como el escrito con 42: %d pixeles "
        "distintos, en %s" % (distintos, donde))
