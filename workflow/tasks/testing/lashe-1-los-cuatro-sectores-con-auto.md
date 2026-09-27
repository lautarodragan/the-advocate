---
name: "Lashe 1: los cuatro sectores con auto"
description: "37, 38, 47 y 48 (con el 39 y el 56) en release, y el 36 que no traba: la elección compila y irse termina la demo"
type: feature
assignee: taro
---

# Qué

El hito 1 de `lashe-city-hasta-la-carrera.md`, que es donde está el contexto
entero y lo medido. Bloquea a los demás.

Meter en `_DE_RELEASE` los cuatro sectores con auto —**37, 38, 47 y 48**—, que
la elección del 36 pide juntos, y los dos interiores que no piden nada: el
**39** (Talan's Pad With Car, copia exacta del 7; prende el 151) y el **56**
(la tienda del Sector 33). Y dejar el 36 sin trabarse en la segunda visita.

# Status

2026-09-27, en `testing/`: hecho sobre `93af39f`, en la rama del agente. Lo que
queda es de taro: jugarlo (abajo, "Qué tiene que mirar taro jugando") y mirar
las fotos sin golden de `pruebas/snapshots/playthrough/lashe-*/`.

# Lo hecho

**Los seis mapas en `MAPAS_DEL_JUEGO`** (`tools/ensamblado/cartuchos.py`), y
con eso en `release`, que es también el cartucho de la tanda. El 38 convierte
con `LAYOUT_VENTANA_AMBOS`, como se había probado a mano.

**El conversor ya no se planta en el 37.** `PawnDoorTop` —el evento 11, en
(67,29)— cumple la regla de `eventos_horneables` pero el reparto de paletas lo
dibuja con una prestada. Donde había un `sys.exit`, ahora se lo deshornea:
vuelve a ser sprite, con los colores prestados, y las capas se rearman con los
horneados que quedan (`_hornear_si_no_mueve_la_cgram`, en
`tools/port/snes_convert.py`). Es lo que el comentario de ahí pedía —"sacarlo
de la regla"—; se pregunta después y no dentro de `eventos_horneables` porque
las prestadas salen del reparto, que corre después de dibujar las capas. Ningún
otro mapa horneaba un prestado: los `parches/auto/mapas/` de los que ya estaban
salen iguales, y la tanda no movió ninguna golden. Lo cobra
`test_la_puerta_de_la_casa_de_empeno_no_se_hornea`.

**El fin de la demo** (la decisión de taro del 2026-09-26): el 36 está
forkeado en `parches/manual/mapas/Map0036.json`, con las capas del original, y
sus cuatro `Teleport [49, 1, 26]` son ahora un mensaje —"END OF THE DEMO / The
escape from Lashe City is not in / the cartridge yet. Thanks for playing!", en
inglés como el resto del juego— y un `ReturntoTitleScreen`. El conversor
compila ese comando al mismo `OP_GAME_OVER` que el `GameOver` (`jml reset`):
acá el Game Over ya no dibuja su imagen, así que los dos son lo mismo, y el
arranque de `release` es la pantalla de título. **Sin opcode nuevo.** El 182
("se van") se sigue prendiendo antes del cartel, como en el original; `reset`
lo borra al volver al título. El porqué del fork está en
`parches/manual/README.md`.

`test_fork_los_teleports_que_entran_siguen_cayendo_en_celdas_pisables` pedía
que toda celda a la que llega un `Teleport` fuera pisable, y el 36 recibe a
`DummyHero` en celdas que ya en el original no se pisan (es una pantalla
negra). Ahora pide lo que protege: que el fork no cierre una celda que el
original dejaba pisar.

`test_puerta_del_10.py` cobraba que la puerta del 10 con el switch 231 **no**
llevara al 8 porque el 38 no estaba; ahora cobra que lleve al 38, a (48,54).

# Lo medido

Todo sobre `release`, `93af39f` contra esta rama:

**Las páginas**: con el script del plan (`medir.py`), 183 de 186 páginas
disparables de 36, 37, 38, 39, 47, 48 y 56 compilan. Las tres que no son las
previstas, puertas a mapas de otros hitos:

    37  evento 13, página 3 (la puerta del vecino) ...... Teleport -> 41 (hito 2)
    48  evento 9, páginas 1 y 2 (la puerta de Stash) .... Teleport -> 57 (hito 3)

Y de paso compilan las dos páginas del mapa 10 que llevan al 38 (las puertas
del switch 231).

**Banco 0** (`TABLAS`, método de `AGENTS.md`): 360 B libres antes, 342
después. **BSS** 109 y **ZEROPAGE** 4, sin cambio. **Banco 1**: el último
símbolo sigue en $01:F874 (~1,9 KB libres), sin cambio. **Cartucho**: de
2.652.978 B (63,3% de 4 MB) a 2.748.268 B (65,5%), +93 KB.

**VRAM**: el 38 entra con 476 tiles de fondo y 347 de sprite, como se había
medido. **CGRAM**: 37 dibuja 5 gráficos con paleta prestada (las dos puertas de
tile, `Chara2:4`, `Crown1:3`, `Future2:5`), el 38 tres (`BLObjs:2`, `Chara2:2`,
`People4:0`). **Cuadros perdidos** caminando 1200 cuadros de a 50, ida y vuelta,
el método de `done/el-mapa-11-se-rediseno.md`: 0 en las cuatro celdas del 37,
0 o 1 en las cinco del 38, 0 en el 47 y el 48 (el 8, en las mismas
condiciones, da 0 a 2).

**Audio.** Ningún tema nuevo: los sectores heredan la música del 36, y los tres
temas del plan (`Kfmus5`, `tsmedit`, `fm2bar_gs`) son de mapas de los hitos 2 y
3. Las pistas de MSU-1 siguen siendo las mismas. Pero **sí hay paquetes
nuevos**, y le bajan la tasa a temas que ya estaban: el 38 y el 47 ponen
`vswar` (la escena del HQ, los guardias) y `golden_axe-turtlevillage2` (la
salida), y por el 10 entra `cd4` al 38 —en RM2k el tema del 10 sigue sonando al
volver a un sector, que hereda—, así que aparecen `38+cd4` (el paquete más
lleno: sobran 1267 B), `8+vswar`, `10+vswar`, `36+vswar`, `56+vswar` y los
`+golden_axe` de cada sector. Medido par por par (tema, instrumento) con el
`Banco` de verdad, contra `93af39f`: de 338 pares **bajan 47** y suben 26; la
mediana pasa de 18,9 a 16,5 kHz. Los que más bajan:

    vswar         15 pares: el polysynth 21,1 -> 12,6; platillos y toms 22 -> 14,1;
                  cuerdas 22,1 -> 14,2 y 16,7; coro 22,3 -> 16,8
    escape_newyork polysynth 21,1 -> 12,6, y cuatro más de 1 a 2 kHz
    golden_axe    golpes 41 y 42: 22 -> 14,1; bajos y cuerdas 22 -> 16,5
    Deflector1    golpe 36 22 -> 14,1
    cd4, T_ProjectJustice, C3classi, Lunar_Pyramid, wb3town: 1,7 a 5,3 kHz

La mitad es propia del paquete —`38+cd4` tiene que meter `vswar`,
`golden_axe` y `cd4` juntos—, pero los que caen a 14,1 "la limita pelea" no:
son copias que la segunda tanda de `snes_music.copias` dejó de hacer (el banco
pasa de 221 a 212 muestras), porque ahora no hay una que no le baje a nadie.
**Está reportado y no tocado**: es del dominio de los agentes de audio, y se
nota en el tema de `vswar` sin MSU-1. `just techos` rehecho con la mezcla
nueva: ningún tema recorta.

# Pruebas

`pruebas/abl/test_recorrido_lashe_golden.py`, sobre `release`, arrancando por
donde arranca el juego —la charla del auto del mapa 4 con el 132, la cinemática
del 34— salvo el HQ y los guardias, que saltan a su sector:

* `test_la_eleccion_del_36_lleva_a_los_cuatro_sectores`: con Arden, los cuatro
  uno detrás de otro —35, 34, 33, 32—, el primero por la página 1 del 36 y los
  demás por la 2. En cada uno: el mapa, la celda del `Teleport`, el grupo
  (Talan y Arden) y subir al auto (148 apagado, 149 prendido, `DummyHero` solo).
* `test_el_pad_de_talan_con_auto`: 37 -> 39, la computadora prende el 151 y
  recién ahí abre la puerta, 39 -> 37 (10,31).
* `test_el_hq_de_los_vipers_por_el_cano_con_arden`: el caño (167, Arden se
  adelanta), el HQ vacío (168), hablarle a Arden (vuelve al grupo), el susurro
  (169) y la salida a la calle.
* `test_los_guardias_del_sector_33_con_saldra`: la tienda del 56 y de vuelta, y
  la escena de los guardias con Saldra (181, la huida a (5,36)).
* `test_irse_de_la_ciudad_termina_la_demo`: con el 161 y el 169, "Stay" (y el
  238 prendido), otra vuelta, "We've got to get out of here", el cartel y la
  vuelta al título.
* `test_la_puerta_de_la_casa_de_empeno_no_se_hornea`.

Las fotos quedan en `pruebas/snapshots/playthrough/lashe-*/` **sin golden**:

    lashe-sectores  el 36 la primera vez, y cada sector al llegar
    lashe-pad       el pad de Talan
    lashe-hq        arriba del caño, el HQ vacío, de vuelta en la calle
    lashe-guardias  la tienda, después de los guardias
    lashe-fin       irse o quedarse, el cartel del fin, el título

Lo que **no** cubren: el auto azul (130 apagado, 131 prendido: las mismas
páginas con la celda de al lado), la rama "solo" (sin compañero no hay nada
propio en este hito) y el 38 por la puerta del 10.

# Qué tiene que mirar taro jugando

Los cuatro sectores con el auto: que la elección lleve a cada uno, que al volver
al auto se pueda elegir otro, el HQ de los Vipers por el caño con Arden, los
guardias del Sector 33, la tienda del 56 y el pad de Talan. Los NPCs con
paleta prestada del 37 —las dos puertas de tile y la gente que aparece con el
161— se ven con colores de otro. El cartel del fin de la demo. Y cómo suena
`vswar` (la escena del HQ y los guardias) sin MSU-1, que es el que más bajó.
