from typing import Literal

from pydantic import BaseModel, Field


class Selection(BaseModel):
    start_line: int = Field(ge=1, description="1-based first line of the selection")
    end_line: int = Field(ge=1, description="1-based last line of the selection")
    text: str


class StartRequest(BaseModel):
    file_path: str
    file_content: str
    selection: Selection
    workspace_root: str | None = None


class QuestionResponse(BaseModel):
    session_id: str
    question: str
    style: str


class AnswerRequest(BaseModel):
    session_id: str
    answer: str


class RelatedRange(BaseModel):
    file_path: str = Field(description="File containing the related code; use the current file when local")
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    why: str = Field(description="One sentence on how this code connects to the selection")


class TutorReply(BaseModel):
    verdict: Literal["correct", "partial", "incorrect", "unsure"]
    feedback: str = Field(description="Short, kind acknowledgement of what the learner got right")
    gaps: list[str] = Field(description="Specific gaps or misconceptions in the learner's answer")
    explanation: str = Field(description="Tutor explanation (markdown) that fills the gaps")
    related: list[RelatedRange] = Field(description="Other code that connects to the selection")
    how_to_dig: list[str] = Field(
        description="Concrete steps/commands/doc links the learner can use to investigate on their own"
    )
    follow_up_question: str = Field(description="One neutral question that checks deeper understanding")


class QuestionDraft(BaseModel):
    question: str = Field(description="One short, neutral question about the selected code")
