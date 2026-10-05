---
name: "Los comandos que faltan"
description: "Qué comandos de eventos de RM2k el compilador todavía no sabe compilar, medido sobre el juego entero: cuántas páginas se caen por cada uno, y qué cuesta cada uno"
type: research
agents: [Aguará]
assignee: taro
---

De taro, el 2026-10-05: "qué comandos del sistema de eventos nos falta
implementar?". El compilador lo sabe página por página, pero no hay un
reporte del juego entero.

# Lo hecho (Aguará, 2026-10-05)

El estudio está en `docs/research/2026-10-05-los-comandos-que-faltan.md`,
con la tabla de cada comando del juego, lo que falta ordenado por páginas
que destraba, lo que se acepta sin hacer, y la recomendación.

Para medirlo quedó una herramienta: **`rm2k-snes-events culprits`**, que
persigue cada página que no compila hasta encontrar todos sus culpables,
y cuenta cuántas páginas deja afuera cada comando solo. Mira mapas,
comunes y tropas, y las llamadas a comunes que se saltean. Ver el README
del crate.

Lo que salió, en corto: en los mapas faltan siete cosas para 36 páginas,
ninguna en `release`; lo único entre la granja y el día siguiente son dos
`EraseEvent` de la cantera (mapa 150 y común 36); y en la pelea,
`ChangeMonsterCondition` y `FlashScreen` dejan afuera `Inscribe` y
`ControlMachines`, 164 páginas.

**Al mergear**: reinstalar `events` (`just -f tools/justfile install
events`). La ROM no cambia: `release` sale byte por byte igual con el
binario nuevo, y el `events.json` de `scan` y `compile` también.

# Lo que queda para taro

* Elegir por dónde seguir: la recomendación del estudio es la cantera
  primero.
* La decisión sobre `ChangeMonsterCondition`: estados de verdad en la
  pelea (grande) o aceptarlo como deuda declarada para destrabar las dos
  habilidades.
