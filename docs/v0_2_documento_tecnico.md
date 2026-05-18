# MCP ARCA v0.2 — Documento Técnico

## Qué se implementó

v0.2 agrega la **Lookup Layer**: consultas deterministas de solo lectura contra ARCA.
Sin emisión de comprobantes, sin escritura. Cuatro módulos nuevos:

| Módulo | Descripción |
|---|---|
| `wsaa/token_store.py` | Cache en memoria de tokens WSAA; evita re-login por sesión |
| `wsfe/client.py` | Cliente SOAP WSFEv1 — 5 operaciones `FEParamGet*` de catálogo |
| `padron/client.py` | Cliente SOAP `ws_sr_padron_a4` — consulta de contribuyentes por CUIT |
| `validation/catalogs.py` | Catálogos AFIP hardcodeados para validaciones sin red |

## Arquitectura de la Lookup Layer

```
Tool MCP (lookup.py)
    └── resolve_runtime_config()        # lee Settings + env vars
         └── _get_wsaa_token()          # WSAA login → token_store cache
              └── wsfe_client / padron_client   # SOAP zeep → CatalogItem / PersonaDetails
```

El resolver central (`resolve_runtime_config`) fusiona las env vars `ARCA_CERT_PATH`,
`ARCA_KEY_PATH`, `ARCA_ENVIRONMENT` con overrides opcionales por llamada.
Toda falla cruza la frontera MCP como `ArcaError` estructurado: nunca excepciones crudas.

## Token Cache

`wsaa/token_store.py` opera sobre un dict de módulo (no un singleton de clase):
- Clave: `(cert_path, key_path, environment, service)`
- Invalidación: `expiration_time > now + 5 min`
- El `login.py` consulta el store antes de ir a WSAA; si hay hit, reutiliza.
- `clear_store()` disponible para tests.

## 10 Tools MCP expuestos (`mcp/lookup.py`)

### Catálogo WSFEv1 (requieren cert + WSAA)

| Tool | Operación SOAP | Retorno |
|---|---|---|
| `get_voucher_types()` | `FEParamGetTiposCbte` | `list[CatalogItem]` |
| `get_document_types()` | `FEParamGetTiposDoc` | `list[CatalogItem]` |
| `get_tax_types()` | `FEParamGetTiposTributos` | `list[CatalogItem]` |
| `get_aliquot_types()` | `FEParamGetTiposIva` | `list[CatalogItem]` |
| `get_currency_types()` | `FEParamGetTiposMonedas` | `list[CatalogItem]` |

`CatalogItem`: `{id: str, description: str}`

### Padrón A4 (requieren cert + WSAA con autorización ws_sr_padron_a4)

| Tool | Retorno |
|---|---|
| `get_taxpayer_details(cuit: str)` | `PersonaDetails` |
| `validate_taxpayer_status(cuit: str)` | `TaxpayerStatus` |

`PersonaDetails`: `{cuit, denomination, status, fiscal_address, activities}`
`TaxpayerStatus`: `{cuit, active: bool, status_description}`

### Validaciones puras (sin red, sin cert)

| Tool | Descripción |
|---|---|
| `validate_invoice_type(invoice_type: str)` | Verifica contra catálogo local AFIP |
| `validate_vat_condition(vat_condition: str)` | Verifica condición IVA |
| `validate_currency(currency: str)` | Verifica código de moneda (ej: "PES", "DOL") |

Todas retornan `{"campo": valor, "valid": bool}`.

## Endpoints de homologación

| Servicio | Endpoint |
|---|---|
| WSAA | `https://wsaahomo.afip.gov.ar/ws/services/LoginCms` |
| WSFEv1 | `https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL` |
| Padrón A4 | `https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA4?WSDL` |

v0.2 solo soporta `"homologacion"`. `"produccion"` retorna `ArcaError(UNSUPPORTED_ENVIRONMENT)`.

## E2E opt-in

`tests/e2e/test_lookup_e2e.py` contiene tests marcados `@pytest.mark.e2e`:
- Skipean automáticamente si `ARCA_TEST_CERT_PATH` / `ARCA_TEST_KEY_PATH` no están seteados
- El fixture `padron_auth` skipea con mensaje explícito si el cert no tiene autorización para `ws_sr_padron_a4`
- Excluir del run normal: `pytest -m "not e2e"`
- Incluir: `ARCA_TEST_CERT_PATH=... ARCA_TEST_KEY_PATH=... pytest -m e2e`

## Tests

- 292 unit tests pasando, 1 skipped (E2E sin credenciales)
- Cobertura: wsfe client, padron client, token store, tools MCP lookup, validaciones de catálogo
