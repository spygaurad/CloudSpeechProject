# telemetry.py — import this FIRST in app/main.py
import os

from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor


def init_telemetry() -> None:
    """Call this before any other setup in your application."""
    connection_string = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not connection_string:
        raise ValueError("APPLICATIONINSIGHTS_CONNECTION_STRING not set in .env")
    configure_azure_monitor(connection_string=connection_string)

    # Enable OpenTelemetry auto-instrumentation for FastAPI and HTTP requests
    FastAPIInstrumentor().instrument()
    RequestsInstrumentor().instrument()

    print("Application Insights initialized with FastAPI instrumentation.")
