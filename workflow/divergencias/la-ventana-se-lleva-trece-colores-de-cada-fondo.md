# Qué

La ventana de mensajes vive en la paleta 0 de CGRAM, y en modo 3 esas
entradas son también las del fondo, que va a 8 bits y direcciona CGRAM
entero. Lo que la ventana toma —`WINDOW_COLORS`, en `cgram.rs` de
`rm2k-snes-mapdata` y en `layers.rs` de `wally`— sale del presupuesto de
**todos** los mapas, y un mapa que necesitaba esas entradas fusiona colores
de su fondo: Adeleine decide cuáles, y lo que decidió queda en
`parches/auto/mapas/` del juego como `presupuesto`.

Desde el 2026-10-04 son **trece y no ocho**: además de su fondo, su marco,
el texto y la sombra, la ventana lleva la flecha de un mensaje que espera
una tecla y el cursor del System, la barra de la elección, porque los dos
se dibujan adentro de sus tiles. Con el System de *A Blurred Line* son
cuatro rojos de la flecha y uno de la barra.

RM2k no tiene esto: la ventana y el mapa no comparten colores.

# Por qué

La ventana es BG2 a 4 bits y la flecha y la barra van en sus tiles, así
que sus colores tienen que estar en la paleta de la ventana. La otra forma
de dibujarlas sin colores propios —sprites— no sirve: la máscara de objetos
los esconde en las líneas de la ventana, para que los eventos "arriba" no
se vean a través de ella (ver `build_hdma` en `messages.s`).

Lo que no se probó: reescribir por HDMA, sólo en las líneas de la ventana,
las paletas de la capa de encima —que en esas líneas no se ve, porque BG2
muestra la ventana— con los colores de la flecha y la barra, y reponerlas
abajo. Cuesta un canal de HDMA y tablas que siguen a la ventana; con eso
la ventana volvería a ocho.

# Medido

El 2026-10-04, comparando lo que decidió Adeleine en `release` con ocho y
con trece —las imágenes de `build/<cartucho>/adeleine/` del juego, en RGB—:
de 111 mapas, **diez** pierden colores, entre uno y cinco cada uno: 66, 67,
69, 70, 86, 112, 113 y 116 a 119. En las goldens se ve como unos pocos
pixeles de un tono vecino: 120 de 57.344 en el peor, el mapa 119.

# Cómo se ve hoy

En esos diez mapas, alguna sombra de barril, de estante o de pared toma el
tono de al lado. No se ve una mancha ni un color equivocado.

# Cuándo deja de alcanzar

Con un System que traiga más colores: la ventana entera —fondo, marco,
texto, sombra, flecha y cursor— tiene quince, y el conversor se niega con
"the window, its arrow and its cursor use N colours and 15 fit". El System
del RTP ya no entra, con o sin flecha: su fondo y su marco solos tienen
treinta. Y con un juego cuyos fondos vengan justos, cada color de la
ventana es uno menos de todos sus mapas: el número tendría que salir de la
ventana del juego y no ser una constante.
