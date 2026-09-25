---
name: "Las variables globales chocan"
description: "Dos ramas que agregan una variable al final de pagina_cero.s, ram_baja.s o ram_lejana.s chocan siempre"
type: refactor
---

El corte de `main.s` repartió el código por subsistema, pero la memoria sigue
declarada en tres archivos globales: `rom/src/pagina_cero.s`, `ram_baja.s` y
`ram_lejana.s`. Dos ramas que suman una variable cada una la agregan al
final del mismo archivo, y ahí chocan aunque trabajen en subsistemas que no
tienen nada que ver. Visto por el crítico del corte, el 2026-09-25.

A investigar antes de decidir:

* si cada subsistema puede declarar sus variables en su propio archivo con
  `.segment "BSS"` / `"ZEROPAGE"` y volver al suyo —el orden en la RAM cambia,
  y eso cambia la ROM y los `.sym`: medir qué pruebas lo notan—;
* qué variables tienen que quedar juntas o en un orden fijo (las que se
  borran en bloque, las que se guardan en la partida —`partida_tabla`—, las
  que la tabla de símbolos exporta a las pruebas por nombre);
* si alcanza con algo más barato, como dejar líneas de relleno por
  subsistema o un orden alfabético que reparta los agregados.

Y la RAM lejana tiene una trampa propia, que `AGENTS.md` nombra en
"Sub-agentes": sus direcciones se eligen "el siguiente libre", así que dos
ramas pueden elegir la misma sin que git lo vea. Lo que se decida acá debería
cerrar también eso.
