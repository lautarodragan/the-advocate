---
name: "La victoria avisa la experiencia"
description: "Que la pelea diga N EXP received y Level up"
type: feature
assignee: taro
---

**Que la victoria diga la experiencia ganada y quién subió de nivel.**

La experiencia y la subida de nivel ya andan (`done/experiencia-y-subida-de-nivel.md`),
pero la pelea no las cuenta: ni "N EXP received" ni "Level up!". El estado cambia
igual; se ve recién en el menú.

Los textos salen de `terms` del LDB, como en RM2k (`Scene_Battle_Rpg2k`).
Mueve las goldens de fin de pelea de la tanda.

## Cómo quedó, el 2026-09-26

Al ganar, la ventana de mensaje tapa al grupo —los cuatro renglones de
`BA_PAG_MSG_FILA0`, los mismos del mensaje de una página de tropa— y cuenta
lo que `ProcessSceneActionVictory` cuenta, página por página, cada una
esperando a A:

* la victoria y la experiencia: " The combat has resulted in" / "victory!" /
  "90 EXP". El término del ABL no entraba en un renglón y se pasaba al de
  abajo cortado a la mitad; ahora el conversor lo parte en un espacio
  (`pantallas.renglones_de_la_victoria`);
* una por cada actor que subió, en el orden del grupo: "Arden LEVEL 6
  achieved!" y un renglón por habilidad aprendida ("Pickpocket acquired!").
  Si son más de tres, siguen en otra página sin repetir el nivel.

Los textos son `victory`, `exp_received`, `level`, `level_up` y
`skill_learned` del LDB, armados como `game_message_terms.cpp` para RM2k en
inglés. El conversor corta si alguno no entra en los 31 caracteres
(`pantallas.cobrar_la_victoria`).

La experiencia se reparte ahora **al ganar**, antes de mostrar nada, como en
RM2k; antes se repartía al cerrar la pantalla.

Lo que queda afuera, a propósito:

* **El oro y los ítems**: RM2k los cuenta en la misma página, pero el port
  todavía no los da al ganar.
* **Una habilidad que ya sabía se cuenta igual**: RM2k sólo avisa las
  nuevas. Difieren sólo si un `ChangeSkills` enseña antes una que después
  enseña un nivel, y en el ABL ninguno lo hace (mirado en `data/`).

Lo cubre `pruebas/rpgmaker/test_victoria.py`, que lee el texto del tilemap.
Usa la RAM lejana `$7E7810-$7E781F` (`BA_VIC*` en `ram_lejana.s`); ningún
opcode nuevo.

Falta que taro lo juegue: que el ritmo de las páginas con A se sienta bien y
que la pelea se cierre en la última. Las capturas de antes y después están
en `/shared/goldens/2026-09-26-victoria/`. Ninguna golden de la tanda se
movió: ninguna captura la pantalla de la victoria. `test_cores.py` tampoco
pasa por ella, así que la comparación entre snes9x y bsnes no cobra la RAM
nueva; `ba_vic_empezar` escribe las ocho posiciones antes de que nadie las
lea.
