from flask import Flask, request, jsonify
from flask_cors import CORS
from pypdf import PdfReader
import os
import uuid
import tempfile
import time
import requests

app = Flask(__name__)
CORS(app)

# Uploads are saved OUTSIDE the project folder (in the system temp directory)
# on purpose. If this folder lived inside the project, tools like VS Code's
# Live Preview would detect the file being written/deleted and force-reload
# the page mid-request, wiping the summary that was about to display.
UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), "pdf_summarizer_uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------------------------------------------------------------------
# IMPORTANT: This must be the CURRENT Colab localtunnel URL + "/summarize".
# Localtunnel gives you a NEW random URL every time you restart the Colab
# notebook, so this value goes stale after every Colab restart.
# ---------------------------------------------------------------------------
AI_SERVER_URL = os.getenv("AI_SERVER_URL")

if not AI_SERVER_URL:
    entered = input(
        "Paste the CURRENT Colab localtunnel URL (e.g.  https://easy-sites-shout.loca.lt): "
    ).strip()
    if not entered:
        raise SystemExit("No URL provided. Restart and paste the Colab tunnel URL.")
    entered = entered.rstrip("/")
    if not entered.endswith("/summarize"):
        entered += "/summarize"
    AI_SERVER_URL = entered

print(f"[INFO] Forwarding PDF text to AI server at: {AI_SERVER_URL}")

AI_TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT_SECONDS", "240"))

# Each chunk sent to the model. Kept small so every single request finishes
# well before localtunnel's idle timeout (~60-90s), no matter how long the
# whole PDF is.
CHUNK_CHARS = 6000


def extract_text(pdf_path):
    reader = PdfReader(pdf_path)
    text = ""

    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"

    return text


def chunk_text(text, chunk_size=CHUNK_CHARS):
    """Split text into chunks, breaking on paragraph boundaries where possible
    so we don't cut a sentence in half mid-chunk."""
    paragraphs = text.split("\n")
    chunks = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 1 > chunk_size:
            if current:
                chunks.append(current)
            current = para
        else:
            current += ("\n" if current else "") + para

    if current:
        chunks.append(current)

    return chunks


def call_ai_server(text, max_tokens, retries=4):
    """Sends text to the Colab AI server. Automatically retries a few times
    if the tunnel returns a 503 (Tunnel Unavailable) or drops the connection,
    since localtunnel's free service is occasionally flaky."""
    last_error = None

    for attempt in range(retries):
        try:
            response = requests.post(
                AI_SERVER_URL,
                json={"text": text, "max_tokens": max_tokens},
                headers={"bypass-tunnel-reminder": "true"},
                timeout=AI_TIMEOUT_SECONDS
            )

            if response.status_code in (502, 503, 504):
                print(f"[WARN] Tunnel/gateway error ({response.status_code}), retrying ({attempt + 1}/{retries})...")
                last_error = RuntimeError(f"Tunnel/gateway error ({response.status_code})")
                time.sleep(3)
                continue

            if response.status_code != 200:
                raise RuntimeError(
                    f"AI server returned status {response.status_code}: {response.text[:300]}"
                )

            data = response.json()

            if "summary" not in data:
                raise RuntimeError(f"AI server sent no 'summary' field: {data}")

            return data["summary"]

        except requests.exceptions.ConnectionError as e:
            last_error = e
            print(f"[WARN] Connection error, retrying ({attempt + 1}/{retries})...")
            time.sleep(3)

    raise RuntimeError(f"Failed after {retries} attempts. Last error: {last_error}")


@app.route("/summarize", methods=["POST"])
def summarize():

    if "pdf" not in request.files:
        return jsonify({"error": "No PDF uploaded"}), 400

    pdf = request.files["pdf"]

    if not pdf.filename:
        return jsonify({"error": "No PDF filename provided"}), 400

    filepath = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}.pdf")
    pdf.save(filepath)

    try:
        text = extract_text(filepath)

        if not text.strip():
            return jsonify({
                "error": "Could not extract any text from this PDF (it may be scanned/image-only)."
            }), 400

        chunks = chunk_text(text)
        print(f"[INFO] Document split into {len(chunks)} chunk(s).")

        # Short document: one call is enough, no need to combine anything.
        if len(chunks) == 1:
            print("[INFO] Sending entire document to AI server...")
            summary = call_ai_server(chunks[0], max_tokens=800)
            return jsonify({"summary": summary})

        # Long document: summarize each chunk separately (small, fast calls),
        # then join the partial summaries directly — no extra model call,
        # so there's no risk of a combine step timing out.
        partial_summaries = []
        for i, chunk in enumerate(chunks):
            print(f"[INFO] Summarizing chunk {i + 1}/{len(chunks)}...")
            partial = call_ai_server(chunk, max_tokens=500)
            partial_summaries.append(f"#### Section {i + 1}\n\n{partial}")

        final_summary = "\n\n---\n\n".join(partial_summaries)
        return jsonify({"summary": final_summary})

    except requests.exceptions.ConnectionError:
        return jsonify({
            "error": "Could not connect to the Colab AI server. This almost always means "
                     "either (1) the Colab notebook is not running / has disconnected, or "
                     "(2) the tunnel URL is stale. Restart Colab, get the new URL, and "
                     "restart this script."
        }), 502

    except requests.exceptions.Timeout:
        return jsonify({
            "error": "The AI server took too long to respond. Check that the Colab "
                     "model is running and try again."
        }), 504

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        return jsonify({"error": str(e)}), 500

    finally:
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception:
                pass


if __name__ == "__main__":
    app.run(debug=False, port=5000, use_reloader=False)