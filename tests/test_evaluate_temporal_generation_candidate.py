from eval.evaluate_temporal_generation_candidate import _content_ok


def test_q291_requires_new_rule_and_rejects_old_rule() -> None:
    assert _content_ok("Q291", "認定された月から支給し、15日以内に提出する。")
    assert not _content_ok(
        "Q291", "認定事由発生日の翌月から支給し、15日以内に提出する。"
    )


def test_comparison_controls_require_both_values() -> None:
    assert _content_ok("Q421", "2km以上から1.5km以上へ変更した。")
    assert not _content_ok("Q421", "1.5km以上へ変更した。")
