---
name: "La escena del ascensor"
description: "Un caso propio en la tanda para la escena del ascensor del mapa 2"
---

# Qué

Darle **caso propio** en la tanda a la escena del ascensor del mapa 2.

# Status

Anotado y **gratis**: lo que lo bloqueaba se destrabó solo el 2026-09-16. Vivía
adentro de "Los cuadros que el lazo pierde en sus picos", en `ESTADO.md`, que es
el límite que lo tuvo afuera y que sigue ahí.

Vale la pena probarlo **antes que cualquier otra cosa de esta carpeta**,
justamente porque no cuesta nada: es escribir el caso y mirar si la golden sale.

# Por qué

La referencia en Python no modelaba los cuadros que el lazo pierde en sus picos,
así que la ROM iba N cuadros atrás y sólo se la podía comparar con la pantalla
quieta. Eso era lo único que le faltaba a esta escena para tener caso propio.

**Contra una golden no hay N**: la captura tiene los cuadros perdidos adentro.

Lo que sigue siendo cierto del límite, y por eso se quedó en `ESTADO.md`: los
picos existen, y la salida no es un desfase a mano —un número que se ajusta
hasta que dé verde— sino aflojarlos, o leer `cuadros_perdidos`, que ya viaja en
la salida de cada captura.
