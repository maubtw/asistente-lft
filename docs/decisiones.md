# Registro de decisiones técnicas

Formato por entrada: qué se probó, resultado medido, decisión y por qué.

| Fecha | Cambio | Hit@5 | MRR | Abstención | Fidelidad | Decisión |
|---|---|---|---|---|---|---|
| 2026-11-17 | baseline (fixed_chunks, 500 tok) | 89% | 0.717 | 100% | 5.00 | Descartada: 2.2× tokens de contexto |
| 2026-11-17 | by_article | 86% | 0.764 | 100% | 5.00 | **Base para la Fase 4** |
| 2026-11-17 | + híbrida (RRF, léxico IDF) | 83% | 0.563 | 100% | 4.91 | Desactivada por defecto: Hit@1 69%→39% |
| 2026-11-17 | + reranker (sobre vectorial) | 83% | 0.730 | 75% | 5.00 | Descartada: no mejora la recuperación |
| 2026-11-17 | + híbrida + reranker | 89% | 0.763 | 100% | 5.00 | **Mejor configuración medida** (+4 s de latencia) |
| 2026-11-17 | fix post-proceso del generador (base) | 86% | 0.764 | 100% | 5.00 | Adoptado: corrección 4.33 (= ruido) |
| 2026-11-17 | fix post-proceso (híbrida + reranker) | 89% | 0.763 | 100% | 4.97 | Adoptado: corrección 4.39 → **4.50** |
| 2026-11-17 | + expansión de referencias (base) | 86% | 0.764 | 100% | 4.97 | Adoptada: corrección 4.33 → 4.47 |
| 2026-11-17 | híbrida + reranker + referencias | 89% | 0.763 | 100% | 5.00 | Corrección 4.64 |
| 2026-11-18 | base + referencias + reescritura | 92% | 0.803 | 100% | 5.00 | Corrección 4.56 sin reranker (sin RAM extra) |
| 2026-11-18 | todo (reranker con pregunta original) | 86% | 0.758 | 100% | 5.00 | Descartada: el reranker anula la reescritura |
| 2026-11-18 | todo (reranker con consulta reescrita) | 94% | 0.811 | 100% | 5.00 | Corrección 4.75, pero q13 responde algo falso |
| 2026-11-18 | todo, reranker `max` + regla de regímenes especiales | **97%** | 0.804 | 100% | 5.00 | **Configuración final**: corrige q13 (recuperación medida en 36; generación en subconjunto de 11) |
| 2026-11-18 | modo completo + respuesta estructurada con pasajes | **97%** | 0.804 | 100% | 5.00 | **Actual**: corrección **4.86**, pasajes verificables **100%** (+8 s de generación) |

## 2026-11-17 — Fase 1: parser de la LFT (DOF 14-05-2026)

**Resultado:** 1,266 artículos del cuerpo (1 → 1010, sin huecos ni duplicados), 1,118 vigentes,
148 derogados, 45 registros transitorios. 60 tests pasan.

- **Encabezados:** una sola regex cubre las 50+ formas reales (`1o.-`, `22.` sin guion,
  `3o. Bis.-`, `153-F Bis.`, `353-Ñ.-`, `890- Se deroga.`). Validación cruzada: el conteo de
  encabezados con grep sobre el PDF (1,266) coincide con el número de artículos parseados.
- **Guardia de numeración:** un encabezado solo se acepta si avanza en orden legal
  (`3 < 3 Bis < 3 Ter < 4`, `353-N < 353-Ñ`) y no salta más de 15 números. Evita que una línea
  de texto que empieza con "Artículo 50." abra un artículo falso.
- **Notas de reforma** ("Artículo reformado DOF…", "Fe de erratas…", ~1,600 líneas): se quitan
  del texto y se guardan en `notas_reforma`. Contaminarían embeddings y búsqueda léxica (la
  palabra "Artículo" aparecería en todos los artículos), pero sirven para mostrar vigencia.
- **Referencias:** se descartan las que apuntan a otra ley (Constitución, Ley del Seguro Social…)
  mirando el texto que sigue a la cita, y solo se guardan IDs que existen en la LFT. 285
  artículos tienen referencias; 31 menciones se descartaron como externas (revisadas a mano).
- **Transitorios:** los de 1970 se guardan por artículo (`Transitorio 1 (1970)`); los de los 32
  decretos de reforma tienen formato libre, así que se guarda un registro por decreto
  (`Transitorios DOF 14-05-2026`).
- **Pendiente para Fase 2:** el Art. 513 (tablas de enfermedades y valuación de incapacidades)
  mide ~313k caracteres; excede el contexto de bge-m3 (8,192 tokens) y habrá que trocearlo.

## 2026-11-17 — Fase 2: pipeline básico (solo vectorial)

- **LLM:** OpenAI (`gpt-5-mini`, `reasoning_effort=low`) en lugar de Anthropic. Configurable en
  `.env` (`LLM_MODEL`, `LLM_REASONING_EFFORT`).
- **Qué se vectoriza:** `"Artículo 76 — TÍTULO … — CAPÍTULO …\n<texto>"`. La columna `texto` guarda
  solo el texto de la ley (para el `tsvector` y para mostrar).
- **Artículos largos:** se parten por párrafos en chunks de ≤800 tokens conservando el ID (el
  Art. 513 genera 128 chunks; 132, 283, 390 Bis y 684-E, 4 cada uno). El retriever deduplica por artículo para que un artículo no
  ocupe varios lugares del top-5. Resultado: 1,118 artículos vigentes → 1,274 chunks con vector.
- **Derogados y transitorios** se guardan sin embedding (para `GET /articulo/{id}`) y se filtran
  en la consulta.
- **"Sin cita, no hay respuesta" se aplica en código**, no solo en el prompt: si la respuesta no
  trae al menos una cita `(Art. X, LFT)` de un artículo del contexto, se convierte en abstención.
  La salida cruda del modelo se conserva en `respuesta_modelo` para la evaluación.
- **Flags** `USE_HYBRID`, `USE_RERANKER`, `USE_REFERENCE_EXPANSION`, `USE_QUERY_REWRITE` ya existen
  en `rag/config.py`; los no implementados fallan con `NotImplementedError` en vez de ignorarse en
  silencio (una evaluación con un flag ignorado daría números engañosos).

**Observaciones a medir en la Fase 3** (pruebas manuales, no métricas):
- "¿Cuántos días de vacaciones me tocan en mi tercer año?" → recupera y cita el Art. 76 ✅, pero
  la aritmética del LLM no es estable (una corrida dio 16 días para "2 años cumplidos"; son 14).
  Candidato a calculadora determinista.
- "Me corrieron sin darme ninguna razón" → la búsqueda vectorial no trae los Arts. 47/48/50
  (recupera 709, 986, 763, 114, 873-A). Lenguaje coloquial vs. lenguaje de la ley: motivo para
  búsqueda híbrida y reescritura de consulta.
- "¿Cuál es la tasa del ISR?" → abstención correcta.
- Latencia CLI ~20 s: ~13 s es la carga de bge-m3 en cada ejecución; en la API el modelo queda
  cargado. Generación: 4–9 s.

## 2026-11-17 — Fase 3: línea base de evaluación (chunks fijos vs. por artículo)

**Set de evaluación:** 40 preguntas (36 con respuesta en la ley, 4 fuera de alcance). Antes de
correrlo se validó cada pregunta contra el texto parseado: 2 tenían el artículo esperado
equivocado (q10: el 67 es pago por siniestro, no horas extra → 66/68; q33: el 330-J es la NOM de
seguridad → 330-F) y en 5 se agregó un artículo que la respuesta completa necesita (q08 +59 por la
reforma de 40 h semanales, q14 +73, q16 +74, q19 +50, q25 +26).

**Configuraciones** (mismo modelo `gpt-5-mini`, mismo prompt, top-5, solo vectorial):
- `fixed_chunks`: la ley vigente como un texto continuo, ventanas de 500 tokens con 50 de
  traslape (621 chunks, ~3 artículos por chunk).
- `by_article`: un chunk por artículo (artículos largos partidos a ≤800 tokens).

| Config | Hit@1 | Hit@5 | MRR | Recall@5 | Abstención ✓ | Falsa abst. | Cita esperada | Fidelidad | Corrección | Tokens ctx |
|---|---|---|---|---|---|---|---|---|---|---|
| fixed_chunks | 64% | 89% | 0.717 | 88% | 100% | 11% | 89% | 5.00 | 4.50 | 2780 |
| by_article | 69% | 86% | 0.764 | 80% | 100% | 14% | 86% | 5.00 | 4.36 | 1253 |

Resultados: `eval/results/2026-11-17_fixed_chunks.json`, `eval/results/2026-11-17_by_article.json`.

**Lectura honesta:** el chunking fijo *no* perdió. Con 36 preguntas, 1 pregunta = 2.8 puntos, así
que Hit@5 89% vs 86% es una sola pregunta. Lo que sí es claro:

1. **Por artículo es más preciso arriba del ranking** (Hit@1 +5, MRR +0.05): q12, q13, q17, q26,
   q28 y q34 ponen el artículo correcto más arriba (p. ej. q26 "renunciar a mis derechos": Art. 33
   en rango 1 vs. 5; q28 "descuentos por romper algo": Art. 110 en rango 1 vs. 5).
2. **El chunking fijo gana cuando un artículo depende de su vecino.** q16 ("si trabajo el 1 de
   enero"): el Art. 75 dice "en los casos del artículo anterior… salario doble"; por sí solo su
   vector no habla del 1 de enero, y por artículo no se recuperó ni el 74 ni el 75 (abstención). El
   chunk fijo `72–77` trae ambos. Igual en q21 (Art. 52: "causas mencionadas en el artículo
   anterior") y q14 (71 y 73 caen en el mismo chunk). **62 de 1,118 artículos vigentes** usan
   "artículo anterior/siguiente".
3. **Costo:** el chunking fijo manda 2.2× más tokens al LLM (2,780 vs. 1,253 por pregunta) para
   una diferencia de calidad dentro del ruido.
4. **Fallan las dos** en q23 (Art. 518: "prescriben… los trabajadores separados del trabajo" vs.
   "demandar si me despidieron"), q30 (el tope de PTU está en la fracc. VIII del Art. 127, y "PTU"
   no aparece en la ley) y q32 (permiso de paternidad: fracc. XXVII Bis dentro del Art. 132, un
   artículo de 29 fracciones). Son brechas de vocabulario y de artículos largos, no de chunking.

**Decisión:** `by_article` como base. Razones: más precisión en los primeros lugares, la mitad
del costo de contexto, y las citas corresponden 1:1 con artículos (la demo muestra el artículo
completo citado). Su debilidad, los artículos que dependen del vecino, es estructural y tiene
solución dirigida en vez de traer vecinos al azar.

**Hipótesis para la Fase 4:**
- Expansión de referencias que resuelva "artículo anterior/siguiente" → debería recuperar q16 y q21.
- Búsqueda híbrida y reescritura de consulta → q23 ("despido" vs. "separados del trabajo") y
  q30 ("PTU" vs. "participación de utilidades").
- q32 probablemente necesita el reranker (el pasaje relevante es 1 de 29 fracciones).

**Notas de método:** el juez es `gpt-5-mini`, el mismo modelo que genera (posible sesgo a
favor). Fidelidad 5.00 en ambas: el juez no detectó afirmaciones fuera del contexto; la métrica
discriminante es Corrección. La regla "sin cita no hay respuesta" hace que la cita válida sea
100% por construcción; por eso se reporta "cita esperada" (cita un artículo de la referencia).

## 2026-11-17 — Fase 4.1: búsqueda híbrida (vectorial + full-text `spanish`, RRF)

**Implementación** (`USE_HYBRID=true`):
- *Léxica:* la pregunta pasa por `to_tsvector('spanish', …)` y se buscan artículos con
  *cualquiera* de sus lexemas (OR). Con AND (`plainto_tsquery`) "¿Cuánto tiempo tengo para demandar
  si me despidieron?" no encuentra **ningún** artículo; con OR encuentra 376, así que todo depende
  del ranking.
- `ts_rank` de Postgres **no usa IDF**: "trabaj" (en el 68% de los chunks) pesa igual que "despid".
  Por eso el ranking por defecto es la **suma del IDF (fórmula BM25) de los lexemas que coinciden**,
  con frecuencias de documento de `ts_stat`. `LEXICAL_RANKING=ts_rank` queda como alternativa.
- *Fusión:* RRF con k=60 sobre el top-20 de cada lista (deduplicado por artículo). RRF solo usa
  posiciones, así que no hay que normalizar coseno (~0.6) contra suma de IDF (~15).

**Resultados.** La recuperación es determinista: estos números salen de `retrieval_only` (36 preguntas
con respuesta en la ley):

| Variante | Hit@1 | Hit@5 | MRR | Recall@5 |
|---|---|---|---|---|
| vectorial (base) | 69% | 86% | 0.764 | 80% |
| léxica sola, IDF | 17% | 42% | 0.255 | 38% |
| léxica sola, ts_rank | 17% | 36% | 0.250 | 33% |
| híbrida, IDF | 39% | 83% | 0.563 | 73% |
| híbrida, ts_rank | 47% | 75% | 0.558 | 70% |

Evaluación completa (generación + juez):

| Config | Hit@1 | Hit@5 | MRR | Recall@5 | Falsa abst. | Cita esperada | Corrección | Tokens ctx |
|---|---|---|---|---|---|---|---|---|
| by_article (corrida 1) | 69% | 86% | 0.764 | 80% | 14% | 86% | 4.36 | 1253 |
| by_article (corrida 2, "antes") | 69% | 86% | 0.764 | 80% | 11% | 86% | 4.36 | 1253 |
| hybrid ("después") | 39% | 83% | 0.563 | 73% | 8% | 81% | 4.19 | 1655 |

**Ruido:** dos corridas idénticas de `by_article` cambian la generación en 2 de 40 preguntas
(q02, q21) y la falsa abstención en 3 puntos. Diferencias de ese tamaño no son señal.

**Qué mejoró:**
- **q32 "¿Los papás tienen derecho a permiso cuando nace su hijo?"**: la vectorial no trae el
  Art. 132 en el top-5; la léxica lo encuentra en 3er lugar gracias a "permiso" y "nacimiento". Es
  la primera configuración que responde bien ("permiso de paternidad de cinco días laborables con
  goce de sueldo", corrección 5). *Bug encontrado aquí:* el 132 está partido en 4 chunks y RRF se
  quedaba con el chunk que vio primero (el de la vectorial, fracc. XXIX) en vez del que encontró
  la léxica (fracc. XXVII Bis). La métrica de recuperación contaba acierto, pero el LLM no veía el
  texto y se abstenía. Ahora se conserva el chunk de la lista donde el artículo quedó mejor.
- q31 (maternidad, Art. 170): rango 3 → 2.

**Qué empeoró:**
- **Precisión en el primer lugar.** La léxica sola acierta poco (42% Hit@5) con preguntas
  coloquiales, y con pesos iguales su ruido desplaza aciertos vectoriales. q03 "¿Me pueden pagar las
  vacaciones en lugar de dármelas?": Art. 79 rango 1 → 5. q26 "¿Puedo renunciar a mis derechos si
  firmo un papel?": Art. 33 rango 1 → 4. q17: 2 → 5.
- **Se pierden del top-5:** q13 "¿Cuántos días de descanso a la semana?" (Art. 69, rango 1 → fuera;
  peor que abstenerse: respondió con otros artículos y el juez le puso corrección 1) y q27 "¿Cada cuánto me tienen que pagar el salario?" (Art. 88, rango 2 →
  fuera, abstención). Las palabras de la pregunta ("días", "semana", "pagar", "salario") son
  frecuentes en toda la ley y la léxica llena su top con artículos irrelevantes.
- **No amplía los candidatos:** Recall@20 es 90% con vectorial y con híbrida. Fallan las mismas
  dos preguntas: q21 (renuncia con indemnización, Arts. 51/52) y q30 (tope de PTU, Art. 127).
- **No resolvió** q23 ("demandar si me despidieron" vs. "separados del trabajo"): la léxica no
  ayuda si la pregunta no comparte palabras con la ley. Eso le toca a la reescritura de consulta.

**Hallazgo de método:** en q16 ("si trabajo el 1 de enero") la híbrida recupera el Art. 74 pero no
el 75 (el del salario doble). Hit@5 cuenta acierto y el sistema se abstiene, lo cual es correcto.
Hit@k sobreestima cuando una respuesta necesita dos artículos; por eso también se reporta Recall@5.

**Decisión:** `USE_HYBRID=false` por defecto. El código se queda porque rescata q32 y para
probarlo combinado con el reranker, que puede reordenar el ruido léxico. IDF le gana a `ts_rank`
en la léxica sola (+6 Hit@5), pero el efecto se diluye en la fusión.

**Pendiente (cambio aparte, afecta a todas las configs):** la regla de abstención convierte en
abstención cualquier respuesta que *contenga* "No encontré esto en la LFT", aunque traiga una
respuesta parcial con cita válida (q08 en la corrida `hybrid`). Corregirla cambia la línea base,
así que va como experimento separado.

## 2026-11-17 — Fase 4.2: reranker cross-encoder (`bge-reranker-v2-m3`)

**Implementación** (`USE_RERANKER=true`): se toman 20 candidatos (`RETRIEVE_K`, deduplicados por
artículo) de la búsqueda vectorial, o de la híbrida si `USE_HYBRID`. El cross-encoder lee cada par
(pregunta, "Artículo X — Capítulo\n texto") y se quedan los 5 mejores. Se probó sobre las dos
fuentes de candidatos.

**Recursos (Mac de 8 GB):** en float32 el reranker hace swap y tarda **~25 s** en puntuar 20
candidatos; en float16 sobre MPS tarda **~3 s con el mismo top-5**. Se usa float16 en GPU y float32
en CPU.

**Recuperación** (determinista, 36 preguntas respondibles):

| Variante | Hit@1 | Hit@5 | MRR | Recall@5 | Latencia recuperación |
|---|---|---|---|---|---|
| vectorial (base) | 69% | 86% | 0.764 | 80% | 0.06 s |
| híbrida | 39% | 83% | 0.563 | 73% | 0.08 s |
| vectorial + reranker | 67% | 83% | 0.730 | 80% | 4.6 s |
| **híbrida + reranker** | **69%** | **89%** | **0.763** | **86%** | 4.4 s |

**Evaluación completa:**

| Config | Hit@5 | MRR | Recall@5 | Abstención ✓ | Falsa abst. | Cita esperada | Corrección | Latencia total |
|---|---|---|---|---|---|---|---|---|
| by_article (base) | 86% | 0.764 | 80% | 100% | 11% | 86% | 4.36 | 6.0 s |
| rerank | 83% | 0.730 | 80% | 75% | 3% | 83% | 4.39 | 8.2 s |
| hybrid_rerank | 89% | 0.763 | 86% | 100% | 8% | 86% | 4.39 | 7.7 s |

**Lectura:** el reranker solo no aporta, porque reordena los mismos candidatos que ya traía la
vectorial. **Lo que funciona es la combinación:** la léxica mete en los candidatos artículos que la
vectorial no ve, y el reranker se encarga del ruido léxico que arruinaba la híbrida con RRF (Hit@1
vuelve de 39% a 69%). Es la primera configuración que mejora Recall@5 (+6 pts, ~2 preguntas) sin
perder precisión arriba. La corrección promedio queda igual (4.36 → 4.39, dentro del ruido), con
matices que se ven pregunta por pregunta.

**Qué mejoró (hybrid_rerank vs. base):**
- **q23 "¿Cuánto tiempo tengo para demandar si me despidieron?"**: el Art. 518 entra al top-5 por
  primera vez en todo el proyecto (rango 5). La respuesta pasa de abstención a corrección 5 ("dos
  meses… a partir del día siguiente a la fecha de la separación").
- **q32 "¿Los papás tienen derecho a permiso…?"**: el Art. 132 (chunk de la fracc. XXVII Bis) queda en
  1er lugar. El modelo respondió bien, pero la respuesta se descartó (ver *Bug de citas* abajo).
- q31 maternidad (Art. 170): 3 → 1. q19 despido sin causa (Arts. 48/50): 3 → 1. q27 periodicidad
  del salario (Art. 88): 2 → 1.
- q14 "Trabajo los domingos": corrección 3 → 5. La respuesta ya incluye el Art. 73 (salario doble en
  el día de descanso), no solo la prima dominical.

**Qué empeoró:**
- **q17 "¿Por qué razones me pueden despedir justificadamente?"**: el Art. 47 (la lista de causas) sale
  del top-5 y queda en 8º lugar; corrección 5 → 3. El reranker prefiere el Art. 46 ("podrá rescindir…
  por causa justificada", 0.45) frente al 47 (0.017): el 47 es una lista de 15 fracciones que nunca
  dice "despedir", y al cross-encoder le cuesta. Es el costo más claro del reranker.
- q13 (descanso semanal, Art. 69): 1 → 4, aunque la respuesta sigue correcta (5). q25 (contrato por
  escrito, Art. 24): 1 → 5; arriba quedan artículos que también piden contrato escrito para
  casos específicos (colectivo, campo, teletrabajo, hogar). q34 (edad mínima): corrección 5 → 3.
- **Latencia:** +1.7 s promedio por pregunta en la evaluación (paralelizada) y ~4.4 s de recuperación
  secuencial en este Mac. Además, +1.1 GB de RAM en float16.

**Abstención con `rerank` (75%):** respondió q39 "¿Cuánto cuesta un abogado laboral en
Guadalajara?" con "los servicios de la Procuraduría de la Defensa del Trabajo son gratuitos (Art.
534)". Es una respuesta útil y fiel a la ley, pero la pregunta pide un precio de mercado. Se cuenta
como error según la definición del set.

**Bug de citas encontrado (afecta a todas las configs):** en q32 el modelo citó `(Art. 132, XXVII
Bis, LFT)`. La regex de citas no acepta la fracción, la respuesta "no tenía cita válida" y se
convirtió en abstención. Junto con el bug de la regla de abstención (q08), son dos fallas del
post-proceso del generador que esconden respuestas correctas. Van en un cambio aparte, medido
contra esta tabla.

**Decisión:** `hybrid + rerank` es la mejor configuración medida para recuperación. Por defecto se
deja **apagada en el `.env`** hasta decidir la demo (Fase 5): en un Mac de 8 GB cuesta +1.1 GB de RAM
y ~4 s por consulta, y en un deploy con CPU sería más lento. La evaluación la corre con
`--config hybrid_rerank`.

## 2026-11-17 — Fix del post-proceso del generador (citas con fracción y abstención parcial)

Dos reglas del código que convierte la salida del LLM en respuesta escondían respuestas correctas:

1. **Citas con fracción.** La regex solo aceptaba `(Art. 132, LFT)`. El modelo escribió
   `(Art. 132, XXVII Bis, LFT)` en la pregunta de paternidad: "sin cita válida" → abstención. Ahora
   se acepta un detalle opcional (fracción, párrafo) y la cita cuenta por el artículo. En las 630
   citas de todas las corridas era el único formato no reconocido.
2. **Abstención parcial.** Cualquier respuesta que *contuviera* "No encontré esto en la LFT" se
   descartaba completa. El modelo responde así cuando la pregunta tiene dos lecturas: "si eres
   trabajadora del hogar… (Art. 333, LFT); para el caso general no encontré esto". Ahora es
   abstención solo si no hay ninguna cita; si hay citas válidas, lo citado se muestra.

**Medición sin LLM:** se reaplicaron las reglas nuevas a las respuestas crudas guardadas de las 9
corridas. Cambian 6 preguntas, todas con respuesta en la ley. **Ninguna pregunta fuera de alcance
deja de abstenerse** (la abstención correcta no puede empeorar por este cambio).

**Evaluación completa** (misma recuperación; la generación se vuelve a correr):

| Config | Falsa abst. | Cita esperada | Fidelidad | Corrección |
|---|---|---|---|---|
| by_article, antes | 11% | 86% | 4.97 | 4.36 |
| by_article, después | 8% | 86% | 5.00 | 4.33 |
| hybrid_rerank, antes | 8% | 86% | 5.00 | 4.39 |
| hybrid_rerank, después | **6%** | **89%** | 4.97 | **4.50** |

- **hybrid_rerank:** q32 (paternidad) pasa de abstención a **corrección 5** ("permiso de paternidad
  de cinco días laborables con goce de sueldo"), el efecto directo del fix 1. El resto de cambios
  (q03 +1, q23 −2, q31 −1, q34 +2) son variación normal entre corridas.
- **by_article:** la corrección queda igual (4.36 → 4.33, ruido). El fix 2 tiene un costo visible en
  q16 ("si trabajo el 1 de enero"), donde la recuperación no trae los Arts. 74/75. Antes el sistema
  se abstenía; ahora dice "para el pago por trabajar el 1 de enero, No encontré esto en la LFT" y
  agrega dos lecturas forzadas (aguinaldo, Art. 87; prima vacacional, Art. 80), bien citadas pero que
  no responden. Es honesta pero rellena. El juez califica 1 en ambos casos.

**Limitación de la métrica:** "corrección" califica igual (1) una abstención y una respuesta que no
contesta. En un dominio legal, una respuesta equivocada es peor que abstenerse. Las respuestas de
q16 no afirman nada falso, pero conviene vigilarlo.

**Siguiente ajuste candidato (prompt):** la regla 6 ("si la pregunta admite más de una
interpretación, responde cada caso") empuja al modelo a inventar lecturas para tener algo que citar
(q16). Acotarla a "solo si ambas lecturas se responden con el contexto" se mediría por separado.

**Decisión:** se adopta el fix. Corrige un error real (q32) sin riesgo para la abstención correcta.

## 2026-11-17 — Fase 4.3: expansión por referencias cruzadas (profundidad 1)

**Implementación** (`USE_REFERENCE_EXPANSION=true`):
- *Parser:* además de las referencias explícitas ("artículo 50", "artículos 47 y 51"), se resuelven las
  relativas: "artículo anterior / precedente / que antecede" → el artículo previo en el orden de la
  ley, "artículo siguiente" → el posterior. El plural ("artículos anteriores") se ignora por ambiguo.
  Artículos con referencias: 285 → 331. Ej.: Art. 75 → [74]; Art. 52 → [51, 50].
- *Retriever:* después del top-5 (y del reranker, si está activo) se agregan hasta 3 artículos
  (`MAX_REFERENCE_ARTICLES`) a los que remiten los recuperados, en orden de rango y sin repetir. Van
  **al final**, sin desplazar lo recuperado. Si el referido es largo y está partido, se usa su chunk
  más parecido a la pregunta. Derogados excluidos.
- *Métricas:* Hit@5/Recall@5 no ven lo que se agrega en las posiciones 6–8. Se añadieron
  `hit@ctx` y `recall@ctx`, calculadas sobre todo el contexto que recibe el generador.
- `ingest.embed --refs-only` actualiza la columna `referencias` sin re-vectorizar.

**La hipótesis original no se cumplió.** En la Fase 3 se esperaba que resolver "artículo anterior"
arreglara q16 (1 de enero, Arts. 74/75) y q21 (renuncia con indemnización, Arts. 51/52). No pasó:
en ninguna configuración se recupera *ninguno* de los dos artículos del par, así que la expansión
no tiene de dónde partir. Se implementó la expansión general sin ajustarla a esas dos preguntas.

**Resultados:**

| Config | Recall@5 | Recall ctx | Falsa abst. | Cita esperada | Fidelidad | Corrección | Tokens ctx | Latencia |
|---|---|---|---|---|---|---|---|---|
| by_article | 80% | 80% | 8% | 86% | 5.00 | 4.33 | 1253 | 5.3 s |
| + referencias | 80% | 84% | 6% | 86% | 4.97 | **4.47** | 1756 | 5.7 s |
| hybrid_rerank | 86% | 86% | 6% | 89% | 4.97 | 4.50 | 1288 | 7.6 s |
| + referencias | 86% | 89% | **3%** | **92%** | 5.00 | **4.64** | 1862 | 9.0 s |

La mejora (+0.14 en ambas bases) supera el ruido observado entre corridas idénticas (~0.03–0.1) y
se explica pregunta por pregunta:

**Qué mejoró:**
- **q17 "¿Por qué razones me pueden despedir justificadamente?"** (hybrid_rerank): el reranker había
  sacado el Art. 47 del top-5. El Art. 291-M, que sí quedó, dice "además de las causas establecidas
  en el artículo 47", y la expansión lo trae de vuelta. Corrección 3 → 5 ("resume correctamente y por
  completo las causas de rescisión del artículo 47"). **La expansión compensa la pérdida más clara
  del reranker.**
- **q14 "Trabajo los domingos"** (base): el 71 trae el 73 (salario doble en día de descanso). 3 → 5.
- **q25 "¿Mi contrato tiene que ser por escrito?"** (base): el 24 trae el 25 (contenido del contrato).
  3 → 5.
- q19 despido sin causa (hybrid_rerank): el 48 trae el 684-A (conciliación previa). 4 → 5.
- q23 plazo para demandar (base): de abstención a respuesta parcial (corrección 3). El 518 sigue sin
  recuperarse en la base.

**Qué empeoró o no ayudó:**
- **Ruido en el contexto:** se agregan ~2 artículos por pregunta (+45% tokens) y no todos aportan.
  En q17 entra el Art. 1 ("La presente Ley es de observancia general…"), porque algún recuperado lo
  menciona. En q11 "¿Cuántas horas extra a la semana?" se agregan 58/60/61 (jornada) y el modelo
  plantea una ambigüedad en vez de responder directo: 5 → 3.
- q34 edad mínima (base): 5 → 3 sin artículos agregados, así que es ruido de generación.
- q16 y q21: siguen fallando (corrección 2): la recuperación no trae los artículos clave.

**Costo:** +500 tokens de contexto por pregunta (~+45%) y +0.4–1.4 s. No usa modelos ni RAM extra.

**Decisión:** la expansión de referencias queda **activada por defecto** (`USE_REFERENCE_EXPANSION=true`
en `.env`): mejora la corrección con cualquier configuración de recuperación y es barata. La mejor
configuración medida queda en **híbrida + reranker + referencias** (corrección 4.64, falsa
abstención 3%, cita esperada 92%). Si la demo usa la híbrida + reranker se decide en la Fase 5, por
RAM y latencia.

**Ideas no probadas (para no sobreajustar a 36 preguntas):** referencias entrantes (artículos que
citan al recuperado: traería el 52 desde el 50 en q21) y filtrar referencias genéricas como el Art. 1.

## 2026-11-18 — Fase 4.4: reescritura de consulta (lenguaje coloquial → términos de la ley)

**Implementación** (`USE_QUERY_REWRITE=true`, `rag/query_rewrite.py`):
- El LLM (`gpt-5-mini`, `reasoning_effort=minimal`, ~1.5 s) reescribe la pregunta "con los términos
  técnicos que emplearía la propia ley".
- **Multi-consulta, no reemplazo:** se busca con la original *y* con la reescrita (una lista por
  consulta y tipo de búsqueda) y se fusiona con RRF. Si la reescritura sale mal, la original sigue
  compitiendo.
- **El prompt no tiene ejemplos ni vocabulario.** Escribir "despido → rescisión" o "1 de enero →
  descanso obligatorio" sería filtrar las respuestas del set de evaluación. Tampoco pide números
  de artículo, para no usar la memoria del modelo sobre la LFT. Hay un test que verifica ambas cosas.
- La recuperación deja de ser determinista (depende de la salida del LLM): una corrida por config.

Ejemplos reales de reescritura:
- q23 "¿Cuánto tiempo tengo para demandar si me despidieron?" → "¿En qué plazo prescribe la acción
  para reclamar… por despido injustificado?"
- q30 "¿Hay un tope para lo que me pueden dar de PTU?" → "¿Existe límite máximo legal para la
  participación de los trabajadores en las utilidades…?"

**Resultados:**

| Config | Hit@1 | Hit@5 | MRR | Recall@5 | Recall ctx | Falsa abst. | Cita esperada | Corrección | Latencia |
|---|---|---|---|---|---|---|---|---|---|
| refs (base) | 69% | 86% | 0.764 | 80% | 84% | 6% | 86% | 4.47 | 5.7 s |
| refs + reescritura | 72% | 92% | 0.803 | 86% | 89% | 6% | 89% | 4.56 | 7.5 s |
| híbrida + rerank + refs | 69% | 89% | 0.763 | 86% | 89% | 3% | 92% | 4.64 | 9.0 s |
| + reescritura (rerank con original) | 69% | 86% | 0.758 | 83% | 88% | 8% | 89% | 4.58 | 10.5 s |
| **+ reescritura (rerank con reescrita)** | **72%** | **94%** | **0.811** | **90%** | **94%** | **0%** | **94%** | **4.75** | 10.1 s |

Abstención correcta: 100% en todas (las 4 fuera de alcance siguen rechazándose; p. ej. "salario
mínimo de este año" se reescribe como "remuneración mínima legal vigente" y el sistema aún se abstiene).

**1. Sobre el pipeline barato (refs, sin reranker), la reescritura ayuda sola:** Hit@5 86% → 92%, MRR
+0.04, corrección 4.47 → 4.56.
- **q30 tope de PTU**: primera vez que se resuelve en el proyecto. Art. 127 sin recuperar → rango 3,
  de abstención a corrección 5.
- q23 plazo para demandar: Art. 518 sin recuperar → rango 4, corrección 3 → 5.
- q19, q27, q31, q34 suben de rango.
- Pierde q13 (Art. 69 sale del top-5; ver abajo) y q32 se sigue absteniendo (llega un chunk del
  Art. 132 que no es el de paternidad).

**2. Con el reranker, la reescritura no sirvió… hasta cambiar con qué pregunta reordena.** La primera
versión pasaba al reranker la pregunta original ("intención del usuario"). Diagnóstico en q30: la
reescritura deja el Art. 127 en **2º lugar entre los 20 candidatos** (1º en ambas listas de la
consulta reescrita), pero el cross-encoder, con "¿tope… de PTU?", lo baja al **18º**. Con la consulta
reescrita lo pone **1º**. El reranker no sabe que "PTU" es "participación de los trabajadores en las
utilidades", así que tiraba exactamente lo que la reescritura había ganado. Se agregó
`RERANK_QUERY=original|rewrite`.

**3. Con `RERANK_QUERY=rewrite` sale la mejor configuración del proyecto:** corrección 4.75, falsa
abstención 0%, Hit@5 94%, Recall del contexto 94%.
- **q16 "Si trabajo el 1 de enero, ¿cuánto me tienen que pagar?"** se resuelve por primera vez,
  **combinando dos mejoras**: la reescritura ("día de descanso obligatorio") trae el Art. 75 y la
  expansión resuelve su "en los casos del artículo anterior" agregando el Art. 74. Respuesta: "El 1o.
  de enero es día de descanso obligatorio (Art. 74)… además del salario por el descanso, un salario
  doble por el servicio prestado (Art. 75)". Corrección 2 → 5. *La hipótesis de la Fase 3 sobre
  "artículo anterior" se cumple, pero solo cuando la recuperación ya trae uno de los dos artículos.*
- q30 PTU: rango 1, corrección 5. q17 despido justificado: el Art. 47 vuelve al top-5 (rango 4).
  q10 horas extra: 3 → 1.

**Qué empeoró (y es grave):**
- **q13 "¿Cuántos días de descanso a la semana me corresponden?" → corrección 1, con información
  incorrecta para la mayoría.** La reescritura agregó un tema que la pregunta no plantea ("¿Cuál es la
  jornada laboral semanal y los días de descanso obligatorios…?") a pesar de la instrucción "no
  agregues temas". La recuperación trajo el Art. 336 (trabajadoras del hogar: "día y medio") y no el
  69 (regla general: un día por cada seis). El sistema respondió "tienes derecho a un descanso
  semanal de día y medio" como si fuera general. **Es el peor tipo de error del proyecto: una
  afirmación falsa con cita válida, no una abstención.** La fidelidad sale 5 (está en el contexto) y
  la corrección 1. El promedio lo esconde.
- q20 indemnización de 20 días: 5 → 3 (respuesta correcta pero incompleta; probable ruido).
- Latencia: +1.5 s por la llamada de reescritura (10.1 s en total con todo activo, en este Mac).

**Decisión:**
- La mejor configuración medida es **híbrida + reranker (con consulta reescrita) + referencias +
  reescritura** (`--config full_rerank_rewrite`). Se fija `RERANK_QUERY=rewrite` en `.env`, porque
  `original` anula la reescritura cuando el reranker está activo.
- Qué se activa en la demo se decide en la Fase 5 (RAM y latencia). Si no hay RAM para el reranker,
  **refs + reescritura** (4.56) es la mejor opción barata.
- **Riesgo abierto:** la deriva de la reescritura (q13). Mitigaciones candidatas, cada una a medir
  por separado: (a) que el reranker puntúe con el máximo de original y reescrita (cuesta 2× de
  reranker); (b) que el generador advierta cuando el artículo citado es de un régimen especial
  (hogar, campo, plataformas) y la pregunta no lo menciona.

**Nota sobre el ruido:** es una sola corrida por configuración y la recuperación ya no es
determinista. La mejora de 4.64 → 4.75 es del orden del ruido (~0.1), pero la acompañan cambios de
recuperación grandes y explicables pregunta por pregunta (q16, q30, q17, q10).

## 2026-11-18 — Corrección de q13 (régimen especial presentado como regla general) y ahorro de API

**Problema** (ver Fase 4.4): "¿Cuántos días de descanso a la semana me corresponden?" se respondía
"día y medio" citando el Art. 336, que es solo para personas trabajadoras del hogar. La regla general
es un día por cada seis (Art. 69). Tiene dos causas:
1. **Recuperación:** la reescritura se desvió ("jornada laboral semanal…") y el reranker, puntuando
   con la consulta reescrita, sacó al Art. 69 del top-5 (7º lugar).
2. **Generación, la causa de fondo:** el contexto ya rotula al 336 como "TÍTULO SEXTO Trabajos
   Especiales / CAPÍTULO … Personas trabajadoras del hogar", y el modelo igual lo presentó como
   general. Puede pasar con cualquier régimen especial (campo, plataformas, deportistas…).

**Cambios:**
- `RERANK_QUERY=max`: cada candidato se queda con el mejor puntaje del cross-encoder entre la pregunta
  original y la reescrita. Así conserva lo que gana la reescritura (q30, PTU) sin que una reescritura
  desviada entierre la respuesta (q13). Cuesta 2× de inferencia del reranker (~+3 s en este Mac).
- Regla 5 del prompt: si un artículo es de un régimen especial y la pregunta no lo menciona, dar
  primero la regla general y decir a quién aplica el especial. Es una regla general, no específica de
  q13.

**Recuperación** (36 preguntas, mismas reescrituras desde caché, sin llamadas a la API):

| Reranker | Hit@1 | Hit@5 | MRR | Recall@5 | Recall ctx |
|---|---|---|---|---|---|
| `rewrite` | 72% | 94% | 0.811 | 90% | 94% |
| **`max`** | 69% | **97%** | 0.804 | **93%** | **96%** |

Solo cambian dos preguntas: q13 (Art. 69 fuera → rango 4) y q34 (rango 1 → 2).

**Generación** (subconjunto de 11 preguntas, `eval/results/2026-11-18_full_rerank_max_parcial.json`):
q13 + las que traen artículos de regímenes especiales en el contexto (q08 hogar, q14 menores/
plataformas, q25 campo/hogar/teletrabajo) + q16, q30, q32 como control + las 4 fuera de alcance.
- **q13: corrección 1 → 5.** "Regla general: … un día de descanso por cada seis días de trabajo (Art.
  69). Si eres persona trabajadora del hogar: … día y medio (Art. 336)". Es la respuesta que debía dar.
- Las otras 6 siguen en 5; las 4 fuera de alcance siguen absteniéndose.
- *Limitación:* la regla nueva del prompt no se midió en las 36 preguntas (para ahorrar API). Se
  verificó donde podía afectar: preguntas con artículos de regímenes especiales en el contexto y
  preguntas fuera de alcance.

**Infraestructura para gastar menos API:**
- `eval/cache/rewrites.json`: caché de reescrituras por (modelo, esfuerzo, hash del prompt, pregunta).
  Volver a correr no paga reescrituras y la recuperación vuelve a ser determinista: la corrida
  `rewrite` de arriba reprodujo exactamente los números de la Fase 4.4.
- `run_eval --ids q13,q16`: evaluación de un subconjunto. Se guarda como `*_parcial.json` y
  `eval.report` la excluye de la tabla, porque sus métricas no son comparables.
- Los cambios de recuperación se miden primero sin LLM; el juez solo donde la generación cambia.

**Bug de infraestructura:** al cargar modelos, `huggingface_hub` consulta en línea si hay versiones
nuevas. Una petición se quedó colgada 20 minutos sin timeout (proceso vivo, 0% CPU). Ahora los
modelos se cargan con `local_files_only=True` y solo se descargan si faltan.

**Configuración final de la Fase 4** (`--config full_rerank_max`, en `.env` `RERANK_QUERY=max`):
híbrida + reranker (max) + expansión de referencias + reescritura de consulta.

## 2026-11-18 — Rediseño, fase 1: respuesta estructurada con pasajes literales (backend)

El diseño nuevo pone la respuesta y la ley lado a lado: cada cita abre el
artículo con **el pasaje exacto resaltado**. Para eso el backend tiene que devolver, por cada
afirmación, la frase literal del artículo que la sustenta.

**Cambios:**
- El generador responde con **JSON estructurado** (structured outputs, esquema estricto):
  `estado`, `frase_principal`, `parrafos[{texto, citas[{articulo, pasaje}]}]`, `sugerencia`.
  Las reglas siguen aplicándose en código: una cita a un artículo fuera del contexto se descarta;
  un párrafo sin cita válida se elimina; si no queda ninguno, `estado = "sin_respuesta"`.
- **Validación de pasajes** (`rag/passages.py`): el backend nunca devuelve el texto que escribió el
  modelo, sino el tramo recortado del artículo real, así que el pasaje es siempre `None` o una
  subcadena literal (test de propiedad con 400 entradas aleatorias). Niveles: exacto → normalizado
  (espacios, comillas, guiones, mayúsculas, "…" internos, con mapa de índices al original) → difuso
  (`rapidfuzz` ≥ 90, ≥ 20 caracteres, ampliado a palabras completas) → `null` (se conserva la cita
  sin resaltado). Cambiar una palabra con significado jurídico ("potestad" → "elección") **no** pasa:
  resaltarlo afirmaría que la ley dice algo que no dice. *La maqueta del diseño cita el Art. 78 con
  "a elección del trabajador", que no es el texto vigente.*
- `POST /ask` devuelve exactamente el contrato (con `debug: true` agrega un bloque `debug`).
  `POST /ask/stream` (SSE) emite `etapa` (avance: reescribiendo, buscando, reordenando, revisando
  referencias, redactando), `articulos`, `frase`, `parrafo` (cada uno con sus pasajes ya validados),
  `fin` y `error`. `GET /meta` da la fecha de reforma y el número de artículos.
- El pipeline es un generador de eventos: un solo camino para `/ask`, `/ask/stream`, el CLI y los
  tests. Artículos de más de 20k caracteres (el 513) se envían solo con los chunks que vio el modelo
  (`texto_parcial: true`).

**Evaluación** (40 preguntas, modo completo, mismas reescrituras desde caché):

| | Texto plano (`full_rerank_rewrite`) | JSON con pasajes (`completo`) |
|---|---|---|
| Pasajes verificables | — | **100%** (98: 94 exactos, 4 normalizados) |
| Corrección | 4.75 | **4.86** |
| Falsa abstención | 0% | 0% |
| Abstención correcta | 100% | 100% |
| Cita esperada | 94% | 97% |
| Generación (mediana) | 5.4 s | **11.8 s** |

- **Pasajes 100% verificables:** con la instrucción de copiar "carácter por carácter", el modelo copió
  literal el 96% de las veces; el 4% restante solo difería en comillas o puntuación de las orillas
  (normalizado). El nivel difuso no hizo falta en esta corrida, pero queda como red de seguridad.
- **Corrección 4.86**, la más alta del proyecto. Pedir el pasaje obliga al modelo a anclar cada
  párrafo en un fragmento concreto. q20 (indemnización de 20 días) sube de 3 a 5 y q17 de 4 a 5;
  q13 queda en 5 (la corrección de regímenes especiales se confirma en las 36 preguntas, no solo en
  el subconjunto). Bajan de 5 a 4 q09, q19 y q28 (respuestas correctas, juzgadas algo incompletas:
  ruido del orden visto entre corridas).
- **Costo: la generación tarda el doble** (5.4 → 11.8 s de mediana) porque el modelo escribe más
  (los pasajes literales). En la demo el streaming lo compensa: la frase principal llega a ~5 s de
  empezar a generar y los párrafos después (prueba real: frase a los 18.5 s, fin a los 23 s, con 13 s
  de recuperación en este Mac).

**Bug encontrado en la prueba real (no en los tests):** el último párrafo nunca se emitía como evento
durante el streaming, porque solo se sabe completo cuando cierra el stream. Los tests no lo vieron
porque en el caso de prueba el último párrafo era justo uno descartado. Se corrigió y se agregaron dos
tests de regresión.

**Decisión:** se adopta. La respuesta estructurada mejora la corrección, cumple el contrato del
diseño y deja una métrica nueva y fuerte para el README.

## 2026-11-18 — Rediseño, fase 2: frontend en Next.js (`web/`)

Next.js 16 (App Router) + TypeScript + Tailwind 4. Los tokens de diseño viven en `@theme`
(`web/app/globals.css`) con sus nombres en español (`bg-papel`, `text-tinta`, `bg-sello`…); Source
Serif 4 (con eje `opsz`) e Instrument Sans vía `next/font`. Se habla con FastAPI desde el navegador
(`NEXT_PUBLIC_API_URL`), por SSE con `fetch` + `ReadableStream`.

**Pantallas y estados:** inicio; conversación con el panel de la ley enlazado (chip ↔ pestaña ↔
pasaje resaltado que se "pinta" en 350 ms); sin respuesta (tarjeta punteada con pregunta sugerida);
cargando (sin spinners: la etapa en curso y los números de artículo como pestañas en el panel);
error con "Reintentar" (y "Abrir ajustes" si el problema es la clave); popover de Ajustes.

**Ajustes al diseño original:**
- La marca ("§ Asistente LFT") va al centro de la pantalla de inicio, sobre el título.
- El tipo de respuesta (Detallada = modo completo / Rápida = modo ligero) va **dentro del campo de
  pregunta**, no en Ajustes. Ajustes queda con la clave de API y el estado de la conexión.
- El avance por etapas (opción 1) reemplaza el "Buscando en la ley…" fijo del panel.

**Desviaciones de las maquetas, con motivo:**
- Hover del botón de enviar: token `sello-oscuro` (`#2E2380`), no el `#3A2C93` de la maqueta
  (los tokens mandan; un solo valor de hover).
- Foco visible en los campos: las maquetas quitan el contorno del textarea/input; se muestra sobre la
  tarjeta completa (`has-[textarea:focus-visible]`), como pide la sección de accesibilidad.
- "Leer la ley completa" (PDF oficial) en lugar de "Leer el capítulo completo": no hay forma de
  enlazar a un capítulo.
- Punto de estado de la conexión en sello (lleno / hueco), no verde/rojo: un solo acento.
- La maqueta cita el Art. 78 con un texto que no es el vigente ("a elección del trabajador"); la app
  muestra siempre el texto real de la base.

**Cómo se verificó:** capturas a 1440×900 con Chrome sin interfaz controlado por DevTools Protocol
(script de ~60 líneas, sin Puppeteer). La ruta feliz usó una pregunta real; los estados (sin
respuesta, carga lenta, error 401, reintento, clave en `X-OpenAI-Key`) se probaron sustituyendo
`fetch` en la página por respuestas SSE simuladas: cero llamadas a OpenAI.

**Bugs encontrados en las capturas (no en el código revisado a ojo):**
- El resaltado salía amarillo intenso: el servidor de desarrollo servía un CSS viejo; se resolvió
  reiniciándolo (se verificó el color con una captura aislada).
- La tarjeta de error quedaba detrás del campo fijo de abajo: la vista no seguía el final de la
  conversación. Ahora baja al preguntar y, durante el streaming, solo si el usuario ya estaba abajo.
- ESLint (React Compiler): leer `localStorage` en un efecto causaba un render doble → se usa
  `useSyncExternalStore`.

## 2026-11-18 — La app exige la clave de API del usuario

El repositorio será público y el `.env` no se incluye. La clave de OpenAI del `.env` es de quien
desarrolla y solo sirve para pruebas, así que:
- **API:** `/ask` y `/ask/stream` exigen `X-OpenAI-Key`; sin ella responden 400 aunque el servidor
  tenga una clave en `.env` (test `test_env_key_is_never_used`). `/health` ya no informa si hay clave
  en el servidor (`requiere_clave_usuario: true`).
- **Frontend:** sin clave no se puede preguntar. Al intentarlo se abre Ajustes con la pregunta en
  espera y un botón "Guardar y preguntar"; el inicio muestra "Para preguntar necesitas tu clave…
  Agregar clave". La clave vive en `sessionStorage` (sobrevive a recargar, se borra al cerrar la
  pestaña); nunca en `localStorage` ni en el servidor.
- `OPENAI_API_KEY` del `.env` queda solo para `eval/run_eval.py` y el CLI.
