# Socratic Code Review Agent

A tutor inside VS Code that helps you *understand* code instead of just reading it.

1. Open any Python file and **highlight** some code.
2. Trigger the tutor: click the **🎓 status-bar button**, use the **lightbulb / Quick Fix** menu, right-click → *Socratic Tutor*, or press `Cmd+Alt+S` (`Ctrl+Alt+S`).
3. It asks a **neutral question** (a different style each time: "what is this doing?", "what was this designed for?", "what if it were removed?", ...).
4. You answer. The tutor **checks your answer against the real code**, names the gaps, explains, **highlights connected code** (orange) and shows you **how to dig in yourself** (Go to Definition, Find References, `help(...)`, official docs).
5. It finishes with a follow-up question, so you keep going.

## Architecture

```
extension/  VS Code extension (plain JS, no build step): selection, UI panel, highlights
backend/    FastAPI + LangChain tutor
  socratic_tutor/agent.py           create_agent(...) with structured TutorReply output
  socratic_tutor/tools.py           read_lines, find_definition, find_references, list_imports,
                                    python_docs, read_workspace_file, search_workspace, search_web_docs (Tavily)
  socratic_tutor/question_styles.py rotating neutral question styles
```

The agent is grounded: it explores your file and workspace with read-only tools (workspace access is confined to
the workspace root) rather than guessing.

## Setup

```bash
uv sync
cp .env.example .env      # add OPENAI_API_KEY (optional: TAVILY_API_KEY, SOCRATIC_MODEL)
uv run pytest             # tests
.venv/bin/python -m uvicorn socratic_tutor.server:app --app-dir backend --port 8765   # optional: the extension auto-starts it
```

Install the extension: open the `extension/` folder in VS Code and press `F5` (Extension Development Host),
or symlink it into `~/.vscode/extensions/`. Settings live under `socraticTutor.*`
(e.g. `socraticTutor.envFile` to point at an existing `.env`).

## Privacy

The selected code, the file under review and any workspace files the tutor reads are sent to the configured LLM provider.
