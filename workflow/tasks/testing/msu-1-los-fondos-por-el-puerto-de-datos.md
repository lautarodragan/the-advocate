---
name: "MSU-1: los fondos por el puerto de datos"
description: "Piloto: los fondos de batalla también en el .msu, y con MSU-1 la ROM los lee de ahí; sin él, de sí misma"
type: feature
---

Idea de taro, el 2026-09-25: usar el **puerto de datos** del MSU-1 para
guardar cosas fuera de la ROM, empezando por los fondos de batalla. Es un
piloto: **probar el mecanismo, no ahorrar espacio todavía**. La condición que
no se negocia es que sin MSU-1 el juego ande igual, porque taro juega en
Mednafen.

## Qué anduvo

El conversor escribe en el `.msu` de cada cartucho los mismos fondos que lleva
la ROM, con una firma del contenido adelante —formato y mecanismo en
`docs/port/msu-datos.md`, referencia en `tools/port/msu_datos.py`—. Al
empezar una pelea con fondo, la ROM mira si hay MSU-1 y si el `.msu` tiene su
firma; si sí, trae los 32 KB por DMA desde `$2001` a los dos búferes de la
WRAM y los colores a la CGRAM, y deja `ESC_MSU` en 1. Si no —sin MSU-1, con
otro `.msu`, vacío, o si el MSU-1 no termina de buscar—, todo sale de la ROM
como antes.

## En qué está verificado

* **Sin MSU-1**: la tanda entera. En el piloto, sin ninguna golden
  cambiada; con el respaldo liviano, con las diez de batalla cambiadas.
* **Con MSU-1, en snes9x y en bsnes**: `pruebas/abl/test_msu_datos.py`. La
  pelea de Sector 27, cada camino contra su golden y el fondo limpio de la
  WRAM contra los bytes del conversor; un control con los tiles del `.msu`
  cambiados se ve distinto —que es lo que prueba que la imagen salió del
  `.msu`—, y un `.msu` de otro build o vacío cae a la ROM.
* **mesen-s**: los mismos tres casos, a mano, con el mismo resultado —en el
  piloto; con el respaldo liviano no se volvió a mirar—. No va
  en la tanda por el arrastre de estado entre consolas del mismo proceso que
  documenta `test_cores.py`.
* **No verificado: el FX Pak Pro.** Es lo que falta que taro pruebe: con
  `abl.sfc`, `abl.msu` y las pistas en la misma carpeta, entrar a una pelea
  con fondo —la del droide, o un encuentro al azar en Sector 27 o 30— y ver
  que el fondo es el de siempre. Con el respaldo liviano es más fácil: con
  MSU-1 tiene que verse el de calidad, y en Mednafen el de 16 colores. Si el
  fondo sale bien pero la entrada tarda más que en un emulador, es la
  búsqueda en la SD.
* **La espera del bit de datos ocupados: en Mednafen, a mano.** Es el único
  emulador que lo prende —400.000 ciclos maestros por búsqueda, ver
  `docs/snes/emulators.md`—, y el 2026-09-26 la pelea del droide leyó el
  fondo del `.msu` ahí, jugando desde el título. Lo que no corre nadie es
  el corte por tope.
* **No lo cubre la firma**: un `.msu` con la cabecera intacta y los datos
  dañados. La ROM no hashea los fondos al empezar cada pelea.

## Cuánto tarda

En snes9x, bsnes y mesen-s buscar es instantáneo, y el DMA va a 8 ciclos
maestros por byte venga de donde venga. En Mednafen cada una de las cuatro
búsquedas por pelea —la firma, los tiles dos veces (uno por búfer) y los
colores— cuesta uno o dos cuadros: unos siete en total, medido. En el FX Pak
no están medidas. Ver "Cuánto tarda" en `docs/port/msu-datos.md`.

## Cómo viaja a taro

`just entregar` copia el `abl.msu` al build, al lado del `abl.sfc`, y
**siempre** a `/shared/msu/`, porque es del build y no de las pistas. Con el
`abl.sfc` de otro build no se rompe nada: la ROM no encuentra su firma y lee
los fondos de sí misma.

## El respaldo liviano (en su rama, sin mergear)

Pedido de taro el mismo día: *"quiero poder confirmar que está efectivamente
cargando por MSU, pudiendo comparar y ver que carga otro fondo en
Mednafen"*. Con los dos fondos iguales no había cómo.

* **Qué es**: la ROM lleva cada fondo en **4bpp y 16 colores**; el `.msu`
  sigue con el de 8bpp y 96, byte por byte el de antes —la firma no cambió—.
  La capa sigue siendo de 8bpp: `esc_llenar` agranda el respaldo al copiarlo
  a la WRAM, dos DMA por tile (el tile por el canal 0, los planos 4 a 7 fijos
  por el 7). El porqué de esta forma y no otra, en "El respaldo liviano" de
  `tools/port/escena.py`.
* **Cuánto ahorra**: lo imprime el conversor en `conversor.log` ("fondo de
  batalla …: en la ROM … B, en el .msu … B"). Es propiedad del formato:
  16.384 B de tiles y 160 de colores por fondo, menos 32 B de patrón para
  todos.
* **Cuánto tarda**: el respaldo un cuadro más que el `.msu` en la pelea del
  droide (`ESC_CUADROS`, en snes9x y en bsnes): copiar de a un tile rearma
  los registros 512 veces por búfer.
* **Cambia lo que ve la tanda**: las diez goldens de batalla, sólo en la
  escena. Vieja y nueva lado a lado en
  `/shared/goldens/2026-09-25-fondo-liviano/`. **taro decide** si se queda.
* **Build para mirar**: `/shared/builds/2026-09-25-demo-fondo-liviano/`, con
  su `LEEME.txt` y dos capturas de la misma pelea por los dos caminos.
* **Lo que se ve raro**: en Sector 27 el cartel verde se ve **en el liviano y
  no en el de calidad**. No es del respaldo: `titulo.reducir`, que arma los
  96, se queda con los colores más usados y el verde del cartel no está entre
  ellos; `merge_least_visible`, que arma los 16, lo conserva. Cambiar los 96
  de reductor cambia el `.msu` y su firma, y queda para después.
* **No lo corre ninguna prueba**: que una búsqueda del MSU-1 no llegue a
  tiempo a mitad de camino. Con fondos distintos eso dejaría colores de uno y
  tiles del otro, así que `escena_subir` rehace el fondo entero desde la ROM;
  ningún emulador busca con demora.

## El paso siguiente

* **Los demás fondos.** El juego nombra una quincena; en el `.msu` no cuestan
  cartucho, así que el respaldo de los que no están en `FONDOS` puede seguir
  siendo el fondo liso.
* **Medir en el FX Pak** cuánto tarda buscar, antes de mover algo que se lea
  en cada cuadro y no una vez por pelea.
* Si se suman otras cosas al `.msu`, la firma sigue cubriendo todo el archivo:
  cualquier cambio en cualquier entrada invalida el `.msu` entero, que es lo
  simple y lo correcto mientras el `.msu` viaje con el build.

**Lo que dijo taro mirando las goldens lado a lado, el 2026-09-25**: "en el
celular se nota, pero no es tan grave. Sospecho que en la tele de tubo casi no
se va a notar." Falta que lo vea en la consola.

## "En Mednafen y en ares no veo ninguna diferencia" (2026-09-26)

taro jugó la pelea del droide en Mednafen (`snes_faust`) y en ares, con y
sin el `.msu`, y vio lo mismo. La sospecha era la espera: que Mednafen tarda
en buscar y los cores de la tanda no. **No se reprodujo**:

* Mednafen sí tarda —`MSU1_WriteDataSeek` prende el bit 7 por 400.000
  ciclos maestros—, y la espera de la ROM llega: su tope es unas diez veces
  eso.
* Con el build que jugó taro (`d7056b6`) y con `main`, jugando desde el
  título hasta el droide en el Mednafen de acá (1.32.1, el mismo paquete de
  Arch), la pelea sale con `ESC_MSU` en 1 y el fondo del `.msu`: leído del
  estado guardado con F5 y comparado contra las capturas de los dos caminos.
  Sin el `.msu`, `ESC_MSU` en 0 y el liviano.
* ares busca en el acto (`dataBusy` no se prende nunca), así que corre el
  mismo camino que bsnes, que la tanda prueba.

Lo más probable es que **la diferencia no se vea a tamaño de juego**: en la
pared violeta, el de calidad es un degradé con la cara y el liviano la misma
cara posterizada en dos o tres violetas. Lado a lado y agrandado se nota;
jugando, no tanto. Las capturas, en `/shared/capturas/2026-09-26-msu-mednafen/`.

**Lo que tiene que mirar taro**, si quiere confirmarlo sin mirar el fondo:
en Mednafen, Alt+D abre el depurador y Alt+3 su editor de memoria; con la
pelea abierta, el byte `$664A` del espacio `wram` —`$7E664A`— es `ESC_MSU`:
1 si el fondo salió del `.msu`, 0 si salió de la ROM.

**Confirmado por taro el 2026-09-26, en Mednafen con `snes_faust`**: el fondo del `.msu` carga y la diferencia con el de la ROM existe, pero tuvo que sacar capturas para verla: jugando no es obvia, y en la tele de tubo lo será menos. Queda sin probar el FX Pak Pro (el riesgo de la lectura de 32 KB en un solo DMA).
