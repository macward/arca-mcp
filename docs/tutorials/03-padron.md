# Tutorial 3 — Consultas al padrón

`arca-mcp` expone dos herramientas para consultar el padrón de contribuyentes de ARCA usando el servicio `ws_sr_padron_a4`.

> **Prerequisito:** Completá el [Tutorial 1 — Setup inicial](01-setup.md). No necesitás tener `wsfe` autorizado; el padrón usa un servicio distinto.

---

## Autorizar el servicio de padrón

En el portal ARCA, en **Administración de Relaciones**, autorizá el servicio `ws_sr_padron_a4` para tu certificado. Es un servicio distinto al de emisión (`wsfe`), aunque pueden coexistir en el mismo certificado.

---

## `get_taxpayer_details` — Datos completos del contribuyente

Retorna el detalle fiscal de un CUIT: razón social, estado, domicilio fiscal y actividades.

```json
{
  "tool": "get_taxpayer_details",
  "arguments": {
    "cuit": "20123456789"
  }
}
```

Respuesta exitosa:

```json
{
  "cuit": "20123456789",
  "denomination": "ACME S.A.",
  "status": "ACTIVO",
  "fiscal_address": {
    "street": "Av. Corrientes",
    "number": "1234",
    "city": "Ciudad Autónoma de Buenos Aires"
  },
  "activities": ["620100", "620200"]
}
```

### Campos de la respuesta

| Campo | Descripción |
|---|---|
| `cuit` | CUIT consultado |
| `denomination` | Razón social o nombre y apellido |
| `status` | Estado en el padrón: `ACTIVO`, `INACTIVO`, `CANCELADO`, `BLOQUEADO`, `CLAUSURADO` |
| `fiscal_address` | Domicilio fiscal registrado en ARCA (puede ser `null`) |
| `activities` | Códigos de actividad CLAE declarados |

---

## `validate_taxpayer_status` — Verificación rápida de estado

Útil para validar que un receptor es un contribuyente activo antes de emitirle una factura.

```json
{
  "tool": "validate_taxpayer_status",
  "arguments": {
    "cuit": "20123456789"
  }
}
```

Respuesta:

```json
{
  "cuit": "20123456789",
  "active": true,
  "status_description": "Activo"
}
```

Si el contribuyente no está activo:

```json
{
  "cuit": "20999999990",
  "active": false,
  "status_description": "Inactivo"
}
```

El campo `active` es siempre un booleano, lo que facilita su uso en flujos automáticos sin necesidad de parsear strings.

---

## Validaciones locales (sin red)

Para validaciones frecuentes que no requieren consultar ARCA, usá las herramientas locales:

### `validate_invoice_type`

```json
{
  "tool": "validate_invoice_type",
  "arguments": {
    "cbte_tipo": 6,
    "receptor_condition": "CONSUMIDOR_FINAL"
  }
}
```

### `validate_vat_condition`

```json
{
  "tool": "validate_vat_condition",
  "arguments": {
    "condition": "RESPONSABLE_INSCRIPTO"
  }
}
```

### `validate_currency`

```json
{
  "tool": "validate_currency",
  "arguments": {
    "currency_code": "DOL"
  }
}
```

Estas herramientas operan offline contra tablas locales y no consumen cuota de servicios ARCA.

---

## Errores frecuentes en padrón

| Causa | Descripción | Acción |
|---|---|---|
| `PADRON_NOT_FOUND` | El CUIT no existe en el padrón | Verificar el CUIT ingresado |
| `WSAA_AUTH_FAILED` | Error de autenticación con WSAA | Revisar certificado y autorización del servicio `ws_sr_padron_a4` |
| `MISSING_CONFIG` | Variables de entorno sin configurar | Verificar `ARCA_CERT_PATH`, `ARCA_KEY_PATH`, `ARCA_CUIT` |
| `ARCA_SERVICE_ERROR` | Error de red o SOAP contra ARCA | Verificar conectividad y estado de los servicios ARCA |

---

## Próximo paso

Aprendé a conectar `arca-mcp` con Claude Desktop en [Tutorial 4 — Integración con Claude Desktop](04-claude-desktop.md).
