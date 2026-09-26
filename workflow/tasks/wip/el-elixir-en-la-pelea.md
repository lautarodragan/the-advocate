---
name: "El Elixir en la pelea"
description: "Usar en la pelea un ítem que sólo sirve sobre un caído"
type: feature
---

**Usar en la pelea un ítem que sólo sirve sobre un caído.**

El `Pungent Elixir-LIFE` (`ko_only`) ya levanta a un caído desde el menú, pero
la pelea no lo ofrece: `batalla.item_usable_en_batalla` deja afuera los ítems
`ko_only`, así que taro no lo pudo usar en Arden con 0 HP.

Lo que pide, según quedó medido al arreglar el menú:

- que el cursor de blanco de un ítem pueda pararse en un aliado caído;
- que el levantado vuelva a pedir órdenes el turno siguiente y cobre la
  experiencia al ganar;
- mover `batalla.py` igual, porque contra eso predice los HP `test_batalla.py`.

Levantar es lo mismo que en el menú: 1 HP y después el porcentaje del ítem
(`medicina_usar`). Referencia: `Scene_Battle` y `Game_Battler::UseItem` de
EasyRPG.

# Cómo quedó (2026-09-26)

- **La lista** ofrece los `ko_only` que levantan —el primero de `state_set`,
  el estado de muerto—: Phoenix Down, Pungent Elixir y Jumper Cable. Una
  `ko_only` que no levanta seguiría afuera: no le serviría a nadie.
- **El cursor de a quién** se para sólo en los actores a los que el ítem les
  sirve: caídos para uno que levanta, en pie para uno que no es `ko_only`. Una
  habilidad sigue parándose sólo en los que están en pie. Arranca en el
  primero al que le sirve; si no le sirve a nadie —un elixir sin caídos—, A no
  sale de la lista. **RM2k deja pararse en cualquiera** y el ítem que no sirve
  se gasta sin efecto; acá se lo saltea, que es lo que la pelea ya hacía con
  los caídos. Es una simplificación a favor del jugador, declarada en
  `ba_item_sirve_sobre`.
- **Levantar** es `max(1, curacion)` con la cura topada contra el máximo
  entero: el `SetHp(1)` de `RemoveStates` y el `ChangeHp(hp - 1)` de
  `ApplyStateEffect`. Lo mismo que `medicina_usar` desde el menú. El
  renglón de abajo del mensaje es el `message_recovery` del estado de muerto,
  "Core has revived!", y no el de los HP: `IsRevived` en `ePreHp`.
- **De paso**: una medicina que no levanta sobre un blanco que murió entre que
  se eligió y que le tocó **ya no lo levanta**. Los dos lados le sumaban la
  cura a los cero HP; `ApplyHpEffect` no toca a un muerto. Ese camino no lo
  ejecuta ninguna prueba: pide que el droide mate al blanco antes de que
  actúe el de la poción, y eso depende del azar.
- **El levantado** pide órdenes desde el turno siguiente y cobra la
  experiencia al ganar sin tocar nada: `ba_actor_siguiente` y
  `ba_exp_repartir` ya miraban los HP.

## Deuda que se vio

- El renglón de arriba de "usar un ítem" con un nombre largo se pasa de las
  32 columnas y la última letra cae en la columna 0 del renglón de abajo:
  "Kersh Pungent Elixir-LIFE  used." deja el punto delante de "Core has
  revived!". Es de antes —cualquier ítem de nombre largo lo hace, y el
  nombre del LDB trae un espacio al final—; no se tocó.
