---
name: "ROM de prueba: el menú en modo 5, en la SNES"
description: "Una ROM mínima que muestra la maqueta del menú en modo 5 (×1,5) como imagen fija, para que taro vea en la SNES con el FX Pak si la alta resolución se lee por su salida de video"
type: research
assignee: Carancho
---

De taro, el 2026-09-30, después de la maqueta
(`testing/maqueta-del-menu-en-alta-resolucion.md`, Ñacurutú). El modo 5 con
la fuente ×1,5 por glifo es lo que mejor se lee en la maqueta, pero hay un
riesgo que sólo se ve en la consola: las columnas de un pixel de alta
resolución están en el límite del ancho de banda de NTSC y pueden verse
borrosas por compuesto o RF. Esta ROM lo contesta antes de invertir en el
texto de ancho variable.

taro, sobre la fuente: si hace falta, se puede hacer una a mano, con el ×1,5
pensado letra por letra —la L y la I, por ejemplo, tratadas aparte—.

No es el juego: no pasa por el conversor ni por `cartuchos`.
