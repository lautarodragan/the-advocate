---
name: "Los eventos decorativos, al fondo"
description: "Eventos que son sólo estética —una página, sin comandos, que nadie mueve— se hornean en el fondo como tiles animados, mezclados contra su celda si son translúcidos, en vez de gastar sprites"
type: feature
agents: [Calandria]
assignee: Calandria
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
