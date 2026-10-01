---
name: "La velocidad del héroe con L y R"
description: "L baja y R sube la velocidad de movimiento del héroe"
type: feature
assignee: Biguá
---

De taro, el 2026-09-30: "poder incrementar o disminuir la velocidad del
héroe con los botones R y L". No es algo de RM2k: es un agregado del port,
y va anotado en `divergencias/`.

## Cómo estaba

El héroe camina a `FAR_HERO_SPEED` (de 1 a 6, 4 al arrancar): lo suben y bajan
las órdenes 28 y 29 de una ruta, **queda puesta** —RM2k restaura la
frecuencia al terminar la ruta, no la velocidad— y viaja en la partida. Se lee
en cada cuadro del paso, por `hero_anim_frames`, que de paso da cuánto dura
cada cuadro de la caminata.

## Lo decidido

Todo está en `workflow/divergencias/la-velocidad-del-heroe-con-l-y-r.md` y
comentado en `tools/runtime/hero_speed_keys.s`. En corto:

* **un agregado encima de la del juego**, no la del juego: L y R mueven
  `FAR_SPEED_BONUS` y el héroe camina a la suma, con topes 1 y 6. Así la
  velocidad del juego, que es estado y viaja en la partida, no se toca nunca;
* **persiste al cambiar de mapa, no se guarda**; lo borra el reset;
* **una ruta sobre el héroe camina a la del juego** mientras dura, su último
  paso incluido, y después vuelve el agregado. Para eso `route_step` se marca
  antes de intentar el paso de la ruta y no después (`hero_route.s`):
  `begin_step` ya avanza el primer cuadro, y sin esto el primer cuadro del
  último paso salía a la velocidad de L y R —lo encontró la prueba: 5 cuadros
  en vez de 8—;
* **sólo con el héroe libre**: sin ruta, mensaje, página adelante ni eventos
  esperando. Menú, pelea, tienda y fundidos tienen su lazo o congelan el
  principal;
* **se apaga con `--no-speed-keys`** en los `flags` del cartucho
  (`HERO_SPEED_KEYS` en `mapdata.inc`). Salió barato porque los cartuchos ya
  pasan flags al conversor: no hizo falta tocar Rust. `test-special` lo lleva,
  para que el camino apagado tenga prueba.

## La RAM lejana

`FAR_SPEED_BONUS = $25F0` y `FAR_SPEED_KEYS = $25F1`, en el hueco entre el
final de `FAR_PAIR_LIST` ($2580) y `FAR_ACCESS` ($25FC). **Nadie me las
repartió**: las elegí lejos de "la siguiente libre" ($25FB) a propósito.
Al mergear, mirar que ninguna otra rama haya tomado esas dos.

## La prueba

`rom/pruebas/rpgmaker/test_velocidad_con_l_y_r.py`: cuántos cuadros tarda una
celda con el pad. Sin el cambio, cinco de las siete en rojo —R una vez daba 8
cuadros en vez de 4, y las que leen `FAR_SPEED_BONUS` no encontraban el
símbolo—; la que pasaba es la de caminar sin tocar nada, que es la base.

## Espacio

El banco 0 de `release` pasó de 182 B libres a 173 B (+9: dos `jsl` en el
arranque y el lazo, y un `jsr` que pasó a `jsl`); el banco 1, de 4.679 B a
4.515 B.

## Verificación

`just pruebas`: 908 en verde (900 de la base, 1 del mosaico de la entrada y
las 7 de ésta); `just -f tools/justfile test`: 46. Ninguna golden se movió.
`NO_CACHE=1 just cartuchos` sale byte por byte igual que con caché (lo único
del conversor que cambió es una constante más en `mapdata.inc`).
