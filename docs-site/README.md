# arca-mcp — Documentación

Sitio de documentación de uso de **arca-mcp**, construido con
[Astro](https://astro.build) + [Starlight](https://starlight.astro.build) y
componentes [Svelte](https://svelte.dev) nativos.

## Stack

- **Astro** — framework de sitio estático
- **Starlight** — theme de documentación
- **Svelte 5** — componentes interactivos (`src/components/*.svelte`)

Los componentes interactivos (stepper del flujo de emisión, tabla filtrable de tools,
comparador de ambientes) están hechos con Svelte nativo y estilados con las variables
CSS de Starlight — sin Tailwind ni dependencias de UI externas.

## Desarrollo

```bash
cd docs-site
npm install
npm run dev      # servidor local en http://localhost:4330
npm run build    # build estático a dist/
npm run preview  # sirve el build de dist/ en http://localhost:4330
```

> El proyecto usa el puerto **4330** (fijado en `package.json`) para no colisionar
> con otros dev servers de Astro corriendo en la máquina (que ocuparían el 4321 por
> defecto y mostrarían otro sitio).

## Estructura

```
src/
  content/docs/       # páginas .mdx (Empezar, Conceptos, Guías, Referencia)
  components/          # componentes Svelte: FlowStepper, ToolTable, EnvComparison
  styles/custom.css    # paleta y estilos propios
astro.config.mjs       # integraciones + sidebar
```

## Fuentes de contenido

Las guías migran los tutoriales de `../docs/tutorials/`. La referencia de tools se
deriva de `../src/arca_mcp/mcp/` (setup, certificates, lookup, invoicing). Al agregar o
cambiar tools, actualizá las páginas de `src/content/docs/referencia/`.

## Deploy

Ajustá `site` y (si aplica) `base` en `astro.config.mjs` según el destino
(GitHub Pages, Netlify, etc.) y publicá el contenido de `dist/`.
