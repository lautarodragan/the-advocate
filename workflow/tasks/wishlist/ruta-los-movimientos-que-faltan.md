---
name: "Ruta: los movimientos que faltan"
description: "Las órdenes de movimiento que la ROM todavía no hace: avanzar, los giros relativos, y las diagonales y los giros del héroe"
type: feature
---

# Qué

Las órdenes de movimiento de una ruta forzada que la ROM no entiende. Del
`rpg::MoveCommand::Code` ya están los cuatro sentidos, las cuatro diagonales
**de un evento**, acercarse al héroe (9), mirarlo (21) y, desde el
2026-10-06, el paso al azar (8), alejarse (10) y mirar para el otro lado (22):
siempre sobre eventos.

Quedan:

* **Las diagonales del héroe** (4 a 7), que son lo que más páginas deja afuera
  en los otros juegos: unas 50 en Sunset y 45 en Vampires Dawn, medido el
  2026-10-06 con `culprits`. Es lo caro: ver abajo.
* **Los giros relativos** —90 a la derecha (16), a la izquierda (17), 180 (18),
  90 al azar (19), mirar al azar (20)—, que en un evento se calculan con la
  dirección de la que ya parte, como `face_diagonal`, y en el héroe con
  `hero_heading` si está trabado y `hero_dir` si no. Sunset: unas 8 páginas.
* **Avanzar** (11): Sunset, 3 páginas, junto con un 18 del héroe.
* **Las de la ruta propia de una página** —9, 10, 21, 22, 8—, que su compilador
  rechaza: ninguna de las propias de ABL las usa.

# Status

Anotado, **sin plan**. Las del héroe, por lo medido abajo.

# Por qué

**En ABL las nueve juntas sumaban +1 página**, y por eso esto estuvo anotado
como "no rinde". En los otros juegos no: 8, 10 y 22 destrabaron páginas de
Desert Nightmare, Vampires Dawn, El Dorado y Sunset, y se hicieron.

**Por qué las diagonales del héroe no se hicieron**: el paso del héroe es de a
una celda por eje. `try_up` y sus tres hermanas mueven `hero_ptr` —el puntero a
la cuadrícula— una celda o una fila, y miran el permiso de salir y el de
entrar con `step_dx_table` indexada por `hero_dir`, que sólo tiene cuatro
entradas. Una diagonal pide las dos patas del permiso en L —lo que hace
`cell_allowed_diag` para un evento, que no usa nada de esto—, el puntero en
las dos direcciones a la vez, `hero_blocked` sobre la celda de destino y la
regla de a dónde queda mirando, que no es "hacia la diagonal". Es un paso
nuevo del héroe y no cuatro rutinas copiadas. **Lo que no se midió**: cuánto
de eso toca la cámara y las franjas de la ventana de tiles; `begin_step` y el
avance son genéricos en `step_dx` y `step_dy`, así que puede ser menos de lo
que parece. Y no hay con qué comparar: ningún juego que tengamos mide una
diagonal del héroe contra RM2k. Cuesta una tarea propia, y rinde unas cien
páginas en dos juegos de siete.
