"""Gateway routes that surface service metadata and simple health checks."""

from __future__ import annotations

from typing import Dict
from urllib import error, request
import json

from flask import Blueprint, current_app, jsonify


bp = Blueprint("gateway", __name__)


def _service_map() -> Dict[str, str]:
    configured = current_app.config.get("SERVICE_DEFAULTS", {})
    return {name: url.rstrip("/") for name, url in configured.items()}


@bp.get("/health")
def health():
    return jsonify({"status": "ok", "services": list(_service_map().keys())})


@bp.get("/services")
def list_services():
    return jsonify({"services": _service_map()})


@bp.get("/services/<service_name>/health")
def service_health(service_name: str):
    services = _service_map()
    base_url = services.get(service_name)
    if not base_url:
        return jsonify({"msg": f"Unknown service '{service_name}'"}), 404

    url = f"{base_url}/health"
    timeout = current_app.config.get("REQUEST_TIMEOUT", 2.0)
    try:
        with request.urlopen(url, timeout=timeout) as upstream:
            body = upstream.read().decode("utf-8")
            content_type = upstream.headers.get("Content-Type", "")
            if "json" in content_type:
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError:  # pragma: no cover
                    payload = body
            else:
                payload = body
            status_code = upstream.status
        return (
            jsonify(
                {
                    "service": service_name,
                    "status_code": status_code,
                    "payload": payload,
                }
            ),
            status_code,
        )
    except error.URLError as exc:  # pragma: no cover - network errors
        return jsonify({"service": service_name, "error": str(exc)}), 502
