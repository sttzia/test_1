const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const api = {
  async list() {
    const r = await fetch("/api/notes");
    if (!r.ok) throw new Error("Failed to list");
    return r.json();
  },
  async get(id) {
    const r = await fetch(`/api/notes/${id}`);
    if (!r.ok) throw new Error("Not found");
    return r.json();
  },
  async create(data) {
    const r = await fetch("/api/notes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!r.ok) throw new Error("Failed to create");
    return r.json();
  },
  async update(id, data) {
    const r = await fetch(`/api/notes/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!r.ok) throw new Error("Failed to update");
    return r.json();
  },
  async remove(id) {
    const r = await fetch(`/api/notes/${id}`, { method: "DELETE" });
    if (!r.ok && r.status !== 204) throw new Error("Failed to delete");
    return true;
  },
};

let state = { notes: [], filtered: [], activeId: null, dirty: false };

function fmtDate(s) {
  try {
    return new Date(s).toLocaleString();
  } catch {
    return s;
  }
}

function renderList() {
  const ul = $("#notesList");
  ul.innerHTML = "";
  for (const n of state.filtered) {
    const li = document.createElement("li");
    li.dataset.id = n.id;
    li.className = n.id === state.activeId ? "active" : "";
    const title = document.createElement("div");
    title.textContent = n.title || "Untitled";
    const small = document.createElement("small");
    small.textContent = fmtDate(n.updated_at);
    li.append(title, small);
    li.addEventListener("click", () => selectNote(n.id));
    ul.appendChild(li);
  }
}

function startClock() {
  const el = document.getElementById("timestamp");
  if (!el) return;
  const tick = () => {
    const now = new Date();
    el.textContent = now.toLocaleString();
    el.title = now.toISOString();
  };
  tick();
  if (state._clock) clearInterval(state._clock);
  state._clock = setInterval(tick, 1000);
}

function setStatus(msg, timeout = 1200) {
  const s = $("#status");
  s.textContent = msg;
  if (timeout)
    setTimeout(() => {
      if (s.textContent === msg) s.textContent = "";
    }, timeout);
}

async function loadNotes() {
  state.notes = await api.list();
  state.filtered = state.notes;
  renderList();
}

async function selectNote(id) {
  // If dirty, prompt before switching
  if (state.dirty && state.activeId !== id) {
    const ok = confirm("Discard unsaved changes?");
    if (!ok) return;
  }
  const note = state.notes.find((n) => n.id === id) || (await api.get(id));
  state.activeId = id;
  state.dirty = false;
  $("#titleInput").value = note.title || "";
  $("#contentInput").value = note.content || "";
  renderList();
}

async function newNote() {
  // Optimistic create with default values
  const created = await api.create({ title: "Untitled", content: "" });
  await loadNotes();
  await selectNote(created.id);
}

async function saveNote() {
  if (!state.activeId) {
    // If no active note, create one with current inputs
    const created = await api.create({
      title: $("#titleInput").value.trim() || "Untitled",
      content: $("#contentInput").value,
    });
    await loadNotes();
    await selectNote(created.id);
    setStatus("Created");
    return;
  }
  const payload = {
    title: $("#titleInput").value.trim(),
    content: $("#contentInput").value,
  };
  const updated = await api.update(state.activeId, payload);
  // Update in-memory list
  const idx = state.notes.findIndex((n) => n.id === updated.id);
  if (idx >= 0) state.notes[idx] = updated;
  else state.notes.unshift(updated);
  state.filtered = state.notes;
  state.dirty = false;
  renderList();
  setStatus("Saved");
}

async function deleteNote() {
  if (!state.activeId) return;
  const ok = confirm("Delete this note?");
  if (!ok) return;
  await api.remove(state.activeId);
  state.activeId = null;
  state.dirty = false;
  $("#titleInput").value = "";
  $("#contentInput").value = "";
  await loadNotes();
  setStatus("Deleted");
}

function attachEvents() {
  $("#newNoteBtn").addEventListener("click", newNote);
  $("#saveBtn").addEventListener("click", saveNote);
  $("#deleteBtn").addEventListener("click", deleteNote);
  $("#titleInput").addEventListener("input", () => (state.dirty = true));
  $("#contentInput").addEventListener("input", () => (state.dirty = true));
  $("#searchInput").addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase();
    state.filtered = state.notes.filter(
      (n) =>
        (n.title || "").toLowerCase().includes(q) ||
        (n.content || "").toLowerCase().includes(q)
    );
    renderList();
  });
}

async function init() {
  attachEvents();
  await loadNotes();
  startClock();
}

init().catch((err) => {
  console.error(err);
  setStatus("Error loading notes");
});
