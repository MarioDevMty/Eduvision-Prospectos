AUTOMATIZACIÓN DE REBOTES Y RESPUESTAS - EDUVISION

ARCHIVOS NUEVOS
- migrate_mailbox_automation.py
- database/repositories/mailbox_state.py
- install_mailbox_task.ps1
- uninstall_mailbox_task.ps1

ARCHIVOS PARA REEMPLAZAR
- database/repositories/mail_tracking.py
- services/mailbox_sync.py
- sync_mailbox.py
- pages/marketing.py
- database/repositories/marketing.py

INSTALACIÓN

1. Detener Streamlit:
   Ctrl + C

2. Crear respaldo:
   Copy-Item data\eduvision.db backups\eduvision_antes_sync_automatico.db

3. Copiar todos los archivos respetando sus rutas.

4. Ejecutar migración:
   python migrate_mailbox_automation.py

   Resultado esperado:
   MIGRATION OK: mailbox automatic sync

5. Compilar:
   python -m py_compile migrate_mailbox_automation.py
   python -m py_compile database\repositories\mailbox_state.py
   python -m py_compile database\repositories\mail_tracking.py
   python -m py_compile services\mailbox_sync.py
   python -m py_compile sync_mailbox.py
   python -m py_compile pages\marketing.py

6. Primera sincronización manual:
   python sync_mailbox.py --apply --limit 500 --user-id 1 --source INITIAL

7. Instalar tarea automática de Windows:
   powershell -ExecutionPolicy Bypass -File .\install_mailbox_task.ps1

   Resultado esperado:
   TASK OK: Eduvision Mailbox Sync

8. Iniciar Streamlit:
   streamlit run app.py

VALIDACIÓN

En Marketing > Operar campaña debe aparecer:
- Última revisión
- Rebotes aplicados
- Respuestas aplicadas
- Sin coincidencia
- Botón Sincronizar bandeja ahora
- Historial reciente de sincronización

La tarea de Windows ejecuta cada 10 minutos:
.venv\Scripts\python.exe sync_mailbox.py --apply --limit 500 --user-id 1 --source SCHEDULER

COMPORTAMIENTO

ERROR SMTP inmediato
- se registra durante el envío;
- aparece de inmediato en Incidencias de entrega.

REBOTE DIFERIDO
- llega a INBOX;
- la tarea lo detecta;
- cambia ENVIADO a REBOTE;
- aparece en Incidencias de entrega.

RESPUESTA
- In-Reply-To o References coincide con Message-ID;
- cambia a RESPONDIO;
- aparece en Seguimiento.

MENSAJE NO RELACIONADO
- no modifica campañas;
- queda registrado como sin coincidencia.

La sincronización usa UID incremental, registra cada mensaje procesado y
bloquea ejecuciones simultáneas.
