"""Explicit offline cache invalidation; no model/API call or private data export."""

import argparse

from app.agent.research import EvidenceCache
from app.config import Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["status", "invalidate"])
    args = parser.parse_args()
    settings = Settings()
    settings.ensure_dirs()
    cache = EvidenceCache(settings.database_path, settings.web_cache_ttl_seconds)
    if args.action == "invalidate":
        cache.invalidate()
        print("Public cache entries marked expired; they remain recoverable in the database.")
    else:
        with cache.connect() as conn:
            count = conn.execute("SELECT count(*) FROM public_evidence_cache").fetchone()[0]
        print(
            f"Public cached query records: {count}. Fresh acquisition is not verification of current law."
        )


if __name__ == "__main__":
    main()
