"""Servidor WSGI local con Waitress para sesiones de revision.

Escucha solo en la interfaz local; ngrok publica el puerto mediante HTTPS.
Se confian unicamente los encabezados de proxy enviados desde 127.0.0.1.
"""
import argparse
import os

from waitress import serve


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PUERTO", "8000")))
    parser.add_argument("--threads", type=int, default=6)
    args = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from config.wsgi import application

    serve(
        application,
        host=args.host,
        port=args.port,
        threads=args.threads,
        trusted_proxy="127.0.0.1",
        trusted_proxy_headers={"x-forwarded-proto", "x-forwarded-for"},
        clear_untrusted_proxy_headers=True,
        ident="plataforma",
    )


if __name__ == "__main__":
    main()
