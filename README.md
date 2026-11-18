# DocuVali · EP3 ITY1102

Sistema de IA que **extrae y valida documentos tributarios chilenos** (facturas, boletas y notas de crédito) y decide, con una explicación, si cada documento se **aprueba automáticamente** o va a **revisión humana**.

Autor: David Antonio Jorquera Rivera · Duoc UC · Arquitectura de Sistemas de IA (ITY1102)

## Arquitectura

```
Cliente (dashboard / Postman)
   │ HTTPS (TLS) + X-API-Key
   ▼
Nginx ──► API REST FastAPI ──► RabbitMQ (cola documentos.procesar + DLQ)
                │                        │
                │                        ▼
                │                 Worker(s) ──► Amazon Textract (OCR de facturas)
                │                        │──► Reglas SII (RUT módulo 11, IVA 19 %, XML DTE)
                │                        └──► Endpoint Amazon SageMaker (modelo de decisión)
                ▼                                   │
          SQLite (resultados) ◄─────────────────────┘
                ▲
Dashboard Streamlit (KPIs, explicación de cada decisión, calidad del modelo)
```

| Componente | Tecnología | Carpeta |
|---|---|---|
| API REST + Swagger | FastAPI (`/docs`) | `app/api` |
| Procesamiento asíncrono | RabbitMQ + worker Python | `app/worker`, `app/common/broker.py` |
| OCR (servicio AIaaS) | Amazon Textract `AnalyzeExpense` (en local: Tesseract) | `app/common/extractor.py` |
| Modelo | Regresión logística (scikit-learn) en Amazon SageMaker | `model/` |
| Dashboard | Streamlit | `dashboard/` |
| Despliegue | Docker Compose en EC2 + Nginx TLS | `docker-compose.yml`, `deploy/` |
| Pruebas | pytest (22 casos) + Locust | `tests/`, `loadtest/` |

## Endpoints principales

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Estado (sin autenticación) |
| POST | `/api/v1/documentos` | Sube imagen/PDF (+ XML del SII opcional). Responde `202` con un ID |
| POST | `/api/v1/documentos/estructurado` | Envía variables ya extraídas a la cola |
| GET | `/api/v1/documentos/{id}` | Estado y resultado (decisión, probabilidad y razones) |
| GET | `/api/v1/documentos` | Últimos documentos |
| POST | `/api/v1/predicciones` | Predicción en tiempo real del modelo |
| GET | `/api/v1/metricas` | Indicadores para el dashboard |

Todas las rutas `/api/v1` requieren el encabezado `X-API-Key` y tienen límite de solicitudes por minuto (`429`). El dashboard (pantalla interna de los revisores) pide usuario y contraseña en Nginx (`DASHBOARD_USUARIO` / `DASHBOARD_CLAVE`); para cambiarla: `bash deploy/crear_clave_dashboard.sh`.

## Ejecutar en local (sin AWS)

```bash
cp .env.example .env            # en .env: EXTRACTOR=local, PREDICTOR=local y tu DASHBOARD_CLAVE
bash deploy/generar_certificado.sh 127.0.0.1   # también crea el usuario del dashboard
docker compose up -d --build
# Dashboard: https://localhost/dashboard/   Swagger: https://localhost/docs
```

## Desplegar en AWS Academy

1. **Modelo en SageMaker** (desde una Notebook Instance de SageMaker):
   `pip install -U sagemaker && python deploy/sagemaker_desplegar.py`
   Entrena el modelo con un Training Job, crea el endpoint `docuvali-endpoint` y configura autoescalado (1 a 2 instancias).
2. **Servidor EC2** (Amazon Linux 2023, `t3.medium`, rol `LabInstanceProfile`, puertos 22/80/443):
   `git clone <este repo> && cd docuvali-ep3 && bash deploy/ec2_instalar.sh`
3. Abrir `https://<IP-pública>/dashboard/` y `https://<IP-pública>/docs`.
4. Al terminar: `python deploy/sagemaker_eliminar.py` para no gastar crédito.

## Entrenar y probar

```bash
pip install -r requirements-dev.txt
python data/generate_dataset.py          # dataset sintético de 8.000 documentos etiquetados
python model/train.py                    # entrena, valida y exporta model.json + metrics.json
python data/generar_muestras.py          # 13 facturas y boletas de muestra (ficticias) para la demo
pytest -v                                # 24 pruebas (las de RabbitMQ requieren un RabbitMQ activo)
locust -f loadtest/locustfile.py --host http://localhost:8000 --headless -u 50 -r 10 -t 60s
```

## Resultados del modelo (conjunto de prueba, 1.600 documentos)

| Accuracy | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|
| 0,829 | 0,663 | 0,778 | 0,716 | 0,895 |

## Datos

El dataset es **sintético**: replica las proporciones del caso DocuVali (8.000 documentos etiquetados, 25 % de fotos de mala calidad) porque no se usan datos reales de clientes (Ley 21.719). Las empresas y RUT de las muestras son ficticios.

## Uso de IA generativa

Se utilizó Claude (Anthropic) como apoyo para buscar información técnica y desarrollar el código y la documentación del proyecto.
