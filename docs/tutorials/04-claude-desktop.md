# Tutorial 4 — Integración con Claude Desktop

Este tutorial explica cómo conectar `arca-mcp` con Claude Desktop para que puedas emitir facturas y consultar el padrón directamente desde la interfaz de Claude.

> **Prerequisito:** Completá el [Tutorial 1 — Setup inicial](01-setup.md) y verificá que `setup_doctor` devuelva `ok: true` en todos los campos.

---

## Cómo funciona

Claude Desktop soporta el protocolo MCP. Cuando configurás `arca-mcp` como servidor, Claude puede llamar a sus herramientas (tools) durante la conversación: validar contribuyentes, crear borradores, emitir facturas, todo sin salir del chat.

El servidor corre localmente en tu máquina: los certificados y la clave privada **nunca salen de tu equipo**.

---

## 1. Ubicar el archivo de configuración de Claude Desktop

| Sistema operativo | Path |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |

Si el archivo no existe, crealo.

---

## 2. Agregar la configuración de arca-mcp

Editá `claude_desktop_config.json` y agregá la entrada dentro de `mcpServers`:

```json
{
  "mcpServers": {
    "arca": {
      "command": "uv",
      "args": [
        "run",
        "--project",
        "/ruta/absoluta/a/arca-mcp",
        "arca-mcp"
      ],
      "env": {
        "ARCA_CERT_PATH": "/ruta/absoluta/homo.crt",
        "ARCA_KEY_PATH": "/ruta/absoluta/homo.key",
        "ARCA_CUIT": "20123456789",
        "ARCA_ENVIRONMENT": "homologacion"
      }
    }
  }
}
```

Reemplazá:
- `/ruta/absoluta/a/arca-mcp` con el directorio donde clonaste el repositorio.
- `/ruta/absoluta/homo.crt` y `/ruta/absoluta/homo.key` con los paths reales de tus certificados.
- `20123456789` con tu CUIT.

### Si instalaste via pip / PyPI

Si instalaste `arca-mcp` con `pip install arca-mcp`, podés usar el ejecutable directamente:

```json
{
  "mcpServers": {
    "arca": {
      "command": "arca-mcp",
      "env": {
        "ARCA_CERT_PATH": "/ruta/absoluta/homo.crt",
        "ARCA_KEY_PATH": "/ruta/absoluta/homo.key",
        "ARCA_CUIT": "20123456789",
        "ARCA_ENVIRONMENT": "homologacion"
      }
    }
  }
}
```

---

## 3. Reiniciar Claude Desktop

Cerrá y volvé a abrir Claude Desktop. En el menú de la conversación deberías ver el ícono de herramientas (🔧) con `arca` listado.

---

## 4. Verificar la conexión

En el chat de Claude, escribí:

```
Ejecutá setup_doctor y contame el resultado
```

Claude va a llamar a la herramienta y mostrarte el diagnóstico. Si ves `ok: true` en todos los campos, la integración está funcionando.

---

## 5. Ejemplo de conversación

Una vez conectado podés usar lenguaje natural:

```
¿Está activo el contribuyente con CUIT 20123456789?
```

```
Necesito emitir una Factura B por $1.000 más IVA 21% al CUIT 27000000000
```

```
Mostrá las últimas 10 facturas emitidas
```

Claude interpretará tu solicitud, elegirá las herramientas correctas y te pedirá confirmación antes de emitir cualquier comprobante.

---

## Seguridad

- Los certificados y la clave privada **solo existen en tu máquina**. Claude Desktop los pasa como variables de entorno al proceso `arca-mcp`, que nunca los expone en respuestas.
- Cada emisión requiere confirmación explícita en el paso `confirm_voucher_creation`. Claude no puede emitir facturas sin que vos lo apruebes.
- Para producción (v1.0), cambiá `ARCA_ENVIRONMENT` a `produccion` y usá certificados productivos. Los ambientes son estrictamente separados.

---

## Troubleshooting

### Claude no muestra las herramientas de arca

1. Verificá que el JSON en `claude_desktop_config.json` sea válido (sin comas sobrantes, sin comillas simples).
2. Verificá que el path al proyecto y a los certificados sean rutas absolutas.
3. Revisá los logs de Claude Desktop: menú **Help → Open Logs**.

### El servidor arranca pero `setup_doctor` falla

Seguí las instrucciones del [Tutorial 1 — Setup inicial](01-setup.md).

### `uv: command not found`

Instalá `uv`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

O usá el path completo al ejecutable `uv` en la configuración.
