---
name: "Los eventos decorativos, al fondo"
description: "Eventos que son sólo estética —una página, sin comandos, que nadie mueve— se hornean en el fondo como tiles animados, mezclados contra su celda si son translúcidos, en vez de gastar sprites"
type: feature
agents: [Calandria]
assignee: taro
---

Medido por Hornero el 2026-10-06 en el mapa 95 de Vampires Dawn (Weg):
209 eventos `water1`, translúcidos, animados, sin comandos y de una sola
página, pintan un río. Hoy `wally` mezcla cada translúcido contra su celda
como un gráfico propio: 206 gráficos y 4096 tiles de sprite, el banco
entero. Sin esos eventos, o con el agua opaca, son 384; pero opaca son 247
eventos para un cache de 18 ranuras, con hasta 30 en pantalla.

taro, el 2026-10-06: "sospecho que optimizaciones generales para casos en
los que los eventos se usan puramente por estética, como una nueva capa de
mapa, podría aprovecharse en muchos mapas y muchos juegos". Y: "No quiero
que sobre-optimicemos un edge case". Sus capturas, de RM2k en ejecución:
`Map0095-runtime*.png` del juego; EV0016 corre algunos eventos de agua un
tile al arrancar, porque en el editor no pueden compartir celda.

# Hecho (Calandria, 2026-10-06)

`[graphics] decorative_events = true` en el `rm2k-snes.toml`, **apagada por
omision**: ABL tiene 502 candidatos en 328 mapas, asi que prenderla le
cambia la ROM, y el encargo era que `abl.sfc` saliera identico (sale
`8bb36b99312730ef`, armado con las herramientas del cambio). Se prende en los
juegos que la usen. El conversor se lo pasa a Wally como `decorative` y,
con ella, `test_commands`: lo que nombran las paginas de prueba.

Un evento es decorativo si tiene una sola pagina, sin comandos, sin
condiciones, con CharSet, sin tipo de movimiento ni ruta, no es de giro
(animacion 5), esta en la capa de abajo o en la del heroe, y nada lo
nombra: ni las paginas del mapa, ni los comunes, ni las de prueba
(`MoveEvent`, `SetEventLocation`, `SwapEventLocations`, `FlashSprite`,
`ShowBattleAnimation`, la condicion por direccion). En la capa del heroe,
ademas, su dibujo tiene que quedar dentro de la celda: si se sale, el heroe
parado en la celda de abajo caminaria por encima de el. Codigo en
`tools/rm2k-snes/wally/src/decor.rs`.

* Se pinta en la capa de abajo, en cada dibujo de su animacion; uno que
  anima en el lugar va con la **familia del agua**, que recorre el mismo
  ciclo 0, 1, 2, 1 que las columnas de un personaje. Translucido se mezcla
  con lo que tiene debajo; dos en una celda se mezclan en orden.
* **Deja de ser un evento**: sin fila, sin ranura, sin pagina en la tabla
  (`maps::pages` salta sus registros; el indice de los demas no se corre,
  como ya pasa con los eventos que se dejan afuera). Sus pixeles no pasan
  por el reparto de paletas de sprites.
* **El bloqueo** de uno en la capa del heroe pasa a la grilla de
  pasabilidad, en su celda.
* Si el fondo no entra —la paleta—, la ruta es: todo mezclado; los
  translucidos tramados (`five_of_eight`); por CharSet, el mas numeroso
  primero; y si no, siguen siendo objetos. Lo que entra es lo que le cuesta
  al suelo hasta `GROUND_LOST_MAX` pixeles de sus colores, no uno solo.

Medido con `wally map` sobre el request de Weg (mapa 95), tiles de sprite /
tiles de fondo / eventos que quedan como objetos: antes 4096 / 327 / 247;
con la perilla, 960 / 394 / 59 —el agua trameada—; con `water1` en
`[graphics] opaque`, 384 / 312 / 59. Mezclado contra su celda no entra: le
cuesta 1557 px al suelo, y el tope es 1024. Uruya (165): sus 8 decorativos
no entran (paleta llena) y todo queda igual; Shannar (15): ninguno.
Candidatos por juego, sin mirar el dibujo ni la capa de arriba:
book-of-three 87, desert-nightmare 2887, dooms2 39, el-dorado 26,
frozen-world 117, sunset-over-imdahl 209, vampires-dawn 5483, ABL 502.

Divergencias en `workflow/divergencias/los-eventos-decorativos-horneados.md`
—el ritmo y la fase de la animacion—. Capturas en
`/shared/capturas/2026-10-06-decorativos/`.

**Lo que no se probo:** ninguna ROM con la perilla puesta —la tanda de ABL
no la prende—; que en la ROM el agua animada del fondo se mueva y que el
heroe no cruce el rio es lo que hay que jugar en Vampires Dawn con
`decorative_events = true`. Lo cubre solo `wally/tests/decorative.rs` —la
pasabilidad de la celda, la corrida del agua, los indices— y el conversor
no tiene prueba de que `pages` salte los decorativos.

**Al mergear, reinstalar:** `wally` y `convert`.
