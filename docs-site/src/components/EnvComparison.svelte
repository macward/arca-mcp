<script>
  // Toggle homologación ⇄ producción. Svelte 5 runes.
  let env = $state('homologacion');

  const data = {
    homologacion: {
      badge: 'homologacion',
      cls: 'homo',
      impacto: 'Ninguno — no hay efecto fiscal real',
      cert: 'Certificado "Computadores Test"',
      portal: 'https://wsaahomo.afip.gov.ar',
      cuando: 'Desarrollo, pruebas y CI',
      estado: 'Habilitado desde v0.1',
    },
    produccion: {
      badge: 'produccion',
      cls: 'prod',
      impacto: 'Irreversible — emite comprobantes fiscales reales',
      cert: 'Certificado productivo',
      portal: 'https://wsaa.afip.gov.ar',
      cuando: 'Operación real con clientes',
      estado: 'Planificado para v1.0',
    },
  };

  const cur = $derived(data[env]);
</script>

<div class="ec">
  <div class="ec-toggle" role="group" aria-label="Seleccionar ambiente">
    <button class:active={env === 'homologacion'} onclick={() => (env = 'homologacion')}>
      Homologación
    </button>
    <button class:active={env === 'produccion'} onclick={() => (env = 'produccion')}>
      Producción
    </button>
  </div>

  <div class="ec-card" class:prod={cur.cls === 'prod'}>
    <div class="ec-head">
      <code>ARCA_ENVIRONMENT={cur.badge}</code>
    </div>
    <dl>
      <div><dt>Impacto</dt><dd>{cur.impacto}</dd></div>
      <div><dt>Certificado</dt><dd>{cur.cert}</dd></div>
      <div><dt>Endpoint WSAA</dt><dd><code>{cur.portal}</code></dd></div>
      <div><dt>Cuándo usarlo</dt><dd>{cur.cuando}</dd></div>
      <div><dt>Estado en arca-mcp</dt><dd>{cur.estado}</dd></div>
    </dl>
  </div>
</div>

<style>
  .ec {
    margin: 1rem 0;
  }
  .ec-toggle {
    display: inline-flex;
    border: 1px solid var(--sl-color-gray-5);
    border-radius: 999px;
    padding: 0.2rem;
    margin-bottom: 0.8rem;
  }
  .ec-toggle button {
    padding: 0.35rem 0.9rem;
    border: none;
    border-radius: 999px;
    background: transparent;
    color: var(--sl-color-gray-2);
    cursor: pointer;
    font-family: inherit;
    font-size: var(--sl-text-sm);
  }
  .ec-toggle button.active {
    background: var(--sl-color-accent);
    color: var(--sl-color-white);
  }
  .ec-card {
    border: 1px solid var(--arca-homo, #2e7d32);
    border-left-width: 4px;
    border-radius: var(--arca-radius, 0.6rem);
    padding: 1rem;
  }
  .ec-card.prod {
    border-color: var(--arca-prod, #b3261e);
  }
  .ec-head {
    margin-bottom: 0.6rem;
  }
  dl {
    margin: 0;
    display: grid;
    gap: 0.5rem;
  }
  dl div {
    display: grid;
    grid-template-columns: 11rem 1fr;
    gap: 0.5rem;
  }
  dt {
    font-weight: 600;
    color: var(--sl-color-white);
  }
  dd {
    margin: 0;
    color: var(--sl-color-gray-2);
  }
  @media (max-width: 30rem) {
    dl div {
      grid-template-columns: 1fr;
      gap: 0.1rem;
    }
  }
</style>
