---
name: "La carrera en release"
description: "La persecución en auto, que hoy no entra en ninguna ROM"
type: feature
---

# Qué

Meter la persecución en auto —los mapas 49 a 54— en `release`, cuando se la
encare. (Hasta el 2026-09-25 decía "y en `test-main`": se juntaron.)

# Status

Hasta el 2026-09-24 tenía su propia ROM, `just build carrera` —antes
`demo-carrera`—, armada aparte. taro la sacó ese día: fue un experimento para
probar ese caso, y no tiene sentido adelantarse tanto. Se retoma cuando entre
en `release`.

Lo que sigue es el comentario que tenía la receta, que es lo que costó
averiguar. La receta no se guarda: arrancaba en el mapa 49 plantando al héroe
con `--inicio 1 26`, y ese flag del conversor se sacó el 2026-09-25. La
carrera se va a probar **llegando al mapa normalmente**, por el `Teleport` del
juego, no arrancando en una celda elegida desde afuera.

# Lo que se sabía

Los siete mapas son los de la escena: el 49, el 52 y el 54 son las tres
vueltas, el 50 es la sala de choque con el "vamos de nuevo", el 51 el puente
levantado, y el 53 el final.

**Con `--grupo 14`, Talan, que es con quien el juego llega hasta acá.** Al
entrar al 49, `RaceController1` saca del grupo a los actores que pueden estar
ahí y mete a `CarRED` o a `CarBLUE` según el switch que él mismo prende, así
que el héroe **es el auto**. Con el grupo de pruebas puesto, Kersh quedaría
adentro —no está en esa lista— y el gráfico saldría mal; con el grupo inicial
de la base, el héroe se dibuja **sin gráfico** hasta que el `PanScreen` de
`RaceController1` termina y recién ahí entra el auto, que es un síntoma que
taro reportó jugando.

**La celda por la que se entra en el juego es la (1, 26)**, y no es
cosmético. Sin ella el conversor planta al héroe en el tile abierto más cercano
al centro, que en este mapa cae en una fila donde **no hay ni un obstáculo** ni
ninguno de los eventos que saltan al mapa siguiente: el auto podía cruzar las
500 celdas del mapa sin chocar con nada y sin llegar a ninguna parte. La celda
sale del `Teleport [49, 1, 26]` del evento 3 del mapa 36, que es por donde el
juego entra, así que llegando al mapa normalmente se cae ahí sin hacer nada.

**El switch 171 es lo que la hace arrancar** —lo prende la página de prueba
`pruebas/casos/switch-171.json`—, y hay que saber por qué. El
evento 1 del mapa 49 tiene dos páginas automáticas, una por switch, y la que
arma el auto pide el 171. Con los dos apagados **ninguna es la activa** y el
evento no hace nada, así que el héroe se queda siendo `DummyHero`, cuyo sprite
es una celda vacía a propósito: pantalla sin auto. Quien lo prende en el juego
es `RaceControllerZERO`, la intro de Talan con el cartel de los controles; esa
página compila, y el switch sigue puesto a mano sólo porque nadie volvió a
mirar esa escena desde entonces: sacarlo es una prueba a mano de toda la intro.

**Y la carrera no corre sola**, que es lo primero que se nota jugando: el héroe
camina libre y a la velocidad que le dejó `RaceController1`. Quien la corre es
`RaceController2`, la única página paralela del 49 que no compila, y lo que la
corta es el `KeyInputProc` **sin espera**; el porqué de que ese comando siga
sin aceptarse está en `KEY_INPUT_PROC` en eventos.py.
