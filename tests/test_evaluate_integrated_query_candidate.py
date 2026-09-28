from eval.evaluate_integrated_query_candidate import _content_ok


def test_content_rules_cover_targets_and_controls() -> None:
    assert _content_ok("Q131", "1.5km以上で実際に通勤し、届出を10日以内に行います。")
    assert _content_ok("Q156", "通勤手当を支給停止し、住所変更届を提出します。")
    assert _content_ok("Q436", "通勤手当を停止し、住所変更届を14日以内に提出します。")
    assert _content_ok("Q441", "一括または分割で返納し、口座変更届と通帳を提出します。")
    assert _content_ok(
        "Q446",
        "本人名義で15,000円を超える場合、住居届、契約書、支払確認書類を30日以内に提出します。",
    )


def test_content_rules_reject_partial_answers() -> None:
    assert not _content_ok("Q131", "1.5km以上なら対象です。")
    assert not _content_ok("Q446", "本人名義なら住居届を提出します。")
