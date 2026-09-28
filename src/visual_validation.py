"""Shared schema and semantic validation for visual extraction payloads."""

from __future__ import annotations

from typing import Any, Iterable

from jsonschema import Draft202012Validator


def validate_bbox(bbox: dict[str, Any], location: str) -> None:
    if bbox["x0"] >= bbox["x1"]:
        raise ValueError(f"bboxはx0 < x1である必要があります: {location}")
    if bbox["y0"] >= bbox["y1"]:
        raise ValueError(f"bboxはy0 < y1である必要があります: {location}")


def iter_bboxes(
    value: Any, location: str = "$"
) -> Iterable[tuple[str, dict[str, Any]]]:
    if isinstance(value, dict):
        if set(("x0", "y0", "x1", "y1")).issubset(value):
            yield location, value
        for key, child in value.items():
            yield from iter_bboxes(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_bboxes(child, f"{location}[{index}]")


def validate_gold(gold: dict[str, Any], schema: dict[str, Any]) -> None:
    errors = sorted(
        Draft202012Validator(schema).iter_errors(gold),
        key=lambda error: list(error.path),
    )
    if errors:
        messages = [
            f"{'.'.join(str(part) for part in error.path) or '$'}: {error.message}"
            for error in errors
        ]
        raise ValueError("Schema validationに失敗しました:\n" + "\n".join(messages))

    for location, bbox in iter_bboxes(gold):
        validate_bbox(bbox, location)

    validators = {
        "flowchart": validate_flowchart,
        "timeline": validate_timeline,
        "table": validate_table,
        "form": validate_form,
    }
    validators[gold["kind"]](gold["data"])


def validate_flowchart(flowchart: dict[str, Any]) -> None:
    nodes = flowchart["nodes"]
    edges = flowchart["edges"]
    node_ids = [node["id"] for node in nodes]
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("flowchartのnode IDが重複しています")
    known_ids = set(node_ids)
    node_by_id = {node["id"]: node for node in nodes}
    start_ids = [node["id"] for node in nodes if node["node_type"] == "start"]
    end_ids = {node["id"] for node in nodes if node["node_type"] == "end"}
    if len(start_ids) != 1:
        raise ValueError("flowchartにはstart nodeが1件必要です")
    if not end_ids:
        raise ValueError("flowchartにはend nodeが1件以上必要です")

    outgoing: dict[str, list[dict[str, Any]]] = {
        node_id: [] for node_id in node_ids
    }
    incoming_count = {node_id: 0 for node_id in node_ids}
    for index, edge in enumerate(edges):
        if edge["from"] not in known_ids:
            raise ValueError(
                f"edge[{index}].fromが未知のnodeを参照しています: {edge['from']}"
            )
        if edge["to"] not in known_ids:
            raise ValueError(
                f"edge[{index}].toが未知のnodeを参照しています: {edge['to']}"
            )
        outgoing[edge["from"]].append(edge)
        incoming_count[edge["to"]] += 1

    start_id = start_ids[0]
    if incoming_count[start_id] != 0:
        raise ValueError("start nodeにはincoming edgeを設定できません")
    for end_id in end_ids:
        if outgoing[end_id]:
            raise ValueError(
                f"end nodeにはoutgoing edgeを設定できません: {end_id}"
            )
    for node_id, node in node_by_id.items():
        if node["node_type"] != "decision":
            continue
        decision_edges = outgoing[node_id]
        if len(decision_edges) < 2:
            raise ValueError(
                f"decision nodeには2件以上のoutgoing edgeが必要です: {node_id}"
            )
        conditions = [edge["condition"] for edge in decision_edges]
        if any(not condition or not condition.strip() for condition in conditions):
            raise ValueError(
                f"decision nodeの分岐条件は空にできません: {node_id}"
            )
        if len(conditions) != len(set(conditions)):
            raise ValueError(
                f"decision nodeの分岐条件が重複しています: {node_id}"
            )

    reachable = {start_id}
    pending = [start_id]
    while pending:
        current = pending.pop()
        for edge in outgoing[current]:
            if edge["to"] not in reachable:
                reachable.add(edge["to"])
                pending.append(edge["to"])
    unreachable = known_ids - reachable
    if unreachable:
        raise ValueError(
            f"start nodeから到達できないnodeがあります: {sorted(unreachable)}"
        )


def validate_timeline(timeline: dict[str, Any]) -> None:
    events = timeline["events"]
    if len(events) < 2:
        raise ValueError("timelineにはeventが2件以上必要です")
    event_ids = [event["id"] for event in events]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("timelineのevent IDが重複しています")


def validate_table(table: dict[str, Any]) -> None:
    cells = table["cells"]
    if not cells:
        raise ValueError("tableにはcellが1件以上必要です")
    occupied: dict[tuple[int, int], int] = {}
    for index, cell in enumerate(cells):
        row_end = cell["row"] + cell["row_span"]
        column_end = cell["column"] + cell["column_span"]
        if row_end > table["row_count"] or column_end > table["column_count"]:
            raise ValueError(f"table cellが行列範囲を超えています: cell[{index}]")
        for row in range(cell["row"], row_end):
            for column in range(cell["column"], column_end):
                position = (row, column)
                if position in occupied:
                    raise ValueError(
                        "table cellが重複しています: "
                        f"cell[{occupied[position]}]とcell[{index}] / {position}"
                    )
                occupied[position] = index


def validate_form(form: dict[str, Any]) -> None:
    fields = form["fields"]
    if not fields:
        raise ValueError("formにはfieldが1件以上必要です")
    field_ids = [field["id"] for field in fields]
    if len(field_ids) != len(set(field_ids)):
        raise ValueError("formのfield IDが重複しています")
