"""Cloud Run Job entrypoint for the hosted RAG v2 bootstrap."""

import json

from scripts.manage_rag_v2 import bootstrap_cloud


def main() -> int:
    result = bootstrap_cloud()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
