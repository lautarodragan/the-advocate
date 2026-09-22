---
name: "Partir main.s"
description: "Las 30.300 líneas de main.s en varios archivos"
---

**Partir `rom/src/main.s`**, que son 30.300 líneas en un archivo. **

Probado en chico —una sección afuera con `.include`, mismo md5—; 
las fronteras ya existen, 82 marcas de sección y 450 `.proc`. 

Tres trampas: 
- el `.segment` cruza el `.include`, 
- las etiquetas anónimas se resuelven textualmente, 
- y reordenar sí cambia la ROM aunque partir no.
