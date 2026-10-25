"""Cloud Run Job entrypoint for the hosted RAG v2 bootstrap."""

import json

from scripts.manage_rag_v2 import SmokeFailure, bootstrap_cloud, smoke_summary


def main() -> int:
    try:
        result = bootstrap_cloud()
    except SmokeFailure as error:
        print(json.dumps(smoke_summary(error.report), ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
