const vscode = require("vscode");
const cp = require("child_process");
const path = require("path");

let panel;
let session;
let backendProc;
let statusItem;
let output;

const selectionDeco = vscode.window.createTextEditorDecorationType({
  backgroundColor: new vscode.ThemeColor("editor.findMatchHighlightBackground"),
  isWholeLine: true,
  overviewRulerColor: "#4fc3f7",
  overviewRulerLane: vscode.OverviewRulerLane.Left,
});
const relatedDeco = vscode.window.createTextEditorDecorationType({
  backgroundColor: new vscode.ThemeColor("editor.wordHighlightStrongBackground"),
  isWholeLine: true,
  borderWidth: "0 0 0 3px",
  borderStyle: "solid",
  borderColor: "#ffa726",
  overviewRulerColor: "#ffa726",
  overviewRulerLane: vscode.OverviewRulerLane.Right,
});

const cfg = () => vscode.workspace.getConfiguration("socraticTutor");

async function api(route, body) {
  const res = await fetch(cfg().get("backendUrl") + route, {
    method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`Backend error ${res.status}: ${await res.text()}`);
  return res.json();
}

async function healthy() {
  try {
    await api("/health");
    return true;
  } catch {
    return false;
  }
}

async function ensureBackend(context) {
  if (await healthy()) return true;
  if (!cfg().get("autoStartBackend")) return false;
  const repoRoot = path.resolve(context.extensionPath, "..");
  const env = { ...process.env };
  const envFile = cfg().get("envFile");
  if (envFile) env.SOCRATIC_ENV_FILE = envFile;
  output.appendLine(`Starting backend in ${repoRoot}`);
  backendProc = cp.spawn(cfg().get("backendCommand"), { cwd: repoRoot, env, shell: true });
  backendProc.stdout.on("data", (d) => output.append(d.toString()));
  backendProc.stderr.on("data", (d) => output.append(d.toString()));
  let exited = false;
  backendProc.on("exit", (code) => {
    exited = true;
    backendProc = undefined;
    output.appendLine(`Backend exited with code ${code}`);
  });
  for (let i = 0; i < 40 && !exited; i++) {
    if (await healthy()) return true;
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

function uriFor(filePath) {
  if (path.isAbsolute(filePath)) return vscode.Uri.file(filePath);
  const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? "";
  return vscode.Uri.file(path.join(root, filePath));
}

function rangeOf(start, end, doc) {
  const s = Math.max(0, start - 1);
  const e = Math.min(doc.lineCount - 1, Math.max(s, end - 1));
  return new vscode.Range(s, 0, e, doc.lineAt(e).text.length);
}

function clearHighlights() {
  for (const ed of vscode.window.visibleTextEditors) {
    ed.setDecorations(selectionDeco, []);
    ed.setDecorations(relatedDeco, []);
  }
}

function highlightSelection(editor, sel) {
  editor.setDecorations(selectionDeco, [rangeOf(sel.start_line, sel.end_line, editor.document)]);
}

async function highlightRelated(related) {
  const byFile = new Map();
  for (const r of related) {
    const key = uriFor(r.file_path).toString();
    byFile.set(key, [...(byFile.get(key) ?? []), r]);
  }
  for (const [key, items] of byFile) {
    const editor = vscode.window.visibleTextEditors.find((e) => e.document.uri.toString() === key);
    if (editor) {
      editor.setDecorations(
        relatedDeco,
        items.map((r) => ({ range: rangeOf(r.start_line, r.end_line, editor.document), hoverMessage: r.why }))
      );
    }
  }
}

async function reveal(item) {
  const doc = await vscode.workspace.openTextDocument(uriFor(item.file_path));
  const editor = await vscode.window.showTextDocument(doc, { viewColumn: vscode.ViewColumn.One, preserveFocus: false });
  const range = rangeOf(item.start_line, item.end_line, doc);
  editor.revealRange(range, vscode.TextEditorRevealType.InCenter);
  editor.selection = new vscode.Selection(range.start, range.start);
  editor.setDecorations(relatedDeco, [{ range, hoverMessage: item.why }]);
}

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function md(text) {
  return esc(text)
    .replace(/```[a-z]*\n([\s\S]*?)```/g, "<pre><code>$1</code></pre>")
    .replace(/`([^`\n]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/\n/g, "<br>");
}

function getHtml(nonce) {
  return `<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';">
<style>
body{font-family:var(--vscode-font-family);padding:12px;color:var(--vscode-foreground)}
.msg{margin:10px 0;padding:10px;border-radius:6px;background:var(--vscode-editor-inactiveSelectionBackground)}
.tutor{border-left:3px solid #4fc3f7}.you{border-left:3px solid #81c784}
code{font-family:var(--vscode-editor-font-family);background:var(--vscode-textCodeBlock-background);padding:1px 4px}
pre{background:var(--vscode-textCodeBlock-background);padding:8px;overflow:auto}
textarea{width:100%;box-sizing:border-box;min-height:80px;font-family:inherit}
button{margin-top:6px;padding:6px 14px}
a.link{color:var(--vscode-textLink-foreground);cursor:pointer;text-decoration:underline}
h4{margin:10px 0 4px}.badge{font-size:11px;padding:1px 6px;border-radius:8px;background:var(--vscode-badge-background);color:var(--vscode-badge-foreground)}
</style></head><body>
<h3>🎓 Socratic Tutor</h3><div id="log"></div>
<div id="input" style="display:none"><textarea id="answer" placeholder="Type your answer… (it's fine to say 'I don't know')"></textarea>
<button id="send">Send answer</button></div>
<script nonce="${nonce}">
const vscode = acquireVsCodeApi();
const log = document.getElementById("log"), input = document.getElementById("input"), answer = document.getElementById("answer");
function add(cls, html){const d=document.createElement("div");d.className="msg "+cls;d.innerHTML=html;log.appendChild(d);d.scrollIntoView();return d;}
document.getElementById("send").onclick=()=>{const t=answer.value.trim();if(!t)return;add("you","<b>You:</b><br>"+t.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/\\n/g,"<br>"));answer.value="";input.style.display="none";add("tutor","<i>Thinking…</i>").id="thinking";vscode.postMessage({type:"answer",text:t});};
log.addEventListener("click",e=>{const a=e.target.closest("a[data-i]");if(a)vscode.postMessage({type:"reveal",index:Number(a.dataset.i)});});
window.addEventListener("message",({data})=>{
  const th=document.getElementById("thinking");if(th)th.remove();
  if(data.type==="html"){add("tutor",data.html);}
  if(data.type==="ready"){input.style.display="block";answer.focus();}
  if(data.type==="error"){add("tutor","⚠️ "+data.html);input.style.display=data.canRetry?"block":"none";}
  if(data.type==="reset"){log.innerHTML="";}
  if(data.type==="info"){add("tutor",data.html);}
});
vscode.postMessage({type:"loaded"});
</script></body></html>`;
}

function renderReply(r) {
  const badge = { correct: "✅ Correct", partial: "🟡 Partly there", incorrect: "🔴 Not quite", unsure: "🌱 Let's build it up" }[r.verdict];
  let html = `<span class="badge">${badge}</span><p>${md(r.feedback)}</p>`;
  if (r.gaps.length) html += `<h4>Gaps to close</h4><ul>${r.gaps.map((g) => `<li>${md(g)}</li>`).join("")}</ul>`;
  html += `<h4>What's really happening</h4><p>${md(r.explanation)}</p>`;
  if (r.related.length)
    html += `<h4>Connected code (highlighted in orange)</h4><ul>${r.related
      .map((x, i) => `<li><a class="link" data-i="${i}">${esc(x.file_path)}:${x.start_line}-${x.end_line}</a> — ${md(x.why)}</li>`)
      .join("")}</ul>`;
  if (r.how_to_dig.length) html += `<h4>How to dig in yourself</h4><ul>${r.how_to_dig.map((x) => `<li>${md(x)}</li>`).join("")}</ul>`;
  html += `<h4>Next question</h4><p><b>${md(r.follow_up_question)}</b></p>`;
  return html;
}

function ensurePanel(context) {
  if (panel) {
    panel.reveal(vscode.ViewColumn.Beside, true);
    return panel;
  }
  panel = vscode.window.createWebviewPanel("socraticTutor", "Socratic Tutor", { viewColumn: vscode.ViewColumn.Beside, preserveFocus: true }, { enableScripts: true });
  const nonce = Math.random().toString(36).slice(2);
  panel.webview.html = getHtml(nonce);
  panel.loaded = new Promise((resolve) => (panel.resolveLoaded = resolve));
  panel.onDidDispose(() => {
    panel = undefined;
    session = undefined;
    clearHighlights();
  });
  panel.webview.onDidReceiveMessage(async (msg) => {
    if (msg.type === "loaded") return panel.resolveLoaded();
    if (msg.type === "reveal" && session?.related[msg.index]) return reveal(session.related[msg.index]);
    if (msg.type === "answer" && !session) {
      panel.webview.postMessage({ type: "error", html: "No active session. Highlight code and run Socratic Tutor again." });
    }
    if (msg.type === "answer" && session) {
      try {
        const reply = await api("/session/answer", { session_id: session.id, answer: msg.text });
        session.related = reply.related;
        await highlightRelated(reply.related);
        panel.webview.postMessage({ type: "html", html: renderReply(reply) });
        panel.webview.postMessage({ type: "ready" });
      } catch (e) {
        panel.webview.postMessage({ type: "error", html: esc(e.message), canRetry: true });
      }
    }
  });
  return panel;
}

async function ask(context) {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.selection.isEmpty) {
    vscode.window.showInformationMessage("Highlight the code you want to understand first, then run Socratic Tutor.");
    return;
  }
  const sel = editor.selection;
  const selection = {
    start_line: sel.start.line + 1,
    end_line: sel.end.character === 0 && sel.end.line > sel.start.line ? sel.end.line : sel.end.line + 1,
    text: editor.document.getText(sel),
  };
  const p = ensurePanel(context);
  await p.loaded;
  p.webview.postMessage({ type: "reset" });
  p.webview.postMessage({ type: "info", html: "<i>Reading your code…</i>" });
  clearHighlights();
  highlightSelection(editor, selection);
  try {
    if (!(await ensureBackend(context))) {
      output.show(true);
      throw new Error("Backend is not reachable. See View > Output > 'Socratic Tutor' for the reason.");
    }
    const q = await api("/session/start", {
      file_path: editor.document.uri.fsPath,
      file_content: editor.document.getText(),
      workspace_root: vscode.workspace.getWorkspaceFolder(editor.document.uri)?.uri.fsPath ?? null,
      selection,
    });
    session = { id: q.session_id, related: [] };
    p.webview.postMessage({ type: "reset" });
    p.webview.postMessage({ type: "html", html: `<b>Tutor:</b><br>${md(q.question)}` });
    p.webview.postMessage({ type: "ready" });
  } catch (e) {
    p.webview.postMessage({ type: "reset" });
    p.webview.postMessage({ type: "error", html: esc(e.message) });
  }
}

class AskCodeActions {
  provideCodeActions(document, range) {
    if (range.isEmpty) return [];
    const action = new vscode.CodeAction("🎓 Socratic Tutor: quiz me on this code", vscode.CodeActionKind.Empty);
    action.command = { command: "socraticTutor.ask", title: "Socratic Tutor" };
    return [action];
  }
}

function updateStatus() {
  const ed = vscode.window.activeTextEditor;
  if (ed && ed.document.languageId === "python") {
    statusItem.text = ed.selection.isEmpty ? "$(mortar-board) Socratic Tutor: select code" : "$(mortar-board) Quiz me on selection";
    statusItem.show();
  } else {
    statusItem.hide();
  }
}

function activate(context) {
  output = vscode.window.createOutputChannel("Socratic Tutor");
  statusItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  statusItem.command = "socraticTutor.ask";
  statusItem.tooltip = "Highlight code, then click to be quizzed by the Socratic tutor";

  context.subscriptions.push(
    output,
    statusItem,
    selectionDeco,
    relatedDeco,
    vscode.commands.registerCommand("socraticTutor.ask", () => ask(context)),
    vscode.commands.registerCommand("socraticTutor.clearHighlights", clearHighlights),
    vscode.commands.registerCommand("socraticTutor.startBackend", async () => {
      const ok = await ensureBackend(context);
      vscode.window.showInformationMessage(ok ? "Socratic Tutor backend is running." : "Could not start the backend; see the output panel.");
    }),
    vscode.languages.registerCodeActionsProvider({ language: "python" }, new AskCodeActions(), {
      providedCodeActionKinds: [vscode.CodeActionKind.Empty],
    }),
    vscode.window.onDidChangeActiveTextEditor(updateStatus),
    vscode.window.onDidChangeTextEditorSelection(updateStatus),
    { dispose: () => backendProc && backendProc.kill() }
  );
  updateStatus();
  ensureBackend(context).catch(() => {});
}

function deactivate() {
  if (backendProc) backendProc.kill();
}

module.exports = { activate, deactivate };
