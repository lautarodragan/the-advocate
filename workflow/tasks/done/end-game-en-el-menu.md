---
name: "End Game en el menú de pausa"
description: "La orden End Game del menú de pausa tiene que andar como en RM2k"
type: feature
assignee: Yaguareté
---

De taro, el 2026-09-28: "que End Game ande bien".

En RM2k, End Game abre `Scene_End`: una ventana que pregunta si volver al
título, con "Yes"/"No" (los términos del LDB), y "Yes" funde la pantalla y la
música y va al título. Hay que ver qué hace hoy la ROM con esa orden (el
menú está en `rom/src/menu.s`; las órdenes y cuándo van en gris, en
`tools/port/titulo.py`).

## Qué hacía la ROM

La orden va en gris y A no hace nada: `MENU_HECHAS` (titulo.py) no la
incluye, y el comentario decía por qué —"terminar el juego pide volver al
título sin reiniciar el SPC700"—. Eso dejó de valer: desde la pantalla de
Game Over, volver al título es un `jml reset`, que repone todo, y
`OP_RETURN_TO_TITLE` hace lo mismo.

## Qué hace el original

Mirado en `Scene_End` de easyrpg-player y en el RPG_RT de 2015 con Wine
(la copia del juego de Tero, con el mapa 4 que arranca con el grupo):

- Pantalla negra con dos ventanas del System: arriba la pregunta, el término
  `exit_game_message` ("End game?"), de 70x32 —el ancho del texto más 16— en
  y=72; abajo `yes` y `no` ("Yes", "No"), de 34x48, en y=120. Las dos
  centradas en x. Texto en el color 0; el cursor es la barra roja del
  System.
- **Entra con el cursor en "Yes"**. easyrpg entra en "No" (`SetIndex(1)`):
  vale el original. El RPG_RT de 2000 no arranca con Wine (se cae al cambiar
  el modo de video), así que el de 2015 es lo único medido.
- B, o "No", vuelve al menú con el cursor en "End Game".
- "Yes": el tema se funde en 400 ms (`BgmFade(400)`) y la pantalla se funde a
  negro en unos 330 ms —medido con capturas cada 18 ms—; después, el título.
- Entre el menú y esta pantalla hay un fundido corto (unos 6 cuadros). En la
  ROM las pantallas del menú se abren sin fundido, y ésta también.

La orden iba en gris desde que nació el menú (606911f4), por el porqué de
arriba; `git blame` no mostró otra razón.

## Qué se hizo

- `tools/port/fin_del_juego.py` dibuja la pantalla con las reglas de
  `Scene_End` —`ventana.ventana`, `ventana.cursor` y `dibujar_linea`, las de
  las otras ventanas— y la convierte: **una sola imagen de tiles y tilemap
  para las dos órdenes, con un índice de paleta por par de colores** (con la
  barra en "Yes", con la barra en "No"). Mover el cursor es subir la otra
  paleta de 16 colores en el vblank. La letra va a 6 pixeles, como en RM2k:
  no es la de a una letra por celda de la pantalla de ítems, porque son tres
  palabras fijas.
- Va en BG2, sobre `RANURA_VRAM` y `RANURA_MAP`, que es lo que ya escribe el
  menú: al volver, `menu_subir` los rearma y el mapa vuelve sin nada nuevo.
- `rom/src/fin_del_juego.s`, en el banco 1: arriba y abajo cambian de orden,
  B y "No" vuelven con `rtl`, y "Yes" funde el tema como un `FadeOutBGM` de
  400 ms —con la guarda de `op_fade_bgm`—, funde la pantalla en 20 cuadros,
  espera que el tema termine, lo calla (y la pista del MSU-1) y salta a
  `reset`, igual que la salida de la pantalla de Game Over. El reset es el
  arranque entero: música, paletas y RAM como al encender.
- En el menú, `MENU_FIN` entra en `MENU_HECHAS` y `menu_pantalla` hace el
  `jsl`; al volver, el cursor queda en End Game. El banco 0 gasta 15 bytes
  (`just espacio release`: de 205 a 190 libres).
- Lo que sigue distinto está en
  `workflow/divergencias/lo-que-la-pantalla-de-end-game-no-modela.md`.

## Pruebas

- `pruebas/rpgmaker/test_fin_del_juego.py`: la pantalla contra
  `fin_del_juego.render` en las dos órdenes y dando la vuelta; "No" y B
  vuelven al menú —contra `render_menu` con el cursor en End Game— sin que
  corra el reloj; "Yes", sobre el mapa 21 con su tema sonando, prende el
  fundido del tema, reinicia, llega a la golden `titulo`, y "Begin the Story"
  vuelve a arrancar el juego.
- Goldens nuevas `fin` y `fin-no` (`test_menu_golden.py`). Cambian `menu`,
  `menu-2` y `menu-grupo`: End Game ya no va en gris. Lado a lado con el
  original en `/shared/capturas/2026-09-28-end-game/`.
- Los techos de la música se volvieron a medir (`just techos`): el cambio de
  la ROM hizo recortar a `dcbest`, como la prueba avisa que puede pasar.
- Lo que ninguna prueba mira: que el fundido del tema **se oiga**, y la
  pista del MSU-1 callándose. La prueba mira que el fundido se prenda.

## Qué tiene que probar taro

- Menú, End Game: la pregunta y "Yes"/"No" en ventanas, con la barra roja en
  "Yes". Arriba y abajo la mueven.
- "No", y B: de vuelta al menú con el cursor en End Game; al cerrar el menú,
  el mapa como estaba.
- "Yes" con música sonando: la pantalla y el tema se funden y aparece el
  título con su tema; "Begin the Story" empieza de cero y "Resume the Story"
  carga la partida. Con y sin MSU-1.

# Probado

taro, el 2026-09-28: anda perfectamente, con y sin MSU-1.
