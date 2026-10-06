---
name: "Elegir otro System desde el proyecto"
description: "Una perilla del rm2k-snes.toml que dice qué System usar en lugar del que nombra la base de datos: uno del juego, del RTP o del proyecto"
type: feature
agents: [Calandria]
assignee: taro
---

De taro, el 2026-10-05: los cuatro juegos que no arman por la ventana
arman y corren con el System de ABL puesto a mano en una copia. "lancémosla
ahora! … un paso hacia adelante barato y atómico, sin introducir hacks ni
complejidad". Es el camino 2: elegir otro System, no una receta sobre el
del juego.

## Lo hecho

`[graphics] system`, **opcional**: un nombre, que se busca como el de la
base de datos —el juego, su carpeta, el RTP—, o la ruta de una imagen
propia, relativa al `rm2k-snes.toml` y terminada en `.png` o `.bmp`. La
lee `system_choice` en `game.rs` del conversor, que la deja absoluta si
es una ruta; de ahí van dos caminos, los únicos que buscaban el System:

* `rm2k-snes-screens --system`, en todas las llamadas con juego
  (`window`, `convert`, `render`): `Game::use_system` cambia el nombre
  que busca `Game::skin`, o le da el archivo. La ventana, el menú, la
  pelea y el título salen de ese `skin`.
* `system_path` en `maps.rs`, los dígitos del cronómetro que dibuja
  `wally`.

Prueba: `tools/rm2k-snes/screens/tests/system_choice.rs`, roja con
`use_system` vacío (dos de tres).

Comprobado con ROMs: ABL sin la perilla sale igual, `abl.sfc`
`27e94e67039533a2…`, y la tanda da 1136. Frozen World, Book of Three y
Desert Nightmare, armados con el juego original y
`system = "ablskin.png"`, arrancan: capturas en
`/shared/capturas/2026-10-05-otros-juegos/system-elegido*.png`, ROMs en
`/shared/builds/otros-juegos/<juego>.sfc`, y la perilla commiteada en
cada repo. Dooms2 no arma por otra cosa: sus CharSets son BMP.

Lo que no cubre nada en la tanda: ningún caso de ABL pone la perilla.

Al mergear: reinstalar `convert` y `screens`.
