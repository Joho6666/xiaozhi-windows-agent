from agent.protocol import decode_message, encode_message, make_request


def test_plain_jsonrpc_round_trip():
    message = make_request(1, "tools/list", {})
    assert decode_message(encode_message(message))[0] == message


def test_xiaozhi_envelope_round_trip():
    message = make_request(1, "initialize", {})
    wrapped = encode_message(message, "xiaozhi_envelope", "session-1")
    decoded, session = decode_message(wrapped, "xiaozhi_envelope")
    assert decoded == message
    assert session == "session-1"
