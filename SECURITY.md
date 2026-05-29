# Security Policy

## Supported Versions

`arca-mcp` está en fase 0.x y solo se soportan parches de seguridad sobre la última versión publicada.

| Versión | Soporte           |
|---------|-------------------|
| 0.6.x   | ✅ activa         |
| < 0.6   | ❌ sin soporte    |

## Reporting a Vulnerability

**No abras un issue público para vulnerabilidades.**

Reportá por email a **ward.maximiliano@gmail.com** con asunto `[arca-mcp security]`. Incluí:

- Descripción del problema y por qué es explotable.
- Versión afectada (`pip show arca-mcp` o commit SHA).
- Pasos para reproducir.
- Impacto estimado (filtración de claves, bypass de validación fiscal, RCE, etc.).

Esperá respuesta inicial dentro de 72 horas. Si el reporte es válido, coordinamos disclosure y fix antes de publicar el aviso.

## Scope

Tienen prioridad alta:

- Exposición de claves privadas o tokens WSAA en respuestas MCP, logs o archivos persistidos.
- Bypass de validaciones fiscales que permitan emitir comprobantes inválidos.
- Bypass del flujo `draft → validate → confirm` que evite el control humano.
- Inyecciones en llamadas SOAP/HTTP a ARCA.
- Vulnerabilidades en la cadena de dependencias que afecten al runtime del MCP.

Fuera de scope:

- Problemas en cuentas de ARCA del usuario (responsabilidad del usuario y de ARCA).
- Errores de configuración del usuario que no derivan en un defecto del código.
- Vulnerabilidades en software de terceros sin impacto demostrable sobre `arca-mcp`.
