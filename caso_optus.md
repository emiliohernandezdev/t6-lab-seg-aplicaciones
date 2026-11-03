# Caso Optus (sept. 2022) vs. mi laboratorio

> **Estudiante:** Emilio Andrés Hernández · **Carné:** 1593-20-19375 · **Correo:** ehernandez10@miumg.edu.gt
> **Curso:** Seguridad en Aplicaciones · **Catedrático:** Luis Enrique Rivas Ventura
> **Portada:** [PORTADA.md](PORTADA.md) · **Repositorio:** https://github.com/emiliohernandezdev/t6-lab-seg-aplicaciones

Según la presentación, en Optus quedaron expuestos nombres, fechas de nacimiento, teléfonos, direcciones y, en algunos casos, documentos de identidad, a través de una API con protección insuficiente. No se intentó reproducir nada contra infraestructura real.

| Qué se puede exponer si falla la autorización | Prueba de mi laboratorio que lo detecta | Control en el servidor | Evidencia de que funciona |
|---|---|---|---|
| Datos de otros clientes recorriendo IDs (nombre, dirección, pedidos) | BOLA: usuarioa pide `/api/orders/3`, que es de usuariob. En crAPI, ubicación de vehículos y pedidos ajenos | Comparar el dueño del objeto con el `sub` del token en cada endpoint. 404 igual para ajeno e inexistente | `test_bola_bfla.py::test_a_no_lee_pedido_de_b`, `test_ajeno_e_inexistente_responden_igual`. `BOLA_BFLA/antes.txt` da 200, `despues.txt` da 404 |
| Todo lo anterior sin siquiera iniciar sesión | Llamar a la API sin token o con un token falso, alterado, `alg=none` o de otro emisor | Validar el JWT completo antes de ejecutar nada: firma RS256 con JWKS, `iss`, `aud`, `exp` y `typ` | `test_jwt.py` (sin token, alterado, vencido, otro realm, ID token: 401). `JWT_OIDC/antes.txt` vs `despues.txt` |
| Extracción masiva (millones de registros) | 11 peticiones seguidas del mismo usuario; ráfaga de 300 contra el gateway | Rate limit por `sub` (10/10 s) en la API más `limit_req` por IP en el gateway | `test_rate_limit.py`: la petición 11 da 429 y B sigue con 200. `esquema_rate_limit/despues.txt` |
| Campos de más en la respuesta (hash, rol, notas internas, tarjeta, documento) | Comparar `GET /api/profile` con lo que de verdad necesita la pantalla. En crAPI, el feed de la comunidad devuelve el correo y el vehículo de otros usuarios | Modelo de respuesta con lista blanca (`ProfileOut`) | `test_perfil_no_expone_campos_internos`. `BOLA_BFLA/antes.txt` muestra la tarjeta y `despues.txt` no |
| Funciones internas o de administración alcanzables desde fuera | usuarioa llama a `/api/admin/audit`. Rutas como `/healthz` o `/docs` desde el gateway | Rol `admin` exigido en el servidor. El gateway solo publica una lista blanca de rutas | `test_usuario_comun_no_puede_ver_auditoria` (403), `test_rutas_no_publicadas` (404) |
| Un servicio interno expuesto que se salta el gateway | Conectar directo a `orders-api` sin certificado o con uno de otra CA. Revisar los puertos publicados | mTLS obligatorio (`CERT_REQUIRED`), red `backend` interna, sin `ports` | `test_mtls.py::test_api_rechaza_*`, `test_orders_api_no_publica_puertos`, `gateway_mTLS/host_segmentacion.txt` |
| Escalar privilegios modificando el propio perfil | `PATCH /api/profile` con `"role":"admin"` y releer el perfil | Lista blanca de campos editables (`extra="forbid"`) | `test_patch_perfil_con_role_admin_se_rechaza` (422, perfil sin cambios) |
