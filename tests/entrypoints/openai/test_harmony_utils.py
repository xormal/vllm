from types import SimpleNamespace

from vllm.entrypoints.harmony_utils import parse_output_message


def _make_message(channel):
    author = SimpleNamespace(role="assistant")
    content = [SimpleNamespace(text="Hello world")]
    return SimpleNamespace(
        author=author,
        recipient=None,
        content=content,
        channel=channel,
    )


def test_parse_output_message_defaults_to_final_channel():
    """Messages without explicit channel should be treated as 'final'."""
    message = _make_message(channel=None)
    output_items = parse_output_message(message)

    assert len(output_items) == 1
    msg = output_items[0]
    assert msg.type == "message"
    assert msg.content[0].text == "Hello world"


def test_parse_output_message_commentary_without_recipient():
    message = _make_message(channel="commentary")
    output_items = parse_output_message(message)

    assert len(output_items) == 1
    reasoning = output_items[0]
    assert reasoning.type == "reasoning"
    assert reasoning.content[0].text == "Hello world"
