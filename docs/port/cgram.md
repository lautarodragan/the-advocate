# El reparto de CGRAM lo decide el conversor

Las 256 entradas de CGRAM se parten al medio: la mitad de arriba es de los
sprites. La de abajo la comparten el fondo, que va en 8 bits y direcciona CGRAM
en directo, y la capa de encima, que va en 4 bits y por lo tanto cuenta su
índice dentro de una paleta de 16.

Un corte fijo no sirve: con dos paletas clavadas para la capa de encima se caen
los mapas cuya capa de encima pide tres o más, que son varias decenas y entre
ellos los tres primeros del juego. Y hay una causa que **no la arregla ningún
reparto**: un tile suelto de 17 colores no entra en una paleta de 15 por muchas
que haya, y eso se arregla fusionando colores: `allocator.reduce_colors`.

Así que el corte lo decide el conversor mapa por mapa, y **el fondo tiene la
primera opción**: se queda con las paletas que necesita para los colores que
realmente usa, y la capa de encima se lleva las que sobren —hasta las que pida,
nunca más— y fusiona si no le alcanzan. Va en ese orden porque son 300 mapas
cuya capa de encima pide una o dos paletas contra un puñado que pediría siete:
servir primero al de encima le sacaría colores al fondo en todos para que unos
pocos no fusionen.

El informe del conversor lo dice mapa por mapa: cuántos colores se quedó el
fondo de cuántos había, cuántas paletas se llevó la capa de encima, desde cuál,
y cuántos colores le tocó fusionar.

Que las dos capas se conviertan juntas no es comodidad: el corte no lo puede
decidir ninguna por su cuenta, así que `convert_layers()` es el único lugar
donde está escrito. Antes cada llamador convertía una y después la otra, y que
las tres copias del orden coincidieran era cuestión de suerte —justo la forma de
error que ya nos había aflojado la comparación una vez.

