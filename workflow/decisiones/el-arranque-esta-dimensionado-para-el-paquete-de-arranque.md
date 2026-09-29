# Qué

**El arranque está dimensionado para el paquete de audio del mapa de
arranque**, no para la ARAM llena: `BOOT_CUADROS` (en `tools/runtime/ram_lejana.s`)
cubre la carga del mapa, el driver y el directorio por el IPL, y ese
paquete, con margen. **Y el conversor se corta si no entra**: la cuenta es
`snes_music.cuadros_del_arranque`.

Reemplaza a "el arranque está dimensionado para el techo de ARAM", que lo
dejaba en 112 cuadros —1,9 s de mapa congelado al encender— para que llenar
la ARAM no costara nada. taro pidió bajarlo a menos de un segundo el
2026-09-26.

# Por qué

El techo tenía sentido cuando el banco entero subía al arrancar, byte a byte
por el IPL. Desde los paquetes por mapa el IPL sube sólo el driver y el
directorio, y las muestras van por el comando 3 del driver, de a ternas: el
"cargador de cuatro puertos" que la decisión vieja decía que lo compraría de
vuelta ya existía. Lo que se sube al encender es un solo paquete, así que el
arranque se puede medir contra él.

Lo que cuesta: si el paquete del mapa de arranque crece —otro tema en el
mapa 4, un reparto que le dé más a `hzstream`—, el conversor avisa y hay que
subir el número a mano. Y las pruebas lo leen de la tabla de símbolos, así
que moverlo no mueve ninguna golden: se verificó al bajarlo de 112.
