---
name: "Eventos opacos al mapa"
description: "Un evento que es un tile opaco fijo se hornea en el mapa"
---

# Qué

Un evento que se dibuja con **un tile opaco del ChipSet**, siempre el mismo y
siempre en la misma celda, no se dibuja como evento: su tile se mete en la capa
alta del mapa y su fila del NPC nace escondida. El evento sigue entero para su
lógica —dispara, cierra el paso, es blanco de una ruta—; lo que se ahorra es su
objeto de OAM y su paso por `place_npc`.

La regla vive en `eventos_horneables`, en `tools/port/snes_convert.py`, con las
cinco condiciones y el porqué de cada una. Cuántos eventos hornea cada mapa lo
dice el conversor en su informe.

# Por qué

Sale del **HQ de los Lazer Teeth, el mapa 11**, que es el más cargado del juego
—68 eventos dibujados, 62 de ellos con un tile— y el que usa
`pruebas/rpgmaker/test_paralelos.py` para medir si el cuadro entra.

**Lo medido, caminando 1200 cuadros en el mapa 11** (cuadros perdidos, con el
contador leído y puesto en cero cada 50 cuadros: satura en 255, y una medición
de 1200 cuadros seguidos contesta 213 por eso y no por lo que pasó):

    eventos dibujados   cuadros perdidos
    68 (como estaba)          450
    50 (horneando 18)         228
    31                        150
     9                         74

O sea que cuesta del orden de **siete cuadros perdidos por evento dibujado** en
ese mapa, y hornear los 18 que caen en la regla los baja a la mitad. Quieto no
se pierde ninguno: lo que los produce es el redibujado del scroll, y los
sprites son lo que lo empuja por encima del cuadro.

Las tres filas de abajo son mediciones de control, con eventos escondidos a
mano: dicen dónde está el techo y no son código que exista.

**El techo de la regla es chico, y es el dato que hay que tener antes de
estirarla**: sobre los 328 mapas del juego hay 522 eventos dibujados con un tile
del ChipSet y **32 caen en la regla, en 12 mapas** —19 de ellos en el mapa 11—.
Aflojando todo menos "opaco y de dibujo fijo" serían 91 en 16 mapas, 49 de ellos
en el 11. La diferencia son los que **el juego mueve**: en el mapa 11, 46 de sus
62 eventos de tile son blanco de un `ChangeEventLocation` —es el minijuego de
las piedras— y ésos no se pueden hornear de ninguna manera.

# Lo que no se ahorra todavía

**La paleta de sprite y la ranura de VRAM.** El evento horneado sigue entrando
en el reparto de `npcs_dibujables` como si se dibujara, a propósito: sacarlo de
ahí le libera una paleta al mapa, y con eso **cambia lo que se ve** —un gráfico
que hoy se dibuja con una paleta ajena pasaría a tener la suya, y el mapa 11
tiene uno: `@tile:lasheint:49`—. Es una mejora, pero es una decisión aparte y
mueve goldens.
