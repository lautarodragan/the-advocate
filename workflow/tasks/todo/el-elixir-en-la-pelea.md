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
