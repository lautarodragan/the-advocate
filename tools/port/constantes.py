"""Números del port que usan varios módulos y no son de ninguno.

Están acá para que quien los necesite no tenga que importar el módulo que los
usa más, y con él todo lo que ése importa: `eventos` preguntaba a `pantallas`
cuántas ranuras de equipo hay, y `pantallas` importa `eventos`.
"""

# La pantalla de la consola, en pixeles y en celdas de 8x8.
CELL = 8
ANCHO = 256
ALTO = 224
COLS = ANCHO // CELL            # 32
FILAS = ALTO // CELL            # 28

# Cuántas entradas de CGRAM se lleva el menú, que va en BG2 a cuatro bits por
# pixel: una paleta de dieciséis, la 0. Son las **primeras** de CGRAM porque un
# BG de 4bpp sólo alcanza las de abajo, así que la imagen no puede quedarse con
# ellas y arranca corrida.
MENU_CGRAM = 16

# Cuántos colores le quedan a la imagen. Bajar de 256 a 240 no se ve: ya venía
# de 369, y los que se fusionan son los que aparecen en un puñado de pixeles.
COLORES = 256 - MENU_CGRAM

# Cuántas líneas de texto entran en la ventana de mensaje. Ver `ventana.py`.
LINEAS = 4

# Cuántos caracteres entran en una línea, y de dónde sale el número. No es el
# ancho de la ventana: es el banco de tiles. El área de texto de la ventana son
# 30 celdas de 8x8 de ancho, y sus tiles no se deduplican porque la ROM los
# reescribe, así que son 30x8 = 240 tiles fijos que con los 12 de la ventana
# vacía llegan a 252 de los 256 que hay. Con 40 caracteres la sombra del último
# se pasa a la celda 31 y harían falta ocho tiles más.
#
# Medido sobre las 18.808 líneas de mensaje del juego: truncar a 39 pierde el
# 1,58% de los caracteres, contra el 1,09% de truncar a 40.
# Medido contra A Blurred Line: un supuesto del motor, no un dato del juego.
# Ver `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
COLUMNAS = 39

# Cuántas ranuras de equipo tiene un actor de RM2k.
RANURAS_EQUIPO = 5              # arma, escudo, armadura, casco, accesorio

# Cuántos enemigos caben en una pelea: lo que entra en la pantalla de texto sin
# taparle nada al grupo. La tropa más grande del juego tiene ocho miembros, así
# que con ocho no se pierde ninguna.
ENEMIGOS_MAX = 8
