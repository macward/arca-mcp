# Operaciones v0.3 — Caché WSAA y Rotación de Certificados

Documento de referencia para operadores. Cubre los procedimientos introducidos en v0.3:
limpieza del caché, rotación de certificados sin downtime, y troubleshooting.

---

## Descripción del caché

A partir de v0.3 el MCP persiste los Tickets de Acceso (TA) de WSAA en filesystem.

| Aspecto | Valor |
|---|---|
| Ubicación por defecto | `~/.arca-mcp/tokens/<cuit>.json` |
| Variable de entorno | `ARCA_TOKEN_CACHE_DIR` |
| Permisos del archivo | `0600` (solo propietario) |
| Permisos del directorio | `0700` |
| Umbral de auto-refresh | 10 minutos antes de expiración |
| TTL real del TA WSAA | ~12 horas (depende de ARCA) |

Además existe un caché en memoria (proceso-scoped, no persiste entre reinicios) con el mismo umbral de 10 minutos. Al arrancar el servidor, si el archivo de caché contiene un token válido, se restaura en memoria sin hacer login de red.

---

## Limpiar el caché

### Limpiar el TA de un CUIT específico

```bash
rm ~/.arca-mcp/tokens/<cuit>.json
```

Con directorio custom:

```bash
rm "$ARCA_TOKEN_CACHE_DIR/<cuit>.json"
```

El próximo request que use ese CUIT hará login automáticamente contra WSAA.

### Limpiar todos los tokens

```bash
rm ~/.arca-mcp/tokens/*.json
```

### Verificar estado del caché

```bash
ls -la ~/.arca-mcp/tokens/
```

Cada archivo debe tener permisos `-rw-------` (0600). Si los permisos son más permisivos, el servidor los detectará en la próxima escritura y los restablecerá.

Para inspeccionar el contenido de un token (sin exponer la private key):

```bash
cat ~/.arca-mcp/tokens/<cuit>.json | python3 -m json.tool
```

Campos clave: `expiration_time` (ISO 8601 UTC), `token`, `sign`.

---

## Rotar certificado sin downtime

Orden correcto para evitar ventana de login fallido:

### 1. Obtener el nuevo certificado

Generar el nuevo par cert/key y registrarlo en el portal ARCA (o con Playwright en v1.0). El nuevo certificado debe estar autorizado para los servicios WSFE/WSMTXCA antes de continuar.

### 2. Invalidar el caché del CUIT afectado

```bash
rm ~/.arca-mcp/tokens/<cuit>.json
```

Esto fuerza re-login con el nuevo certificado en el próximo request.

### 3. Verificar con el tool MCP `check_wsaa_setup`

Invocar el tool apuntando al nuevo cert:

```
check_wsaa_setup(cert_path="/ruta/al/nuevo.crt", key_path="/ruta/al/nuevo.key")
```

Resultado esperado: `ok: true` con el TA emitido.

### 4. Actualizar la configuración del servidor

Editar `~/.config/arca-mcp/config.json` (o variable de entorno equivalente) para apuntar a los nuevos paths de cert/key.

### 5. Reiniciar el servidor MCP

```bash
# Si corre como proceso manual:
# matar el proceso y volver a arrancar

# Si corre vía Claude Desktop / Zed:
# cerrar y reabrir la aplicación
```

> **Nota:** El orden importa. Si se cambia la configuración antes de invalidar el caché, el servidor intentará hacer login con el nuevo cert, pero WSAA podría rechazarlo si el cert anterior aún tiene un TA vivo. Invalidar primero elimina ese riesgo.

---

## Troubleshooting

### Error: "No se puede crear el directorio de caché de tokens"

```
ValueError: No se puede crear el directorio de caché de tokens '/ruta/tokens': [Errno 13] Permission denied
```

**Causa:** El servidor no tiene permisos para crear el directorio especificado.

**Solución:**

```bash
# Opción 1: crear el directorio manualmente
mkdir -p ~/.arca-mcp/tokens
chmod 700 ~/.arca-mcp/tokens

# Opción 2: usar un path alternativo vía variable de entorno
export ARCA_TOKEN_CACHE_DIR=/tmp/arca-tokens
```

---

### Error: "El directorio de caché de tokens no es escribible"

```
ValueError: El directorio de caché de tokens '/ruta/tokens' no es escribible.
Verificá permisos o configurá ARCA_TOKEN_CACHE_DIR con un path alternativo.
```

**Causa:** El directorio existe pero el usuario actual no puede escribir en él.

**Solución:**

```bash
chmod 700 ~/.arca-mcp/tokens
# o
chown $USER ~/.arca-mcp/tokens
```

---

### Token corrupto o inválido en disco

Si el archivo JSON está corrupto (por ejemplo, escritura interrumpida), el servidor lo trata como cache miss y hace re-login automáticamente. El archivo se sobreescribe con el token fresco.

Si el servidor está en un loop de login fallido, eliminar el archivo manualmente:

```bash
rm ~/.arca-mcp/tokens/<cuit>.json
```

---

### Permisos incorrectos en el archivo de token

Si el archivo tiene permisos más permisivos que 0600 (p.ej. por copia con `cp` sin `--no-preserve`):

```bash
chmod 600 ~/.arca-mcp/tokens/<cuit>.json
```

El servidor restaura los permisos a 0600 en cada escritura, por lo que esto solo es necesario si el archivo fue modificado externamente.

---

### WSAA responde "ya posee un TA válido"

Cuando el servidor no tiene el TA en caché (p.ej. tras reinicio) pero WSAA ya emitió uno para el mismo cert/servicio, WSAA rechaza re-emitir. El servidor registra esto como `ok: true` con mensaje "auth previa válida".

**Causa:** El TA anterior sigue vivo (TTL ~12h) pero no está en el caché local.

**Opciones:**
1. Esperar a que el TA expire naturalmente (el siguiente login funcionará).
2. Proveer el parámetro `cuit` en las llamadas; si el TA fue persistido antes del reinicio estará en disco y se restaurará.

---

## Variables de entorno relevantes

| Variable | Descripción | Default |
|---|---|---|
| `ARCA_TOKEN_CACHE_DIR` | Directorio de persistencia del caché de tokens | `~/.arca-mcp/tokens/` |
| `ARCA_TEST_CERT_PATH` | Cert para tests E2E de homologación | — |
| `ARCA_TEST_KEY_PATH` | Key para tests E2E de homologación | — |
| `ARCA_TEST_CUIT` | CUIT para tests E2E | — |

---

## Referencia de archivos

| Path | Descripción |
|---|---|
| `src/arca_mcp/wsaa/token_cache.py` | Implementación del caché filesystem |
| `src/arca_mcp/wsaa/token_store.py` | Caché en memoria (proceso-scoped) |
| `src/arca_mcp/wsaa/login.py` | Flujo de login con integración de caché |
| `src/arca_mcp/wsaa/retry.py` | Política de retry con backoff exponencial |
| `src/arca_mcp/wsaa/wsaa_logger.py` | Logging estructurado JSON de llamadas WSAA |
