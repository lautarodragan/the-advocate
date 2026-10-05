# Qué

Desde el 2026-10-04 `ChangeExp` y `ChangeLevel` compilan: son `OP_EXP` y,
con el mensaje, `OP_LEVEL_PAGE` detrás —ver `exp_change` y `level_page` en
`tools/runtime/level.s`—. El nivel, la experiencia, las habilidades, los HP y
SP recortados al bajar y el texto de cada página son los de
`Game_Actor::ChangeExp` y `ChangeLevel` de easyrpg. Lo que no es igual:

* **Dos habilidades que se aprenden en el mismo nivel** salen en el mensaje
  en el orden de sus pares —por número de habilidad— y no en el de la tabla
  del LDB. La ROM recorre nivel por nivel, como la página de la victoria; el
  editor guarda la tabla ordenada por nivel, así que entre niveles distintos
  el orden es el de RM2k.
* **En una página de tropa no hay mensaje**: la ventana de la pelea no es la
  del mapa. El nivel cambia igual, y por lo que se lee en `ba_sync_in` la
  pelea toma el ataque, la defensa, el espíritu y la agilidad del nivel
  nuevo —`ba_reparam`— pero no el máximo de HP ni el de SP. No se midió:
  ninguna tropa de ABL lo hace.
* **Un mensaje de más de 73 renglones** —el de cada nivel y el de cada
  habilidad nueva, sumando todo el grupo— pierde los que siguen, que se
  aprenden igual; y **un renglón de más de 48 letras** se corta ahí, aunque
  la ventana lo corta antes.
* **El actor por variable no compila**, como en `ChangeHP`.

# Medido

Contra el modelo de la pelea —`rm2k-snes-battle experience`, que es el de
easyrpg en `rm2k-rules`— en `pruebas/rpgmaker/test_experiencia_de_eventos.py`
de ABL. Contra el RPG_RT no se midió: el juego no usa los comandos, y el
orden de dos habilidades del mismo nivel no se da en ningún actor de ABL.

# Cómo reproducirlo

Un `ChangeLevel` con mensaje sobre un actor cuya tabla enseñe dos
habilidades en un nivel, la de número más alto primero.
