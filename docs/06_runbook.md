# Runbook

Cómo correr el sistema, qué esperar de cada comando y qué hacer cuando algo falla.

**Si solo quieres verlo funcionar:** está desplegado en
**https://noema.5-78-236-186.sslip.io**. No hace falta instalar nada.

---

## 1 · Desde cero, en local

```bash
git clone https://github.com/EduardoLoz12/factored-hackathon-2026-noema.git
cd factored-hackathon-2026-noema
cp .env.example .env
python -m pip install -e ".[dev]"
pre-commit install
```

Dos variables importan, y conviene saber qué pasa sin cada una:

| Variable | Sin ella |
|---|---|
| `JWT_SECRET` (≥ 32 caracteres) | `/verify` y la verificación de identidad devuelven 503. **Ninguna sesión se emite sin firmar.** |
| `ANTHROPIC_API_KEY` | Todo corre igual. La extracción y la redacción son deterministas. En `make eval` el brazo `baseline` queda marcado `no_corrido` en vez de simularse. |

Las credenciales de AWS para la ingesta están en la página 1 del diccionario de datos que
Factored repartió. **El repositorio no las contiene** y `gitleaks` corre en pre-commit y
en CI para que siga siendo así.

---

## 2 · Los comandos, en el orden en que se usan

```bash
make ingest     # S3 → data/bronze/*.parquet + manifest con checksums  (~4 min, 1.5 GB)
make audit      # perfil de calidad de las 13 tablas
make build      # dbt: bronze → silver → gold (perfil duckdb)
make cases      # genera el conjunto retenido: 87 es, 47 pt, 20 adversariales
make eval       # los tres brazos y la tabla comparativa
make serve      # API + interfaz en http://localhost:8000
make test       # pytest
make check      # lint + tests + gitleaks
```

**Sin `make ingest` no se puede correr el agente contra datos reales**, pero sí la suite
completa: las pruebas usan fixtures en memoria.

---

## 3 · Verificar que está sano

```bash
curl -s localhost:8000/health
```

Dice la verdad también cuando está roto: `listo`, el `motivo` si no lo está, la versión de
la política, la fecha de corte, si el SCM está encendido y los contadores de anclaje.

**La comprobación que importa antes de entregar** es que la suite pase con la bandera del
SCM en los dos estados. Si falla apagada, el tercer brazo de la evaluación no es medible:

```bash
pytest -q
SCM_ENABLED=false pytest -q
```

---

## 4 · Cuando algo falla

| Síntoma | Causa casi siempre | Qué hacer |
|---|---|---|
| `/health` dice `listo: false` con `falta data/noema.duckdb` | no se corrió el ETL | `make ingest && make build` |
| `/verify` devuelve 503 | `JWT_SECRET` ausente o corta | poner una de 32+ caracteres en `.env` |
| `make eval` deja el baseline en `no_corrido` | sin `ANTHROPIC_API_KEY` | es el comportamiento correcto; un baseline simulado sería peor |
| El agente escala siempre | la política se abstiene | mirar `avisos` en la respuesta: dice qué dato falta |
| Un turno responde «prefiero no darte cifras» | el verificador de anclaje bloqueó | **es el control funcionando**; el log dice qué cifra quedó huérfana |
| `IOException: file is already open` en DuckDB | dos procesos sobre la misma base | cerrar el `uvicorn` anterior |

**Regla general:** nada se cae en silencio. Toda llamada externa va en `try/except` con
fallback visible al cliente y log con contexto. Si algo falló y el cliente no vio nada,
eso es un bug en sí mismo.

---

## 5 · El despliegue

Corre como servicio de systemd detrás de nginx, con HTTPS por certbot.

```bash
# actualizar
cd /opt/noema/app
git fetch -q origin trabajo/cierre-entrega
git reset -q --hard origin/trabajo/cierre-entrega
systemctl restart noema.service
systemctl is-active noema.service
```

Tres cuidados que no son opcionales **porque el servidor está compartido con servicios en
vivo de otros proyectos**:

1. La unidad lleva `MemoryMax=320M`. Si noema se desmadra lo mata su propio cgroup y no el
   OOM killer eligiendo a otro proceso.
2. nginx se recarga **solo después** de que `nginx -t` pase.
3. Tras cada reinicio se comprueba que los otros servicios sigan activos.

La base del despliegue es una **muestra de 6.8 MB** que arma `scripts/make_demo_db.py`
desde los 2 854 MB de la completa: clientes reales y **enteros** —cada uno con todos sus
productos y transacciones— más las cotizaciones de moneda completas, porque sin ellas la
conversión a USD falla cerrado. La relectura se verifica tabla por tabla.

---

## 6 · Antes de cerrar una sesión de trabajo

```bash
python -m scripts.worklog "en qué trabajaste"
python -m scripts.checklist
git commit -m "Tipo (ÍTEM): qué cambió, en español"
```

La bitácora es parte del trabajo. El commit dice qué cambió; la bitácora dice por qué, con
qué fricción y qué quedó a medias.
