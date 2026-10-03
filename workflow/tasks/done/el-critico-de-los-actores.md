---
name: "El crítico de los actores"
description: "El LDB les da golpe crítico a casi todos los actores, y la ROM lo pone en cero con un comentario que dice que ninguno lo tiene"
type: bug
assignee: taro
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

# Lo que se hizo (Cardenal, 2026-10-02)

**Qué dijo el blame.** El comentario nace en `9527063d`, "Las peleas de la
intro se pueden pelear", la primera versión de la pelea (2026-09-12): "ningún
actor del ABL tiene golpe crítico". Fue un supuesto, no una decisión: el
modelo de entonces (`tools/batalla.py`) leía `critical_hit` con un
`getattr(..., False)`, y el lector del LDB de entonces (`tools/lcf.py`) no
leía ese campo del actor —sólo el del enemigo—, así que daba falso para
todos y el docstring dijo "en el ABL ninguno lo tiene". La ROM se escribió
contra ese modelo. Nadie lo midió contra el volcado.

**Qué es en RM2k** (easyrpg, `Game_Actor::GetCriticalHitChance` y
`Algo::CalcCriticalHitChance`): `1 / critical_hit_chance` si tiene
`critical_hit`, más el mejor `critical_hit` de las armas equipadas —en por
ciento—, sumado **en float** y después `* 100.0` truncado. Con 30 es un 3 %.
El float importa: `1/25` da 3 y no 4, y un arma de 12 sin crítico propio da
11. Ningún actor del grupo tiene hoy un arma con bonus, pero hay 70 armas
que lo tienen.

**Cómo quedó.**

- `rm2k-snes-battle`: `rules::critical_percent` hace la cuenta en f32, y
  `Combatant::actor` y el `ChangeEquipment` de una página la usan. Los
  enemigos pasan por la misma función (en ABL dan lo mismo que antes).
- La consola no suma: el conversor escribe `crit_table`, con una fila por
  cada parte propia distinta y una columna por cada bonus distinto, y la ROM
  la indexa con `actor_crit_row` y la mejor de las columnas de los slots 0 y
  1 (`item_crit_k`). `ba_crit_of`, en `battle.s`, la llaman `ba_actor_setup`
  y `ba_reparam`.
- **El azar no se movió**: el tiro del crítico ya se hacía siempre, con 0.
  Por eso ninguna golden cambió: en las peleas de la tanda no sale ningún
  crítico del grupo con la semilla de fábrica.
- El juego de prueba de `rm2k-snes-battle` (`tests/game/dump`) tenía a sus
  actores con crítico; ahora no lo tienen, para que los hashes del Python
  —que nunca lo leyó— sigan siendo la respuesta correcta. Ver el encabezado
  de `tests/model.rs`.

**Pruebas** (en ABL, `pruebas/rpgmaker/test_batalla.py`):

- `test_cada_actor_entra_a_la_pelea_con_su_critico`: `BA_CRIT` de Kersh,
  Core y Manta contra una cuenta de easyrpg hecha en la prueba —del volcado,
  en float— y contra el modelo. En rojo antes: "el actor 11 entró con un
  crítico de 0 y easyrpg le da 3".
- `test_un_critico_del_grupo_da_el_mismo_hp_que_el_modelo`: la primera
  semilla con la que a alguien del grupo le sale un crítico contra el
  droide, escrita en `BA_SEED`, turno por turno contra el modelo. En rojo
  antes: con el modelo viejo, "con ninguna de 200 semillas le sale un
  crítico a nadie del grupo".
- `test_la_cuenta_del_critico_es_la_de_easyrpg`: la cuenta de la prueba con
  1/25, y que el grupo tenga crítico.
- En Rust: `the_critical_hit_adds_in_floating_point`.

**Cuánto cambia el balance**, medido con el modelo: 2000 semillas por pelea,
todos atacando al primer enemigo, sin las páginas de la tropa. Sale un
crítico del grupo en ~3 % de los golpes que pegan.

| pelea | turnos antes → ahora | victorias |
| --- | --- | --- |
| el droide (82), Kersh, Core y Manta | 2,10 → 2,03 | 100 % |
| la pandilla LT (86), los tres | 2,00 → 2,00 | 100 % |
| los Lazer Teeth (86), Kersh y Talan | 4,24 → 4,18 | 100 % |
| el Rat King (97), AG7 solo, sin ratas | 10,63 → 10,19 | 78,0 % → 81,4 % |
| los agentes (102), Kersh | 4,25 → 4,19 | 100 % |
| los merodeadores (222), los tres | 1,87 → 1,85 | 100 % |

Entre 1 % y 4 % más cortas; la única que se nota es la del Rat King, que
AG7 solo gana tres veces más de cada cien.

**Lo que queda afuera**: `PreventsCritical` —el Talisman (ítem 76) tiene
`prevent_critical`, y en RM2k anula los críticos de los enemigos contra el
que lo lleva—. Ni la ROM ni el modelo lo miran, desde antes de esto.

# Qué tiene que mirar taro

- **Una pelea cualquiera, varias veces**: de vez en cuando —uno de cada
  treinta golpes que pegan— un golpe del grupo hace el triple. La pantalla
  no lo anuncia distinto: RM2k 2000 tampoco dice "crítico" con el ataque
  normal, sólo se ve el número.
- **El Rat King con AG7 solo**, que es donde más se nota (78 % → 81 % de
  victorias en el modelo).

# Al mergear

- Instalar en el global: `just -f tools/justfile install battle mapdata`
  (y `cartridge`, que arma con el runtime del checkout).
- Ramas: `worktree-agent-a33a321932dffd972` acá, `cardenal-textos-y-critico`
  en el clon de ABL (`/extras/scratch/cardenal/abl`).
