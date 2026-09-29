# Qué

El evento común 37, `UpdateAG7 Skills`, es **paralelo con el switch 150**: en
RM2k corre en cada cuadro mientras AG7-17 está en el grupo, le saca sus
diecisiete habilidades y le da la de cada pieza que tiene puesta. La ROM no
corre eventos comunes paralelos, y a éste lo corre **en los dos momentos en
que su resultado puede cambiar**:

* al prenderse el switch: el conversor pega el cuerpo detrás del
  `ControlSwitches` que lo prende, como si le siguiera un `CallEvent`;
* al cerrar el menú de pausa, que es donde se cambia el equipo:
  `comunes_del_equipo`, en `tools/runtime/equipo_desde_eventos.s`, desde
  `menu_pantalla`.

Vale para cualquier evento común paralelo, con switch, que no tenga más que
`ChangeSkills` y ramas "tiene puesto tal ítem": `eventos.COMUNES_DEL_EQUIPO`.
En el juego es uno solo.

Lo que queda distinto:

* **En RM2k corre en el cuadro que sigue al switch; acá, en el mismo.** No se
  ve: nada mira las habilidades en el medio.
* **Un `ChangeEquipment` de una página no lo vuelve a correr.** En el juego no
  hay ninguno sobre el actor 18.
* **Apagar el switch no le saca nada**, igual que en RM2k: el evento deja de
  correr y las habilidades quedan como estaban.

# Medido

Lo general —un intérprete más que corra los comunes paralelos en cada cuadro,
como las páginas paralelas de los mapas— se midió el 2026-09-27 contra esto:

* **El lazo por cuadro.** Con casos descartables que corrían el cuerpo del 37
  N veces seguidas en una página, 0, 10, 20 y 30 veces tardaron 63, 64, 66 y
  67 cuadros: **unos 0,13 cuadros por vuelta**. Como paralelo, cerca de un
  octavo de la CPU de cada cuadro, en todos los mapas, desde que AG7 entra al
  grupo.
* **Lo que prendería además.** El 2 (`DisableSaving`) es paralelo **sin
  switch** y apaga el guardado cada vez que el 236 está apagado; el 3
  (`Raining`, switch 94) y el 8 (`EnableSaving`, switch 236) también compilan.
  Hacer lo general cambia `release` mucho más allá de AG7.
* **Esto**: 8 bytes del banco 0 (la llamada desde el menú y el puente a
  `correr_codigo`), 117 del banco 1, ningún byte de RAM, y ningún ciclo por
  cuadro. El cuerpo compilado son 307 bytes en RODATA y otros tantos pegados
  en la página 5 del evento 2 del mapa 57.

Lo cobran los tres casos de AG7 en `rom/pruebas/rpgmaker/test_ag7_y_la_planta.py`:
al entrar sabe la de su arma, cambiarla y cerrar el menú la cambia —comprobado
en rojo sin la llamada desde el menú—, y con el switch apagado cerrar el menú
no toca nada.

# Cómo se ve hoy

Igual que en RM2k: se equipa una pieza, se sale del menú, y en la pelea está
su habilidad.

# Cuándo deja de alcanzar

Un evento común paralelo que mire otra cosa que el equipo —una variable, el
mapa, el tiempo—, o que haga algo más que cambiar habilidades: ése necesita el
intérprete de verdad. O una página que le cambie el equipo al actor que el
evento mira.
