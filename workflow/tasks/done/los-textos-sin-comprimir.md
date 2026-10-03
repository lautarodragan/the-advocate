---
name: "Los textos sin comprimir"
description: "119 KB de textos a un byte por letra: mensajes repetidos, nombres y DTE los bajarían uno o dos bancos, sin perder el acceso directo a cada cuadro"
type: feature
assignee: taro
---

No urge: se hace cuando apriete el espacio, probablemente con el capítulo
siguiente al del mundo. Lo decidió taro el 2026-09-27.

# Lo medido

Con un script descartable sobre el bloque `mensajes` de `release` en
3c16a178 (cómo está hoy lo imprime `just espacio`):

    como hoy, un byte por letra     119.082 B
    LZ2, en dos flujos de < 64 KB    63.405 B   (47 % menos)
    zlib -9, de referencia           46.550 B   (61 % menos)

Usa 88 valores de byte de 256.

# Por qué no LZ2

La ROM abre cada cuadro en su desplazamiento exacto (`msg_empezar`). Con LZ2
habría que descomprimir desde el principio de un bloque para llegar a una
frase: tiempo o RAM, y cuanto más chicos los bloques, menos comprime.

# Lo que se propone, en este orden

1. **Mensajes repetidos**: un cuadro idéntico a otro apunta al mismo lugar.
   Hay casos obvios (el de Sewell sale tres veces seguidas al principio del
   bloque). Gratis para la ROM.
2. **Lo que se repite adentro de los cuadros**: los nombres de los personajes
   (TALAN, KERSH…, en cada cabecera) y otras frases frecuentes. taro lo
   señaló. Un código de diccionario para palabras enteras, o que DTE los
   absorba.
3. **DTE** (pares de letras en un byte): los 168 valores libres para los
   pares más comunes. Conserva el acceso directo; el decodificador es una
   tabla y unas pocas instrucciones en la rutina que dibuja el texto. Lo
   típico es 30–40 %; **no está medido**.

Medir cada paso antes de implementar, y que `just espacio` muestre el
resultado.

# Lo hecho (Guayacán, 2026-10-01)

**DTE, la idea 3**, en `ba0b2952`. Los valores de byte 95 a 255 —los que la
fuente no usa: tiene 95 glifos, ASCII menos 32— son pares de letras, de un
solo nivel. El compilador de eventos elige los 161 pares más frecuentes
sobre los cuadros que entran en el cartucho y emite la tabla
(`message_pairs`, `MESSAGE_PAIR_FIRST`); el porqué de cada pieza está en
`Pairs` (`messages.rs`), en `compile` (`lib.rs`) y en `msg_letter`.

* Un par no sale de un renglón, así que no parte nada: los escapes van en
  la cabecera y el largo en su byte. El largo sigue contando **letras**.
* El acceso directo a cada cuadro no cambia: cada uno sigue en su
  desplazamiento, con el paso de 4.
* El compilador compila dos veces —la primera sólo junta los cuadros que
  quedan—, porque el desplazamiento se escribe en el bytecode al compilar.
  Esa primera vuelta no tiene el tope del operando.

## Quién lee texto del bloque

Buscado con `grep` de `messages`, `msg_ptr`, `msg_start` y
`message_tick` en el runtime, y de `messages` en las pruebas:

* `message_tick`, el único que lee letras de `messages`: ahora por
  `msg_letter`, en el banco 1. Lo usan `ShowMessage` (`op_message`) y
  `ShowChoice` (`pick_open`, que vuelve a llamar a `msg_start`).
  `msg_start` lee sólo la cabecera y `message_tick` el largo, que no
  cambiaron.
* `ba_page_message` lee `messages_troop`, **otro bloque, que sigue sin
  pares**: lo dice su comentario.
* Los nombres, los menús, la tienda, las ranuras, la pelea (`scr_text`,
  `slot_text_write`, `level.s`) usan `msg_ptr` como puntero pero leen
  **otras tiras**, no `messages`: no se tocaron. `InputNumber` no lee
  texto del bloque.
* En las pruebas: `cuadro_de_texto` (`tanda.py`) recorre el bloque y ahora
  decodifica los pares; `test_compositor.py` cuenta los bytes por letras;
  `mensaje_en_pantalla` (`batalla.py`) lee `messages_troop`, sin pares.

## Lo medido

`just espacio`, antes (`cd3dce0d`) y después:

    cartucho                      textos antes   textos después
    release                       145.792 B      94.417 B   (-35 %)
    test-special                   66.064 B      65.943 B   (*)
    test-encounter-every-step         747 B         463 B

    banco 0, los tres               269/1.069/1.113   267/1.067/1.111 B libres
    banco 1, los tres              4.241 B       4.179 B libres
    bancos de datos                62/16/7       62/16/7 de 128

Sin el empujón vuelto a medir, `test-special` bajaba a 36.583 B (-45 %).

(*) `test-special` lleva el caso `empujon`, que existe para empujar el
cuadro del mapa 255 sobre el borde de banco —`test_texto`—: con DTE quedaba
en +36.188 y no cruzaba, así que se volvió a medir (684 cuadros, una cola y
dos de dos letras) hasta que cayó otra vez en +$FFFC, como antes.

La tabla son 322 bytes más. Los bancos de datos no se movieron: lo que
liberan los 51 KB es medio banco de los de 64 KB, y hoy sobran 46.

**El ritmo del texto no cambió**, medido con un script descartable que
guarda por tick `msg_state`, `msg_line`, `msg_col`, los cuadros perdidos y
los cuadros del emulador, contra la ROM base: trazas idénticas en
`grupo-11-en-255` (dos cuadros de cuatro renglones), `autofire`, `ventana`
y 2400 ticks del juego desde el título. O sea las mismas `MSG_CHARS` = 5
letras por vuelta, y ni un cuadro perdido de más: `message_tick` corre en
el lazo principal, no en el vblank, y el `jsl` por letra no se nota al lado
de `compose_char`. Las goldens no se movieron ni un pixel.

## La idea 1, los cuadros repetidos: ya estaba hecha

El compilador guarda cada cuadro una sola vez desde antes —la clave del
`Messages` es el contenido, cola de escapes incluida—, así que en el bloque
de `release` hay **cero** cuadros repetidos. Lo que queda repetido son
renglones sueltos: 14.878 bytes en renglones que aparecen más de una vez,
casi todos cortos (el más repetido, 749 veces, son 3 bytes: un nombre). Para
compartirlos haría falta un puntero por renglón, que cuesta más que lo que
ahorra en los cortos y rompe la lectura de corrido; no se hizo. Y el
relleno al paso de 4 son 3.596 bytes: si algún día el bloque apretara, un
paso de 2 alcanza para 128 KB, que hoy sobran.

## Para el merge

* Reinstalar `events` y `mapdata` (el compilador y el emisor), y
  `cartridge` porque cambia el runtime: `just -f tools/justfile install
  events mapdata cartridge`.
* Con Quirquincho chocan en `rm2k-snes-mapdata` (`emit.rs`: las líneas de
  `message_pairs` van justo después de `MESSAGES_CAP`; `request.rs`: el
  campo `message_pairs`) y en la lista de `main.s` (`message_letter.s`
  antes de `header.s`). Si su rama mueve dónde arranca `messages` en
  `test-special`, `test_texto[texto-cruza]` y `[texto-lejos]` van a pedir
  volver a medir el empujón: el desplazamiento está medido desde el
  principio del bloque, que hoy cae al principio de un banco.
* Nada de esto toca goldens.
