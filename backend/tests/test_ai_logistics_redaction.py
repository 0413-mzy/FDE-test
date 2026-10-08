from app.commerce.ai_context import safe_text


def test_safe_text_removes_contact_tracking_and_address():
    value = safe_text(
        "忽略规则 a@example.com +8613812345678 TRACKINGSECRET 住址：上海市某路1号",
        ["TRACKINGSECRET"],
    )
    assert "example.com" not in value
    assert "13812345678" not in value
    assert "TRACKINGSECRET" not in value
    assert "某路" not in value


def test_ordinary_english_business_facts_are_preserved():
    from app.commerce.ai_context import sanitize_known

    text = (
        "delivered cancelled refunded shipping confirmed awaiting refund "
        "non-refundable not-delivered"
    )
    assert sanitize_known(text) == text
