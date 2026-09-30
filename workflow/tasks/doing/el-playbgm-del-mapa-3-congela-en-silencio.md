---
name: "El PlayBGM del mapa 3 congela en silencio"
description: "Sin MSU-1, al aparecer el mapa 3 el juego queda 86 cuadros congelado y en silencio subiendo TF3_1_awe, y la mitad es volver a subir lo que ya estaba"
type: bug
assignee: Cachirla
---

Medido el 2026-09-26 al verificar `done/al-mapa-3-le-falta-un-efecto.md`:
sin MSU-1, apenas aparece el mapa 3 (después del fundido) el `PlayBGM
TF3_1_awe` congela **86 cuadros (1,4 s) con la imagen quieta y en silencio**.
TF3 no está en el paquete del 3 y hay que subirlo, pero de los 61.614 B que
se suben, **25.623 ya estaban en la ARAM** (evilrhys y los 5 primeros
efectos): `compactar` rearma todo desde cero cuando el paquete quedó
incompleto, y rearmar gana a lo sumo un efecto que no se usa hasta después.
Con MSU-1 no pasa.

Propuestas del agente, sin implementar, sin bajarle calidad a nada:
1. **No compactar cuando lo que se quiere igual no entra en la ARAM**
   (sumar los tamaños de las muestras marcadas antes de rearmar): ~36
   cuadros menos, el congelamiento bajaría a ~50, lo que tarda TF3 solo.
2. **Subir TF3 al lado de escape_newyork sin callarlo** (entran juntos:
   61.668 de 63.419 B): seguiría congelado pero sin el silencio. Toca
   `tema_asegurar`.

De paso: el docstring de `test_el_paquete_que_no_entro_con_otro_tema_sonando_se_completa`
y el comentario de `tema_asegurar` dicen que el paso real del 2 al 3 se hace
"con el tema del 2 sonando"; no es así (en el 2 suena escape_newyork, que
viene del 1). El caso `paquete-incompleto` prende TF3 a mano y ejercita el
mismo mecanismo: corregir la prosa.

## Tomada el 2026-09-30

Decidido por Hornero: se hace la propuesta 1 —no rearmar la ARAM cuando lo
que se quiere igual no entra— y, si el tiempo medido lo justifica, la 2 —no
callar el tema que suena mientras sube el nuevo—. Sin bajarle calidad a
nada. De paso, la prosa que dice mal cómo se llega del 2 al 3.
