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

**Desde el 2026-09-30 el común 35 corre**: lo que lo trababa eran las
variables que sólo él nombra —las 53 de las invocaciones y de los HP de
Talan—, que no tenían ranura en la partida porque el barrido de variables no
miraba los comunes. Ahora los mira (`variables`, en los índices de
`rm2k-snes-events`), y el común compila en el lugar de su `CallEvent`. Lo
cuida `test_despues_de_la_pelea_lerle_vuelve_al_grupo`, en
`rom/pruebas/rpgmaker/test_sistemas_de_tropa.py`.

Lo que cuesta ahora es espacio: el común entero se copia en cada mapa con
encuentros, porque `CallEvent` compila en el lugar y no hay llamada a un
cuerpo compartido. El día que se lo agregó, eso fue un banco de datos más en
`release`. Si algún día hace falta el lugar, es lo primero que se puede
compartir.
