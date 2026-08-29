"""Records hand-entered tank readings and exposes them to Prometheus."""

import argparse
import logging
import os
import signal
import sys
from http.server import ThreadingHTTPServer

from prometheus_client import REGISTRY

from .app import build_handler
from .collector import ReadingCollector
from .store import Store

log = logging.getLogger("reeflog")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reeflog", description=__doc__)
    parser.add_argument("--db", default=os.environ.get("REEFLOG_DB", "/data/reef-log.db"))
    parser.add_argument("--port", type=int,
                        default=int(os.environ.get("REEFLOG_PORT", "8080")))
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=os.environ.get("REEFLOG_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    store = Store(args.db)
    REGISTRY.register(ReadingCollector(store))

    server = ThreadingHTTPServer(("", args.port), build_handler(store, REGISTRY))
    server.daemon_threads = True
    signal.signal(signal.SIGTERM, lambda *_: server.shutdown())
    log.info("serving on :%s, database %s", args.port, args.db)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
