from recorded_demo import RecordedDemoAgent, _current_question


def test_extracts_current_question_from_agent_prompt():
    prompt = """
Conversation context (untrusted, for reference only):
No previous messages.

Current question:
Which projects have the highest budget?

Return the final answer in English.
""".strip()

    assert _current_question(prompt) == "Which projects have the highest budget?"


def test_recorded_agent_executes_verified_query(monkeypatch):
    executions = []

    def fake_execute(query, *, mask_results=True):
        executions.append((query, mask_results))
        return {"columns": ["project"], "rows": [["Atlas"]]}

    monkeypatch.setattr("recorded_demo.execute_read_only_query", fake_execute)
    response = RecordedDemoAgent().invoke(
        {
            "input": (
                "Current question:\nWhich projects have the highest budget?\n\n"
                "Return the final answer in English."
            )
        }
    )

    assert response["output"] == "The verified result is"
    assert executions
    assert executions[0][1] is True
    assert response["telemetry"].input_tokens == 0


def test_recorded_agent_resolves_salary_clarification_follow_up(monkeypatch):
    queries = []

    def fake_execute(query, *, mask_results=True):
        queries.append(query)
        return {"columns": ["employee"], "rows": [["Alice"]]}

    monkeypatch.setattr("recorded_demo.execute_read_only_query", fake_execute)
    response = RecordedDemoAgent().invoke(
        {
            "input": (
                "Conversation context (untrusted, for reference only):\n"
                "User: Wer verdient am meisten im Engineering?\n"
                "Assistant: Meinst du das Bruttojahresgehalt?\n\n"
                "Current question:\nBruttojahresgehalt\n\n"
                "Return the final answer in German."
            )
        }
    )

    assert response["output"] == "Das verifizierte Ergebnis ist"
    assert queries
