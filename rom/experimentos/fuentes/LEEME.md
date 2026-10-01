# Las fuentes candidatas

Fuentes para el texto del menú y de la pelea que se parezcan a la de RM2k
pero pongan la legibilidad antes que la fidelidad: la de RM2k escalada a la
alta resolución se veía rara en una tele de tubo. No es el juego: son hojas
de glifos, maquetas armadas con ellas y una ROM de prueba que las muestra.

    just fuentes                 arma las maquetas, la ROM, y la verifica
    just fuentes <directorio>    y deja ahí las capturas de los emuladores

Todo sale a `build/fuentes/`: las maquetas y `medidas.txt` en `maquetas/`,
las hojas de comparación en `comparar/`, y la ROM, `fuentes.sfc`. La ROM es
la hermana de la de `menu-modo-5`, con el mismo código: derecha o A pasa a
la pantalla siguiente, izquierda a la anterior, y B esconde el número de la
esquina.

## Las hojas

`hojas/` tiene una por candidata, y son **la fuente de verdad**: se editan
a mano y la receta vuelve a armar todo sin tocar código.

| hoja                      | celda | qué es |
|---------------------------|-------|--------|
| `rm2k.png`                | 8     | La Mincho de easyrpg, la de hoy, de 6 de avance. Es la referencia y no se edita: sirve para dibujar RM2k y para empezar de cero. |
| `baja-ancho-variable.png` | 8     | Baja resolución, ancho variable: cada glifo recortado a su tinta más un pixel de aire, y de dos columnas interiores iguales queda una (la "o" de 5 pasa a 4). Dígitos y barra a mano, de 4 de tinta y 5 de avance, todos iguales. |
| `alta-ancho-fijo.png`     | 16    | Alta resolución, avance fijo de 10: cada columna con un trazo vertical mide 2 pixeles de alta y las demás 1; las letras de tres trazos (m, w, M, W) se angostan hasta 8 con huecos de 1. |
| `alta-ancho-variable.png` | 16    | Alta resolución, ancho variable, con la misma regla de los trazos pero sin angostar: cada glifo mide lo suyo más 2 de aire. Dígitos iguales entre sí. |

Las tres candidatas se derivaron una sola vez de la Mincho, con reglas
mecánicas: son un punto de partida, no un diseño. Lo que más pide mano está
en las de alta: la "s", la "c", la "a" y las diagonales tienen pixeles de
alta sueltos, que es justo lo que la tele borronea.

### Cómo se edita

Cada hoja es un PNG **indexado** de cuatro colores. Lo que cuenta es el
índice, no el color: se puede cambiar la paleta para ver mejor.

| índice | color          | qué es |
|--------|----------------|--------|
| 0      | negro          | el fondo |
| 1      | blanco         | el glifo |
| 2      | rojo           | la marca del avance |
| 3      | gris azulado   | la grilla: se ignora |

Los 95 caracteres de ASCII, del espacio a la `~`, en su orden: 16 por fila,
seis filas. `comparar/hoja-*-con-letras.png` es la misma hoja con la letra
arriba de cada celda. El juego usa 93; la `` ` `` y la `~` no aparecen en
ningún texto.

Cada celda mide 8 columnas (16 en las de alta) por 13 filas:

* **filas 0 a 11, el glifo**, con la línea de base de la Mincho: las
  mayúsculas van de la fila 1 a la 9, y lo que baja, hasta la 11;
* **fila 12, el avance**: tantos pixeles rojos, pegados desde la izquierda,
  como columnas corre la línea después del glifo. **El aire entre letras va
  en el avance**, no en el glifo: una letra de 4 de tinta con 1 de aire
  lleva 5 rojos. Si la marca tiene un hueco, la receta se niega.

**La sombra no se dibuja**: la agrega la receta, como RM2k y como la ROM,
un pixel de baja a la derecha y uno abajo (en las de alta, 2 columnas y 1
fila). Por eso el aire de una letra es también donde cae su sombra.

En Aseprite: abrir el PNG, que entra en modo indexado, y dibujar con el
índice 1. La grilla de la hoja es parte de la imagen; la de Aseprite se
puede poner igual (*View > Grid Settings*: 9x14 en las de baja, 17x14 en
las de alta, con origen en 0,0). **En las de alta conviene mirar con los
pixeles el doble de altos**, que es como salen en la tele: *Sprite >
Properties > Pixel Aspect Ratio > Double-high Pixels (1:2)*. Guardar como
PNG, sin pasar a RGB.

Los dígitos de las tres candidatas son **todos del mismo ancho**, para que
los números se alineen en columna como en RM2k; si se toca uno, conviene
tocar el avance de todos.

## Qué mide

`medidas.txt` dice, para cada candidata, cuánto ancho necesitan el menú y
la pelea y si entran en su pantalla. Las maquetas no escalan la disposición
de RM2k: la **empaquetan** —cada bloque de texto empieza donde termina el
anterior más un hueco fijo— con la fuente de la hoja. Con la fuente de hoy,
el menú empaquetado mide justo 320, que es lo que mide en RM2k: los huecos
son los suyos.

Se mide con los textos más largos del juego —nombres y títulos de los
actores con cara, estados y comandos— y con los del grupo que se dibuja; y
cada uno, como en RM2k y "apretado", con tres concesiones que dice
`medir_menu`. La maqueta se dibuja con el primero que entra; si ninguno
entra, el texto se choca, y eso es lo que se ve.

Las ventanas, los cursores y las caras salen de `rm2k-render`, con el
System y las caras del juego, en pixeles de baja; en alta cada uno ocupa
dos. Las pantallas de la pelea muestran sólo las dos ventanas de abajo.
