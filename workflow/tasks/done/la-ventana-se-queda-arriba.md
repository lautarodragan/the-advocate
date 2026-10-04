---
name: "La ventana de mensajes se queda arriba"
description: "Jugando, la ventana pasó a quedar siempre arriba —y el cronómetro abajo— con NPCs de Lashe City que en el original hablan abajo"
type: bug
assignee: Calancate
---

De taro, el 2026-10-04, con el build `2026-10-04-5b29ba9-f6a44973`: "en algún
momento pasó a quedarse permanentemente arriba, y el cronómetro, abajo.
Creo que debería haber vuelto a estar abajo en algún momento". El Bum al
lado de la casa de Talan, el worried worker, el oficial del hover tram,
varios NPCs del lado izquierdo de Lashe City, los Neon Vipers: todos arriba.

Es de `la-ventana-arriba-al-medio-y-sin-fondo.md` (Quirquincho). Un
candidato, sin confirmar: el común 15, `CustomMenuSideQuests`, termina con
`MessageOptions [0,0,0,0]` —arriba— y los otros menús de la consola con
`[0,2,0,0]`.

## No es un bug: el original hace lo mismo (Calancate)

taro lo confirmó jugando el original: "estoy probando el original y parece
que sí es así". Lo que la deja arriba, leído en el volcado de ABL en
`5b29ba9` y en easyrpg-player:

* **La pone arriba primero la escena de los Neon Vipers**: mapa 14
  (`NV Get Talan to Work`), evento 2 `SceneDriver`, autostart. Su comando
  120 es `MessageOptions [0,0,0,1]`, para "LAZER TEETH LOOKOUT", y el 124
  la deja en `[0,0,0,0]` —arriba, fija— justo antes de pasar al mapa 16, la
  corrida al trabajo, que no tiene ningún `MessageOptions`. Por eso el
  cronómetro de esa corrida va abajo.
* **Y en Lashe City casi todo la vuelve a dejar arriba**. En los mapas 8 y
  9, los carteles hacen `[1,0,0,0]` y después `[0,0,0,0]`. El Bum abre su
  página 1 con `[0,0,0,0]`. Los eventos que la pasan abajo un rato (EV0013,
  los chicos, el EV0004 del 9) terminan volviendo a `[0,0,0,0]`. Para el
  autor, arriba es lo normal de esa zona. El único que la deja abajo es la
  página 2 del `DetourOfficer` del mapa 8, con `[0,2,1,0]`. Los NPCs sin
  `MessageOptions`, como el Tram Officer o el UpsetWorker, hablan donde
  quedó.
* **El común 15 no hace falta**: termina en `[0,0,0,0]`, pero la ventana ya
  estaba arriba sin abrir la consola.

Contra easyrpg-player:

* **La opción persiste igual**. `CommandMessageOptions` la guarda en
  `Game_System` (`message_position` y `message_prevent_overlap`), que es
  parte de la partida y no se resetea al cambiar de mapa. liblcf da por
  omisión abajo y correrse. Lo nuestro es `FAR_MSG_OPTIONS`, en la
  partida, que `msg_place` sólo lee: lo corrido va a `MSG_PLACE` y no se
  guarda. El compilador traduce `p[2] != 0` a `MSG_DODGE`, que es el
  inverso de `SetMessagePositionFixed(p[2] == 0)`, como debe.
* **El cronómetro también va abajo**. `Sprite_Timer` lo baja cuando la
  ventana tiene `GetY() < 20`, se vea o no: "RPG_RT doesn't check for the
  global setting … just checks for the Y position of the message window,
  regardless if it is active or visible". `timer.s` mira `MSG_PLACE`, la
  última ventana, y hace lo mismo.

No se cambió ni código ni goldens. No se corrió Wine ni ninguna ROM:
alcanzó con el volcado y el fuente de easyrpg-player, más lo que taro jugó.
