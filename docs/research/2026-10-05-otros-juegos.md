# Otros juegos: el relevamiento

> **Medido el 2026-10-05 sobre `24e0223e`**, por Aguará, sin MSU-1. Es una
> foto: los números son de ese día y este archivo no se actualiza. Cómo
> rehacer cada cuenta está al final, en "Cómo se midió".

Hasta hoy el motor portó un solo juego. taro dejó siete más de RPG Maker
2000 para ver qué tan general quedó —El Dorado, Sunset Over Imdahl, The
Book of Three, Dooms 2, The Frozen World, Desert Nightmare y Vampires
Dawn—, con un pedido: encontrar lo que comparten antes de arreglar nada.


## Resumen

* **Seis de los siete arman un cartucho que arranca**, y en tres el
  comienzo se juega casi igual que en RM2k (Book of Three, Frozen World,
  Dooms 2: ver las hojas). Vampires Dawn no arma ninguno: usa más
  variables que las 256 que el motor tiene.
* **Pero cuatro de los seis necesitan una muleta que no es del juego**: el
  System —la piel de las ventanas— no entra en la paleta de 15 colores de
  la ventana del motor, y el relevamiento lo reemplazó por una copia
  reducida. **Es lo primero que hay que arreglar**: sin eso ningún juego
  con un System con degradé llega a la pantalla.
* **Lo que más se repite**, ordenado por cuántos juegos destraba:

  | arreglo | juegos | qué hace hoy |
  |---|:-:|---|
  | la ventana con más de 15 colores | 5 | corta el juego entero |
  | más de 8 gráficos de la orden 34 por mapa (`ROUTE_GFX_MAX`) | 5 | corta el mapa |
  | los escapes de los mensajes (`\C`, `\N`, `\.`, `\!`, `\|` adentro) | 4 | la página no compila: miles |
  | las páginas de tropa con condición que la ROM no mira | 5 | la página no compila |
  | `ConditionalBranch` por la dirección de un evento | 3 (+ ABL) | la página no compila |
  | las caras en los mensajes | 2 | la página no compila: miles |
  | `EraseScreen`/`ShowScreen` | 2 | la página no compila |
  | `EraseEvent` | 2 (+ ABL) | la página no compila |
  | el título que no entra en VRAM | 2 | corta el juego entero |
  | el grupo vacío al empezar | 2 | corta el juego entero |

* **Armar un proyecto nuevo cuesta**: dieciséis secciones del
  `rm2k-snes.toml` de ABL que las herramientas piden aunque el juego no
  las use, más un caso vacío. Hace falta un `rm2k-snes-project new`, y que
  las claves neutras tengan valor por omisión.
* **Ocho cosas chicas y generales se arreglaron en la rama**, cada una con
  su prueba: cuatro de los siete supuestos de ABL que había listado
  `2026-10-02-el-juego-de-pruebas.md` y cuatro nuevos. Ninguna mueve a ABL.
* **Por dónde seguir**: la ventana por Adeleine, `ROUTE_GFX_MAX`, los
  escapes de los mensajes y `rm2k-snes-project new`, en ese orden. Ver la
  sección 6.


## 1. Los siete

| juego | mapas | idioma | música | Harmony.dll | qué tiene de raro |
|---|--:|---|---|---|---|
| El Dorado | 13 | alemán | 3 MIDI | v1.2 de Ineluki, con teclas | |
| Sunset Over Imdahl | 65 | inglés | 8 MIDI | la de RM2k | archivos en mayúsculas; un solo ítem en la base |
| The Book of Three | 89 | inglés | 67 MIDI | ninguna | System del RTP; héroe invisible |
| Dooms 2 | 93 | inglés | 53 MIDI | ninguna | tres BMP; un `PlayMovie` |
| The Frozen World | 155 | inglés | 73 MIDI | ninguna | 500 variables y 1.500 switches |
| Desert Nightmare | 189 | inglés | MP3 por Harmony | v1.1.1 de Ineluki, con enlaces | ninguna pelea; grupo vacío |
| Vampires Dawn | 440 | inglés | 274 MIDI | la de RM2k | carpeta anidada, con su instalador |

Ninguno usa DynRPG ni fuentes propias. Los siete son de RM2k (ningún
`ldb_id` de 2003).

**Lo de afuera de RM2k**, con las DLL comparadas por su huella: la
`Harmony.dll` de 473.600 bytes es la de RM2k —está en Sunset y Vampires
Dawn, y como `oldharmony.dll` en El Dorado y Desert—. Las otras dos son
**parches de Ineluki**:

* **Desert Nightmare** toca su música en MP3: quince `.link.wav` de texto
  (`..\mp3\Credits.mp3` y `loop`) que su Harmony convierte en una pista
  MP3. El port no los lee: esos temas no suenan. Es lo único de afuera de
  RM2k que cambia lo que se oye, y el MSU-1 sería la forma natural de
  llevarlo; sin MSU-1, habría que conseguir un MIDI o callarlos.
* **El Dorado** trae el parche de teclas (v1.2, "mit KeySupport"), pero no
  tiene ningún `.script`: no lo usa.


## 2. Armar un proyecto

Cada uno es un repo propio, fuera de estos dos —dónde, lo dice la tarea—:
`rm2k-snes.toml`, `justfile`, `data/` volcado con Ditto, `casos/nada.json`
y un README. El primero se armó a mano, contra los "missing key" de las
herramientas; los otros seis los copió un script descartable de setenta
líneas, que es lo que haría un `rm2k-snes-project new`.

**Lo que hubo que llenar sin que el juego lo pidiera**:

* dieciséis tablas o claves que son decisiones de ABL y tienen un valor
  neutro obvio —`[graphics] opaque = []`, `[music] apart_themes = []`,
  `[sound_effects.whole]` vacía, `[events] counters = []`,
  `effect_slots_of_first_copies = 0`…—;
* `[cases] real_game` con su archivo vacío, y `debug_map_entry`, el nombre
  de un caso que no existe;
* `[battle] fallback_backdrop`, que tenía que ser un fondo del juego;
* un cartucho que se llame `release`, con `cases = "all"` y
  `excluded_cases`.

**La propuesta**: que las claves con valor neutro lo tengan por omisión
—`int_or` ya existe para eso—, y que `rm2k-snes-project new <juego>` escriba
lo que sí es del juego: el nombre, el título, las firmas, el mapa de
arranque del árbol y `below`. Es poco código y es lo que cualquier juego
nuevo va a pagar.

**Ditto**: los siete vuelven byte por byte (`just datos-vuelta` en cada
proyecto), después de buscar `RPG_RT.LDB` sin mirar la caja.


## 3. Hasta dónde llega cada uno

### Cada mapa solo

Un cartucho por mapa, con ese mapa de arranque y ningún otro. Con una
salvedad que importa: **un mapa solo compila menos páginas** —las que
llevan a mapas que no están se caen—, así que lo que corta con vecinos
puede no aparecer acá (el 8 de El Dorado arma solo y no con los demás).

Para ver detrás de lo que corta un juego entero se usaron tres muletas,
anotadas en cada proyecto: el System reducido a 12 colores (el propio en
Dooms 2 y Frozen World; el del RTP, reducido, en Book of Three, Desert y
Vampires Dawn, porque el suyo no entra ni reducido), las BMP pasadas a PNG
(Dooms 2), `party = [1]` (Sunset, Desert), y sin título (Frozen, Desert).
`BOOT_FRAMES` subió a 255 sólo en el árbol, sin commitear.

| juego | arman solos | lo que corta a los demás |
|---|--:|---|
| El Dorado | 9 de 13 | `ROUTE_GFX_MAX` (4) |
| Sunset Over Imdahl | 65 de 65 | — (la `ô`, antes del arreglo) |
| The Book of Three | 85 de 89 | la ventana no entra en VRAM (3); la animación de tiles en WRAM (1) |
| Dooms 2 | 89 de 93 | un tema con más de 255 sonidos (3); los nombres del menú (1, el de arranque) |
| The Frozen World | 151 de 155 | la ventana no entra (2); el código del mapa en WRAM (1); `ROUTE_GFX_MAX` (1) |
| Desert Nightmare | 177 de 189 | panoramas sin disposición en VRAM (6); más de 104 NPCs en OAM (3); más de 120 eventos (2); animación de tiles en WRAM (1) |
| Vampires Dawn | 0 de 440 | más de 256 variables (290 + 92); la ventana (19); OAM (19); animaciones de batalla (7); 120 eventos (7) |

**El arranque**: el paquete de audio del mapa de arranque tiene que subir
en 44 cuadros (`BOOT_FRAMES`). Los cinco mapas de arranque de los
cartuchos entran, pero de los mapas que arman solos pasan de 44 —si
fueran el de arranque— 7 de 9 en El Dorado, 126 de 151 en Frozen World y
30 de 89 en Dooms 2, hasta 119 cuadros. Está dimensionado para el de ABL a
propósito (`decisiones/el-arranque-esta-dimensionado-para-el-paquete-de-arranque.md`);
para otro juego tendría que salir del cartucho.

### El cartucho de cada uno

Con todos los mapas y sacando los que cortan, de a uno, hasta que arma:

| juego | arranque | mapas | afuera | por qué afuera |
|---|--:|--:|---|---|
| El Dorado | 8 | 8 de 13 | 4, 5, 6, 11, 12 | `ROUTE_GFX_MAX`; con el 12, el 8 también pasa de 8 |
| Sunset Over Imdahl | 11 | 60 de 65 | 34, 47, 56, 57, 63 | `ROUTE_GFX_MAX` |
| The Book of Three | 1 | 85 de 89 | 44, 46, 69, 74 | los del barrido |
| Dooms 2 | **2** | 86 de 93 | 1, 10, 14, 45, 58, 59, 63 | el 1, elegir personaje, no arma; con vecinos el 2 y el 3 pasan de `ROUTE_GFX_MAX` |
| The Frozen World | 7 | 130 de 155 | los de id 135 o más, y 1, 2, 69, 84 | con más mapas el directorio de muestras pasa de 255 entradas (`SRCN` es un byte) |
| Desert Nightmare | 1 | 165 de 189 | 24 | los del barrido, y doce más por `ROUTE_GFX_MAX` con vecinos |
| Vampires Dawn | — | — | — | las variables |

**`ROUTE_GFX_MAX` es lo que más mapas saca**: veintitrés en cinco juegos.
Son 2 bytes de RAM por gráfico (`route_gfx_buf`); el comentario dice que
ABL pide seis como mucho. Subirlo a 16 cuesta 16 bytes de la RAM baja, y
mueve el `BSS` —o sea, la ROM de ABL—.

### El espacio

`just espacio` en cada proyecto, con los cartuchos de arriba: ninguno pasa
de 78 de los 127 bancos de datos, y bancos 0 y 1 sobran en todos. **El
espacio no es el problema** de ningún juego; los límites que cortan son
de VRAM, de RAM, de paletas y de índices de un byte.


## 4. Las páginas que compilan

`rm2k-snes-events culprits --every-map`, con el request del cartucho de
cada uno (y las muletas de arriba):

| juego | mapas | comunes | tropas |
|---|---|---|---|
| El Dorado | 698 de 972 | 9 de 10 | 0 de 80 |
| Sunset Over Imdahl | 896 de 1.369 | 4 de 8 | 0 de 1 |
| The Book of Three | 1.271 de 1.282 | 19 de 25 | 206 de 746 |
| Dooms 2 | 341 de 496 | 10 de 10 | 1 de 82 |
| The Frozen World | 3.554 de 3.891 | 88 de 100 | 0 de 80 |
| Desert Nightmare | 5.190 de 7.340 | 24 de 30 | 0 de 100 |
| Vampires Dawn | no llega: la compilación corta por las variables | | |

Lo que las traba, por familia y no por código:

* **Los escapes de los mensajes.** El motor entiende `\V[n]` y, como cola
  de la última línea, `\|` y `\^`. Todo lo demás deja la página afuera:
  `\C[n]` (el color) en Sunset —690 cajas sólo con `\C`— y en Desert
  —2.144—; `\N[n]` (el nombre de un actor) en Frozen —696— y Dooms 2;
  `\.`, `\!` y `\|` en el medio de la caja en Sunset y Dooms 2 (667 cajas
  con `\!`). **Cuatro juegos**, y en Frozen World es casi todo lo que no
  compila.
* **Las caras**: `ChangeFaceGraphic` antes de un mensaje. 831 usos en
  Dooms 2, 2.049 en Desert Nightmare. Arrastra a los mensajes de la
  página, que por eso aparecen como culpables "con otros".
* **`ConditionalBranch` por la dirección de un evento** (clase 6): 176 en
  El Dorado, 153 en Sunset, 354 en Desert. Es la misma familia que las 31
  páginas de ABL que pregunta hacia dónde mira el héroe
  (`2026-10-05-los-comandos-que-faltan.md`).
* **`EraseScreen` y `ShowScreen`**, con la transición por omisión o un
  fundido: 270 en El Dorado —siempre con `PlayerVisibility`— y 698 en
  Desert.
* **`EraseEvent`**: 157 páginas en Desert, 127 solas; 3 en El Dorado. Es
  la tarea que ya está en `todo/` por ABL.
* **Las tropas**: casi todas sus páginas tienen una condición que la ROM no
  mira —turnos, HP de un enemigo—. En Book of Three, que tiene muchas,
  `ChangeMonsterCondition`, `TerminateBattle` y los comentarios.
* De a uno: `ChangeMapTileset` (Frozen, 8 páginas), `ChangeSystemGraphics`
  (Sunset, Desert), `ChangeEquipment` (Book of Three), `PlayMovie`
  (Dooms 2), `EnterHeroName` (Dooms 2), `InputNumber` con variable
  (Frozen, Desert).


## 5. La captura al lado del original

Una hoja por juego, donde taro mira las capturas (la tarea dice dónde):
arriba el original con Wine —el runtime de 2015, que no usa Harmony—,
abajo el cartucho en snes9x, en los mismos momentos: el título, y 5, 15 y
30 segundos después de aceptar la primera opción. Las ROMs, al lado de
los builds, una por juego.

Lo que se ve:

* **The Book of Three** y **The Frozen World**: el comienzo es el mismo,
  cuadro por cuadro, salvo el color de la letra (el System reducido).
  Frozen, sin título, entra directo a la escena del mago.
* **Dooms 2**: arranca en el mapa 2 porque el 1 no arma, y el título es
  igual al original.
* **El Dorado**: el título es igual; el mapa 8, elegir dificultad, se ve
  sin sus dos carteles —son imágenes, y el mapa no tiene paletas de sprite
  para ellas: el conversor lo avisa—.
* **Sunset Over Imdahl**: el título igual; la introducción, que en el
  original son imágenes que se funden, queda en blanco con el héroe que el
  relevamiento le puso (`party = [1]`).
* **Desert Nightmare**: el menú de imágenes ("With Intro / No Intro /
  Quit") sale bien, pero **el fondo, un panorama en modo 3, es basura
  celeste**. Es un error de los panoramas, que se mergearon el mismo día:
  no está en ninguna golden porque ABL no tiene uno así. Hay que mirarlo
  antes que nada de lo de arriba.
* **Vampires Dawn**: sólo el original.


## 6. Qué es de quién, y por dónde seguir

### Arreglado en la rama

Cada uno en su commit, con una prueba que se vio en rojo:

| arreglo | juegos | era |
|---|---|---|
| Ditto busca `RPG_RT.LDB` en cualquier caja | Sunset | nuevo |
| un juego sin mapa de debug carga | todos | supuesto 1 |
| un cartucho de un solo mapa no pasa `--maps` vacío | todos | supuesto 3 |
| el System, las caras, el título y las imágenes también del RTP, en cualquier caja | Book of Three | supuesto 5 |
| un líder sin CharSet es un líder sin gráfico | Book of Three, Vampires Dawn | nuevo |
| un ítem que no está en la base no se lleva | Sunset | nuevo |
| el fondo de reemplazo se pide sólo si alguna pelea lo necesita | Desert | supuesto 6 |
| una letra que la fuente no tiene detiene la página y no el juego | Sunset | nuevo |

### Del motor, por cuántos juegos destraba

1. **La ventana con más de 15 colores** (5: Dooms 2, Frozen, Book of
   Three, Vampires Dawn, y Desert por End Game). El supuesto 7. Hoy la
   paleta de la ventana lleva el fondo, el marco, la flecha, el cursor, las
   doce filas del degradé de la letra y la sombra; un System con degradé
   pasa de 30. Además el marco con fondo estirado pide más tiles de los que
   el banco tiene (Book of Three, Vampires: 259-261 de 256), y la elección
   de actor otros dos tiles de más. **La forma es que Adeleine decida qué
   colores se pierden**, como con los mapas —Voodoo no decide colores—, y
   que sea una decisión versionada del juego. Es grande y es de criterio:
   taro tiene que ver cómo queda.
2. **`ROUTE_GFX_MAX`** (5: El Dorado, Sunset, Dooms 2, Frozen, Desert;
   veintitrés mapas). Chico: un `.res` más grande y la constante. Mueve la
   ROM de ABL.
3. **Los escapes de los mensajes** (4). `\C` es el más pedido y el más
   barato de los visibles; `\N` necesita el nombre en la ROM, que ya está
   para el menú; las esperas en el medio de una caja son del compositor.
4. **`rm2k-snes-project new` y los valores por omisión** (todos los
   juegos que vengan).
5. **Las páginas de tropa** (5): las condiciones de turno y de HP.
6. **`ConditionalBranch` por dirección** (3 y ABL), **`EraseEvent`** (2 y
   ABL), **`EraseScreen`/`ShowScreen`** (2), **las caras** (2).
7. **El título en VRAM** (2: Frozen, Desert): imágenes fotográficas de 800
   tiles únicos en 8bpp contra lo que deja el menú.
8. **El grupo vacío** (2: Sunset, Desert): RM2k arranca sin nadie y sin
   héroe visible; el conversor pide un líder para dibujar.
9. **`BOOT_FRAMES` por cartucho** (ninguno lo necesita hoy, pero cualquier
   otro mapa de arranque sí).
10. De a uno: el directorio de más de 255 muestras (Frozen entero), un tema
    de más de 255 sonidos (Dooms 2), los nombres del menú con muchos
    actores (Dooms 2), BMP (Dooms 2; RM2k las acepta y `rm2k-render` las
    rechaza a propósito por no tener contra qué probarlas: ahora hay), las
    reservas de LZ2 en WRAM, los panoramas sin disposición, OAM y los 120
    eventos (Desert, Vampires).
11. **Las variables** (Vampires Dawn entero): 256 ranuras de un byte y 512
    bytes de RAM lejana. Es un rediseño de cómo viven las variables, y lo
    único que destraba es ese juego.

### Propio de cada juego, como parche suyo

* **Dooms 2**: el mapa 1, elegir personaje, pide más nombres de los que el
  banco del menú tiene; un parche podría partirlo.
* **El Dorado**: los carteles del mapa 8 como tiles del mapa y no como
  imágenes.
* **Sunset**: los ítems que la base no tiene son una rareza del juego, y
  ya no cortan nada.

### De afuera de RM2k

* La música en MP3 de Desert Nightmare (Harmony de Ineluki): el MSU-1, o
  callarla.
* La `ô` de Sunset y el alemán de El Dorado: la fuente de la consola es
  ASCII. Una fuente con Latin-1 es trabajo de dibujo, de taro.

### La recomendación

Primero **mirar el panorama de Desert**, que es un error de algo que ya se
dio por hecho. Después, en este orden: **la ventana por Adeleine** —sin eso
cuatro de los siete no se ven sin una copia retocada del juego—,
**`ROUTE_GFX_MAX`** —el arreglo más barato que más mapas devuelve—, **los
escapes `\C` y `\N`** —miles de páginas en cuatro juegos— y **`rm2k-snes-project
new`**. Con esos cuatro, Book of Three, Frozen World y Dooms 2 tendrían un
cartucho jugable sin muletas, y El Dorado y Sunset casi todos sus mapas.
Vampires Dawn va al final: pide rehacer las variables para un solo juego.

Y una advertencia de proceso: **instalar en local sólo algunas
herramientas mezcla dos runtimes**. Cada binario lee `tools/runtime/` del
checkout del que se instaló (`suite::runtime`), así que con `cartridge`
local y `rm2k-snes-audio` global, `BOOT_FRAMES` salía de un árbol y el
ensamblado de otro. No mordió acá porque se vio enseguida; en una rama que
cambie el runtime, morderá. La salida es instalar en local todo lo que lee
el runtime —`cartridge`, `convert`, `rm2k-snes-audio`— cuando se lo toca.


## Cómo se midió

Con las herramientas de esta rama instaladas en `tools/.local-tools`, el
RTP de Don Miguel y el SoundFont de siempre. Los scripts fueron
descartables y no se versionaron:

* **Ditto**: `just datos-vuelta` en cada proyecto: `unpack`, `pack` y
  `cmp` de cada `.lmu`, `.ldb` y `.lmt`.
* **El barrido**: para cada mapa de tipo 1 del árbol, un `rm2k-snes.toml`
  copiado del proyecto con `start_map` y `maps` en ese mapa, y
  `rm2k-snes-cartridges --project <copia> release`; ocho a la vez. La
  causa es la última línea del error. `BOOT_FRAMES = 255` en el árbol
  durante el barrido, y la estimación de cada mapa del `conversor.log`.
* **El cartucho**: todos los mapas menos los del barrido, y sacar el que
  nombra el error hasta que arma; en Dooms 2, sumando de a uno desde el 2;
  en Frozen World, el prefijo más largo por id, por bisección.
* **Las páginas**: el request de `rm2k-snes-events compile` copiado al
  armar el cartucho —un envoltorio en el PATH—, y `culprits --every-map`.
  Las familias de la sección 4 salen de agrupar los culpables de
  `culprits.json` por código y parámetros.
* **Las capturas**: Wine con el runtime de 2015 y un prefijo copiado del de
  ABL, en un Xvfb propio, Enter con `xdotool`; el cartucho con el arnés de
  libretro de ABL (`retro.Console`), A a los 4 s.

Lo que **no** se midió: si lo que compila hace lo que tiene que hacer más
allá de los primeros treinta segundos, ni las peleas, ni la música: nadie
jugó estos cartuchos. Las capturas son lo único que miró la pantalla.
