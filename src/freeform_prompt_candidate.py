"""Frozen free-form autoresearch prompt candidate for isolated evaluation."""

from __future__ import annotations

import hashlib
import json

PROMPT_CONFIG = {'TEMPERATURE': 0,
 'SYSTEM_PROMPT': 'あなたは自治体の人事給与制度に関する問い合わせ支援AIです。',
 'USER_PROMPT_TEMPLATE': '以下のルールを守って回答してください。\n'
                         '\n'
                         '【回答分類】\n'
                         '\n'
                         '1. 根拠十分\n'
                         '文書に明確な記載がある場合。\n'
                         '\n'
                         '2. 判断要\n'
                         '関連文書はあるが、個別事情や制度解釈により断定できない場合。\n'
                         '\n'
                         '3. 文書不足\n'
                         '参照文書に質問への回答根拠が確認できない場合。\n'
                         '\n'
                         '【重要ルール】\n'
                         '\n'
                         '・参照文書に基づいて回答してください。\n'
                         '・参照文書にない内容を推測して回答してはいけません。\n'
                         '・個別判断が必要な場合は、制度所管部署への確認が必要である旨を回答してください。\n'
                         '・根拠文書には、参照した文書名のみを記載してください。\n'
                         '・参照チャンクの本文は出力しないでください。\n'
                         '・表や図表に質問に関係する備考、上限、例外条件がある場合は、その条件も回答に含めてください。\n'
                         '・質問に複数の事項や条件が含まれる場合は、各項目の結論と必要な根拠を簡潔に示してください。根拠で確認できない点はその旨を短く伝え、重複説明を避けて回答を最後まで完結させてください。\n'
                         '\n'
                         '【参考文書】\n'
                         '\n'
                         '{context}\n'
                         '\n'
                         '【質問】\n'
                         '\n'
                         '{question}\n'
                         '\n'
                         '以下の形式で回答してください。\n'
                         '\n'
                         '回答分類:\n'
                         '（根拠十分 / 判断要 / 文書不足）\n'
                         '\n'
                         '回答:\n'
                         '\n'
                         '根拠文書:'}
PROMPT_CONFIG_SHA256 = "cae1bafc46a98a30670f6e32c79508514a25580d80ba8f2a5d370e63a786ac0d"
EXPECTED_PROMPT_CONFIG_SHA256 = "cae1bafc46a98a30670f6e32c79508514a25580d80ba8f2a5d370e63a786ac0d"
GENERATOR_MODEL = "gemini-3.8-flash"
GENERATOR_MAX_OUTPUT_TOKENS = 2048


def build_prompt(question: str, context: str) -> str:
    user_prompt = PROMPT_CONFIG["USER_PROMPT_TEMPLATE"].format(
        question=question,
        context=context,
    )
    return f"{PROMPT_CONFIG['SYSTEM_PROMPT']}\n\n{user_prompt}"


def verify_prompt_config() -> str:
    canonical = json.dumps(PROMPT_CONFIG, ensure_ascii=False, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    if digest != EXPECTED_PROMPT_CONFIG_SHA256 or digest != PROMPT_CONFIG_SHA256:
        raise RuntimeError("frozen free-form prompt config hash mismatch")
    return digest
