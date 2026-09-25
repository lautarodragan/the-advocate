---
name: "Capas dibujadas versionadas"
description: "Las capas de cada mapa como artefacto que se mira en git"
type: test
---

# Qué

Que las capas dibujadas de los mapas sean un artefacto versionado, como
`data/`: se generan cuando cambian los gráficos del juego, van a git, y el
build sólo las lee.

# Status

Anotado y **medido**, sin empezar. Es de taro, el 2026-09-20. Lo que está hecho
es el paso que lo hace barato: desde ese día la clave del caché de capas sale de
los insumos, así que un build caliente ya no dibuja ningún mapa. Lo que esto
agregaría no es velocidad sino **sacar el juego original y el RTP del build**.

# Cuánto ocupa

Medido el 2026-09-20 con Pillow, sobre los dibujos que devuelve
`Renderer.capas_animadas`: la capa de abajo, la de encima, y un dibujo más por
cada paso de cada familia animada —agua y tiles animados—. Todos entran en 256
colores, así que un PNG indexado de 8 bits los guarda **sin perder un pixel**;
la peor paleta de las dos tandas tiene 167 colores.

    abl (29 mapas)       78 dibujos    1,3 MB
    pruebas (40 mapas)  102 dibujos    1,6 MB

Los 40 del cartucho de pruebas incluyen a los 29 de `abl`, así que el artefacto
entero son esos 1,6 MB. Los mismos pixeles crudos, a un byte cada uno, son
114 MB: el PNG los deja en el 1,4%.

El desglose dice dónde está el gordo, y es el que no hace falta guardar:

    base        40 dibujos    842 KB
    encima      40 dibujos     88 KB
    variantes   22 dibujos    680 KB

# Una forma más compacta que sigue siendo legible

Las variantes son el dibujo entero con **unas pocas celdas cambiadas**: son
42% del peso y aportan 18.705 celdas de 16x16 distintas en total. Guardadas
como una tira de sólo esas celdas —un PNG indexado más, que se abre y se mira
igual— pasan de **680 KB a 21 KB**, y el artefacto entero de 1,6 MB a menos de
1 MB. El costo es que hay que guardar al lado en qué celda va cada una, y que
lo que se mira ya no es el mapa sino una tira de celdas.

La otra forma, mucho más compacta todavía, es no guardar las capas sino **los
17 ChipSets que las dibujan**: 518 KB, y siguen siendo las imágenes originales.
Pero eso versiona el insumo y no el resultado, así que deja el dibujo adentro
del build —que es justo lo que hoy ya no cuesta—. Sirve para sacar la
dependencia, no para sacar el paso.

# Qué haría falta para que el build no necesite el juego ni el RTP

Las capas son **una** de las cosas que el build lee de `/extras/abl-rm` y
`/extras/rtp`. Los datos ya no: `data/` es el volcado de Ditto y de ahí salen
los mapas, la base y el árbol. Lo que queda son los gráficos y el audio, y cada
uno tiene su camino propio:

    ChipSet        las capas de los mapas          render_map.atlas_por_nombre
    CharSet        el héroe y los NPCs             render_map.Charsets.get
    FaceSet        las caras del menú              titulo.cara_de
    System         la ventana de mensaje           ventana.skin, titulo
    Title          la pantalla de título           titulo
    Backdrop       el fondo de las peleas          escena
    Monster        los battlers                    escena
    Battle/Battle2 las animaciones de batalla      animacion
    Picture        las de `ShowPicture`            eventos.Recortes
    Music (.mid)   los temas, y las pistas MSU-1   snes_music, msu
    Sound (.wav)   los efectos                     snes_music

Versionar las capas tacha **una sola línea** de esa lista, la primera. Las que
quedarían afuera igual son todas las demás, y dos de ellas son las que más
pesan: los CharSets —que son el otro gran costo del conversor hoy,
`build_characters` y `sprite_colors`— y la carpeta `Music`, que son 230 MIDI
del juego más 111 del RTP.

Y hay una que no se va nunca por esta vía: **el SoundFont**,
`/extras/soundfonts/`, de donde salen las muestras. Ése no es del juego.

Así que "el build no necesita el juego" es un objetivo de varios pasos, no de
uno, y el orden que sale de lo medido es: capas (1,6 MB), personajes, y después
el resto. La fuente ya está adentro del repo —`tools/port/fuente.py` es un
generado de easyrpg-player— y no cuenta.
