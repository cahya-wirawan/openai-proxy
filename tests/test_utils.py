from app.utils import (
    chat_messages_to_prompt,
    flatten_content,
    responses_input_to_prompt,
)


def test_flatten_content():
    assert flatten_content(
        [{"type": "input_text", "text": "hello"}]
    ) == "hello"


def test_chat_prompt():
    prompt, instructions = chat_messages_to_prompt(
        [
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Hello"},
        ]
    )
    assert instructions == "Be concise."
    assert prompt == "USER:\nHello"


def test_responses_prompt():
    assert responses_input_to_prompt(
        [{"role": "user", "content": "Hello"}]
    ) == "USER:\nHello"
