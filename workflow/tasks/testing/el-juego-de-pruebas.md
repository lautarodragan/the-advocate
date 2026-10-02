---
name: "Plan: un juego de RM2k para pruebas"
description: "Un juego sintético, sin assets con derechos, con el que las pruebas de lo que hace RM2k vivan con las herramientas y el runtime y no con ABL"
type: research
assignee: taro
---

De taro, el 2026-10-02: "empezar el proyecto de tener un juego de rpg maker
2000 para pruebas". Hoy las pruebas de "lo que hace RM2k"
(`rom/pruebas/rpgmaker/`) viven del lado de ABL sólo porque necesitan un
juego. Los crates ya tienen juegos chicos en `tests/game/`. Es un plan, no
código: de él salen las tareas.

# La dirección de taro (2026-10-02)

"Cuando terminen estos, me gustaría proceder con el juego de pruebas, si
Leñatero lo encuentra factible":

1. **Primero, todo lo de ABL en un solo lugar, fuera de este repo**: un repo
   propio, con su historia.
2. **Después, pruebas en este repo 100% originales**, sin referencias a ABL
   ni assets con copyright.
3. **Los assets**: el reemplazo del RTP de EasyRPG
   (https://easyrpg.org/rtp-replacement/), otros assets libres —taro tiene
   sitios guardados—, o fabricados por ahora; efectos de sonido que taro
   puede hacer en FL Studio; y MIDIs de obras de dominio público (Bach,
   Beethoven, Mozart), con la licencia del archivo verificada.

## Mientras se trabaja (Leñatero, 2026-10-02)

* La tanda de base: `just pruebas --junitxml=…` da 999 en 86,5 s, 643
  CPU-s. Sin las del motor (`--ignore` de cada archivo M1 y M2), 394 en
  73 s y 351 CPU-s.
* El juego sintético se escribió como volcado exacto de Ditto (~8 KB de
  JSON y texto, con un generador de unas 120 líneas) y armó un cartucho que
  arranca y camina, con el RTP de EasyRPG y FluidR3. Para llegar hubo que
  esquivar seis supuestos de ABL en las herramientas: van al estudio.
* taro, por el coordinador, el mismo día: la primera fase es sacar ABL a un
  repo propio; después, pruebas 100% originales. El estudio lo incluye.

## Resultado

El estudio es `docs/research/2026-10-02-el-juego-de-pruebas.md`. Lo corto:

* De los 999 casos, 605 en 80 archivos son del motor y se pueden escribir
  contra un juego sintético; 208 en 20 corren en los dos juegos; 186 en 38
  son de ABL.
* El juego se escribe como volcado exacto de Ditto, sin editor ni `.lmu`,
  con los assets del reemplazo del RTP de EasyRPG (CC0 y CC-BY 4.0) y
  FluidR3 (MIT); los fondos de pelea y los enemigos se fabrican.
* Cinco fases: ABL a su repo con `git filter-repo`; el juego mínimo con los
  siete supuestos de ABL arreglados y el arnés partido; el resto de M1; M2
  con assets; M3 en los dos. Las tareas que salen están al final del
  estudio, sin crear: las decide taro.
* ABL baja de 643 a 351 CPU-s, pero de 86,5 a 73 s de reloj.

**Al mergear no hay que instalar nada**: son un documento y esta tarea.
`just pruebas` dio 999 en verde sobre este árbol, y `just -f tools/justfile
test` 36.
