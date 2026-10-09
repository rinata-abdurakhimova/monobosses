"""Production entrypoint with one socket accepting IPv4 and IPv6 traffic."""
import os
import socket


def create_listener(port: int) -> socket.socket:
    if not 0 <= port <= 65535:
        raise ValueError("PORT must be between 0 and 65535")
    if not socket.has_dualstack_ipv6():
        raise RuntimeError("Deployment requires IPv4/IPv6 dual-stack socket support")
    return socket.create_server(("::", port), family=socket.AF_INET6,
                                dualstack_ipv6=True)


def main() -> None:
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be between 1 and 65535")
    with create_listener(port) as listener:
        print(f"API listening on IPv4 and IPv6, port {port}", flush=True)
        config = uvicorn.Config("vic.main:app", host="::", port=port, workers=1)
        uvicorn.Server(config).run(sockets=[listener])


if __name__ == "__main__":
    main()
