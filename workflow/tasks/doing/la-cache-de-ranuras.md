---
name: "La caché de ranuras de sprites"
description: "Cada evento pide una ranura de VRAM al entrar en pantalla y la suelta al salir, en vez de tener una fija por el mapa entero; con ayudas para achicar el pico, y la granja (127) de ABL como primer caso"
type: feature
assignee: Yaguareté
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
