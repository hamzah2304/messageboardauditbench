"""Check the Batch API adapter preserves the reviewed finding judge's results."""

from benchmarks.urlquery.judge.grade_openai_batch import parse_response


def test_batch_response_uses_reviewed_finding_validation() -> None:
    row = {
        "response": {
            "status_code": 200,
            "body": {
                "choices": [{"finish_reason": "stop", "message": {"content": (
                    '{"finding_id":"F1","sub_findings":['
                    '{"id":"F1.1","score":1,"contradicted":false,"quote":"a","reason":"yes"},'
                    '{"id":"F1.2","score":0.75,"contradicted":false,"quote":"b","reason":"yes"},'
                    '{"id":"F1.3","score":0.5,"contradicted":false,"quote":"c","reason":"yes"}'
                    '],"score":0.7,"contradicted":false,"quote":"e","reason":"yes"}'
                )}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            },
        }
    }

    result = parse_response(row, "F1")

    assert result["status"] == "ok"
    assert result["score"] == 0.7
    assert result["usage"] == [{"prompt_tokens": 100, "completion_tokens": 50}]
    assert [item["score"] for item in result["sub_findings"]] == [1, 0.75, 0.5]


def test_batch_refusal_is_unscored() -> None:
    row = {"response": {"status_code": 200, "body": {
        "choices": [{"finish_reason": "content_filter", "message": {"content": ""}}]}}}

    result = parse_response(row, "F1")

    assert result["status"] == "refused"
    assert "score" not in result
