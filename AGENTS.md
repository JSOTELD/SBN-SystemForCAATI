# Context-efficient repository navigation

- Respeta la solicitud del usuario y estas instrucciones antes de investigar.
- No leas ni vuelques todo el repositorio. Consulta `.codex-context/project-summary.md`
  solo si necesitas orientación general.
- Empieza con `python tools/code-context/context.py query "solicitud"`.
  La consulta actualiza automáticamente solo archivos cambiados; no abre JSON completos.
- Sigue: solicitud → consulta → módulo/símbolos → dependencias → archivos afectados
  → fragmentos necesarios → implementación.
- Usa `impact "archivo:símbolo" --depth 2` antes de ampliar el alcance.
  Los resultados son estáticos: confirma relaciones relevantes en el código.
- Lee únicamente archivos probablemente relacionados; usa `rg -n` con rutas y
  fragmentos pequeños. Amplía una relación a la vez si falta evidencia.
- No releas archivos sin cambios ni cargues dependencias, backups, binarios,
  lockfiles completos o directorios generados.
- Después de cambios ejecuta `python tools/code-context/context.py update`.
  Reserva `rebuild` para cambios del extractor, arquitectura o índices dañados.
- Mantén resumen y arquitectura al cambiar el stack. Valida cambios con pruebas
  pertinentes; no ejecutes scripts de importación/restauración contra datos reales.

Comandos y límites: `.codex-context/README.md`. Python estándar, sin instalación.
