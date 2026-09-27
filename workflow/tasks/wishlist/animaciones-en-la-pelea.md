---
name: "Animaciones en la pelea"
description: "El animation_id de las habilidades y las armas, dibujado sobre la escena"
type: feature
---

# Qué

Que una habilidad —del grupo o de un enemigo— dibuje su `animation_id` sobre
la escena de la pelea, como `Game_BattleAlgorithm::GetAnimationId`. Hoy no se
dibuja ninguna: ni las siete del grupo de la intro ni `ShortCircuit` (la 62),
que el hito 4 de Lashe City (`lashe-4-ag7-en-la-pelea.md`) pedía.

# Status

Anotado el 2026-09-27, sin empezar. Se dejó afuera del hito 4 por tamaño: es
un subsistema nuevo adentro de la pelea, y la mecánica del hito no dependía de
él.

# Lo que se sabe

El dibujo de las animaciones existe **para el mapa** —`OP_ANIMATION`,
`rom/src/animacion_de_batalla.s`—: cuatro objetos de 32x32 en una caja de
64x64, una paleta de sprite y los cuadros subidos por DMA en el vblank. En la
pelea no corre nada de eso, y lo que haría falta, mirado el 2026-09-27:

* **VRAM**: la pelea usa de `$2000` en adelante —el texto, sus dos tilemaps y
  los 32 KB de la escena— y deja libre `$0000`-`$1FFF`, que alcanza para los
  64 tiles de la caja con el `OBSEL` apuntado ahí.
* **CGRAM**: la escena reparte **una paleta por battler distinto desde la 8**
  (`ESC_PAL_N` en `batalla_escena.s`), que son las de los objetos. Con los
  battlers de una tropa quedan libres las de arriba, salvo en una tropa de
  ocho battlers distintos.
* **La pantalla**: `TM` prende sólo BG1 y BG2; habría que prender los objetos y
  armar la OAM en el lazo de la pelea, que hoy no la toca.
* **El tiempo**: el mensaje de la acción dura `BA_MSG_CUADROS`, y la animación
  tendría que caber adentro o estirarlo.
* **El cartucho**: una animación son decenas de KB (la 77, 40 KB), y el
  cartucho lleva sólo las que algún `ShowBattleAnimation` de un mapa pide. La 62
  ya está (`parches/auto/animaciones/0062.toml`); de las de las habilidades de
  AG7 —1, 118, 145, 78, 8, 95, 119, 30, 93, 60, 38, 115, 151— sólo la 1 y la
  78.

# Por qué

Se ve. taro lo confirma jugando: hoy una habilidad es un mensaje y un número
que baja.
