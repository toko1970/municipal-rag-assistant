"""Run the bounded cleanup of expired anonymous API HMAC state."""

from __future__ import annotations

import json

from src.persistence.database import get_session_factory
from src.public_api_cleanup import cleanup_expired_state


def main() -> int:
    counts = cleanup_expired_state(get_session_factory())
    print(json.dumps(counts, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
