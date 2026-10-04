---
name: "La caché de ranuras de sprites"
description: "Cada evento pide una ranura de VRAM al entrar en pantalla y la suelta al salir, en vez de tener una fija por el mapa entero; con ayudas para achicar el pico, y la granja (127) de ABL como primer caso"
type: feature
assignee: taro
---

De taro, el 2026-10-03: "vamos con la 1", entre los caminos para la granja
de ABL (`workflow/tasks/testing/mundo-8-paradise.md` y
`mundo-7-camino-a-paradise.md`, opción D, en ABL). Es del motor: sirve para
cualquier mapa con mucha gente, de cualquier juego.

Lo medido (Puma, 2026-10-01) sobre el 127: 22 eventos que caminan y 18
poses quietas; en pantalla a la vez, 30 ranuras distintas sin margen y 36
con 2 celdas, contra 32 de "+sprite". La caché sola entra justa: hacen falta
ayudas que achiquen el pico (compartir quietos como en el 108, espejados en
una ranura, …).

Primero se mide sobre todos los mapas del juego —cuántos destraba la caché
sola y cuántos con cada ayuda—, y después se implementa.

Para después (taro): ver si vale hornear NPCs en el 127 —los de la escena
de bandidos que se queden quietos—, una vez que esto esté.

Base: herramientas `60097b1a`, ABL `57ef34d`.

# Lo medido, sobre el juego entero

**Cómo**: una copia del `rm2k-snes.toml` de ABL con `below = 400` y sin
excluir el 58, el 104 ni el 111 —quedan afuera sólo las carpetas del árbol
y los respaldos inalcanzables—, convertida con `rm2k-snes-cartridges
--convert-into` y un `wally` envoltorio que guarda el pedido de cada mapa.
La conversión entera se frena antes (el actor 34, candidato a líder, no
tiene CharSet: es el límite del estudio de los mapas por el MSU-1), así que
cada pedido se volvió a correr con el `wally` de hoy, sin el actor 34 entre
los líderes, y sobre lo que contestó se contó. Son **320 mapas**. Los
scripts quedaron en `/extras/scratch/yaguarete/medir/` (`convertir.sh`,
`correr_wally.py`, `analizar.py`, `fases.py`, `espejos.py`).

**Qué es "a la vez"**: la ventana de margen m son (18+2m)x(16+2m) celdas.
Margen 0 es exactamente lo que la consola dibuja —la caja de 32x32 tocando
la pantalla de 256x224, el `reach` de `share.rs`—, que es lo que Puma
llamaba "margen 1"; su "sin margen" (16x14) es más chico que lo que se
dibuja. Las posiciones son **las de arranque**: los que caminan se cuentan
donde empiezan.

**Hoy**: 316 entran (el 108 con sus turnos). No entran cuatro:

    no entran por fondo     148 Paradise Burning     614 de fondo, techo 544
                            250 Return to Paradise   621 de fondo
    no entran por sprites   127 ParadiseFarmland     41 ranuras, 692 tiles
                            285 Tasgarde Mainframe   50 ranuras + la caja de
                                                     la animación y la lluvia

(El 285 lo listaba Puma como "la caja de 64 tiles de las animaciones de
batalla": es lo mismo, la caja no entra porque 50 ranuras ya llenan el
banco.) El 148 y el 250 no son de esto: es el camino de los tiles del
fondo en caliente.

**Los modelos** —ranuras dinámicas a la vez, más las fijas: el héroe, y la
del giro si hay un quieto que se da vuelta—:

* (a) **la caché sola**: una ranura por evento en la ventana, camine o no;
* (b) **+ compartir quietos**: los quietos que muestran la misma pose, una
  sola ranura —lo que hoy hace `Slot::Still`, pero sólo para los que están
  en la ventana—; el que camina, o el quieto con más de un gráfico, la suya;
* (c) **+ espejados**: la izquierda de un quieto, el espejo de su derecha;
* (d) **+ las fases de la historia**: cuento sólo los que pueden estar
  visibles a la vez según los switches de sus páginas.

Ranuras (dinámicas + fijas) contra el tope del mejor reparto para su fondo:

                           margen 0     margen 1     margen 2    tope
    127  (a) sola          36+2  NO     40+2  NO     45+2  NO     32
         (b) +quietos      33+2  NO     36+2  NO     41+2  NO
         (c) +espejos      33+2  NO     36+2  NO     41+2  NO
         (d) +fases        26+2  sí     26+2  sí     26+2  sí
    285  (a) sola          13+1  sí     16+1  sí     17+1  sí   32, menos
         (b) +quietos      11+1  sí     12+1  sí     13+1  sí   la caja
         (c) +espejos      11+1  sí     12+1  sí     13+1  sí   y la lluvia

**Destraba**: la caché sola, el 285 con cualquier margen. El 127, **sólo
contando por fases**.

**Los espejos no suman nada.** RM2k no espeja, pero el dibujo sí suele ser
simétrico: de los 165 personajes del juego con hoja, 75 tienen las tres
poses de la izquierda iguales, pixel por pixel, al espejo de las de la
derecha cruzando las columnas (la columna 0 de una con la 2 de la otra: el
pie que adelanta cambia de lado); sin cruzar, 10. Pero en el pico de los
dos mapas no hay un mismo personaje mirando a los dos lados.

**Las fases del 127**, que es lo que lo destraba. El mapa son dos escenas
que nunca están juntas:

* **la celebración** (switch 383): veintinueve personas en un rectángulo de
  10x8 celdas, todas en la misma pantalla —Pierson, los de las cuatro
  profesiones y el consejo— mientras Talan elige profesión. 16 de ésas las
  mueve la escena (saltan en su lugar y giran: `MoveEvent` con 24/25 y las
  caras), y 13 se quedan quietas mostrando 10 poses distintas: **26
  ranuras**, 28 con el héroe y el giro, contra 32.
* **el baile** (389): la escena apaga el 383 y prende el 389 en la misma
  página (ev31), y salta dentro del mapa. Quince personas repartidas, 6
  caminando: 13 o 14 ranuras.

Las dos juntas no pasan nunca, pero un conversor no puede saberlo de los
switches: por eso el conteo estático dice 33. **(d) no es una ayuda que el
conversor pueda aplicar**: es lo que la consola va a ver.

**No hay bandidos en el 127.** "Una escena de bandidos" (Puma, en
`mundo-7`) es la celebración: los veintidós "que caminan" son los que la
escena hace saltar y girar. Los bandidos son del 121, Bandit Ambush, de
una tanda posterior.

(d) también mira otra cosa: si los que caminan compartieran ranura por
pose —los siete granjeros saltando juntos mirando arriba son la misma
pose—, la celebración bajaría a unas 17. No lo implemento: la caché por
fila ya alcanza y es mucho más simple.

## Qué se elige, y por qué

**La caché con los quietos compartiendo por pose (b), con margen 0.** Es la
única variante que se puede implementar sin saber el futuro y que alcanza
para el 127 tal como se juega: el conversor no ve las fases, pero la
consola sí, porque **una fila que no se dibuja no pide ranura**. El margen
lo da el tiempo y no las celdas: una ranura que se dejó de usar no se
recicla hasta dos cuadros después, y la que se recicla es la que lleva más
tiempo sin usarse, así que el que sale y vuelve a entrar suele encontrar su
pose todavía arriba. El margen en celdas sólo agranda el pico (36 contra
33 en el 127) sin evitar subidas que el tiempo ya evita.

Como el pico estático del 127 (33) pasa el lugar que hay (30 dinámicas), el
conversor lo dice como advertencia y no se frena: lo que pasa si la caché
se llena está abajo.

# Qué hace el conversor

`wally` (`map.rs`) prueba, en orden: el mapa como siempre; si no entra, sin
las imágenes; si no, con los quietos turnándose (el 108); y si eso tampoco
entra, **`Mode::Cache`**. Sólo un mapa que no entra de ninguna otra forma
cambia: los demás salen byte por byte iguales —medido con los 320 mapas del
juego, comparando la respuesta de `wally` de antes y de ahora: cambian el 127
y el 285, y nada más—.

En la caché:

* **Nadie tiene ranura en el banco**: el héroe sigue en el bloque 0 y la
  ranura del giro en la suya; detrás van tantos bloques en blanco como
  entren en el mejor reparto para su fondo (32 bloques en total, el tope del
  hardware), sin pasar de cuántos se pueden pedir a la vez. Los extras —el
  cronómetro, la lluvia, las imágenes, la caja de la animación— van
  después, como siempre.
* **Las poses quietas se numeran**: todas las que puede mostrar un quieto,
  en orden; ese número es lo que la fila lleva en su byte de tile, y lo que
  lleva la página de uno que cambia de gráfico (`Draws.key` en
  `rm2k-snes-mapdata`). Sus personajes pasan a tener sus doce poses en el
  cartucho, como los que caminan.
* **Cuenta cuántas a la vez** por dónde arrancan los eventos (`peak` en
  `sprites::cache`, el modelo (b) de arriba con margen 0) y lo avisa si son
  más que las ranuras.

`rm2k-snes-mapdata` emite `cache_maps` y `cache_data` (`cache_table`): por
mapa, cuántas ranuras, el primer tile de cada una y dónde está cada pose
quieta en `npc_poses`.

# Qué hace la ROM

`tools/runtime/cache_slots.s`, en FAR. Que el mapa tiene caché lo dice el bit
7 de `SHARE_N`, así `place_npc` mira un solo byte para los turnos y la caché.

* `place_npc` le pregunta a `cache_want` por cada fila que va a dibujar. Lo
  que pide la fila es su **clave**: la pose quieta que lleva en el byte de
  tile, o 128 más su evento si camina —una ranura suya—. Si la ranura que
  tenía todavía tiene su clave, se dibuja de ahí. Si no, un quieto busca
  otra que ya tenga su pose (la comparte). Si no hay, se toma **la ranura
  libre que lleva más tiempo sin dibujarse**; libre es que nadie la dibujó
  ni en este cuadro ni en el anterior. Su pose se encola con `vram_queue` y
  la fila se dibuja desde el cuadro siguiente, como en el 108.
* `build_oam` envejece las ranuras al empezar cada cuadro (`cache_age`).
* `upload_npc_pose`, el de los que caminan, sube a la ranura que la fila
  tiene si todavía es suya (`cache_dest`); si no tiene, la pose espera en
  +12 a que la fila entre en pantalla y pida una.
* `build_oam_settled` —entrar al mapa, un salto dentro de él, volver de la
  pelea, cargar— libera todas antes de armar (`cache_settle`): lo dibujado
  justo antes del salto no es razón para guardarle una ranura a nadie.
* `load_sprite` llama a `cache_load`, que la pone en limpio.
* El que mira al héroe se dibuja de la ranura del giro, como siempre.

**Si la caché se llena** —todas las ranuras se dibujaron en este cuadro o en
el anterior— **el que pide no se dibuja** ese cuadro y vuelve a pedir en el
siguiente: espera a que alguien salga de la pantalla. No se cuelga nunca, y
quien espera es el que `build_oam` alcanza último, que es el de más atrás
—la fila de más arriba de la pantalla, o la capa de abajo—. Elegí eso y no
"dibujarlo con la ranura de otro" porque un personaje que falta un instante
se ve mucho menos que uno con la cara de otro. En la granja no pasa: la
celebración pide 26 y hay 30.

**Lo que se ve distinto**: un evento que aparece por un refresco de páginas
—el baile, después del salto dentro del 127— se dibuja uno o dos cuadros
tarde, porque el refresco viene después de armar el cuadro y la ranura se
pide en el siguiente. Con la pantalla recién subida no se nota.

**Lo que cuesta**: en el banco 0, los ganchos de `place_npc`, `build_oam`,
`build_oam_settled`, `upload_npc_pose` y `load_sprite`, y `reclaim_slot`
(abajo); en FAR, `cache_slots.s`, unos 600 B. Los números del cartucho, en
"Verificación". En la celebración se pierden 8 cuadros de 1.900, casi todos
alrededor del salto al baile; en 600 cuadros de baile, 5.

## La RAM y los opcodes

RAM lejana: **$7E7C00 a $7E7CFF** —`CACHE_N`, `CACHE_REC`, lo que
`cache_want` le pasa a `cache_took`, y desde $7C10 `CACHE_KEY` y `CACHE_AGE`
(32 cada uno) y `CACHE_EV` (120, por evento y no por fila: las filas cambian
de lugar)—. Nadie la usaba: medido en la tabla de símbolos de `release`.
**Ningún opcode.**

# Y las rutas: doce moviéndose a la vez, no doce en el mapa

Con la caché el 127 convertía y el conversor se frenaba en otra cosa: sus
páginas mandan a caminar a **18 eventos distintos** y la ROM tiene **12
lugares de ruta** (`route_ev`, en la BSS del banco 0, que tiene 128 B libres:
no alcanza para seis más). Un lugar era de su evento hasta el próximo mapa.

Ahora, sin lugar libre, **el primero cuya ruta terminó se lo pasa al que
pide** (`reclaim_slot` en `event_pages.s`), y el conversor avisa en vez de
frenarse. El evento que lo suelta conserva hacia dónde mira y pierde lo
demás que la ruta le había cambiado: ver
`divergencias/las-rutas-terminadas-sueltan-su-lugar.md`. En la granja nunca
hay más de nueve moviéndose a la vez. Es un desvío del encargo —"si no
entra, frená"—: el que no entraba ya no era la VRAM sino esto, y era chico.

# La escena "de bandidos" del 127: quién se queda quieto

No hay bandidos en el 127 (ver arriba): es la celebración. Para ver qué vale
hornear, por número de evento de RM2k:

**La celebración (switch 383)**, todos en un rectángulo de 10x8 celdas:

* **se mueven** —la escena les da ruta—: Pierson (1), que gira; los
  granjeros 2 a 8 (con Radin, el 6); los defensores 11, 12 y 15; los
  actores 16 a 19 y 21. Sólo saltan los de la profesión que se elige, y
  giran o saltan **en su lugar**: nadie camina.
* **quietos siempre**: Emily (9), el granjero 10, el defensor 13, Isabella
  (14), el actor 20, los cinco abogados (22 a 26) y el consejo (28, 29 y
  30). Trece, con diez poses distintas. El 10, el 13 y el 20 son de su
  profesión y la escena no los hace saltar: es así en el original (el 21
  está dos veces en la lista de los actores, y el 20 no).

**El baile (389)**:

* **se mueven**: 33, 34, 35, 36, 41 y 42, con ruta propia, de un lado al
  otro. El 37 y la 38 tienen ruta propia y la animación "girar", y en la ROM
  no se mueven: el conversor no los cuenta como de los que caminan. No lo
  seguí.
* **quietos**: 32, 39, 40, 43, 44, 45 e Isabella (46, que cambia de pose con
  la página).

Hornear los quietos de la celebración sacaría diez ranuras del pico (de 26 a
16); los de la celebración están sobre los bancos, así que habría que mirar
si el horneado los deja bien parados.

# ABL

En su rama `cache-de-ranuras` (ver su `workflow/tasks/testing/mundo-9-la-granja.md`):

* **`below = 129`**: el 127 y la arboleda (128), que es la noche que sigue.
* **El corte**: el fork del 108 devuelve la salida a la granja a la del
  juego y cambia el `Teleport` del evento 47 —las buenas noches de Emily, al
  volver de la arboleda— a la casa de Talan por el cartel del fin: ahí
  empieza el día siguiente, el trabajo de cada profesión. Nada más se
  alcanza antes de ese corte.
* **Pruebas**: `abl/test_granja.py`, la celebración cuadro por cuadro con la
  VRAM de cada uno contra su pose (`arnes/cache_de_ranuras.py`), con tres
  goldens; `abl/test_recorrido_granja_golden.py`, del pueblo al cartel, con
  once fotos con golden y mirando que los que pasean en el baile se muevan;
  `rpgmaker/test_cores.py::test_la_cache_de_ranuras`. El recorrido del
  primer día termina ahora al llegar a la granja.
* `parches/auto/` del 127 y del 128, y `techos.toml` rehecho: los temas
  nuevos movieron el reparto de las muestras.

El 285 (Tasgarde Mainframe) también entraría con la caché —sin sus imágenes,
que se sacan antes de probar los turnos—, pero no es de este tramo.

# Verificación

Sobre los árboles mergeados con `main` de los dos repos (sólo traían
tareas):

* ABL, `just pruebas`: **1043** en verde. `abl.sfc` `dbd0c55b6f5b…`,
  `abl.msu` `5902e0bbabb6…`.
* Antes de sumar el 127, con la caché ya en la ROM y ningún mapa que la
  use: **1035** en verde, sin mover ninguna golden; el `mapdata.inc` de
  `release` cambiaba sólo por la tabla nueva, vacía.
* **El rojo**: sin subir la pose al tomar una ranura, `test_granja.py` y el
  recorrido de la granja fallan en el primer cuadro mirado; sin
  `reclaim_slot`, el recorrido falla porque el 41 y el 42 no se mueven.
* `just -f tools/justfile test`: 27. `cargo test` de `wally`,
  `rm2k-snes-mapdata`, `rm2k-snes-convert` y `rm2k-snes-cartridge` en
  verde. Los hashes de `mapdata/tests/python.rs` se movieron a propósito:
  sacando la tabla nueva vuelven a dar los de antes.
* `just espacio release`, antes (`main`, sin el 127) y después:

                      antes        después
      bancos          71 de 127    72 de 127
      banco 0         2.868 B      2.725 B
      banco 1         14.204 B     13.587 B
      BSS, ZEROPAGE   128 B, 4 B   128 B, 4 B

**No cubre `just pruebas`**: volver de una pelea en un mapa con caché (el
127 no tiene peleas) y cargar una partida guardada en él —los dos pasan por
`cache_load` y `build_oam_settled`, como el salto dentro del mapa, que sí
se juega—; la caché llena, que ningún mapa del juego alcanza; y las ramas
de defensor y de actor de la celebración.

# Al mergear

Instalar `wally`, `mapdata`, `convert` y `cartridge`: `just -f
tools/justfile install wally mapdata convert cartridge`. `cartridge` arma
con el runtime. No hay Python nuevo en `tools/`.

# Qué tiene que probar taro

* En ABL, desde la salida del pueblo a la granja: la celebración con cada
  una de las tres profesiones, el baile, Isabella, Emily, la arboleda y el
  cartel del fin.
* Que nadie aparezca tarde o con la pose de otro, sobre todo en el salto
  al baile.
* Las goldens, en `/shared/capturas/2026-10-03-cache-de-ranuras/`, antes del
  merge.
