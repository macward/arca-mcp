// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import svelte from '@astrojs/svelte';

// https://astro.build/config
export default defineConfig({
  // GitHub Pages (project page): https://macward.github.io/arca-mcp
  site: 'https://macward.github.io',
  base: '/arca-mcp',
  integrations: [
    starlight({
      title: 'arca-mcp',
      description:
        'Servidor MCP para operaciones fiscales ARCA/AFIP. Determinista, seguro y Human-in-the-Loop.',
      defaultLocale: 'root',
      locales: {
        root: { label: 'Español', lang: 'es' },
      },
      social: [
        {
          icon: 'github',
          label: 'GitHub',
          href: 'https://github.com/macward/arca-mcp',
        },
      ],
      editLink: {
        baseUrl: 'https://github.com/macward/arca-mcp/edit/main/docs-site/',
      },
      customCss: ['./src/styles/custom.css'],
      sidebar: [
        {
          label: 'Empezar',
          items: [
            { label: 'Qué es arca-mcp', slug: 'empezar/introduccion' },
            { label: 'Instalación', slug: 'empezar/instalacion' },
            { label: 'Configuración', slug: 'empezar/configuracion' },
            { label: 'Quickstart', slug: 'empezar/quickstart' },
          ],
        },
        {
          label: 'Conceptos',
          items: [
            { label: 'Arquitectura', slug: 'conceptos/arquitectura' },
            { label: 'Human in the Loop', slug: 'conceptos/human-in-the-loop' },
            { label: 'Ambientes', slug: 'conceptos/ambientes' },
            { label: 'Seguridad', slug: 'conceptos/seguridad' },
          ],
        },
        {
          label: 'Guías',
          items: [
            { label: 'Setup y certificados', slug: 'guias/setup' },
            { label: 'Emitir una factura', slug: 'guias/emitir-factura' },
            { label: 'Consultas al padrón', slug: 'guias/padron' },
            { label: 'Claude Desktop', slug: 'guias/claude-desktop' },
          ],
        },
        {
          label: 'Referencia de tools',
          items: [
            { label: 'Índice', slug: 'referencia/tools' },
            { label: 'Setup', slug: 'referencia/setup' },
            { label: 'Certificados', slug: 'referencia/certificados' },
            { label: 'Catálogos y validación', slug: 'referencia/lookup' },
            { label: 'Padrón', slug: 'referencia/padron' },
            { label: 'Facturación', slug: 'referencia/facturacion' },
            { label: 'Errores', slug: 'referencia/errores' },
          ],
        },
      ],
    }),
    svelte(),
  ],
});
