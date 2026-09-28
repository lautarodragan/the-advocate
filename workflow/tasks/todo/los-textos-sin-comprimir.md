---
name: "Los textos sin comprimir"
description: "119 KB de textos a un byte por letra: mensajes repetidos, nombres y DTE los bajarían uno o dos bancos, sin perder el acceso directo a cada cuadro"
type: feature
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
