how to run 
cd "C:\Users\manikanp\OneDrive - Capgemini\My Resources\L&D\Agentic AI\RAG\My notes AI"
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py

# Notes AI

A small, local web app for asking questions about the notes you upload. It retrieves relevant text with TF-IDF and sends that context to the AI model configured in your existing `.env` file.

## Run it

1. Open PowerShell in this project folder.
2. Activate the existing virtual environment, or create one:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

   If you do not have a virtual environment yet:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install the dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Make sure `.env` contains your existing `AI_BASE_URL`, `AI_MODEL`, and `AI_API_KEY` values. Optional `AI_AUTH_HEADER` and `AI_AUTH_PREFIX` settings are also supported. The app reads these settings as-is; it does not replace the model or credentials.
5. Start the app:

   ```powershell
   python main.py
   ```

6. Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser. Press **Ctrl+C** in PowerShell to stop the server.

## Use it

- `notes.txt` is loaded automatically when the app starts.
- Add one or more PDF or UTF-8 TXT files in **Add your notes**. Files can be up to 10 MB each; the total upload is limited to 25 MB.
- Ask a question in **Ask a question**. The answer panel displays the response and the source filenames used for retrieval.
- **Clear all** removes the current notes from the app's in-memory workspace. Uploaded documents are not saved to disk and are cleared when the server stops.

The server listens on `127.0.0.1` by default. The API key stays on the server and is not sent to the browser. Relevant retrieved note text and your question are sent to the AI service at the configured `AI_BASE_URL` to generate an answer. Scanned/image-only PDFs may not contain extractable text.

Optional local settings:

```dotenv
NOTES_AI_HOST=127.0.0.1
NOTES_AI_PORT=8000
```
