from agent import AgentExecutorAdapter, _message_text


class FakeMessage:
    text = "A complete answer."
    content = "ignored"


class FakeGraph:
    def invoke(self, payload, config):
        assert payload["messages"][0]["content"] == "question"
        assert config["recursion_limit"] == 9
        return {"messages": [FakeMessage()]}


def test_agent_adapter_uses_message_state(monkeypatch):
    monkeypatch.setenv("AGENT_RECURSION_LIMIT", "9")

    response = AgentExecutorAdapter(FakeGraph()).invoke({"input": "question"})

    assert response["output"] == "A complete answer."
    assert response["telemetry"].tool_call_count == 0
    assert response["telemetry"].input_tokens == 0


def test_message_text_reads_provider_content_blocks():
    class BlockMessage:
        text = None
        content = [{"type": "text", "text": "First"}, {"text": "Second"}]

    assert _message_text(BlockMessage()) == "First\nSecond"
