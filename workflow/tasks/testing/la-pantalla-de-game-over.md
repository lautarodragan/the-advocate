---
name: "La pantalla de Game Over"
description: "Perder una pelea o un GameOver vuelven directo al título; RM2k muestra la imagen de GameOver con su música y espera una tecla"
type: feature
assignee: Carpincho
---

Pedido de taro, el 2026-09-28.

Hoy `op_game_over` (`rom/src/interprete_game_over.s`) y la derrota sin
manejador (`op_battle_destination`) hacen `jml reset`: vuelven al arranque sin
mostrar nada. RM2k pasa por `Scene_Gameover`: la imagen del juego en
`GameOver/` (la que nombra el `System` del LDB), la música de Game Over del
sistema, un fundido, y espera una tecla antes de volver al título.

El juego trae su imagen en `GameOver/` (ver `ABL_GAME_DIR`).

2026-09-28, en `testing/`: hecho por Carpincho en su rama, sobre `main` en
17685f7d; `just cartuchos` y `just pruebas` sobre la rama. Lo que queda es
de taro: ver "Qué tiene que probar taro", abajo.

# Qué tiene que probar taro

* **Escuchar** `/shared/audio/2026-09-28-game-over/` (con su `LEEME.txt`):
  el tema nuevo, y los nueve temas a los que les baja algo sin MSU-1 —el
  bombo de siete, y un instrumento de bubstix, bmlv2-sbl y golden_axe—. Si
  no se acepta, hay que buscarle lugar a los dos programas de `GameOver3` en
  el directorio; no está resuelto.
* **Mirar** `/shared/capturas/2026-09-28-game-over/`: la golden nueva al
  lado del original.
* **Jugar** sin MSU-1 y con MSU-1 (la pista 231 es nueva: hay que copiarla a
  la tarjeta): perder una pelea sin manejador —el cofre trampa de los Rat
  Tracks B1, o el jefe del 26—, que la pantalla aparezca sin pasar por el
  mapa, que suene `GameOver3`, que A o START la cierren y que el título
  ande después ("Resume the Story" con la partida guardada). Y el fin de la
  demo del mapa 66, que es un `ReturntoTitleScreen`: tiene que ir derecho
  al título, sin la pantalla.
* En el FX Pak: ninguna búsqueda de MSU-1 nueva, pero el paquete de audio de
  la pantalla sube con la pantalla en negro; mirar que no tarde.

# Qué hace el original

Mirado en easyrpg-player (`Scene_Gameover`) y en el original con Wine, el
2026-09-28, con una copia del juego cuyo mapa de arranque llama a `GameOver`
(Ditto: `read`, un comando más, `write`):

* **La imagen es la del RTP, no `ablgameover.png`.** El `System` dice
  `gameover_name = "GameOver"`, y el juego trae en `GameOver/` un solo
  archivo, `ablgameover.png`, que no nombra nadie: RM2k busca `GameOver` en
  el juego, no lo encuentra, y usa el `GameOver.png` del RTP. Es lo que se ve
  con Wine: el "GAME OVER" gris sobre fondo oscuro. (La premisa del pedido
  era la otra imagen.)
* **El tema es `GameOver3`, también del RTP.** Ningún `ChangeSystemBGM` del
  juego cambia el de Game Over (sólo el de la pelea y el de la victoria).
* El mapa se borra con un fundido (35 cuadros), la imagen entra en 80 y sale
  en 80; la cierra `DECISION` (Enter/Z) y de ahí el título, que entra con
  su propio fundido.
* `CommandGameOver` y `CommandReturnToTitleScreen` esperan si hay un mensaje
  abierto.
* Perder una pelea sin manejador no pasa por el mapa: la pelea se borra y
  aparece la imagen. Y `ProcessSceneActionDefeat` prende el tema de Game Over
  **ya en el mensaje de la derrota**, con o sin manejador: eso no lo hace la
  ROM (ver la divergencia).

# Lo que se hizo

* `rom/src/game_over.s`, en el banco 1: la pantalla, con su audio, sus dos
  fundidos, A o START, y `jml reset`. Tres entradas: `game_over_anotar`
  (`op_battle` anota el destino de la derrota antes de pelear),
  `game_over_siempre` (encuentro al azar) y `game_over_si_perdio`
  (`pelea_arrancar`, con la pelea ya en negro: no vuelve a cargar el mapa).
  `GameOver` entra por `game_over_desde_el_mapa`, que funde el mapa.
* **`ReturntoTitleScreen` tiene opcode propio**, `OP_RETURN_TO_TITLE` (0x34):
  compartía el de `GameOver` cuando ninguno dibujaba nada, y tiene que seguir
  yendo directo al título.
* **La imagen, comprimida en LZ2** (tools/port/pantalla_completa.py): la
  convierte `titulo.convertir` —el mismo camino que la de título, que no pasa
  ni por el asignador ni por Voodoo: tiene su propia reducción de colores—,
  y un solo flujo lleva tiles, tilemap y colores. La ROM lo descomprime en la
  WRAM del $7F y lo sube con tres DMA: `pantalla_subir`, que lee una fila de
  `pantallas_tabla` y no sabe qué pantalla sube, así que la de título la
  puede usar tal cual.
* **El tema**, con paquete de audio propio (`PAQUETE_GAME_OVER`, el tema
  solo, detrás del de la pelea), que la ROM sube con la pantalla en negro.
  Con MSU-1, su pista. La música se busca ahora en el juego y después en el
  RTP, como en RM2k, y las pistas de los temas del RTP que nombra el `System`
  van numeradas detrás de las del juego (`GameOver3` es la 231): ninguna
  pista del juego cambia de número.

# Espacio

`just espacio release`, antes (17685f7d) y después:

    bancos de datos  115 de 124, 9 libres        115 de 124, 9 libres
    huecos           28.874 B                    15.367 B
    banco 0          72 B                        50 B
    banco 1          5.621 B                     5.135 B

(test-special: banco 0 de 951 a 929, banco 1 de 8.125 a 7.639.)

# La imagen: comprimida y no liviana + `.msu`

Medido el 2026-09-28 con `titulo.convertir` y el `lz2` de `tools/lz2/`:

    Game Over (GameOver.png del RTP, 32 grises)   crudo    LZ2
      256x224, 8bpp, 566 tiles                   36.224  11.530
      + tilemap y colores, un solo flujo         38.336  12.843
      liviana: 128x112 4bpp 16 colores, x2        5.024   2.901

    Título (ABL20Title, hoy sin comprimir)
      256x224, 8bpp, 240 colores, 496 tiles      31.744  15.241
      256x224, 4bpp, 16 colores, 453 tiles       14.496   6.234
      liviana: 128x112 4bpp 16 colores, x2        4.512   2.483
      liviana: 128x112 8bpp, 240 colores, x2      9.152   5.190

**Se decidió la de calidad, comprimida, en la ROM, sin versión liviana.** La
liviana ahorraría unos 10 KB contra la comprimida, y costaría un segundo
camino en la ROM —agrandar al doble, buscar en el `.msu`, la espera de la
búsqueda— que ningún core de la tanda corre entero. Comprimida, la imagen
de calidad se ve en todas las consolas.

**Para el título**: comprimir lo que hay hoy, sin tocar un pixel, ahorraría
**16,5 KB** (31.744 → 15.241 de tiles; el tilemap y los colores aparte);
una liviana en la ROM con la de calidad en el `.msu`, **29 KB** (a 2.483).
El mecanismo para lo primero ya está: `pantalla_completa.comprimida` y
`pantalla_subir`, con otra fila en `pantallas_tabla`.

# El audio

**El tema entra**: `GameOver3`, con paquete propio y pista de MSU-1 (la 231).
La prueba mira que suene con todas sus muestras en la ARAM.

**Y sin MSU-1 le baja a otros**, así que no está resuelto: se decide
escuchando. Medido con `Banco`, par por par (tema, programa o golpe), con los
argumentos que el conversor le pasa a `build_varios` en `release`, contra
main en 17685f7d: de 406 pares, 392 igual, 4 suben y **10 bajan** más de 0,5
kHz. La causa: `GameOver3` trae dos programas que ningún tema del cartucho
usaba —19 y 54— y el directorio está lleno, así que son dos copias menos
para los demás (`snes_music.copias`).

    golpe 35 (bombo)   21,8 -> 18,2   Fire_Mustang..., Story Music,
                                      bmlv2-sbl, fm2bar_gs, jackalstg2,
                                      lufsorr, rshinld
    golpe 65           18,2 -> 14,2   bubstix
    programa 27        22,0 -> 18,9   bmlv2-sbl
    programa 50        22,0 -> 18,4   golden_axe-turtlevillage2

Con MSU-1 no cambia nada. Los wav de antes y después de los nueve temas, y
`GameOver3` por el SPC700 y por su pista, en
`/shared/audio/2026-09-28-game-over/` (con su `LEEME.txt`).

**La tabla de techos se volvió a correr** (`just techos`): la huella de todos
los temas cambió, porque los números de muestra se corren con las dos
nuevas. Cambia el aire de ocho temas, casi todos en menos de 0,1 dB; los que
más: dcbest 0,325 -> 0,354 (+0,7 dB), T_VGFighterMAX_Masako 0,335 -> 0,342,
jackalstg2 0,270 -> 0,279, rshinld 0,275 -> 0,269. dcbest no cambió ninguna
muestra: en main, con 0,325, su pico queda a -1,4 dB (`techos.py --medir`),
y el objetivo es -0,5.

# Pruebas

* `pruebas/rpgmaker/test_game_over.py`: la pelea sin manejador, el encuentro
  al azar y el comando llegan a la pantalla —la golden `game-over`, la misma
  para los tres—; no se va sola; A la cierra y del otro lado está el título
  (la golden `titulo` de siempre) y el juego vuelve a correr. El control: la
  pelea con manejador y una página sin el comando no llegan. Y
  `ReturntoTitleScreen` (caso nuevo `volver-al-titulo`) va al título sin
  pasar por la pantalla.
* `test_cores.py::test_game_over`: la pantalla en snes9x y en bsnes.
* `test_curar.py`: el control de `FullHeal` miraba que el encuentro no
  reiniciara; ahora el Game Over no reinicia hasta la tecla, así que mira
  la pantalla.
