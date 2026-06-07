"""Observabilidade SUPREME: métricas Prometheus e logging estruturado mínimo."""
from __future__ import annotations

import time
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

HTTP_REQUESTS = Counter("supreme_http_requests_total", "Total de requests HTTP", ["method", "path", "status"])
HTTP_LATENCY = Histogram("supreme_http_request_duration_seconds", "Latência HTTP", ["method", "path"])
INGEST_EVENTS = Counter("supreme_ingest_events_total", "Eventos recebidos/armazenados", ["result"])
PIPELINE_RUNS = Counter("supreme_pipeline_runs_total", "Execuções do pipeline", ["status"])
DLQ_SIZE = Gauge("supreme_dead_letter_queue_size", "Itens em Dead Letter Queue")

class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        route = request.scope.get("route")
        path = getattr(route, "path", request.url.path)
        HTTP_REQUESTS.labels(request.method, path, str(response.status_code)).inc()
        HTTP_LATENCY.labels(request.method, path).observe(time.perf_counter() - start)
        return response

def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
