---
name: "El crítico de los actores"
description: "El LDB les da golpe crítico a casi todos los actores, y la ROM lo pone en cero con un comentario que dice que ninguno lo tiene"
type: bug
---

Lo encontró Cardón el 2026-09-30, pasando el modelo de la pelea a Rust
(`testing/rust-el-dominio-de-la-pelea.md`). taro lo pidió como tarea ese día.

`tools/runtime/battle.s`, al armar un actor para la pelea, guarda
`BA_CRIT` en cero con el comentario "no actor in ABL has a critical hit".
El volcado lo desmiente: `critical_hit` está prendido en casi todos los
actores de `rom/data/db/actors.json`, los del grupo incluidos —Kersh, Core,
Manta, Talan, Arden, AG7—, casi todos con `critical_hit_chance` 30. En RM2k
eso es una chance de 1 en 30, no un 30 %: confirmarlo en easyrpg
(`Game_Actor::GetCriticalHitChance`) antes de tocar nada.

El Python viejo tampoco leía el campo, así que la ROM y el modelo se
equivocaban igual y ninguna prueba lo veía. El modelo en Rust
(`rm2k-snes-battle`, `Combatant::actor`) lo conserva a propósito, con un
comentario: arreglarlo **mueve la ROM y el azar de todas las peleas**, y el
modelo tiene que moverse junto con ella, porque las pruebas lo comparan paso
a paso.

El comentario de `battle.s` viene de antes de la traducción al inglés
(`456dd0d4`): el `git blame` con `-C --diff-algorithm=histogram` dice de
cuándo es y si fue una decisión o un supuesto.

Hecho es: el crítico de los actores leído del LDB en los dos lados, una
prueba con un actor que lo tiene y un azar que lo dispara, vista en rojo
antes, y las goldens de la pelea que se muevan mostradas a taro.
