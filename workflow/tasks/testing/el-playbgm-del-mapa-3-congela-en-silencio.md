---
name: "El PlayBGM del mapa 3 congela en silencio"
description: "Sin MSU-1, al aparecer el mapa 3 el juego queda 86 cuadros congelado y en silencio subiendo TF3_1_awe, y la mitad es volver a subir lo que ya estaba"
type: bug
assignee: taro
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

## Lo hecho, el 2026-09-30 (Cachirla)

**Propuesta 1, hecha.** `package_load_done` suma, en `exit_q`, lo que el
paquete quiere —el tema que suena, el extra, los temas del paquete y sus
efectos; no los de salida, que no tienen por qué entrar— con
`wanted_fits`, y si no entra ni con la ARAM vacía deja `PKG_COMPACT` en 2
y no rearma. Salvo que lo que quedó afuera sea un tema: ahí rearmar sí
sirve, porque pone los temas primero, y se rearma como antes.

Medido con el caso nuevo `paso-al-3` —escape_newyork en el 2, `Teleport`
al 3 y `PlayBGM` de TF3_1_awe, como la página del ascensor—, en
cuadros de hardware con la música callada y la imagen quieta:

    antes (3d83de68)    86
    con la propuesta 1  38

Y la llegada, bajo el fundido, 53 en vez de 55: ahí tampoco se rearma.
Con TF3 sonando quedan diez efectos del paquete en vez de nueve, y
evilrhys, Earth2 y Open1 no se mueven de donde estaban.

**Propuesta 2, no se hizo.** Subir TF3 al lado de escape_newyork sin
callarlo no alcanza sólo con no callar: a la llegada, al lado de escape
ya están evilrhys y los cinco primeros efectos, y TF3 no entra con ellos.
Habría que soltarlos para subir TF3, y ahí se pierden Earth2 y Open1, que
el mapa pide antes del `PlayBGM` de evilrhys —el temblor y la puerta—:
escape (35.793) + TF3 (25.875) + esos dos (3.780) pasan la ARAM de
muestras (63.419). Volver a subirlos con TF3 ya sonando sería una segunda
carga y un segundo congelamiento, con la imagen quieta más tiempo en
total, a cambio de que no haya silencio. Con 38 cuadros la cuenta no da;
si taro oye que el hueco molesta, es por ahí.

**La prueba:** `test_el_paso_del_2_al_3_no_vuelve_a_subir_lo_que_estaba`,
en `rom/pruebas/rpgmaker/test_musica_paquete.py`. Pide que lo que estaba en
la ARAM antes del `PlayBGM` no se mueva y que el silencio no pase de
`TOPE_DEL_PASO_AL_3`, un segundo. Con el runtime de antes da rojo: se
mueven 26 muestras. Para mirar dónde está cada una, `lugares_en_la_aram`
en el arnés.

**La prosa**, en su commit: el docstring de
`test_el_paquete_que_no_entro_con_otro_tema_sonando_se_completa` y el
comentario de `song_ensure`.

**El audio**, para escuchar: `/shared/audio/2026-09-30-mapa-3/`, el paso
antes y después, con el SPC700 solo.

**Lo que se paga, y no se vio en ningún mapa:** sin rearmar, qué efectos
entran en los huecos lo decide el orden en que quedaron, no el de la
lista. En el 3 entran más que antes; en otro paso con un paquete que no
entra podría quedar afuera uno de adelante de la lista que antes entraba,
hasta el próximo `PlayBGM`. `just pruebas` no mira eso fuera del 3.

**Al mergear:** no hay que instalar nada. Cambió `tools/runtime/`, que el
global arma desde el checkout principal, y ningún proyecto de Rust.
Ninguna golden se movió.

**Qué jugar:** sin MSU-1, el ascensor del 2 al 3. Entre que el mapa 3
aparece y suena TF3_1_awe hay un hueco callado con la imagen quieta: tiene
que ser más corto que antes. Y en el 3, que el temblor y la puerta suenen.
