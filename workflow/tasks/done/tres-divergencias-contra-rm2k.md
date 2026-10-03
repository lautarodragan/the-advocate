---
name: "Tres divergencias, contra RM2k"
description: "Verificar con el RPG_RT en Wine tres divergencias que se midieron contra la referencia en Python y no contra RM2k"
type: test
assignee: taro
---

Las marcó Guayabo el 2026-09-29, al clasificar las divergencias por repo
(`testing/decisiones-y-divergencias-por-repo.md`): se midieron contra la
referencia en Python que existía hasta el 2026-09-16, no contra RM2k, así
que no se sabe si la ROM difiere de RM2k.

- `workflow/divergencias/fase-de-los-tiles-animados.md` (lo dice ella misma)
- `workflow/divergencias/cronometro-llegando-a-cero.md` (sus 252 pixeles son
  de `27c828de`, contra la referencia)
- `workflow/divergencias/move-event-tras-teleport-interno.md`

Para cada una: o se confirma contra el RPG_RT con Wine —y la divergencia
dice qué se midió—, o se descarta y se borra, contándolo en el commit.

## Cómo se midió (Caranday, 2026-09-29)

**El original**: el RPG_RT de 2015 con Wine, sobre una copia del juego donde
la página 1 del EV0001 del mapa 4 —el autostart con que arranca la partida—
se reemplaza por la página del caso: la de `rom/pruebas/casos/timer-cero.json`
tal cual, o un `Teleport` al lugar que se quiere mirar. Se elige "Begin the
Story" y se graba el escritorio de Wine con `ffmpeg -f x11grab -framerate 60`,
sin pérdida; después se lee cuadro por cuadro a 320x240. **Wine no deja contar
cuadros absolutos** —la grabación va a reloj de pared y a veces duplica o
pierde uno—, así que todo se mide **entre marcas del mismo video**: cuándo
aparece algo, cuándo empieza a oscurecer un fundido, cuándo se mueve la
cámara. Cada número de abajo salió igual en dos grabaciones por lo menos.

**La ROM**: `release`, con `tanda.partida` y una captura por tick, y las mismas
marcas.

**easyrpg** coincide en lo que se miró: el cronómetro se apaga cuando le quedan
menos de sesenta cuadros (`Game_Party::UpdateTimers`), y la animación del
ChipSet sale de un contador que no avanza durante las transiciones
(`Player::Update(false)`).

## Lo que dio

**El cronómetro — se borra.** Con la página de `timer-cero`, medido desde el
cuadro en que aparece el cronómetro, en los dos: el dos puntos se apaga en el
+30, los dígitos se ven hasta el +59 y en el +60 el cronómetro ya no está.
**Nunca muestra 00:00, ni en uno ni en el otro.** Los 252 pixeles del cuadro 60
eran la referencia equivocándose. Lo único distinto es el tinte de después del
`Wait 2`: +12 en el original, +13 en la ROM; va a la tarea nueva de abajo.

**El `MoveEvent` tras el teletransporte interno — se borra.** En los dos, el
héroe da el primer paso dos cuadros después de que termina el fundido, en las
cuatro vueltas de la escena del mapa 16, y en la cuarta —la que el archivo
señalaba— camina los mismos 88 cuadros y la cámara corre los mismos 176
pixeles que en las otras. No hay nada que empiece cuatro ticks antes ni
pantalla corrida ocho pixeles. Lo que sí difiere es el largo de cada vuelta:
161 ticks en la ROM y 158 en el original. Es una tarea nueva:
`todo/el-teletransporte-tarda-tres-cuadros-de-mas.md`.

**La fase de los tiles animados — se borra.** Los diez pixeles son el agua del
ChipSet del mapa 6, que se ve después de que la ruta de `grafico-heroe` baja la
cámara: hoy cambia de paso en el tick 47 de ese caso, igual que el 2026-09-12.
Contra el original se midió la regla, no la fase absoluta —ésa depende de todo
lo que se jugó desde "Begin the Story", y el arranque de la ROM no dura lo
mismo; lo dice `tools/rpgmaker/rm2k.py`—:

* **cada 24 cuadros**, en los dos;
* **quieta durante el fundido del teletransporte**, y exactamente durante él:
  en el original el agua cambia 24 cuadros después del último del fundido, con
  el último paso de antes en el cuadro previo al primero del fundido. En la
  ROM, con un `Teleport` de verdad (los de la escena del mapa 16),
  `vueltas_congeladas` sube durante los mismos 69 ticks que dura el fundido que
  se ve.

La diferencia de un cuadro que medía el archivo era entre dos relojes —el de
la referencia contaba los ticks del fundido y el de la ROM no— y dejó de
existir el 2026-09-18 (`4b2c6fe5`), cuando la ROM pasó a congelar la animación
como easyrpg.

Dos cosas vistas de paso, que no cambian lo de arriba:

* `Partida.ir_al_mapa` congela **un tick más** que el fundido que se ve (70
  contra 69): la animación sale de ahí un cuadro atrasada. Es del arnés, que
  pide el fundido desde afuera; con el `Teleport` de una página no pasa.
* En el original, abrir el menú y cerrarlo también deja el agua quieta: en un
  menú que estuvo abierto 103 cuadros contando las dos transiciones, el agua
  perdió 100. La ROM tampoco cuenta `vueltas` en el menú; no se midió cuadro
  por cuadro.

## Dónde quedaron las capturas

`/shared/capturas/2026-09-29-divergencias/`, el original y la ROM con el
mismo nombre y el número relativo a la marca que se usó:

* `cronometro-{rpgrt,rom}-*`: antes, al aparecer, el tinte, el dos puntos, el
  último cuadro con dígitos y el primero sin cronómetro. El número es el
  cuadro desde la llegada al mapa 6.
* `mapa16-{rpgrt,rom}-tramo3-*` y `tramo4-*`: el final de la tercera vuelta,
  y la cuarta de punta a punta.
* `agua-{rpgrt,rom}-*`: el último paso del agua antes del fundido, el primero
  y el último cuadro del fundido, y el paso de después. Los de la ROM salen de
  `ir_al_mapa`, así que llevan el tick de más del arnés.

En las de la ROM del mapa 16 el héroe no se ve: la partida sale de `en-5` y
llega al 16 por `ir_al_mapa`, sin el grupo con el que el juego entra ahí. La
cámara lo sigue igual, que es lo que se midió.

Lo que no cubre `just pruebas`: nada de esto. Son mediciones con scripts
descartables; no se tocó código ni goldens, sólo dos comentarios de prueba
que citaban los archivos borrados.
