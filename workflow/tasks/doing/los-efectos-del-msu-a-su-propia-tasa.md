---
name: "Los efectos del .msu, cada uno a su tasa y sólo los que conviven"
description: "Con MSU-1 todos los efectos de un paquete van a una sola tasa, la que entra con todos juntos en la ARAM: uno largo baja a los demás"
type: feature
assignee: Zorzal
---

De taro, el 2026-09-28, al meter el `Thunder9` del despegue en la pelea: con
MSU-1, los efectos de calidad de la pelea bajaron de 14000 a 12000 Hz, todos,
por un solo trueno de dos segundos. No urge, porque 12000 Hz con MSU-1 sigue
sonando bien.

# Por qué pasa

`tools/audio/efectos_msu.py` elige **una tasa por paquete**: la más alta de
`TASAS` a la que entran **todos** los efectos del paquete, enteros, en lo que
la música deja libre de la ARAM. La ROM los sube todos al cargar el paquete
(`se_msu_preparar`, en `rom/src/efectos_con_msu.s`). El `.msu` no tiene tope:
el límite son los 64 KB de ARAM. La tasa única es una elección, no un límite
de la consola: una sola versión por tasa sirve a varios paquetes y el caché del
BRR la codifica una vez.

# Dos ideas, de menos a más

1. **Una tasa por efecto dentro del paquete.** El que más pesa baja primero, y
   un ruido grave como el trueno pierde poco a menos tasa. Es del conversor;
   hay que mirar si `se_msu_preparar` supone una tasa común en algún lado.
2. **Que en la ARAM esté sólo lo que puede sonar junto.** taro: "no tiene
   sentido bajarle la calidad a los efectos asumiendo que todos podrían sonar
   a la vez". El problema hoy no es cuántos suenan a la vez, sino que todos
   **tienen que estar cargados** a la vez, porque se suben al entrar al paquete.
   Con MSU-1 la ROM podría subir un efecto recién cuando se pide, o por grupo:
   un análisis estático de las páginas —qué `PlaySound` pueden pasar en la
   misma escena, en la misma pelea, en el mismo tramo de una página— diría qué
   grupos tienen que convivir, y cada grupo elegiría su tasa. Hay que medir
   cuánto tarda subir un efecto por el puerto de datos, porque subirlo al
   pedirlo puede atrasar el sonido; y qué pasa con los efectos del sistema
   (cursor, menú), que pueden sonar en cualquier momento.

Medir primero, con `Banco` y par por par, cuánto sube cada efecto en cada
paquete de `release` con cada idea.
