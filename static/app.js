const fileInput = document.querySelector("#file-input");
const uploadForm = document.querySelector("#upload-form");
const uploadButton = document.querySelector("#upload-button");
const selectedFiles = document.querySelector("#selected-files");
const uploadStatus = document.querySelector("#upload-status");
const documentList = document.querySelector("#document-list");
const emptyDocuments = document.querySelector("#empty-documents");
const clearButton = document.querySelector("#clear-button");
const dropZone = document.querySelector(".drop-zone");
const questionForm = document.querySelector("#question-form");
const questionInput = document.querySelector("#question-input");
const askButton = document.querySelector("#ask-button");
const questionStatus = document.querySelector("#question-status");
const answerContent = document.querySelector("#answer-content");
const sources = document.querySelector("#sources");
const sourceList = document.querySelector("#source-list");

let pendingFiles = [];

function showStatus(element, message, isError = false) {
  element.textContent = message;
  element.classList.toggle("is-error", isError);
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.error || "Something went wrong. Please try again.");
  }
  return result;
}

function renderDocuments(documents) {
  documentList.replaceChildren();
  emptyDocuments.hidden = documents.length > 0;
  clearButton.hidden = documents.length === 0;

  for (const docRecord of documents) {
    const item = document.createElement("li");
    item.className = "document-item";

    const tag = document.createElement("span");
    tag.className = "file-tag";
    tag.textContent = docRecord.name.split(".").pop().toUpperCase();

    const name = document.createElement("span");
    name.className = "file-name";
    name.textContent = docRecord.name;
    name.title = docRecord.name;

    const meta = document.createElement("span");
    meta.className = "document-meta";
    meta.textContent = `${docRecord.characters.toLocaleString()} chars`;

    item.append(tag, name, meta);
    documentList.append(item);
  }
}

function renderSelectedFiles() {
  selectedFiles.replaceChildren();
  for (const file of pendingFiles) {
    const row = document.createElement("div");
    row.className = "selected-file";

    const tag = document.createElement("span");
    tag.className = "file-tag";
    tag.textContent = file.name.split(".").pop().toUpperCase();

    const name = document.createElement("span");
    name.className = "file-name";
    name.textContent = file.name;
    name.title = file.name;
    row.append(tag, name);
    selectedFiles.append(row);
  }
  uploadButton.disabled = pendingFiles.length === 0;
}

function selectFiles(files) {
  pendingFiles = Array.from(files);
  renderSelectedFiles();
  showStatus(uploadStatus, "");
}

function renderAnswer(answer) {
  answerContent.replaceChildren();
  const paragraph = document.createElement("p");
  paragraph.className = "answer-text";
  paragraph.textContent = answer;
  answerContent.append(paragraph);
}

function renderSources(items) {
  sourceList.replaceChildren();
  const names = [...new Set(items.map((item) => item.name))];
  for (const name of names) {
    const item = document.createElement("li");
    item.className = "source-chip";
    item.textContent = name;
    sourceList.append(item);
  }
  sources.hidden = names.length === 0;
}

fileInput.addEventListener("change", () => selectFiles(fileInput.files));

for (const eventName of ["dragenter", "dragover"]) {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add("is-dragging");
  });
}

for (const eventName of ["dragleave", "drop"]) {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove("is-dragging");
  });
}

dropZone.addEventListener("drop", (event) => {
  selectFiles(event.dataTransfer.files);
});

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (pendingFiles.length === 0) return;

  const formData = new FormData();
  for (const file of pendingFiles) formData.append("files", file);

  uploadButton.disabled = true;
  uploadButton.textContent = "Adding notes…";
  showStatus(uploadStatus, "");
  try {
    const result = await requestJson("/api/documents", {
      method: "POST",
      body: formData,
    });
    renderDocuments(result.documents);
    pendingFiles = [];
    fileInput.value = "";
    renderSelectedFiles();
    showStatus(uploadStatus, "Your notes are ready. Ask a question whenever you like.");
  } catch (error) {
    showStatus(uploadStatus, error.message, true);
  } finally {
    uploadButton.innerHTML = 'Add selected files <span aria-hidden="true">↗</span>';
    uploadButton.disabled = pendingFiles.length === 0;
  }
});

questionForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = questionInput.value.trim();
  if (!question) return;

  askButton.disabled = true;
  askButton.textContent = "Thinking…";
  showStatus(questionStatus, "");
  answerContent.replaceChildren();
  const loading = document.createElement("p");
  loading.className = "answer-text";
  loading.textContent = "Searching your notes and preparing an answer…";
  answerContent.append(loading);
  renderSources([]);

  try {
    const result = await requestJson("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    renderAnswer(result.answer);
    renderSources(result.sources);
  } catch (error) {
    answerContent.replaceChildren();
    showStatus(questionStatus, error.message, true);
  } finally {
    askButton.innerHTML = 'Ask Notes AI <span aria-hidden="true">→</span>';
    askButton.disabled = false;
  }
});

questionInput.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    questionForm.requestSubmit();
  }
});

clearButton.addEventListener("click", async () => {
  if (!window.confirm("Remove all notes from this workspace?")) return;
  clearButton.disabled = true;
  try {
    const result = await requestJson("/api/documents", { method: "DELETE" });
    renderDocuments(result.documents);
    answerContent.replaceChildren();
    const placeholder = document.createElement("div");
    placeholder.className = "answer-placeholder";
    const message = document.createElement("p");
    message.textContent = "Your answer will appear here.";
    const hint = document.createElement("span");
    hint.textContent = "Upload a note, then ask away.";
    placeholder.append(message, hint);
    answerContent.append(placeholder);
    renderSources([]);
    showStatus(uploadStatus, "All notes have been removed.");
  } catch (error) {
    showStatus(uploadStatus, error.message, true);
  } finally {
    clearButton.disabled = false;
  }
});

requestJson("/api/documents")
  .then((result) => renderDocuments(result.documents))
  .catch((error) => showStatus(uploadStatus, error.message, true));
