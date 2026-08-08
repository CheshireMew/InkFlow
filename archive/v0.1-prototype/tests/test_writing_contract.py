from core.writing_contract import build_writing_contract, cleanup_text, compose_system_prompt, review_text


def test_default_contract_flags_template_phrases_and_cleanup_removes_openers():
    contract = build_writing_contract({})
    text = "首先，这件事值得做。其次，成本也不高。"

    report = review_text(text, contract)

    assert report.passed is False
    assert cleanup_text(text, contract).startswith("这件事值得做。")
    assert "总而言之" in compose_system_prompt(contract)


def test_contract_can_disable_default_banned_phrases_for_translation():
    contract = build_writing_contract(
        {
            "writing_contract": {
                "inherit_default_banned_phrases": False,
                "style_rules": ["优先保证信息准确。"],
            }
        }
    )

    assert contract.banned_phrases == ()
    assert "不要写成模板腔" in compose_system_prompt(contract)
