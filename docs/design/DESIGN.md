# Asistente LFT: especificación de diseño

Referencia visual: el lienzo "Asistente LFT — rediseño" y los archivos de `docs/design/referencia/`
(`Main.dc.html` = inicio, `Respuesta.dc.html` = conversación con citas).
Esos archivos son maquetas en un formato de componentes propio (`{{variable}}`, `<sc-if>`,
`class Component extends DCLogic`). **No se copian tal cual**: se leen para sacar estructura, medidas,
colores, textos y comportamiento, y se reimplementan en el frontend real.

Contexto de uso: la app se usa **en local**, después de clonar el repo. Es una app de escritorio en el
navegador; no hay versión móvil.

## Idea central

Es un chatbot: llegas y preguntas. La portada no tiene nada más que el título, el campo de
pregunta y cuatro temas sugeridos.

Lo memorable aparece al responder: la respuesta y la ley están **lado a lado y enlazadas**. Cada
cita en la respuesta es un botón ("Art. 76") que abre ese artículo en el panel derecho, con el
pasaje exacto que sustenta la respuesta **marcado con resaltador**. Todo lo demás es sobrio.

## Tokens

### Color
| Nombre | Hex | Uso |
|---|---|---|
| papel | `#ECEEEA` | fondo de la app (gris verdoso frío, no crema) |
| hoja | `#F7F8F5` | superficies elevadas: panel de la ley, campo de pregunta |
| hoja-pie | `#EFF1EC` | pie del panel de la ley |
| tinta | `#18202B` | texto principal |
| tinta-ley | `#2A323D` | texto largo en serif (respuesta y artículos) |
| grafito | `#4F5864` | texto secundario |
| grafito-claro | `#5D6570` | metadatos y ayudas (mínimo 4.5:1 sobre papel) |
| sello | `#4536A6` | color de acento: citas, botón de enviar, enlaces, foco |
| sello-oscuro | `#2E2380` | hover |
| sello-claro | `#E2DEF6` | fondo de chip de cita inactivo |
| resaltador | `#E9F27A` | pasaje que sustenta la respuesta |
| burbuja | `#E1E4DE` | mensaje del usuario, hover |
| línea | `#CDD2CB` | bordes y divisores |
| borde-campo | `#B9BFB7` | borde de inputs |

Un solo acento (sello). Sin degradados decorativos ni modo oscuro en esta versión.

### Tipografía (Google Fonts)
- **Source Serif 4** (400/500): título, respuesta y texto de la ley. Es la voz de "la ley".
- **Instrument Sans** (400/500/600): toda la interfaz.
- Sin monoespaciada ni etiquetas en MAYÚSCULAS. Todo en minúsculas normales (sentence case).

| Rol | Fuente | Tamaño / interlineado | Peso |
|---|---|---|---|
| Título de inicio | Serif | 48px / 1.08, tracking −0.02em, centrado | 500 |
| Primera frase de la respuesta | Serif | 30px / 1.2 | 500 |
| Cuerpo de la respuesta | Serif | 19px / 1.7 | 400 |
| Título de artículo | Serif | 32px | 500 |
| Texto del artículo | Serif | 18px / 1.72 | 400 |
| Interfaz | Sans | 14–17px | 500/600 |
| Metadatos | Sans | 13px | 400 |

### Forma y profundidad
- Hoja de la ley: radio **6px** (se siente como papel), sombra `0 1px 0 #CDD2CB, 0 30px 60px -30px rgba(24,32,43,.28)`.
- Campo de pregunta: radio 18px. Burbujas: 16px. Botones: 10–12px. Chips de cita: 7px. Temas sugeridos: píldora.
- Área clicable mínima: 44px en botones principales.

## Pantallas

1. **Inicio** (minimalista). Encabezado casi invisible: logo "§ Asistente LFT" a la izquierda e
   ícono de ajustes a la derecha. Al centro, vertical y horizontalmente: el título "¿Qué dice la
   ley sobre tu trabajo?", el campo de pregunta (máx. 680px, botón de enviar con flecha en sello) y
   cuatro temas sugeridos como píldoras discretas (Días de vacaciones, Despido sin causa, Horas
   extra, Permiso de paternidad). Al hacer clic en uno, se envía una pregunta completa sobre ese tema.
   Pie con una sola línea: fecha de la última reforma (leída de `GET /meta`) y el aviso legal.
   Enter envía; Shift+Enter hace salto de línea.
2. **Respuesta**. Al enviar la primera pregunta, la portada se transforma en la conversación:
   conversación a la izquierda (máx. 720px) y panel de la ley a la derecha (`position: sticky`).
   La respuesta abre con una frase directa en serif grande y luego párrafos, cada uno terminado en
   su chip de cita. Un clic en un chip o en una pestaña del panel cambia el artículo mostrado; el
   chip y la pestaña activos se pintan en sello sólido. Si el artículo remite a otro (campo
   `referencias`), aparece "Este artículo remite al artículo X" como enlace. Bajo la respuesta:
   "Copiar respuesta" y "3 artículos citados". El campo para seguir preguntando queda fijo abajo.
   En el encabezado aparece "Nueva consulta", que regresa a la portada.
3. **Sin respuesta** (abstención): borde punteado, ícono de lupa, título "Esto no está en la ley",
   explicación breve y un botón con una pregunta alternativa que sí está en la ley.
   Nunca se presenta como error.

## Estados (impleméntalos con el mismo lenguaje)
- **Cargando**: la respuesta se transmite por streaming. Mientras se recupera, el panel muestra
  "Buscando en la ley…" y los números de artículo aparecen como pestañas. Sin spinners a pantalla completa.
- **Error de API**: mensaje en la conversación que diga qué pasó y qué hacer ("No pudimos
  conectar con el servicio. Revisa tu clave en Ajustes o intenta de nuevo."), con botón "Reintentar".
- **Ajustes** (popover desde el ícono): tipo de respuesta (Detallada / Rápida), clave de API y
  estado de la conexión.

## Movimiento
Un solo momento orquestado: al cambiar de artículo, el resaltador se "pinta" de izquierda a derecha
(animando `background-size` de 0 a 100% en ~350ms). La transición de la portada a la conversación
puede ser un desplazamiento simple del campo de pregunta hacia abajo. Nada más se anima solo.
Respeta `prefers-reduced-motion`.

## Accesibilidad
- Chips y pestañas son `<button>` con `aria-pressed`. El pasaje es un `<mark>`.
- Foco visible: `outline: 2px solid #4536A6; outline-offset: 2px`.
- El panel es `<aside aria-label="Texto de la ley">`, con `aria-live="polite"` en el título del artículo.
- Contraste mínimo de 4.5:1 en todo el texto.

## Contrato de API que necesita este diseño

El resaltado exige que el backend devuelva **la frase exacta del artículo** que usó para cada afirmación:

```json
{
  "estado": "respondida",
  "frase_principal": "Te corresponden 16 días laborables de vacaciones pagadas al año.",
  "parrafos": [
    {
      "texto": "La ley parte de 12 días al cumplir el primer año…",
      "citas": [{ "articulo": "76", "pasaje": "que en ningún caso podrá ser inferior a doce días laborables, …" }]
    }
  ],
  "sugerencia": null,
  "articulos": {
    "76": { "titulo": "Título tercero, Condiciones de trabajo", "capitulo": "Capítulo IV, Vacaciones",
            "texto": "…", "referencias": [] }
  },
  "fecha_reforma": "2026-05-14"
}
```

- `estado` puede ser `"respondida"` o `"sin_respuesta"`. Con `"sin_respuesta"`, `sugerencia` trae una pregunta alternativa.
- `pasaje` debe ser una **subcadena literal** de `articulos[n].texto`. Valídalo en el backend: si
  no coincide, búscalo con coincidencia difusa y, si falla, descarta el resaltado pero conserva la cita.
- Esa validación es una métrica nueva de evaluación: "% de pasajes verificables".
- `GET /meta` devuelve la fecha de reforma y el número de artículos.
