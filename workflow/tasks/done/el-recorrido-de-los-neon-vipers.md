---
name: "El recorrido de los Neon Vipers"
description: "Una jugada larga que cubra la escena donde aparecieron los dos bugs"
---

**Una prueba que juegue el tramo de los Neon Vipers de punta a punta**: arrancar
en la calle de Lashe City, subir por el caño, cruzar el techo, entrar al HQ,
caminar hasta disparar la cinemática, pasar todos los diálogos y volver a la
calle. Lo pidió taro el 2026-09-22.

El punto no es la cobertura en abstracto: **ahí aparecieron los dos bugs de esta
semana** —el salto que quedaba colgado y el mapa que quedaba corrido— y ninguna
prueba los ejecutaba. Del mapa 11 la tanda sólo tiene `en-11`, que entra y nada
más; del 12 y el 14, nada. De paso ejercita dos teletransportes y varios tipos
de evento: contacto, automáticos, paralelos y el salto.

Los mapas: la calle es el **8** (`Lashe City - 34,35`) y el HQ es el **12**
(`Trash Dump 004`), donde están `Conda`, `NVone`, `NVtwo`, `NVthree`,
`NV Lookout` y `NV hotplate`. El 12 tiene además dos saltos de 5 celdas, que son
de los más rápidos del juego: 7,3 px por cuadro.

El modelo es `pruebas/abl/test_recorrido.py`, que ya juega desde el título hasta
el auditorio con `Mundo`/`Recorrido` —el grafo de islas y el plan por puertas—,
y guarda una captura por hito.

Hecho es: la prueba corre en la tanda, y **se la vio fallar contra la ROM de
antes de los dos arreglos**, que es lo que dice si cubre de verdad lo que taro
encontró jugando.

---

## Al 2026-09-23: la prueba está, y cubre uno de los dos

`pruebas/abl/test_recorrido_vipers.py`. Camino, todo por estado y con tope:
arranca en (73,32) del mapa 8 —la celda a la que el propio mapa teletransporta
desde (0,56)— con el switch 24; el caño es el evento 41 de (52,23), que deja al
héroe en (55,18); el cruce de techos es el 45 de (58,17), que lo deja en
(64,17); la puerta del HQ es el 47 de (71,14), **de los que se hablan de al
lado**; adentro se baja hasta el `NV hotplate` de (5,39), que es de contacto y
dispara la cinemática; y la rama de "Yes, I'll do it!" —la que sale de tocar A
sin mover el cursor— devuelve a (44,13). Tarda 1,2 s, 1807 ticks.

**El salto colgado: cazado, y visto en rojo.** Contra `main.s` del padre de
`f50d654` la prueba falla. Lo que lo dispara es el salto **en el lugar** de la
cinemática —`begin_jump` y `end_jump` pegados, Talan saltando del susto— que es
la última orden de su ruta: `ruta_salto` queda en 232 con `ruta_i == ruta_n`
durante 49 muestras seguidas del vigilante, seis de ellas con un mensaje en
pantalla; con el arreglo, una. **Ese salto no se ve**: sin desplazamiento
`salto_posicion_heroe` deja `hero_y` donde estaba, así que ninguna golden lo
habría notado y `hero_y == tile_y * 16` tampoco lo delata. Lo único que lo
delata es `ruta_salto`.

**El mapa corrido: este tramo no lo puede reproducir, y está medido.** Armada la
ROM que tiene el salto arreglado y `stream_map` no —revirtiendo `9997bf2` sobre
HEAD— esta prueba **pasa**, y las dos de `test_camara.py` fallan. La razón,
medida vuelta por vuelta sobre esa ROM y fuera de los fundidos: en todo el tramo
la cámara no se mueve más de **5 px** por vuelta —el pico son los saltos del
caño— y para saltear una fila hacen falta más de 8. Las dos cosas que suman 16
son el héroe a velocidad 6 y un `PanScreen` a velocidad 6 en el mismo eje, y esta
escena no tiene ninguno de los dos. La comprobación de la ventana va igual en los
dos hitos donde se puede, y el docstring dice que hoy no puede dar rojo.

**Un agujero del arnés que apareció de paso**: `activar` hablaba de al lado sin
girar. Giraba con un toque de un tick y un tick se puede perder entero, porque la
ROM lee el pad una vez por vuelta y una vuelta puede durar varios cuadros de
hardware. Medido recién llegado a la celda: no gira con uno ni con dos ticks
apretados, y sí con cuatro. Lo tapaba que `caminar_a` deja al héroe mirando hacia
su último paso; la puerta del HQ es de las que no. Hoy gira `Recorrido.mirar_a`,
que lo comprueba en la RAM.

**Lo que queda sin cubrir** —ninguna de las tres la hace esta prueba—: la rama de
"No, it's a waste of time!" de la cinemática, que es la que baja caminando y sale
por la reja con **los dos saltos de 5 celdas**; el evento 1 de (1,47), la reja
con su `ShowChoice` de "Climb the Fence"; y el mapa 14, donde ninguna de las dos
ramas entra con estos switches.
