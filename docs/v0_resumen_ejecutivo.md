# MCP ARCA — Entrega v0 (Setup Doctor)

## En una frase

Construimos la primera capa del producto: un **asistente de diagnóstico** que detecta automáticamente por qué falla la conexión con ARCA y le dice al usuario, en lenguaje claro, qué tiene que arreglar.

---

## El problema que estamos resolviendo

Hoy, cuando un desarrollador o una empresa intenta integrarse con ARCA (el sistema fiscal argentino), se encuentra con un proceso largo y frustrante:

- Hay que generar certificados digitales
- Hay que configurar autenticación con AFIP
- Hay que pasar por homologación antes de producción
- Cuando algo falla, el sistema devuelve mensajes incomprensibles tipo *"Error CMS inválido"* o *"alias no autorizado"*
- No queda claro **qué** está mal ni **dónde**

El resultado: integraciones que tardan días o semanas, y errores que requieren conocimiento muy especializado para diagnosticar.

---

## Qué entregamos en esta primera versión

Una herramienta que **antes de intentar facturar**, valida que toda la configuración esté correcta y, si algo falla, te dice exactamente qué.

Concretamente, el sistema ahora puede responder estas preguntas automáticamente:

| Pregunta | ¿Lo resuelve? |
|---|---|
| ¿Mi certificado es válido? | ✅ |
| ¿Mi certificado venció o todavía no es vigente? | ✅ |
| ¿Mi clave privada está bien? | ✅ |
| ¿El certificado y la clave corresponden entre sí? | ✅ |
| ¿Quién es el dueño del certificado y hasta cuándo dura? | ✅ |
| ¿AFIP me reconoce y me deja entrar? | ✅ |
| ¿Tengo permiso para usar el servicio de facturación electrónica? | ✅ |
| **Diagnóstico completo en un solo paso** | ✅ |

---

## Cómo se compara con el "antes"

**Antes:**

> *"Error 0: CMS inválido"*
>
> El usuario no sabe si es el certificado, la clave, la conexión, los permisos, o algo más. Empieza una investigación manual de horas.

**Ahora:**

> ```
> Diagnóstico:
>   ✅ Clave privada — OK
>   ✅ Certificado — OK
>   ❌ Coincidencia certificado/clave — El certificado no corresponde a la clave privada
>   ⏭ Login AFIP — saltado (problema previo)
>   ⏭ Acceso al servicio — saltado (problema previo)
> ```

El usuario sabe **exactamente** qué está mal y dónde mirar.

---

## Valor para el negocio

1. **Reducción dramática del tiempo de onboarding.** Un problema que antes requería abrir un ticket de soporte o consultar a un experto, ahora se diagnostica solo en segundos.

2. **Menos fricción para que un agente de IA pueda integrarse.** Hoy un agente que intente usar ARCA falla con mensajes ininteligibles. Con esta capa, el agente recibe respuestas estructuradas y puede actuar sobre ellas o pedir ayuda al usuario de forma precisa.

3. **Base sólida para todo lo que viene.** Las siguientes fases (consulta de comprobantes, emisión de facturas, automatización del portal) se apoyan en esta capa de diagnóstico. Si la base falla, todo falla. Construirla primero fue una decisión estratégica.

4. **Seguridad por diseño.** En ningún momento la clave privada del usuario se expone fuera del sistema local. Esto es crítico para confiar el producto a clientes empresariales.

---

## Qué viene después

El producto tiene un camino claro de evolución:

| Fase | Qué entrega |
|---|---|
| **v0 (entregado)** | Diagnóstico completo del setup técnico |
| v1 | Autenticación recurrente con cache de sesiones |
| v2 | Consultas básicas: ¿quién es este contribuyente?, ¿cuál fue mi última factura? |
| v3 | Emisión de facturas con confirmación obligatoria del usuario |
| v4 | Automatización del portal AFIP (registro de certificados sin intervención manual) |
| v5 | Operación en producción real con todas las salvaguardas |

Cada fase agrega capacidades sobre la anterior, sin romper lo que ya funciona.

---

## Filosofía del producto

Un principio guía todas las decisiones:

> **El agente propone. El sistema valida. AFIP confirma. El usuario autoriza acciones irreversibles.**

Esto significa:

- El sistema **no toma decisiones fiscales por su cuenta**. No inventa montos, no elige tipos de factura, no asume cosas.
- **Nunca emite comprobantes sin confirmación explícita.** Las acciones que mueven plata o tienen consecuencias legales siempre requieren un "sí" del usuario.
- **Errores opacos se transforman en errores claros.** No le pasamos al usuario lo que dice AFIP; le decimos qué significa.

---

## Estado actual del proyecto

- ✅ Repositorio privado creado y versionado
- ✅ Empaquetado en Docker (corre en cualquier máquina sin instalación)
- ✅ Cobertura de pruebas automatizadas amplia
- ✅ Documentación técnica para los siguientes desarrollos
- ✅ Plan de fases definido hasta producción

El producto está listo para usar internamente como herramienta de diagnóstico y como base para construir las siguientes capacidades.
