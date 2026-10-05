---
name: "ChangeExp y ChangeLevel"
description: "El compilador no tiene ChangeExp ni ChangeLevel, y una página con un comando que no compila se cae entera: las puertas del mapa de debug no pueden dar experiencia"
type: feature
agents: [Hurón, Carpintero]
assignee: taro
---

Lo encontró Hurón el 2026-10-04, al agregar las puertas de Paradise y de
después de Fortitude (`workflow/tasks/*/dos-puertas-mas-en-el-mapa-de-debug.md`,
en ABL). Con los dos comandos, cada puerta podría dejar los niveles que
tendría alguien que jugó: después de Fortitude, Talan 3, Arden 4, Saldra 5,
AG7-17 6; en Paradise, Talan 7, Arden y Saldra 7, AG7-17 8. Fijarse si el
juego mismo los usa en algún lado.

## Carpintero, 2026-10-04

**El juego no los usa.** Ningún `ChangeExp` (10410) ni `ChangeLevel`
(10420) en los mapas, los comunes ni las tropas del volcado: sólo los
van a usar las puertas 7 y 8 del mapa de debug.

**Cómo queda.** Los dos comandos comparten un opcode, `OP_EXP` (el 0x42):
el actor —0 el grupo—, qué hace —nivel o experiencia, restar, por
variable, con mensaje— y la cantidad. En la ROM es `exp_change`, en
`level.s`: el `ChangeExp` y el `ChangeLevel` de `Game_Actor`, con las
habilidades que enseñan los niveles que pasó y el `SetLevel` que recorta
HP y SP al máximo del nivel nuevo.

**El mensaje es el otro opcode, `OP_LEVEL_PAGE` (el 0x44)**, que el
compilador pone pegado detrás cuando el comando lo pide. `OP_EXP` anota
los renglones —el del nivel de cada uno que subió y el de cada habilidad
que no sabía— y `OP_LEVEL_PAGE` arma una caja por vez en la RAM, con
cuatro renglones o hasta el fin de un actor, que es el `PushPageEnd` de
RM2k, y la abre con la ventana de siempre; se queda en sí mismo hasta que
no queda ninguna.

**La RAM**: $7E7A50 a $7E7AFF (`LVL`, lo que trabaja `exp_change` y los
renglones anotados) y $7E6128 a $7E61FF (`LVL_BOX`, la página). Ningún
símbolo de `release` cae ahí.

**El modelo** es `Standing::change_exp` y `change_level` en `rm2k-rules`, y
`rm2k-snes-battle experience` lo contesta para las pruebas.

**Lo que no es igual a RM2k** está en
`workflow/divergencias/lo-que-changeexp-y-changelevel-no-modelan.md`: el
orden de dos habilidades del mismo nivel, nada de mensaje en una página de
tropa, y los topes de renglones.

## En ABL

Rama `carpintero-changeexp` del clon de Carpintero
(`/extras/scratch/Carpintero/abl`):

* `pruebas/rpgmaker/test_experiencia_de_eventos.py` y cuatro casos: nivel,
  experiencia, habilidades y HP contra el modelo, cada página del mensaje
  leída de `LVL_BOX`, y una página contra el mismo texto en un
  `ShowMessage`. Con las herramientas de `main`, los casos no compilan.
* Las puertas 7 y 8 de `parches/manual/nuevos/Map0900.json`: Talan y el
  compañero de la rama en los niveles que midió Hurón, con un `ChangeLevel`
  de -49 y otro que sube; los `ChangeSkills` de Arden que suplían el subir
  se fueron. `test_mapa_de_debug.py` lo cobra en las dos puertas, por rama.

**Una trampa que apareció**: un caso con `ChangePartyMembers` le cambia al
conversor quién puede liderar en todos los mapas (`page_party` en
`convert.rs`), y con eso las paletas: el mecánico del 20 y el tram salían
con otros colores. El caso del grupo pone el grupo desde la prueba.

## Al mergear

Reinstalar en el global `cartridge events convert battle`: el runtime y el
bytecode, el compilador, y el subcomando `experience` que piden las
pruebas. `rules` cambió sólo agregando, así que `rm2k-render` y `mapdata`,
que lo compilan adentro, no cambian de comportamiento.

Tanda: 1098 en verde con las herramientas de la rama, sobre los dos árboles
mergeados con `main`. No hay goldens nuevas ni movidas.
