---
name: "Experiencia y subida de nivel"
description: "Ganar experiencia, subir de nivel y crecer según las curvas del LDB"
---

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

## Dónde quedó, el 2026-09-21

Lo de "hecho es" está, con casos que corren la ROM en
`pruebas/rpgmaker/test_experiencia.py`. Lo que quedó afuera:

- **La victoria no dice nada**: RM2k pone "N EXP received", "<nombre> Level
  up!" y lo que se aprendió (`PushExperienceGainedMessage`, `ChangeLevel` con
  su `PendingMessage`), y acá la pelea sigue diciendo sólo el término de la
  victoria. El estado cambia igual; lo que falta es contarlo. Mueve las
  pantallas de fin de pelea de la tanda.
- **`ChangeExp`, `ChangeLevel` y `ChangeParameters` no están**, porque el juego
  no los usa: ningún mapa, evento común ni tropa de `data/` los nombra, y
  ninguna rama pregunta por el nivel de un actor. Tampoco los `*_mod` de
  `ChangeParameters`, por lo mismo. Si alguno aparece, `exp_sumar` es la mitad
  de `ChangeExp` que sube; bajar de nivel pide además topar los HP y los SP,
  que es el `SetLevel` de easyrpg.
- Un actor que no puede entrar al grupo no tiene experiencia: sólo pelean ésos.
