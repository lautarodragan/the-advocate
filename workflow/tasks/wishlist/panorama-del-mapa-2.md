---
name: "El panorama del mapa 2"
description: "Los puntitos sobre azul que se desplazan en diagonal"
type: feature
---

# Qué

El panorama del mapa 2: los puntitos sobre azul que se desplazan en diagonal
solos, detrás de la pantalla grande.

# Status

Anotado, sin empezar, y **no es prioridad**.

# Por qué

Se nota faltando cuando la pantalla grande se enciende. Lo que cuesta es una
capa: el **modo 3 tiene dos capas de fondo y las dos están tomadas** —el mapa, y
la capa de encima con la ventana—, así que un panorama pide una tercera o el
modo 1, que la conversión no usa.

De ahí sale que **`ChangePBG` se acepte y se tire**: si no hay panorama, no hay
nada que cambiarle, y se tira al compilar, así que no queda nada a medias.
Aparece **una sola vez en todo el juego** —siete comandos en la página del viaje
en el Hover-Tram, donde el paisaje de la tarde corre por detrás y cambia de
velocidad al arrancar y al frenar— y sin él esa página no compila. O sea que lo
que esto compra es **el viaje entero**, y lo que cuesta hoy es que las
ventanillas se vean quietas.
