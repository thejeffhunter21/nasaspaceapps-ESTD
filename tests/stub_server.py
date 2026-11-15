"""A tiny HTTP server for tests: answers fixed JSON per path, no uvicorn needed."""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@contextmanager
def serve(routes: dict[str, tuple[int, object]]):
    """routes: path (with query) -> (status, json body). Unknown paths answer 404."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            status, body = routes.get(self.path, (404, {"detail": "Not Found"}))
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def healthy_api(region="Phoenix study area", source="NASA MODIS",
                method="Seasonal Mann-Kendall test") -> dict:
    """Routes for an API that passes every smoke check."""
    trend = {"slope": 0.01, "slope_unit": "degC/month", "p": 0.001, "tau": 0.3,
             "trend": "increasing"}
    results = {"region_id": "phoenix_study_area", "region": region, "series": [{}] * 264,
               "trend": trend, "explanation": "x", "explanation_source": "fallback",
               "source": source, "method": method, "units": "degC"}
    one = {**results, "region": region}
    return {
        "/health": (200, {"status": "ok"}),
        "/": (200, {"name": "API", "try": []}),
        "/results": (200, results),
        "/regions": (200, {"regions": [{"region_id": "phoenix_study_area"}]}),
        "/series": (200, one),
        "/trend": (200, one),
        "/trend?region=phoenix_study_area": (200, one),
        "/series?region=phoenix_study_area": (200, one),
        "/demo": (200, {"cases": []}),
        "/version": (200, {"commit": "abc"}),
        "/anomaly?region=phoenix_study_area": (200, {"series": [], "baseline": []}),
        "/series?region=not_a_region": (404, {"detail": "Unknown region"}),
        "/series?region=%3Cscript%3E": (422, {"detail": "bad"}),
    }
