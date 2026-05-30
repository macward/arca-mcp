# Tutorial 2 — Emitir una factura

Este tutorial muestra el flujo completo de emisión de una Factura B (cbte_tipo 6) en el ambiente de homologación: `create_voucher_draft → validate_voucher_draft → confirm_voucher_creation`.

> **Prerequisito:** Completá el [Tutorial 1 — Setup inicial](01-setup.md) antes de continuar.

---

## Conceptos clave

### El flujo de tres pasos es obligatorio

```
create_voucher_draft → validate_voucher_draft → confirm_voucher_creation
```

No existe un atajo. Este diseño previene errores costosos: un comprobante rechazado por ARCA genera un "hueco" en la numeración que puede traer problemas contables.

### Los borradores son locales

`create_voucher_draft` solo persiste el borrador en tu máquina (SQLite en `~/.arca-mcp/drafts.db`). Nada se envía a ARCA hasta `confirm_voucher_creation`.

### Idempotencia en la confirmación

`confirm_voucher_creation` requiere una `idempotency_key` única por operación. Si el proceso falla a mitad de camino y reintentás con la misma key, obtenés el resultado original sin volver a emitir.

---

## Paso 1 — Consultar el último número de comprobante

Antes de emitir conviene saber en qué número va el punto de venta:

```json
{
  "tool": "get_last_voucher_number",
  "arguments": {
    "cbte_tipo": 6,
    "punto_venta": 1
  }
}
```

Respuesta:

```json
{ "cbte_nro": 41 }
```

El siguiente comprobante será el `42`. En homologación ARCA asigna el número automáticamente; este dato es solo referencial.

---

## Paso 2 — Crear el borrador

```json
{
  "tool": "create_voucher_draft",
  "arguments": {
    "cbte_tipo": 6,
    "punto_venta": 1,
    "fecha_cbte": "20260529",
    "cuit_receptor": "27000000000",
    "doc_tipo": 80,
    "imp_neto": "1000.00",
    "alicuota_id": "5"
  }
}
```

Respuesta:

```json
{
  "draft_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "PENDING",
  "imp_total": "1210.00",
  "cbte_tipo": 6,
  "punto_venta": 1,
  "fecha_cbte": "20260529"
}
```

Guardá el `draft_id` — lo necesitás en los siguientes pasos.

### Parámetros de uso frecuente

| Parámetro | Descripción | Valores comunes |
|---|---|---|
| `cbte_tipo` | Tipo de comprobante | `6` = Factura B, `11` = C, `1` = A |
| `punto_venta` | Número de punto de venta ARCA | `1` en homologación |
| `fecha_cbte` | Fecha de emisión `YYYYMMDD` | Fecha de hoy |
| `doc_tipo` | Tipo de documento receptor | `80` = CUIT, `96` = DNI |
| `alicuota_id` | Alícuota de IVA | `"5"` = 21%, `"4"` = 10.5%, `"3"` = 0% |

Para obtener todos los tipos disponibles usá `get_voucher_types`, `get_document_types` y `get_aliquot_types`.

---

## Paso 3 — Validar el borrador

```json
{
  "tool": "validate_voucher_draft",
  "arguments": {
    "draft_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
  }
}
```

Respuesta exitosa:

```json
{
  "is_valid": true,
  "status": "VALIDATED",
  "errors": []
}
```

Si hay errores:

```json
{
  "is_valid": false,
  "status": "PENDING",
  "errors": [
    { "field": "cuit_receptor", "message": "CUIT inválido: dígito verificador incorrecto" }
  ]
}
```

Corregí los errores y volvé a llamar `validate_voucher_draft`. Podés crear un nuevo draft con los datos corregidos si preferís.

---

## Paso 4 — Confirmar la emisión

```json
{
  "tool": "confirm_voucher_creation",
  "arguments": {
    "draft_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "idempotency_key": "factura-cliente-abc-001"
  }
}
```

Respuesta exitosa:

```json
{
  "cae": "74291826403951",
  "cbte_nro": 42,
  "cae_fch_vto": "20260608",
  "status": "CONFIRMED"
}
```

El `cae` es el Código de Autorización Electrónico emitido por ARCA. Guardalo: es la prueba fiscal de la operación.

---

## Paso 5 — Consultar el historial

Podés listar los comprobantes confirmados en cualquier momento:

```json
{
  "tool": "list_vouchers",
  "arguments": {
    "status": "CONFIRMED",
    "limit": 20
  }
}
```

---

## Paso 6 — Obtener el comprobante desde ARCA

Si necesitás verificar un comprobante ya emitido contra los registros de ARCA:

```json
{
  "tool": "get_voucher_info",
  "arguments": {
    "cbte_tipo": 6,
    "punto_venta": 1,
    "cbte_nro": 42
  }
}
```

---

## Errores frecuentes en emisión

| Causa | Descripción | Acción |
|---|---|---|
| `DRAFT_NOT_VALIDATED` | Se intentó confirmar sin validar | Llamar `validate_voucher_draft` primero |
| `WSFE_REJECTED` | ARCA rechazó el comprobante | Ver campo `observaciones` en la respuesta |
| `EMISSION_IN_PROGRESS` | Confirmación duplicada en curso | Esperar o usar otra `idempotency_key` |
| `DRAFT_NOT_FOUND` | `draft_id` inexistente o de otro proceso | Verificar que el `draft_id` sea el correcto |

---

## Próximo paso

Aprendé a consultar datos de contribuyentes en [Tutorial 3 — Consultas al padrón](03-padron.md).
