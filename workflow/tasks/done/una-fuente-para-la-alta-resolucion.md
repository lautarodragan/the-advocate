---
name: "Una fuente para la alta resolución, o más angosta"
description: "Candidatas de fuente que se lean bien en una tele de tubo y entren en 256 o 512 de ancho, parecidas a la de RM2k pero con la legibilidad antes que la fidelidad, para que taro las pruebe en la SNES y las retoque a mano"
type: research
assignee: taro
---

De taro, el 2026-09-30, después de probar en la SNES la ROM de
`testing/rom-de-prueba-del-menu-en-modo-5.md` (Carancho): "ninguna me
convence. Con el texto estirado, se ve raro en la tele de tubo. En algunos
casos se hace difícil leer". Pero no descarta el modo 5, porque **la pelea
también tiene muchos problemas de UI por la resolución**, y ahí podría
ayudar. Lo que propone probar: "una font diseñada para funcionar bien en esa
resolución, que se parezca lo más posible a la original, pero que sacrifique
fidelidad antes que legibilidad". Y está dispuesto a retocarla a mano,
pixel por pixel.

## Qué se armó (Espinillo, 2026-09-30)

Tres candidatas, cada una como **una hoja de glifos para editar a mano** en
`rom/experimentos/fuentes/hojas/`, y **`just fuentes`**, que lee las hojas,
arma con ellas las maquetas del menú de pausa y de las ventanas de la pelea,
arma la ROM de prueba con ésas y la verifica en snes9x, bsnes y mesen-s,
pantalla por pantalla contra su maqueta. Cómo se edita una hoja, en
`rom/experimentos/fuentes/LEEME.md`; después de editarla alcanza con volver
a correr la receta.

La ROM es la hermana de `menu-modo-5`, con su mismo código: `armar.py` y
`verificar.py` de ahí aprendieron a recibir otras pantallas —el modo sale del
ancho, las caras de un `.json` al lado— y a poner los bancos que hagan
falta. `just menu-modo-5` sigue saliendo byte por byte igual (sha256 antes y
después: `1b85307e…`).

Las candidatas, derivadas de la Mincho con reglas mecánicas (un punto de
partida, no un diseño):

1. **`baja-ancho-variable`**: la resolución de siempre. Cada glifo recortado
   a su tinta más un pixel de aire, y de dos columnas interiores iguales
   queda una —la "o", la "n", la "H" pasan de 5 a 4—: lo que hacen FF6 o
   Chrono Trigger. Dígitos y barra a mano, de 4 de tinta, todos de 5 de
   avance. **No tiene el problema de la tele.**
2. **`alta-ancho-fijo`**: alta resolución, avance fijo de 10 (5 de baja).
   Cada columna de la Mincho con un trazo vertical de 2 o más filas mide 2
   pixeles de alta, las demás 1, y las iguales y seguidas se juntan; entre
   dos trazos el hueco mide 2. Las de tres trazos (m, w, M, W) se angostan a
   8 con huecos de 1.
3. **`alta-ancho-variable`**: la misma regla, sin angostar, con 2 de aire.

La regla de los trazos se probó con "3 o más filas" también: ahorra un 4 %
más pero deja de 1 pixel las diagonales de 2 filas (la "v", la "w"), que es
lo que se borronea. Quedó la de 2.

### Cuánto ancho gana cada una

El **avance promedio**, pesado por las letras de los nombres, títulos,
técnicas, ítems, estados y enemigos del juego, en pixeles de baja: la de
hoy 6; `baja-ancho-variable` 4,7 (78 %); `alta-ancho-fijo` 5 (83 %);
`alta-ancho-variable` 3,64 (61 %).

Pero lo que importa es si entra la **disposición** de RM2k, y eso lo mide
`maquetas.py` empaquetándola: cada bloque de texto empieza donde termina el
anterior más un hueco fijo. Con la fuente de hoy el menú empaquetado mide
justo 320, así que los huecos son los de RM2k. `just fuentes` lo imprime
(`build/fuentes/maquetas/medidas.txt`); el 2026-09-30, con las hojas como
salieron:

| candidata | menú, como RM2k | menú, apretado | pelea, grupo | pelea, peor caso |
|-----------|-----------------|----------------|--------------|------------------|
| baja-ancho-variable (256) | 277: falta 21 | 255: **entra** | 228: entra | 268: falta 12 |
| alta-ancho-fijo (512)     | 566: falta 54 | 522: falta 10  | 458: entra | 538: falta 26 |
| alta-ancho-variable (512) | 510: **entra** | 466 | 409: entra | 486: entra |

"Peor caso" es con los textos más largos del juego —"Gang Member" de
nombre, "Agency Guard" de título, "Brambles" de estado, "Components" de
técnica—; "grupo", con Kersh, Core y Manta. En el menú los dos casos casi
no se diferencian, porque lo que manda es la línea del Ex: "Ex" y dos
campos de 6 cifras, 76 pixeles en baja. **"Apretado" son tres concesiones**:
4 de aire a cada lado de la cara en vez de 8, la ventana de comandos sin la
holgura del cursor, y la experiencia en campos de 5 cifras (un actor de ABL
pasa de 99.999 cerca del nivel 40).

**Así que, con todas las letras: la de ancho variable en baja resolución no
entra con la disposición de 320 tal cual —le faltan 21 pixeles—, pero con
esas tres concesiones sí entra, con el peor caso del juego, y le sobra 1.**
Es la que no tiene el problema de la tele. La pelea entra con el grupo de
hoy (sobran 28) y no con el peor caso: un nombre de 11 letras, un estado
de 8 y "Components" en los comandos se pasan por 12.

`alta-ancho-fijo` no tiene a favor nada más que la legibilidad: en la ROM
cuesta lo mismo que la de ancho variable (ver abajo) y no entra en el menú.
Sólo vale si en la tele se lee claramente mejor que la variable.

### Qué hay para mirar

* `/shared/capturas/2026-09-30-fuentes/`: las comparaciones lado a lado
  (RM2k, la ROM de hoy y las tres, al mismo tamaño físico), los recortes ×4
  de la fila de Kersh, las hojas con la letra arriba, las hojas para editar,
  las maquetas sueltas y `medidas.txt`. Con un `LEEME.txt`.
* `/shared/experimentos/2026-09-30-fuentes/`: la ROM, `fuentes.sfc`, con un
  `LEEME.txt` de qué mirar en la tele.

### Lo que costaría en la ROM (estimado, sin implementar)

**La ROM ya tiene un compositor de texto** (`compose_char` en
`messages.s`): la ventana de mensajes no usa una letra por celda, compone
glifos de 6 en un búfer de tiles de 4 bits y lo sube por DMA. Lo que no
sabe es el ancho variable: calcula la x como `8 + 6 × columna`, que módulo 8
cae sólo en 0, 2, 4 o 6, y por eso trae la fuente **pre-corrida en esas
cuatro fases** con el color y la sombra ya puestos: 95 glifos × 156 bytes ×
4 = 59 KB (`font_prerender` en `screens/src/message_window.rs`).

* **`baja-ancho-variable`, en baja.** Es el compositor que ya hay con tres
  cambios: una tabla de avances (95 bytes), la x acumulada en vez de
  multiplicada, y **las ocho fases** en vez de cuatro. Con las tablas
  pre-corridas eso duplica la fuente, +59 KB por color, y el menú usa tres
  (blanco, rojo y gris): no conviene. Lo barato es una fuente de 1 bit
  (95 × 12 bytes, 1,1 KB) y correrla al componer, que con la pantalla
  apagada —el menú abre así— no se nota. Lo caro es pasar el menú y la
  pelea de "una letra por celda" (`layout.rs`, `slot_glyph_cells`) a texto
  compuesto. Medido sobre la maqueta, el texto del menú toca 299 tiles de
  8x8 (279 distintos, ~9 KB); con las tres caras, 108 más, son unos 400, y
  la zona del menú de hoy (`SLOT_VRAM`..`SLOT_MAP` en `vram.py`) llega a
  448: entra, justo. La pelea toca 158 (~5 KB), y al cambiar los HP se
  recompone una fila, ~30 tiles en el vblank.
  **Unos cientos de bytes de código y dos o tres días**, casi todo de mover
  las pantallas a texto compuesto.
* **De regalo, en los mensajes**: hoy entran 39 caracteres por línea de 6;
  con un avance promedio de 4,7, unos 49, que es lo que entra en la ventana
  de RM2k. Habría muchas menos cajas partidas por el reparto (`refit`). Ahí
  el compositor corre con el mapa andando y con un tope de 5 letras por
  cuadro (`MSG_CHARS`), medido con las tablas pre-corridas: con la fuente
  de 1 bit habría que volver a medirlo, o pagar los 59 KB de las ocho fases
  sólo para el color de la ventana.
* **Las de alta**, lo que estimó Ñacurutú para el modo 5 en
  `maqueta-del-menu-en-alta-resolucion.md`: el cambio de modo y las caras en
  sprites son baratos; el texto pide el mismo compositor, en alta, y unos
  25 KB de VRAM. Medido sobre estas maquetas, el texto del menú toca 486
  tiles con la variable y 531 con la fija (12 KB distintos las dos), y el
  de la pelea, 246 y 280. **El avance fijo de 10 no ahorra el compositor**: 10 no
  divide a 16, así que los glifos tampoco caen alineados con las celdas de
  16x8 del modo 5. Las dos de alta cuestan lo mismo, y es más que la de
  baja: el compositor de baja ya existe y el de alta hay que escribirlo, más
  el modo 5 en cada pantalla que lo use.

### Falta

Que taro las mire en la tele con la ROM, y que retoque las hojas. Lo que
más mano pide está en las de alta: la "s", la "c", la "a" y las diagonales
tienen pixeles sueltos de alta. Con una hoja editada, `just fuentes` vuelve
a armar todo.

Al mergear no hay nada que instalar: no toca Rust ni agrega scripts al PATH.

# Lo que eligió taro

El 2026-10-03: le gustan las dos de ancho variable, la de baja y la de
alta, y quiere probarlas en el juego. Primero la de baja en todo el juego
—`las-letras-de-ancho-variable.md`, en el repo de las herramientas—, y
después el modo 5 como perilla del proyecto, para comparar dos builds sin
revertir nada.
