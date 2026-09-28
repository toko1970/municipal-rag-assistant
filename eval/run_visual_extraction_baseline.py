"""Run one fixed, no-retry visual extraction baseline across a manifest."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from config import BASE_DIR, LLM_MODEL_NAME
from eval.evaluate_visual_extraction import (
    EVALUATION_REVISION,
    evaluate_visual_extraction,
    load_json,
)
from src.llm_provider import GeminiProvider, StructuredLLMResult
from src.visual_extractor import extract_visual_candidate, prepare_visual_candidate
from src.visual_ingestion import load_visual_schema, render_pdf_page


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _reused_candidate(
    fixture_id: str, reuse_dir: Path, page
) -> tuple[Any, dict[str, Any]] | None:
    candidate_path = reuse_dir / f"{fixture_id}.json"
    if not candidate_path.exists():
        return None
    metadata_path = reuse_dir / f"{fixture_id}.metadata.json"
    metadata = load_json(metadata_path) if metadata_path.exists() else {}
    result = StructuredLLMResult(
        provider=str(metadata.get("provider", "unknown")),
        model=str(metadata.get("model", "unknown")),
        data=load_json(candidate_path),
        input_tokens=int(metadata.get("input_tokens", 0)),
        output_tokens=int(metadata.get("output_tokens", 0)),
        request_id=str(metadata.get("request_id", "")),
    )
    return prepare_visual_candidate(result=result, page=page), metadata


def run_baseline(
    *,
    manifest_path: Path,
    output_dir: Path,
    provider,
    reuse_dir: Path | None,
    max_api_calls: int,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"baseline出力は上書きしません: {output_dir}")
    manifest = load_json(manifest_path)
    schema = load_visual_schema()
    fixtures = manifest["fixtures"]
    reusable_ids = (
        {
            path.stem
            for path in reuse_dir.glob("*.json")
            if not path.name.endswith(".metadata.json")
        }
        if reuse_dir
        else set()
    )
    required_calls = sum(
        fixture["fixture_id"] not in reusable_ids for fixture in fixtures
    )
    if required_calls > max_api_calls:
        raise ValueError(
            f"必要API call数が上限を超えます: required={required_calls}, "
            f"max={max_api_calls}"
        )

    output_dir.mkdir(parents=True)
    records: list[dict[str, Any]] = []
    api_calls = 0
    transport_blocker: str | None = None
    for fixture in fixtures:
        fixture_id = fixture["fixture_id"]
        if transport_blocker and fixture_id not in reusable_ids:
            records.append(
                {
                    "fixture_id": fixture_id,
                    "kind": fixture["kind"],
                    "status": "SKIPPED",
                    "source": "api",
                    "error": transport_blocker,
                }
            )
            continue
        page_number = fixture["source_images"][0]["page"]
        page = render_pdf_page(BASE_DIR / fixture["document"]["path"], page_number)
        started = time.perf_counter()
        source = "api"
        reused = _reused_candidate(fixture_id, reuse_dir, page) if reuse_dir else None
        try:
            if reused:
                candidate, prior_metadata = reused
                elapsed = prior_metadata.get("elapsed_seconds")
                source = "reused"
            else:
                api_calls += 1
                candidate = extract_visual_candidate(
                    page=page,
                    kind_hint=fixture["kind"],
                    provider=provider,
                )
                elapsed = time.perf_counter() - started
            _write_json(output_dir / f"{fixture_id}.raw.json", candidate.raw_data)
            _write_json(output_dir / f"{fixture_id}.normalized.json", candidate.data)
            metrics = None
            if not candidate.validation_errors:
                metrics = asdict(
                    evaluate_visual_extraction(
                        candidate.data,
                        load_json(BASE_DIR / fixture["gold"]["path"]),
                        schema,
                    )
                )
            record = {
                "fixture_id": fixture_id,
                "kind": fixture["kind"],
                "status": "VALIDATED" if metrics is not None else "INVALID",
                "source": source,
                "provider": candidate.provider,
                "model": candidate.model,
                "prompt_version": candidate.prompt_version,
                "input_tokens": candidate.input_tokens,
                "output_tokens": candidate.output_tokens,
                "elapsed_seconds": elapsed,
                "normalized_bbox_count": candidate.normalized_bbox_count,
                "normalized_structure_count": candidate.normalized_structure_count,
                "validation_errors": list(candidate.validation_errors),
                "metrics": metrics,
            }
        except Exception as error:
            error_name = type(error).__name__
            record = {
                "fixture_id": fixture_id,
                "kind": fixture["kind"],
                "status": "ERROR",
                "source": source,
                "error": f"{error_name}: {error}",
            }
            if error_name in {"ConnectError", "APIConnectionError"}:
                transport_blocker = record["error"]
        records.append(record)

    validated = [item for item in records if item["status"] == "VALIDATED"]
    summary = {
        "manifest_version": manifest.get("manifest_version"),
        "evaluation_revision": EVALUATION_REVISION,
        "model": LLM_MODEL_NAME,
        "fixture_count": len(fixtures),
        "api_calls": api_calls,
        "validated_count": len(validated),
        "invalid_count": sum(item["status"] == "INVALID" for item in records),
        "error_count": sum(item["status"] == "ERROR" for item in records),
        "skipped_count": sum(item["status"] == "SKIPPED" for item in records),
        "gate_passed_count": sum(
            bool(item["metrics"]["gate_passed"]) for item in validated
        ),
        "total_input_tokens": sum(
            int(item.get("input_tokens", 0)) for item in records
        ),
        "total_output_tokens": sum(
            int(item.get("output_tokens", 0)) for item in records
        ),
        "records": records,
    }
    _write_json(output_dir / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--reuse-dir", type=Path)
    parser.add_argument("--max-api-calls", required=True, type=int)
    args = parser.parse_args()
    summary = run_baseline(
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        provider=GeminiProvider(LLM_MODEL_NAME),
        reuse_dir=args.reuse_dir,
        max_api_calls=args.max_api_calls,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
