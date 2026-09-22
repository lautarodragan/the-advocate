---
name: "La victoria avisa la experiencia"
description: "Que la pelea diga N EXP received y Level up"
---

**Que la victoria diga la experiencia ganada y quién subió de nivel.**

La experiencia y la subida de nivel ya andan (`done/experiencia-y-subida-de-nivel.md`),
pero la pelea no las cuenta: ni "N EXP received" ni "Level up!". El estado cambia
igual; se ve recién en el menú.

Los textos salen de `terms` del LDB, como en RM2k (`Scene_Battle_Rpg2k`).
Mueve las goldens de fin de pelea de la tanda.
