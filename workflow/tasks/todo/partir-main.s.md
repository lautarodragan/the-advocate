---
name: "Partir main.s"
description: "main.s, que es un solo archivo de más de treinta mil líneas, en varios"
---

**Partir `rom/src/main.s`**, que son más de treinta mil líneas en un
archivo —cuántas, `wc -l`—.

Probado en chico —una sección afuera con `.include`, mismo md5—; 
las fronteras ya existen: marcas de sección y `.proc`. 

Tres trampas: 
- el `.segment` cruza el `.include`, 
- las etiquetas anónimas se resuelven textualmente, 
- y reordenar sí cambia la ROM aunque partir no.
