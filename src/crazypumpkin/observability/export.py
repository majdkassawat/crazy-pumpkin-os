"""Prometheus-compatible metrics export.

Exposes collected metrics in Prometheus text exposition format via a
simple HTTP ``/metrics`` endpoint that can be scraped by external
monitoring tools.
"""

from __future__ import annotations

import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any

from crazypumpkin.observability.metrics import get_metrics_snapshot


def format_metrics(snapshot: dict[str, Any] | None = None) -> str:
    """Render the current metrics as Prometheus text exposition format.

    Args:
        snapshot: Optional pre-fetched metrics snapshot.  When *None* a
            fresh snapshot is obtained via :func:`get_metrics_snapshot`.

    Returns:
        A string in Prometheus text format containing
        ``task_throughput``, ``agent_uptime_seconds``, and
        ``error_rate_total`` metrics.
    """
    if snapshot is None:
        snapshot = get_metrics_snapshot()

    lines: list[str] = []

    # task_throughput gauge
    lines.append("# HELP task_throughput Total number of tasks completed")
    lines.append("# TYPE task_throughput gauge")
    lines.append(f"task_throughput {snapshot['tasks_completed']}")

    # error_rate_total gauge
    lines.append("# HELP error_rate_total Total number of errors recorded")
    lines.append("# TYPE error_rate_total gauge")
    lines.append(f"error_rate_total {snapshot['errors']}")

    # agent_uptime_seconds gauge (one time-series per agent)
    lines.append(
        "# HELP agent_uptime_seconds Agent uptime in seconds"
    )
    lines.append("# TYPE agent_uptime_seconds gauge")
    agent_uptime: dict[str, float] = snapshot.get("agent_uptime", {})
    for agent_id, seconds in sorted(agent_uptime.items()):
        safe_id = agent_id.replace('"', '\\"')
        lines.append(
            f'agent_uptime_seconds{{agent_id="{safe_id}"}} {seconds:.6f}'
        )

    lines.append("")  # trailing newline per spec
    return "\n".join(lines)


class MetricsHandler(BaseHTTPRequestHandler):
    """HTTP request handler that serves ``/metrics`` in Prometheus format."""

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/metrics":
            body = format_metrics().encode("utf-8")
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "text/plain; version=0.0.4; charset=utf-8",
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Suppress default stderr logging."""


def start_metrics_server(
    port: int = 9100,
    host: str = "0.0.0.0",
) -> HTTPServer:
    """Start a background HTTP server that exposes ``/metrics``.

    Args:
        port: TCP port to listen on (default ``9100``).
        host: Bind address (default ``"0.0.0.0"``).

    Returns:
        The running :class:`HTTPServer` instance.  Call
        ``server.shutdown()`` to stop it.
    """
    server = HTTPServer((host, port), MetricsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
