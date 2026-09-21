**Experiencia y subida de nivel.**

Hoy no existen: cada actor queda en el `initial_level` del LDB y aprende las
habilidades de ese nivel (`batalla.habilidades_de`). Falta ganar experiencia al
ganar una pelea, subir de nivel con la curva de experiencia del LDB, y que al subir
crezcan HP, SP, ataque, defensa, mente y agilidad según las curvas de parámetros de
cada actor, y se aprendan las habilidades del nivel nuevo.

Referencia: `Game_Actor` de EasyRPG en `/extras/ref/easyrpg-player`. Taro lo pidió
el 2026-09-21.

Hecho es: una pelea ganada da experiencia, un actor sube de nivel y sus números
crecen como en RM2k, y todo eso viaja en la partida guardada.
