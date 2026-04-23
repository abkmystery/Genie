from app.providers.openai_compatible import _sanitize_model_output


def test_sanitize_model_output_removes_thought_blocks():
    value = "<thought>hidden reasoning</thought>You are on YouTube watching a video."
    assert _sanitize_model_output(value) == "You are on YouTube watching a video."


def test_sanitize_model_output_removes_dangling_think_blocks():
    value = "<think>\ninternal\nYou are on a page"
    assert _sanitize_model_output(value) == ""
