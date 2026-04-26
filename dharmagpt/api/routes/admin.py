from __future__ import annotations

import json
import re
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from core.config import get_settings
from core.local_vector_store import upsert_vectors
from core.retrieval import get_openai, get_pinecone

router = APIRouter()
settings = get_settings()


def _normalize_text(raw: str) -> str:
  return re.sub(r"\s+", " ", raw).strip()


def _chunk_text(raw: str, max_chars: int = 1200) -> list[str]:
  text = _normalize_text(raw)
  if not text:
    return []

  # Split first on paragraph breaks, then fold into bounded chunks.
  paragraphs = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
  if not paragraphs:
    paragraphs = [text]

  chunks: list[str] = []
  buf = ""
  for para in paragraphs:
    para = _normalize_text(para)
    if not para:
      continue

    if len(para) > max_chars:
      sentences = re.split(r"(?<=[.!?])\s+", para)
      for sentence in sentences:
        sentence = _normalize_text(sentence)
        if not sentence:
          continue
        if not buf:
          buf = sentence
        elif len(buf) + 1 + len(sentence) <= max_chars:
          buf += " " + sentence
        else:
          chunks.append(buf)
          buf = sentence
      continue

    if not buf:
      buf = para
    elif len(buf) + 1 + len(para) <= max_chars:
      buf += " " + para
    else:
      chunks.append(buf)
      buf = para

  if buf:
    chunks.append(buf)

  return chunks


def _extract_text(filename: str, raw: bytes) -> str:
  suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else "txt"
  decoded = raw.decode("utf-8", errors="ignore")

  if suffix in {"txt", "md", "rst", "csv", "tsv"}:
    return decoded

  if suffix == "jsonl":
    lines: list[str] = []
    for line in decoded.splitlines():
      line = line.strip()
      if not line:
        continue
      try:
        obj = json.loads(line)
      except json.JSONDecodeError:
        lines.append(line)
        continue
      if isinstance(obj, dict):
        val = obj.get("text") or obj.get("content") or obj.get("body") or obj.get("text_en") or ""
        if val:
          lines.append(str(val))
    return "\n".join(lines)

  if suffix == "json":
    try:
      obj = json.loads(decoded)
    except json.JSONDecodeError:
      return decoded
    if isinstance(obj, dict):
      return str(obj.get("text") or obj.get("content") or obj.get("body") or decoded)
    if isinstance(obj, list):
      parts: list[str] = []
      for item in obj:
        if isinstance(item, dict):
          val = item.get("text") or item.get("content") or item.get("body") or ""
          if val:
            parts.append(str(val))
        elif isinstance(item, str):
          parts.append(item)
      return "\n".join(parts)
    return decoded

  return decoded


@router.post("/admin/vector/upload")
async def upload_document_to_vector_db(
  file: UploadFile = File(...),
  vector_db: str = Form("local"),
  index_name: str = Form(""),
  namespace: str = Form(""),
) -> dict:
  vector_db = (vector_db or "local").strip().lower()
  if vector_db not in {"local", "pinecone"}:
    raise HTTPException(status_code=400, detail="vector_db must be 'local' or 'pinecone'")

  filename = file.filename or "upload.txt"
  raw = await file.read()
  if not raw:
    raise HTTPException(status_code=400, detail="Uploaded file is empty")

  text = _extract_text(filename, raw)
  chunks = _chunk_text(text)
  if not chunks:
    raise HTTPException(status_code=400, detail="Could not extract usable text from uploaded file")

  client = get_openai()
  embed_response = await client.embeddings.create(model=settings.embedding_model, input=chunks)
  vectors = [row.embedding for row in embed_response.data]

  if vector_db == "local":
    default_index = settings.local_vector_index_name
    default_namespace = settings.local_vector_namespace
  else:
    default_index = settings.pinecone_index_name
    default_namespace = ""

  target_index = (index_name or default_index).strip()
  if not target_index:
    raise HTTPException(status_code=400, detail="index_name is required")

  target_namespace = (namespace or default_namespace).strip()

  records = []
  doc_id = uuid.uuid4().hex[:12]
  for i, (chunk, vec) in enumerate(zip(chunks, vectors), start=1):
    records.append(
      {
        "id": f"admin-doc-{doc_id}-{i}",
        "values": vec,
        "metadata": {
          "text": chunk,
          "source_type": "admin_upload",
          "citation": f"Admin upload: {filename}",
          "document_name": filename,
          "chunk_index": i,
        },
      }
    )

  batch_size = 50
  upserted = 0
  if vector_db == "local":
    upserted = upsert_vectors(
      index_name=target_index,
      namespace=target_namespace,
      records=records,
    )
  else:
    pc = get_pinecone()
    index = pc.Index(target_index)
    for i in range(0, len(records), batch_size):
      batch = records[i : i + batch_size]
      if target_namespace:
        index.upsert(vectors=batch, namespace=target_namespace)
      else:
        index.upsert(vectors=batch)
      upserted += len(batch)

  return {
    "status": "ok",
    "vector_db": vector_db,
    "index_name": target_index,
    "namespace": target_namespace,
    "document": filename,
    "chunks_created": len(chunks),
    "vectors_upserted": upserted,
  }


def _feedback_page() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>DharmaGPT Gold Store Dashboard</title>
  <style>
    :root {
      --bg: #0b1220; --panel: rgba(17,24,39,0.88); --panel-2: rgba(15,23,42,0.92);
      --text: #e5eefb; --muted: #96a7c3; --line: rgba(148,163,184,0.22);
      --accent: #f59e0b; --shadow: 0 24px 80px rgba(0,0,0,0.35);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(245,158,11,0.18), transparent 28%),
        radial-gradient(circle at top right, rgba(59,130,246,0.18), transparent 22%),
        linear-gradient(180deg, #0b1220 0%, #0f172a 100%);
      min-height: 100vh;
    }
    .shell { max-width: 960px; margin: 0 auto; padding: 32px 24px; }
    .topbar {
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 28px; gap: 16px; flex-wrap: wrap;
    }
    .topbar h1 { margin: 0; font-size: 26px; }
    .controls {
      display: flex; gap: 10px; align-items: flex-end; flex-wrap: wrap;
      background: var(--panel); border: 1px solid var(--line);
      border-radius: 20px; padding: 18px 20px; margin-bottom: 24px;
      box-shadow: var(--shadow);
    }
    .field { display: flex; flex-direction: column; gap: 6px; flex: 1; min-width: 200px; }
    label { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; }
    input {
      border-radius: 12px; border: 1px solid var(--line);
      background: var(--panel-2); color: var(--text);
      padding: 10px 14px; outline: none; font-size: 14px;
    }
    input:focus { border-color: rgba(245,158,11,0.6); }
    button {
      border: 0; border-radius: 12px; padding: 10px 16px;
      font-weight: 600; cursor: pointer; font-size: 14px;
      transition: transform 100ms ease, opacity 100ms ease;
    }
    button:hover { transform: translateY(-1px); }
    .btn-primary { background: linear-gradient(135deg,#f59e0b,#f97316); color: #111827; }
    .btn-approve { background: rgba(34,197,94,0.18); color: #bbf7d0; border: 1px solid rgba(34,197,94,0.35); }
    .btn-reject  { background: rgba(239,68,68,0.18);  color: #fecaca; border: 1px solid rgba(239,68,68,0.35); }
    .notice { font-size: 13px; color: #dbeafe; min-height: 1.2em; margin-top: 4px; }
    .stats { display: grid; grid-template-columns: repeat(3,1fr); gap: 12px; margin-bottom: 24px; }
    .stat {
      background: var(--panel); border: 1px solid var(--line); border-radius: 16px;
      padding: 16px; box-shadow: var(--shadow);
    }
    .stat-label { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.07em; }
    .stat-value { font-size: 26px; font-weight: 700; margin-top: 6px; }
    .card {
      background: var(--panel); border: 1px solid var(--line);
      border-radius: 20px; padding: 20px; margin-bottom: 16px;
      box-shadow: var(--shadow);
    }
    .card-head {
      display: flex; justify-content: space-between; align-items: flex-start;
      gap: 12px; margin-bottom: 14px; flex-wrap: wrap;
    }
    .query-text { font-size: 16px; font-weight: 600; flex: 1; }
    .chip {
      font-size: 11px; padding: 4px 10px; border-radius: 999px;
      border: 1px solid var(--line); color: var(--muted); white-space: nowrap;
    }
    .chip.up { border-color: rgba(34,197,94,0.4); color: #86efac; }
    .block-label {
      font-size: 11px; color: var(--muted); text-transform: uppercase;
      letter-spacing: 0.07em; margin-bottom: 6px;
    }
    .answer-text {
      white-space: pre-wrap; line-height: 1.65; font-size: 14px;
      background: rgba(2,6,23,0.45); border-radius: 14px;
      border: 1px solid var(--line); padding: 14px; margin-bottom: 14px;
    }
    textarea.answer-edit {
      width: 100%; min-height: 130px; resize: vertical;
      white-space: pre-wrap; line-height: 1.65; font-size: 14px;
      background: rgba(2,6,23,0.45); border-radius: 14px;
      border: 1px solid var(--line); color: var(--text);
      padding: 14px; margin-bottom: 14px;
    }
    .note-text { font-size: 13px; color: #fde68a; font-style: italic; margin-bottom: 12px; }
    .sources { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }
    .source-chip {
      font-size: 11px; padding: 4px 8px; border-radius: 8px;
      background: rgba(59,130,246,0.12); border: 1px solid rgba(59,130,246,0.25); color: #93c5fd;
    }
    .card-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
    .ts { font-size: 12px; color: var(--muted); margin-left: auto; }
    .empty {
      color: var(--muted); padding: 40px; text-align: center;
      border: 1px dashed var(--line); border-radius: 18px;
      background: rgba(15,23,42,0.55);
    }
    @media (max-width: 700px) {
      .stats { grid-template-columns: 1fr 1fr; }
      .card-head { flex-direction: column; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <div class="topbar">
      <h1>Gold Store Dashboard</h1>
      <a class="nav-link" href="/docs" style="color: var(--muted); font-size: 13px; text-decoration: none; padding: 6px 14px; border: 1px solid var(--line); border-radius: 999px;">API Docs</a>
    </div>

    <div class="controls" style="align-items: center;">
      <div class="field" style="min-width: 180px;">
        <label for="vectorDb">Vector DB</label>
        <select id="vectorDb" style="border-radius: 12px; border: 1px solid var(--line); background: var(--panel-2); color: var(--text); padding: 10px 14px;">
          <option value="local" selected>Local (Beta)</option>
          <option value="pinecone">Pinecone (Later)</option>
        </select>
      </div>
      <div class="field" style="min-width: 220px;">
        <label for="indexName">Index Name</label>
        <input id="indexName" type="text" placeholder="dharma-local" />
      </div>
      <div class="field" style="min-width: 180px;">
        <label for="namespace">Namespace</label>
        <input id="namespace" type="text" placeholder="optional" />
      </div>
      <div class="field" style="min-width: 240px;">
        <label for="docFile">Document File</label>
        <input id="docFile" type="file" />
      </div>
      <button class="btn-primary" id="uploadBtn" style="margin-top: 18px;">Upload & Index</button>
    </div>

    <div class="controls">
      <button class="btn-primary" id="loadBtn">Load</button>
      <div class="notice" id="notice"></div>
    </div>

    <div class="stats">
      <div class="stat"><div class="stat-label">Pending review</div><div class="stat-value" id="pendingCount">-</div></div>
      <div class="stat"><div class="stat-label">Gold entries</div><div class="stat-value" id="goldCount">-</div></div>
      <div class="stat"><div class="stat-label">Showing</div><div class="stat-value" id="showingCount">-</div></div>
    </div>

    <div class="tab-bar" style="display:flex; gap:4px; margin-bottom:20px;">
      <button class="tab active" id="tabPending" onclick="switchTab('pending')" style="padding:8px 18px;border-radius:999px;border:1px solid var(--line);background:rgba(245,158,11,0.18);color:#ffd28b;">Pending</button>
      <button class="tab" id="tabGold" onclick="switchTab('gold')" style="padding:8px 18px;border-radius:999px;border:1px solid var(--line);background:transparent;color:var(--muted);">Gold</button>
    </div>

    <div id="cards"></div>
  </div>

  <script>
    const API = "/api/v1";
    let currentTab = "pending";
    let pendingData = [];
    let goldData = [];

    function headers() { return { "Content-Type": "application/json" }; }
    function setNotice(msg, err=false) {
      const n = document.getElementById("notice");
      n.style.color = err ? "#fecaca" : "#dbeafe";
      n.textContent = msg;
    }
    function switchTab(tab) {
      currentTab = tab;
      document.getElementById("tabPending").style.background = tab === "pending" ? "rgba(245,158,11,0.18)" : "transparent";
      document.getElementById("tabPending").style.color = tab === "pending" ? "#ffd28b" : "var(--muted)";
      document.getElementById("tabGold").style.background = tab === "gold" ? "rgba(245,158,11,0.18)" : "transparent";
      document.getElementById("tabGold").style.color = tab === "gold" ? "#ffd28b" : "var(--muted)";
      render();
    }
    function fmtDate(iso) {
      try { return new Date(iso).toLocaleString(); } catch(e) { return iso || ""; }
    }
    function sourceChips(sources) {
      if (!sources || !sources.length) return "";
      return sources.slice(0,4).map(s => {
        const label = s.citation || (s.section || "") + (s.chapter ? " Ch." + s.chapter : "");
        return label ? '<span class="source-chip">' + label + '</span>' : "";
      }).join("");
    }
    function pendingCard(r) {
      const d = document.createElement("div");
      d.className = "card";
      d.id = "card-" + r.query_id;
      d.innerHTML =
        '<div class="card-head">' +
          '<div class="query-text">' + escHtml(r.query) + '</div>' +
          '<span class="chip up">&#128077; upvoted</span>' +
          '<span class="chip">' + (r.mode || "") + '</span>' +
        '</div>' +
        (r.note ? '<div class="note-text">Note: ' + escHtml(r.note) + '</div>' : '') +
        '<div class="block-label">Answer (editable before approval)</div>' +
        '<textarea class="answer-edit" id="answer-' + escHtml(r.query_id) + '">' + escHtml(r.answer) + '</textarea>' +
        '<div class="sources">' + sourceChips(r.sources) + '</div>' +
        '<div class="card-actions">' +
          '<button class="btn-approve" onclick="review(' + JSON.stringify(r.query_id) + ', \\'approved\\')">Approve &rarr; Gold</button>' +
          '<button class="btn-reject"  onclick="review(' + JSON.stringify(r.query_id) + ', \\'rejected\\')">Reject</button>' +
          '<span class="ts">' + fmtDate(r.timestamp) + '</span>' +
        '</div>';
      return d;
    }
    function goldCard(r) {
      const d = document.createElement("div");
      d.className = "card";
      d.innerHTML =
        '<div class="card-head">' +
          '<div class="query-text">' + escHtml(r.query) + '</div>' +
          '<span class="chip" style="border-color:rgba(245,158,11,0.4);color:#fde68a;">&#10003; gold</span>' +
          '<span class="chip">' + (r.mode || "") + '</span>' +
        '</div>' +
        '<div class="block-label">Gold answer</div>' +
        '<div class="answer-text">' + escHtml(r.gold_answer) + '</div>' +
        '<div class="sources">' + sourceChips(r.evidence || []) + '</div>' +
        '<div class="card-actions"><span class="ts">Promoted ' + fmtDate(r.promoted_at) + '</span></div>';
      return d;
    }
    function escHtml(s) {
      return String(s || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
    }
    function render() {
      const cards = document.getElementById("cards");
      cards.innerHTML = "";
      const data = currentTab === "pending" ? pendingData : goldData;
      document.getElementById("showingCount").textContent = String(data.length);
      if (!data.length) {
        cards.innerHTML = '<div class="empty">' + (currentTab === "pending" ? "No pending responses." : "No gold responses yet.") + '</div>';
        return;
      }
      for (const r of data) {
        cards.appendChild(currentTab === "pending" ? pendingCard(r) : goldCard(r));
      }
    }
    async function load() {
      setNotice("Loading...");
      try {
        const [pResp, gResp] = await Promise.all([
          fetch(API + "/feedback/pending", { headers: headers() }),
          fetch(API + "/feedback/gold",    { headers: headers() }),
        ]);
        if (!pResp.ok) throw new Error("Pending: " + pResp.statusText);
        if (!gResp.ok) throw new Error("Gold: " + gResp.statusText);
        const p = await pResp.json();
        const g = await gResp.json();
        pendingData = p.pending || [];
        goldData    = g.gold    || [];
        document.getElementById("pendingCount").textContent = String(pendingData.length);
        document.getElementById("goldCount").textContent    = String(goldData.length);
        setNotice("Loaded.");
        render();
      } catch(e) { setNotice(e.message, true); }
    }
    async function review(queryId, status) {
      setNotice("Saving...");
      try {
        const answerEl = document.getElementById("answer-" + queryId);
        const editedAnswer = answerEl ? answerEl.value.trim() : "";
        const resp = await fetch(API + "/feedback/" + encodeURIComponent(queryId), {
          method: "PATCH",
          headers: headers(),
          body: JSON.stringify({
            review_status: status,
            gold_answer: status === "approved" ? editedAnswer : null,
          }),
        });
        if (!resp.ok) {
          let msg = resp.statusText;
          try {
            const body = await resp.json();
            if (body && body.detail) msg = body.detail;
          } catch (_) {}
          throw new Error(msg);
        }
        pendingData = pendingData.filter(r => r.query_id !== queryId);
        document.getElementById("pendingCount").textContent = String(pendingData.length);
        const card = document.getElementById("card-" + queryId);
        if (card) card.remove();
        if (status === "approved") {
          const gResp = await fetch(API + "/feedback/gold", { headers: headers() });
          if (!gResp.ok) throw new Error("Gold: " + gResp.statusText);
          const g = await gResp.json();
          goldData = g.gold || [];
          document.getElementById("goldCount").textContent = String(goldData.length);
          setNotice("Approved and added to gold set.");
        } else {
          setNotice("Rejected.");
        }
        render();
      } catch(e) { setNotice(e.message, true); }
    }

    async function uploadDocument() {
      const fileInput = document.getElementById("docFile");
      const file = fileInput.files && fileInput.files[0];
      if (!file) {
        setNotice("Please choose a document file first.", true);
        return;
      }

      const fd = new FormData();
      fd.append("file", file);
      fd.append("vector_db", document.getElementById("vectorDb").value || "local");
      fd.append("index_name", document.getElementById("indexName").value || "");
      fd.append("namespace", document.getElementById("namespace").value || "");

      setNotice("Uploading and indexing document...");
      try {
        const resp = await fetch("/admin/vector/upload", {
          method: "POST",
          body: fd,
        });
        if (!resp.ok) {
          let msg = resp.statusText;
          try {
            const body = await resp.json();
            if (body && body.detail) msg = body.detail;
          } catch (_) {}
          throw new Error(msg);
        }
        const data = await resp.json();
        setNotice(
          "Indexed " + data.vectors_upserted + " chunks into " + data.vector_db + ":" + data.index_name +
          (data.namespace ? (" (namespace: " + data.namespace + ")") : "") + "."
        );
      } catch (e) {
        setNotice("Upload failed: " + e.message, true);
      }
    }

    document.getElementById("loadBtn").addEventListener("click", load);
    document.getElementById("uploadBtn").addEventListener("click", uploadDocument);
    load();
  </script>
</body>
</html>"""


@router.get("/admin/feedback", response_class=HTMLResponse)
async def feedback_admin() -> HTMLResponse:
    return HTMLResponse(_feedback_page())
