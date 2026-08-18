from medical_evals.judges.rubric import parse_rubric_judgment


def test_parser_extracts_json_after_reasoning_block():
    response = '<think>Evaluate the criterion carefully.</think>\n{"criteria_met": true, "explanation": "yes"}'

    assert parse_rubric_judgment(response) == {
        "criteria_met": True,
        "explanation": "yes",
    }


def test_parser_extracts_json_from_markdown_with_surrounding_text():
    response = 'Here is the result:\n```json\n{"criteria_met": false, "explanation": "no"}\n```\n'

    assert parse_rubric_judgment(response) == {
        "criteria_met": False,
        "explanation": "no",
    }
