# Tutorial 1 — Setup inicial

Este tutorial cubre la instalación de `arca-mcp`, la obtención de certificados de homologación y la verificación del setup con `setup_doctor`.

---

## Requisitos previos

- Python 3.12 o superior
- `uv` instalado (`pip install uv` o `brew install uv`)
- CUIT habilitado en ARCA (cualquier CUIT de persona jurídica o física activa)
- Acceso al portal ARCA para gestionar certificados

---

## 1. Clonar e instalar

```bash
git clone https://github.com/macward/arca-mcp
cd arca-mcp
uv sync
```

Verificá la instalación:

```bash
uv run arca-mcp --help
```

---

## 2. Obtener certificados de homologación

ARCA tiene un ambiente de pruebas completamente separado del productivo. Para usarlo necesitás un certificado emitido por la CA de homologación.

### 2.1 Generar la clave privada y el CSR

```bash
# Clave privada RSA 2048
openssl genrsa -out homo.key 2048

# CSR (Certificate Signing Request)
openssl req -new -key homo.key -out homo.csr \
  -subj "/C=AR/O=MiEmpresa/CN=MiServicio/serialNumber=CUIT 20123456789"
```

Reemplazá `20123456789` con tu CUIT real (sin guiones).

### 2.2 Solicitar el certificado en el portal ARCA

1. Ingresá a [https://homo.afip.gob.ar](https://homo.afip.gob.ar) con tu CUIT y clave fiscal.
2. Navegá a **Administración de Certificados Digitales**.
3. Pegá el contenido del archivo `homo.csr` en el campo de solicitud.
4. Descargá el certificado emitido y guardalo como `homo.crt`.

### 2.3 Autorizar el servicio wsfe

En el mismo portal, en **Administración de Relaciones**, autorizá el servicio `wsfe` para el certificado que acabás de crear.

---

## 3. Configurar variables de entorno

Creá un archivo `.env` en la raíz del proyecto:

```env
ARCA_CERT_PATH=/ruta/absoluta/homo.crt
ARCA_KEY_PATH=/ruta/absoluta/homo.key
ARCA_CUIT=20123456789
ARCA_ENVIRONMENT=homologacion
```

---

## 4. Verificar el setup con `setup_doctor`

Iniciá el servidor MCP y llamá a la herramienta `setup_doctor`:

```bash
uv run arca-mcp
```

En otro terminal (o desde Claude Desktop), invocá:

```json
{
  "tool": "setup_doctor"
}
```

Una respuesta exitosa luce así:

```json
{
  "certificate": { "ok": true, "subject": "...", "expires": "2027-01-01" },
  "private_key": { "ok": true },
  "cert_key_match": { "ok": true },
  "wsaa_login": { "ok": true, "token_expires": "2026-05-29T12:00:00" },
  "wsfe_authorization": { "ok": true }
}
```

Si algún campo tiene `"ok": false`, el mensaje `"message"` te indica exactamente qué corregir.

---

## Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| `MISSING_CONFIG` | Variable de entorno no seteada | Revisá el `.env` y el path |
| `WSAA_AUTH_FAILED` | Certificado vencido o key incorrecta | Regenerar cert o verificar que key y cert correspondan |
| `CERT_KEY_MISMATCH` | Usaste la key de otro certificado | Regenerar CSR con la key correcta |
| Certificado rechazado en portal | CN o serialNumber incorrecto | El `serialNumber` debe ser exactamente `CUIT 20XXXXXXXXX` |

---

## Próximo paso

Con el setup funcionando, seguí con [Tutorial 2 — Emitir una factura](02-emitir-factura.md).
