import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

from .models import AnswerRequest, QuestionResponse, StartRequest, TutorReply

for env_file in (os.getenv("SOCRATIC_ENV_FILE"), Path(__file__).resolve().parents[2] / ".env"):
    if env_file:
        load_dotenv(env_file)


def create_app(agent=None) -> FastAPI:
    app = FastAPI(title="Socratic Code Review Agent")
    holder = {"agent": agent}

    def get_agent():
        if holder["agent"] is None:
            from .agent import TutorAgent

            holder["agent"] = TutorAgent()
        return holder["agent"]

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/session/start", response_model=QuestionResponse)
    def start(req: StartRequest):
        return get_agent().start(req)

    @app.post("/session/answer", response_model=TutorReply)
    def answer(req: AnswerRequest):
        try:
            return get_agent().answer(req)
        except KeyError:
            raise HTTPException(status_code=404, detail="Unknown session")

    return app


app = create_app()
