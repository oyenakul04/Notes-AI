import json
import os
import re
import threading
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from dotenv import load_dotenv
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
STATIC_FILES = {"index.html", "styles.css", "app.js"}
MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_UPLOAD_SIZE = 25 * 1024 * 1024
MAX_DOCUMENT_CHARS = 1_000_000
MAX_QUESTION_LENGTH = 2_000
load_dotenv(ROOT / ".env")


def split_into_chunks(text):
    return [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", text)
        if paragraph.strip()
    ]


def extract_document_text(filename, content):
    extension = Path(filename).suffix.lower()
    if extension == ".txt":
        text = content.decode("utf-8-sig")
    elif extension == ".pdf":
        try:
            reader = PdfReader(BytesIO(content))
        except PdfReadError as error:
            raise ValueError(f"{filename} is not a readable PDF file.") from error
        if reader.is_encrypted:
            raise ValueError(f"{filename} is password-protected.")
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
    else:
        raise ValueError(f"{filename} is not a supported PDF or TXT file.")

    text = text.strip()
    if not text:
        raise ValueError(f"No readable text was found in {filename}.")
    if len(text) > MAX_DOCUMENT_CHARS:
        raise ValueError(f"{filename} exceeds the 1,000,000-character limit.")
    return text


class NotesIndex:
    def __init__(self):
        self.lock = threading.Lock()
        self.documents = {}
        self.chunks = []
        self.vectorizer = None
        self.chunk_vectors = None

        notes_file = ROOT / "notes.txt"
        if notes_file.exists():
            content = notes_file.read_text(encoding="utf-8")
            if content.strip():
                self._replace_documents({"notes.txt": content})

    def _build_index(self, documents):
        chunks = [
            {"source": filename, "text": chunk}
            for filename, text in documents.items()
            for chunk in split_into_chunks(text)
        ]
        if not chunks:
            return chunks, None, None

        vectorizer = TfidfVectorizer(stop_words="english")
        try:
            vectors = vectorizer.fit_transform([item["text"] for item in chunks])
        except ValueError as error:
            if "empty vocabulary" in str(error).lower():
                raise ValueError(
                    "The document contains no searchable English text."
                ) from error
            raise
        return chunks, vectorizer, vectors

    def _replace_documents(self, documents):
        chunks, vectorizer, vectors = self._build_index(documents)
        self.documents = documents
        self.chunks = chunks
        self.vectorizer = vectorizer
        self.chunk_vectors = vectors

    def add_documents(self, new_documents):
        with self.lock:
            documents = {**self.documents, **new_documents}
            self._replace_documents(documents)
            return self._list_documents_unlocked()

    def clear_documents(self):
        with self.lock:
            self._replace_documents({})
            return []

    def list_documents(self):
        with self.lock:
            return self._list_documents_unlocked()

    def _list_documents_unlocked(self):
        return [
            {"name": name, "characters": len(text)}
            for name, text in self.documents.items()
        ]

    def retrieve(self, question, top_k=3):
        with self.lock:
            if self.vectorizer is None or self.chunk_vectors is None:
                return []
            question_vector = self.vectorizer.transform([question])
            similarities = cosine_similarity(
                question_vector, self.chunk_vectors
            ).flatten()
            best_indices = similarities.argsort()[::-1][:top_k]
            return [
                {
                    "source": self.chunks[index]["source"],
                    "text": self.chunks[index]["text"],
                    "score": float(similarities[index]),
                }
                for index in best_indices
                if similarities[index] > 0
            ]


notes_index = NotesIndex()


def generate_answer(question, retrieved_notes):
    base_url = os.getenv("AI_BASE_URL")
    model = os.getenv("AI_MODEL")
    api_key = os.getenv("AI_API_KEY")
    if not base_url or not model or not api_key:
        raise RuntimeError(
            "AI configuration is incomplete. Check AI_BASE_URL, AI_MODEL, "
            "and AI_API_KEY in .env."
        )

    auth_header = os.getenv("AI_AUTH_HEADER", "Authorization")
    auth_prefix = os.getenv("AI_AUTH_PREFIX", "Bearer")
    context = "\n\n".join(
        f"Source: {item['source']}\n{item['text']}" for item in retrieved_notes
    )
    prompt = f"""You are Notes AI, a helpful study assistant.

Answer the question using ONLY the provided notes.
If the notes do not contain the answer, say that the information is not available in the notes.
Do not invent information.

NOTES:
{context}

QUESTION:
{question}

ANSWER:
"""
    headers = {
        auth_header: f"{auth_prefix} {api_key}".strip(),
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }
    response = requests.post(
        base_url.rstrip("/") + "/chat/completions",
        headers=headers,
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    result = response.json()
    try:
        return result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError("The AI service returned an unexpected response.") from error


class NotesAIHandler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = self._content_length()
        if length > MAX_UPLOAD_SIZE:
            raise ValueError("Request is too large.")
        try:
            return json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("Request body must be valid JSON.") from error

    def _content_length(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Invalid content length.") from error
        if length < 0:
            raise ValueError("Invalid content length.")
        return length

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/documents":
            self._send_json(200, {"documents": notes_index.list_documents()})
            return

        if path == "/":
            relative_path = "index.html"
        elif path.startswith("/static/"):
            relative_path = unquote(path.removeprefix("/static/"))
        else:
            relative_path = ""
        if relative_path not in STATIC_FILES:
            self.send_error(404)
            return
        file_path = (STATIC_DIR / relative_path).resolve()
        if not file_path.is_relative_to(STATIC_DIR.resolve()) or not file_path.is_file():
            self.send_error(404)
            return

        content_type = (
            "text/html; charset=utf-8"
            if file_path.suffix == ".html"
            else "text/css; charset=utf-8"
            if file_path.suffix == ".css"
            else "text/javascript; charset=utf-8"
        )
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/documents":
                self._upload_documents()
            elif path == "/api/ask":
                self._answer_question()
            else:
                self._send_json(404, {"error": "Endpoint not found."})
        except ValueError as error:
            self._send_json(400, {"error": str(error)})
        except requests.RequestException:
            self._send_json(
                502,
                {"error": "Could not reach the configured AI service. Check the service and .env settings."},
            )
        except RuntimeError as error:
            self._send_json(502, {"error": str(error)})

    def _upload_documents(self):
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data"):
            raise ValueError("Upload must use multipart form data.")

        length = self._content_length()
        if length == 0:
            raise ValueError("Choose at least one PDF or TXT file.")
        if length > MAX_UPLOAD_SIZE:
            raise ValueError("Total upload must be 25 MB or smaller.")

        message = BytesParser(policy=policy.default).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode()
            + self.rfile.read(length)
        )
        uploads = {}
        for part in message.iter_parts():
            filename = part.get_filename()
            if not filename:
                continue
            safe_name = Path(filename.replace("\\", "/")).name
            content = part.get_payload(decode=True) or b""
            if len(content) > MAX_FILE_SIZE:
                raise ValueError(f"{safe_name} exceeds the 10 MB per-file limit.")
            if safe_name in uploads:
                raise ValueError(f"Duplicate filename in upload: {safe_name}.")
            try:
                uploads[safe_name] = extract_document_text(safe_name, content)
            except UnicodeDecodeError as error:
                raise ValueError(f"{safe_name} must be a UTF-8 encoded text file.") from error

        if not uploads:
            raise ValueError("Choose at least one PDF or TXT file.")
        documents = notes_index.add_documents(uploads)
        self._send_json(200, {"documents": documents})

    def _answer_question(self):
        data = self._read_json()
        question = data.get("question", "") if isinstance(data, dict) else ""
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Enter a question about your notes.")
        question = question.strip()
        if len(question) > MAX_QUESTION_LENGTH:
            raise ValueError("Question must be 2,000 characters or fewer.")

        retrieved = notes_index.retrieve(question)
        if not retrieved:
            self._send_json(
                200,
                {
                    "answer": "I couldn't find relevant information in the uploaded notes.",
                    "sources": [],
                },
            )
            return

        answer = generate_answer(question, retrieved)
        self._send_json(
            200,
            {
                "answer": answer,
                "sources": [
                    {"name": item["source"], "score": round(item["score"], 3)}
                    for item in retrieved
                ],
            },
        )

    def do_DELETE(self):
        if urlparse(self.path).path != "/api/documents":
            self._send_json(404, {"error": "Endpoint not found."})
            return
        self._send_json(200, {"documents": notes_index.clear_documents()})

    def log_message(self, format_string, *args):
        print(f"{self.address_string()} - {format_string % args}")


if __name__ == "__main__":
    host = os.getenv("NOTES_AI_HOST", "127.0.0.1")
    port = int(os.getenv("NOTES_AI_PORT", "8000"))
    server = ThreadingHTTPServer((host, port), NotesAIHandler)
    print(f"Notes AI is ready at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Notes AI...")
    finally:
        server.server_close()
