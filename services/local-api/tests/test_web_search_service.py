from app.domain.web_search_service import should_search_web


def test_should_search_web_for_current_info():
    assert should_search_web("What's the latest Gemini API model?")


def test_should_not_search_web_for_local_question():
    assert not should_search_web("What is written in my attached PDF?")
