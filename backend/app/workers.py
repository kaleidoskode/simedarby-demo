from uvicorn.workers import UvicornWorker


class ConfigurableWorker(UvicornWorker):
    """Uvicorn worker used by gunicorn_conf.py.

    `ws="websockets"` is explicit because the seating plan pushes seat lock
    events over a WebSocket; the default "auto" resolves to the same library
    but only when it happens to be installed, and a silent fallback to "none"
    would reject every upgrade request at runtime.

    `proxy_headers` lets the app see the real client scheme and address when it
    sits behind a load balancer or ingress.
    """

    CONFIG_KWARGS = {
        "loop": "auto",
        "http": "auto",
        "ws": "websockets",
        "proxy_headers": True,
    }
