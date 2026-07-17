<script>
  // Stepper interactivo del flujo Human-in-the-Loop de emisión.
  // Componente Svelte 5 (runes), estilado con las variables de Starlight.
  const steps = [
    {
      tool: 'create_voucher_draft',
      title: 'Crear borrador',
      side: 'Local',
      desc: 'Persiste un draft en SQLite local (~/.arca-mcp/drafts.db) en estado PENDING. No toca ARCA.',
      irreversible: false,
    },
    {
      tool: 'validate_voucher_draft',
      title: 'Validar',
      side: 'Local',
      desc: 'Corre las reglas de política fiscal. Si pasa, el draft queda VALIDATED. Sigue sin emitir nada.',
      irreversible: false,
    },
    {
      tool: 'confirm_voucher_creation',
      title: 'Confirmar',
      side: 'Irreversible',
      desc: 'Solicita el CAE a WSFE (FECAESolicitar). Requiere idempotency_key. Acá recién se emite el comprobante fiscal.',
      irreversible: true,
    },
  ];

  let active = $state(0);
</script>

<div class="flow">
  <ol class="flow-tabs" role="tablist" aria-label="Flujo de emisión">
    {#each steps as step, i}
      <li>
        <button
          role="tab"
          aria-selected={active === i}
          class:active={active === i}
          class:danger={step.irreversible}
          onclick={() => (active = i)}
        >
          <span class="num">{i + 1}</span>
          <span class="lbl">{step.title}</span>
        </button>
        {#if i < steps.length - 1}<span class="arrow" aria-hidden="true">→</span>{/if}
      </li>
    {/each}
  </ol>

  <div class="flow-panel" role="tabpanel">
    <div class="flow-head">
      <code>{steps[active].tool}</code>
      <span class="side" class:danger={steps[active].irreversible}>{steps[active].side}</span>
    </div>
    <p>{steps[active].desc}</p>
    {#if steps[active].irreversible}
      <p class="warn">⚠️ Único paso que produce efectos fiscales reales. En producción es irreversible.</p>
    {/if}
  </div>
</div>

<style>
  .flow {
    border: 1px solid var(--sl-color-gray-5);
    border-radius: var(--arca-radius, 0.6rem);
    overflow: hidden;
    margin: 1rem 0;
  }
  .flow-tabs {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.25rem;
    list-style: none;
    margin: 0;
    padding: 0.6rem;
    background: var(--sl-color-gray-6);
  }
  .flow-tabs li {
    display: flex;
    align-items: center;
    margin: 0;
  }
  button[role='tab'] {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.35rem 0.7rem;
    border: 1px solid transparent;
    border-radius: 999px;
    background: transparent;
    color: var(--sl-color-gray-2);
    cursor: pointer;
    font-size: var(--sl-text-sm);
    font-family: inherit;
  }
  button[role='tab']:hover {
    background: var(--sl-color-gray-5);
  }
  button[role='tab'].active {
    background: var(--sl-color-accent);
    color: var(--sl-color-white);
    border-color: var(--sl-color-accent);
  }
  button[role='tab'].active.danger {
    background: var(--arca-prod, #b3261e);
    border-color: var(--arca-prod, #b3261e);
  }
  .num {
    display: inline-grid;
    place-items: center;
    width: 1.35rem;
    height: 1.35rem;
    border-radius: 50%;
    background: var(--sl-color-gray-4);
    color: var(--sl-color-gray-1);
    font-size: var(--sl-text-xs);
    font-weight: 700;
  }
  button[role='tab'].active .num {
    background: rgba(255, 255, 255, 0.25);
    color: var(--sl-color-white);
  }
  .arrow {
    color: var(--sl-color-gray-3);
    padding: 0 0.15rem;
  }
  .flow-panel {
    padding: 1rem;
  }
  .flow-head {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.4rem;
  }
  .flow-head code {
    font-size: var(--sl-text-base);
  }
  .side {
    font-size: var(--sl-text-xs);
    font-weight: 600;
    padding: 0.1rem 0.5rem;
    border-radius: 999px;
    background: var(--arca-homo-bg, #e7f4e8);
    color: var(--arca-homo, #2e7d32);
  }
  .side.danger {
    background: var(--arca-prod-bg, #fbe9e7);
    color: var(--arca-prod, #b3261e);
  }
  .flow-panel p {
    margin: 0.4rem 0 0;
    color: var(--sl-color-gray-2);
  }
  .warn {
    font-size: var(--sl-text-sm);
    color: var(--sl-color-gray-1);
  }
</style>
