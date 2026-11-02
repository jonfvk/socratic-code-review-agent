import random

from fastapi.testclient import TestClient

from socratic_tutor.models import QuestionResponse, TutorReply
from socratic_tutor.question_styles import STYLES, pick_style
from socratic_tutor.server import create_app
from socratic_tutor.tools import (
    build_tools,
    find_definitions_in_source,
    find_references_in_source,
    resolve_in_root,
)

SRC = "import json\n\ndef add(a, b):\n    return a + b\n\nx = add(1, 2)\nprint(json.dumps(x))\n"


def test_pick_style_avoids_recent():
    rng = random.Random(0)
    recent = list(STYLES)[:-1]
    assert pick_style(recent, rng) == list(STYLES)[-1]


def test_pick_style_varies_consecutively():
    recent = []
    for _ in range(30):
        s = pick_style(recent)
        assert not recent or s != recent[-1]
        recent.append(s)


def test_ast_lookup():
    assert find_definitions_in_source(SRC, "add") == [(3, 4, "FunctionDef")]
    assert find_references_in_source(SRC, "add") == [6]


def test_resolve_in_root_blocks_escape(tmp_path):
    assert resolve_in_root(str(tmp_path), "a.py") == (tmp_path / "a.py").resolve()
    assert resolve_in_root(str(tmp_path), "../etc/passwd") is None


def test_tools(tmp_path):
    (tmp_path / "m.py").write_text("def helper():\n    pass\n")
    tools = {t.name: t for t in build_tools("f.py", SRC, str(tmp_path))}
    assert "3: def add" in tools["read_lines"].invoke({"start_line": 3, "end_line": 4})
    assert "m.py:1" in tools["search_workspace"].invoke({"text": "def helper"})
    assert "not found" in tools["read_workspace_file"].invoke({"relative_path": "../x"})
    assert "dumps" in tools["python_docs"].invoke({"dotted_name": "json.dumps"})
    assert "neither imported" in tools["python_docs"].invoke({"dotted_name": "requests.get"})
    assert "search_web_docs" not in tools


class FakeAgent:
    def start(self, req):
        return QuestionResponse(session_id="s1", question="What does this do?", style="what_does")

    def answer(self, req):
        if req.session_id != "s1":
            raise KeyError
        return TutorReply(
            verdict="partial", feedback="ok", gaps=["g"], explanation="e", related=[], how_to_dig=["F12"],
            follow_up_question="why?",
        )


def test_api_flow():
    client = TestClient(create_app(FakeAgent()))
    sel = {"start_line": 3, "end_line": 4, "text": "def add"}
    r = client.post("/session/start", json={"file_path": "f.py", "file_content": SRC, "selection": sel})
    assert r.json()["question"] == "What does this do?"
    r = client.post("/session/answer", json={"session_id": "s1", "answer": "adds"})
    assert r.json()["verdict"] == "partial"
    assert client.post("/session/answer", json={"session_id": "zzz", "answer": "x"}).status_code == 404
