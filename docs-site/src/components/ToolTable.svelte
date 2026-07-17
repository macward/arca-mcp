<script>
  // Tabla filtrable de tools. Recibe `tools` como prop (array de objetos).
  // Demuestra reactividad de Svelte 5: el filtro por texto y por capa es en vivo.
  let { tools = [] } = $props();

  let query = $state('');
  let layer = $state('all');

  const layers = ['all', 'local', 'red'];
  const layerLabel = { all: 'Todas', local: 'Local', red: 'Red (ARCA)' };

  const filtered = $derived(
    tools.filter((t) => {
      const matchesLayer = layer === 'all' || t.layer === layer;
      const q = query.trim().toLowerCase();
      const matchesQuery =
        !q || t.name.toLowerCase().includes(q) || t.desc.toLowerCase().includes(q);
      return matchesLayer && matchesQuery;
    })
  );
</script>

<div class="tt">
  <div class="tt-controls">
    <input
      type="search"
      placeholder="Filtrar tools…"
      bind:value={query}
      aria-label="Filtrar tools por nombre o descripción"
    />
    <div class="tt-layers" role="group" aria-label="Filtrar por capa">
      {#each layers as l}
        <button class:active={layer === l} onclick={() => (layer = l)}>{layerLabel[l]}</button>
      {/each}
    </div>
  </div>

  <table>
    <thead>
      <tr>
        <th>Tool</th>
        <th>Capa</th>
        <th>Descripción</th>
      </tr>
    </thead>
    <tbody>
      {#each filtered as t (t.name)}
        <tr>
          <td>
            {#if t.href}
              <a href={t.href}><code>{t.name}</code></a>
            {:else}
              <code>{t.name}</code>
            {/if}
          </td>
          <td>
            <span class="pill" class:net={t.layer === 'red'}>
              {t.layer === 'red' ? 'Red' : 'Local'}
            </span>
          </td>
          <td>{t.desc}</td>
        </tr>
      {/each}
      {#if filtered.length === 0}
        <tr><td colspan="3" class="empty">Sin resultados para “{query}”.</td></tr>
      {/if}
    </tbody>
  </table>
  <p class="tt-count">{filtered.length} de {tools.length} tools</p>
</div>

<style>
  .tt {
    margin: 1rem 0;
  }
  .tt-controls {
    display: flex;
    flex-wrap: wrap;
    gap: 0.6rem;
    align-items: center;
    margin-bottom: 0.7rem;
  }
  input[type='search'] {
    flex: 1 1 12rem;
    padding: 0.4rem 0.7rem;
    border: 1px solid var(--sl-color-gray-5);
    border-radius: var(--arca-radius, 0.6rem);
    background: var(--sl-color-black);
    color: var(--sl-color-white);
    font-size: var(--sl-text-sm);
    font-family: inherit;
  }
  .tt-layers {
    display: inline-flex;
    gap: 0.25rem;
  }
  .tt-layers button {
    padding: 0.35rem 0.7rem;
    border: 1px solid var(--sl-color-gray-5);
    border-radius: 999px;
    background: transparent;
    color: var(--sl-color-gray-2);
    cursor: pointer;
    font-size: var(--sl-text-xs);
    font-family: inherit;
  }
  .tt-layers button.active {
    background: var(--sl-color-accent);
    border-color: var(--sl-color-accent);
    color: var(--sl-color-white);
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--sl-text-sm);
  }
  th,
  td {
    text-align: left;
    padding: 0.5rem 0.6rem;
    border-bottom: 1px solid var(--sl-color-gray-5);
    vertical-align: top;
  }
  th {
    color: var(--sl-color-white);
    font-weight: 600;
  }
  .pill {
    font-size: var(--sl-text-xs);
    font-weight: 600;
    padding: 0.1rem 0.5rem;
    border-radius: 999px;
    background: var(--sl-color-accent-low);
    color: var(--sl-color-accent-high);
    white-space: nowrap;
  }
  .pill.net {
    background: #3a2e12;
    color: #ffd479;
  }
  :root[data-theme='light'] .pill.net {
    background: #fff3d6;
    color: #8a5a00;
  }
  .empty {
    color: var(--sl-color-gray-3);
    text-align: center;
    font-style: italic;
  }
  .tt-count {
    margin: 0.5rem 0 0;
    font-size: var(--sl-text-xs);
    color: var(--sl-color-gray-3);
  }
</style>
