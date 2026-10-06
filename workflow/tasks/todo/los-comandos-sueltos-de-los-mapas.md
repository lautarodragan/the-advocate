---
name: "Los comandos sueltos de los mapas"
description: "Los casos chicos que dejan páginas afuera: ChangeGold por variable, EraseEvent antes de un salto, la posición en pantalla en ControlVars, el corte en ChangeScreenTransitions, y el ControlVars = 999999 del común 45"
type: feature
agents: [Aguará, Chajá]
---

Del estudio de Aguará, `docs/research/2026-10-05-los-comandos-que-faltan.md`; lo midió `rm2k-snes-events culprits`. taro, el 2026-10-05: dejarlas en todo, sin lanzar todavía. Ninguno está en release; el común 45, al no compilar, hace saltear 47
llamadas desde los cuartos de Eisen.

## Ya hechos

Dos de los de la lista salieron el 2026-10-06 con
`cuatro-atajos-para-los-otros-juegos` (Chajá), porque rendían en los otros
juegos:

* **La condición por la dirección de un personaje**, `OP_IF_FACING`: las 31
  páginas de la simulación de Eisen de ABL, y las de los otros juegos.
* **Alejarse del héroe en una ruta**, la orden 10, con el paso al azar y mirar
  para el otro lado.

Sin ellos y sin el `ControlVars` = 999999 la simulación de Eisen sigue sin
andar: el común 45 es lo que falta.
