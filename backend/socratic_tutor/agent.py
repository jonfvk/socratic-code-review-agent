import os
import uuid
from dataclasses import dataclass, field

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model

from .models import AnswerRequest, QuestionDraft, QuestionResponse, StartRequest, TutorReply
from .question_styles import STYLES, pick_style
from .tools import build_tools

DEFAULT_MODEL = "openai:gpt-4o-mini"

QUESTION_PROMPT = """You are a Socratic code tutor. The learner selected code and you must ask ONE short question.
Rules:
- Stay neutral: never reveal, hint at, or judge what the code does.
- Do not use the words "obviously" or "simply".
- Follow this style: {style_instruction}
- Do not repeat these earlier questions: {previous}
Return only the question."""

TUTOR_PROMPT = """You are a patient, Socratic programming tutor helping the learner understand code they are reviewing.
You have read-only tools to explore the file and workspace; USE them to ground your answer, never guess.

Process for each learner answer:
1. Compare the answer with what the code really does (verify with tools).
2. Say what they got right, then name specific gaps or misconceptions.
3. Explain the real behaviour clearly, referencing line numbers.
4. Find OTHER code (callers, callees, definitions, config, imports) that connects to the selection and return it in
   `related` with accurate 1-based line ranges you verified with tools.
5. In `how_to_dig`, teach HOW to investigate: e.g. "Go to Definition on X (F12)", "Find All References (Shift+F12)",
   a python_docs lookup like `help(json.dumps)`, official docs URLs, or a tiny snippet to run in a REPL.
6. End with ONE neutral follow-up question that tests deeper understanding. Do not give its answer.
If the learner says they don't know, treat it as verdict "unsure", teach from basics, and be encouraging.

File under review: {file_path}
Selected lines {start}-{end}:
```python
{selection}
```"""


@dataclass
class Session:
    request: StartRequest
    question: str
    style: str
    messages: list[dict] = field(default_factory=list)


class TutorAgent:
    def __init__(self, model: str | None = None):
        self.model_name = model or os.getenv("SOCRATIC_MODEL", DEFAULT_MODEL)
        self.llm = init_chat_model(self.model_name, temperature=0.7)
        self.sessions: dict[str, Session] = {}
        self.recent_styles: list[str] = []
        self.recent_questions: list[str] = []

    def start(self, req: StartRequest) -> QuestionResponse:
        style = pick_style(self.recent_styles)
        self.recent_styles = (self.recent_styles + [style])[-5:]
        prompt = QUESTION_PROMPT.format(
            style_instruction=STYLES[style],
            previous=self.recent_questions[-5:] or "none",
        )
        draft = self.llm.with_structured_output(QuestionDraft).invoke(
            [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": f"File: {req.file_path}\nLines {req.selection.start_line}-{req.selection.end_line}:\n"
                    f"```python\n{req.selection.text}\n```",
                },
            ]
        )
        self.recent_questions = (self.recent_questions + [draft.question])[-5:]
        session_id = uuid.uuid4().hex
        self.sessions[session_id] = Session(req, draft.question, style, [{"role": "assistant", "content": draft.question}])
        return QuestionResponse(session_id=session_id, question=draft.question, style=style)

    def answer(self, req: AnswerRequest) -> TutorReply:
        session = self.sessions.get(req.session_id)
        if session is None:
            raise KeyError(req.session_id)
        start_req = session.request
        agent = create_agent(
            self.llm,
            tools=build_tools(
                start_req.file_path,
                start_req.file_content,
                start_req.workspace_root,
                os.getenv("TAVILY_API_KEY"),
            ),
            system_prompt=TUTOR_PROMPT.format(
                file_path=start_req.file_path,
                start=start_req.selection.start_line,
                end=start_req.selection.end_line,
                selection=start_req.selection.text,
            ),
            response_format=TutorReply,
        )
        session.messages.append({"role": "user", "content": req.answer})
        result = agent.invoke({"messages": session.messages})
        reply: TutorReply = result["structured_response"]
        session.messages.append({"role": "assistant", "content": f"{reply.explanation}\n\nFollow-up: {reply.follow_up_question}"})
        return reply
