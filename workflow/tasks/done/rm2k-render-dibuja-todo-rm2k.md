---
name: "rm2k-render dibuja todo lo de RPG Maker"
description: "Llevar a rm2k-render lo que hoy dibuja el conversor en Python: CharSets, animaciones de pelea, enemigos y fondos, FaceSets, System y el cartel de ShowPicture"
type: refactor
assignee: taro
---

Decidido con taro el 2026-09-29 (ver
`workflow/decisiones/las-herramientas-se-separan-de-abl.md`): `rm2k-render`
es el dueño de dibujar gráficos de RPG Maker, sin saber de la SNES.

Hoy lo dibuja el Python del conversor:

- los CharSets —poses, translúcidos horneados, los hechos con un tile—:
  `tools/port/sprites.py` y `render_map.Charsets`;
- las animaciones de pelea: `battle_animations.py` y `animation.py`;
- los fondos de batalla y los enemigos: `battle_scenes.py` y `scene.py`;
- las FaceSets (`menus.py`), el System (`window.py`) y el cartel de
  `ShowPicture` (`picture.py`);
- la base de todo: `render_map.load_image`, que ya tiene su par en
  `picture.rs`.

Va por partes, un subcomando por tipo de asset, cada una con las ROMs byte
por byte iguales, igual que las capas de los mapas. Lo que sea decidir
colores o cortar en 8x8 se queda del lado de Adeleine y de `voodoo`.

## Hecho, el 2026-09-30

En tres partes, cada una con las ROMs byte por byte iguales y todo lo que
dibuja comparado pixel por pixel contra el Python:

- los CharSets: `testing/rm2k-render-los-charsets.md` (Yaguarundí);
- la pelea —animaciones, enemigos, fondos—: `testing/rm2k-render-pelea.md`
  (Coatí);
- las pantallas —caras, System, cartel de `ShowPicture`—:
  `testing/rm2k-render-pantallas.md` (Hurra).

`load_image` se fue. Lo que el port hace con esas imágenes para la consola
—achicar, cortar en 8x8, la trama, el horneado, los colores— sigue en el
conversor y en Adeleine.
