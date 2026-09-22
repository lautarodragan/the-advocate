---
name: "El desempate de try_pack"
description: "Que el reparto de colores no dependa del orden de hash de CPython"
---

# Qué

Que el reparto de colores de `try_pack` desempate por algo que sea parte de la
entrada, y no por el orden de iteración de una tabla de hash de CPython.

# Status

Anotado y sin empezar. **Es una decisión del asignador**, `tools/port/asignador.py`,
desde el paso 8: `tools/voodoo/` ya no empaqueta, y **no frena enchufar a
Voodoo**, que está enchufado desde el paso 8c —hasta el 2026-09-22 esta tarea
decía lo contrario—. Se arregla cambiando el desempate en Python, o cuando el
asignador pase a Rust, donde el orden de hash de CPython no existe.

# Por qué

`try_pack` reparte los colores recorriendo `sorted(sets, key=-len)` sobre un
`set` de `frozenset`, así que los empates —que son el caso normal— los
desempata el orden de iteración de una tabla de hash, que no es parte de la
entrada. Medido: **156 de 200 barajadas del mismo conjunto dan otro reparto**.

La ROM de hoy sale siempre igual porque los hashes de enteros no varían entre
corridas, así que no es una ROM que cambie sola: es un desempate del que
dependemos sin haberlo elegido, y tiene costo —en una llamada medida obliga a
fusionar dos colores que con un desempate determinista no haría falta
fusionar—.

Lo que se sabe de la alternativa, porque ya existió: el `tools/voodoo/` de antes
del paso 8 desempataba por los colores mismos, y de 32 llamadas dio **25
idénticas, 1 con las mismas paletas en otro orden, 6 distintas y ninguna
peor**. Ese código está en la historia de `tools/voodoo/`, antes de `4953089`.

Lo que cuesta hacerlo: cualquiera de los dos caminos **mueve el tilemap de
algunos mapas**, así que hay goldens que se van a mover y taro las tiene que
rebendecir.
