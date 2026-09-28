# Qué

Cuando un `CallEvent` llama a un evento que no compila, **la llamada se
saltea**. Es lo que el port viene haciendo, y en la escena del Tram Officer se
midió lo que eso cuesta cuando la página que se saltea hace algo.

# Medido

El 2026-09-12, verificando `tram` en rojo: con `CallEvent` sin hacer **de los
dos lados** —que es como estuvo hasta ese día— el **cuadro 620** de esa escena
daba **34,64%** de pixeles distintos entre la ROM y la referencia. Con la
llamada hecha daba cero.

El sospechoso es el cronómetro, que esa rama arranca. No se investigó.

# Cómo se ve hoy

La página que lo destapaba ya no pasa por ahí —`CallEvent` se compila en línea
desde el 2026-09-12— pero **el camino sigue existiendo** para las **216
llamadas que se siguen salteando**, casi todas a eventos comunes que se cortan
en `ControlVars` y en los menús propios del original.

# La automática que sólo llama

Desde el 2026-09-28 una página automática o paralela que **compila a nada**
—todo lo suyo eran llamadas que se saltearon— no se lleva, igual que una
vacía: correrla era un lazo sin fin que dejaba al héroe sin moverse. Ver
`paginas_del_mapa` en `tools/port/eventos.py`.

Es el `AfterBattleMint` de los mapas con encuentros —del 20 al 255—: con
el switch 498 llama al común 35, `ResetAfterBattles`, y el común es el que
apaga el 498. Lo prende la página de turno 0 que trae cada tropa, que corre
desde que la pelea sabe mirar el turno
(`tasks/*/eventos-de-tropa-de-release.md`).

**Lo que cuesta**: el común 35 no corre, y el 498 queda prendido para
siempre. En RM2k cura a los actores 36 a 53 y los saca del grupo —las
invocaciones de los sistemas, que `release` no tiene—, y le vuelve a dar a AG7
las habilidades de sus piezas, que el port ya hace al cerrar el menú (ver
`los-comunes-del-equipo-corren-al-cerrar-el-menu.md`). No compila por un
`ControlVars` con los datos de un actor, `ChangeEquipment` para equipar y
`ChangeSP`.
