---
name: "Al mapa 3 le puede faltar un efecto"
description: "Hay que investigarlo: la cuenta dice que su paquete de audio no entra entrando desde el 2"
---

# Qué

**Hay que investigarlo.** Puede ser que al entrar al mapa 3, el Emitter Room,
desde el 2, su paquete de audio no entre entero en la ARAM y se le caiga el
último efecto.

# De dónde sale

De la investigación de `efectos-de-sonido-sin-recortes.md`, el 2026-09-24.
**Es una cuenta, no algo medido en la ROM**: un sub-agente sumó los tamaños del
`musicdata.inc` de `abl`.

* el paquete del mapa 3, música más efectos, era de los dos más pesados del
  juego;
* durante el fundido del salto 2→3 sigue fija en la ARAM la muestra del tema
  que venía sonando, `TF3_1_awe`;
* sumados, pasaban el espacio que hay para muestras por unos 2,5 KB.

Los números concretos se vuelven a medir: dependen de qué temas y efectos entran
en cada paquete, y eso cambia.

# Qué averiguar

1. Si pasa de verdad: entrar al 3 desde el 2 en una ROM y mirar qué muestras
   quedaron cargadas y cuál falta. O leer lo que decide el cargador de paquetes
   cuando no entra todo.
2. Si pasa, qué efecto es y si se oye: puede ser uno que el mapa casi no usa.
3. Qué hace hoy el conversor o la ROM cuando no entra: si lo avisa, lo recorta
   callado, o lo decide en tiempo de carga.

Toca la misma restricción que `efectos-de-sonido-sin-recortes.md`: **todos los
mapas tienen que tener todos sus efectos**.
