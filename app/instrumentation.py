"""
OpenTelemetry SDK setup for the demo app.

Must be imported BEFORE any other app modules so the global tracer/meter
providers are in place before Flask or any instrumented library is loaded.

Usage: import instrumentation  (at the top of app.py)

Environment variables:
  OTEL_SERVICE_NAME                      (default: demo-app)
  OTEL_EXPORTER_OTLP_ENDPOINT           (default: http://otel-collector.platform:4318)
  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT    (overrides the traces path)
  OTEL_EXPORTER_OTLP_METRICS_ENDPOINT   (overrides the metrics path)
  APP_VERSION                            (default: 1.0.0)
  APP_ENV                                (default: development)
"""

import os
import signal

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_service_name    = os.getenv("OTEL_SERVICE_NAME", "demo-app")
_otlp_endpoint   = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector.platform:4318")
_trace_endpoint  = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",  f"{_otlp_endpoint}/v1/traces")
_metric_endpoint = os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", f"{_otlp_endpoint}/v1/metrics")

resource = Resource.create({
    "service.name":            _service_name,
    "service.version":         os.getenv("APP_VERSION", "1.0.0"),
    "deployment.environment":  os.getenv("APP_ENV", "development"),
})

# ── Traces ────────────────────────────────────────────────────────────────────
_tracer_provider = TracerProvider(resource=resource)
_tracer_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=_trace_endpoint))
)
trace.set_tracer_provider(_tracer_provider)

# ── Metrics ───────────────────────────────────────────────────────────────────
# PeriodicExportingMetricReader is required — without it, all meter instruments
# are registered but silently discarded, producing no data in Prometheus/Grafana.
_meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[
        PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=_metric_endpoint),
            export_interval_millis=10_000,
        )
    ],
)
metrics.set_meter_provider(_meter_provider)


def _shutdown(signum, frame):
    _tracer_provider.shutdown()
    _meter_provider.shutdown()
    raise SystemExit(0)


signal.signal(signal.SIGTERM, _shutdown)

print(f"OpenTelemetry initialized for {_service_name} → {_otlp_endpoint}")
