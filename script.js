const dropzone = document.getElementById("dropzone");
const pdfFile = document.getElementById("pdfFile");
const dzTitle = document.getElementById("dzTitle");
const summarizeBtn = document.getElementById("summarizeBtn");

const heroSection = document.querySelector(".hero");
const howSection = document.getElementById("how-it-works");
const resultView = document.getElementById("resultView");
const backBtn = document.getElementById("backBtn");
const resultFilename = document.getElementById("resultFilename");

const pdfPreview = document.getElementById("pdfPreview");
const scanLine = document.getElementById("scanLine");

const loadingState = document.getElementById("loadingState");
const loadingText = document.getElementById("loadingText");
const summaryContent = document.getElementById("summaryContent");
const errorState = document.getElementById("errorState");
const errorText = document.getElementById("errorText");

const BACKEND_URL = "http://127.0.0.1:5000/summarize";

let selectedFile = null;

// ---------- Dropzone interactions ----------
dropzone.addEventListener("click", () => pdfFile.click());
dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    pdfFile.click();
  }
});

["dragenter", "dragover"].forEach(evt =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("drag-over");
  })
);

["dragleave", "drop"].forEach(evt =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.remove("drag-over");
  })
);

dropzone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) handleFileSelected(file);
});

pdfFile.addEventListener("change", () => {
  if (pdfFile.files[0]) handleFileSelected(pdfFile.files[0]);
});

function handleFileSelected(file) {
  if (file.type !== "application/pdf") {
    alert("Please select a PDF file.");
    return;
  }
  selectedFile = file;
  dzTitle.textContent = file.name;
  summarizeBtn.disabled = false;
}

// ---------- Summarize ----------
summarizeBtn.addEventListener("click", async () => {
  if (!selectedFile) return;
  enterResultView(selectedFile);
  await runSummarize(selectedFile);
});

function enterResultView(file) {
  document.documentElement.classList.add("locked");

  heroSection.hidden = true;
  howSection.hidden = true;
  resultView.hidden = false;
  resultFilename.textContent = file.name;

  window.scrollTo({ top: 0, behavior: "instant" });

  const objectUrl = URL.createObjectURL(file);
  pdfPreview.src = objectUrl;

  scanLine.classList.add("active");
  loadingState.hidden = false;
  loadingText.textContent = "✨ Generating your summary…";
  summaryContent.hidden = true;
  summaryContent.textContent = "";
  errorState.hidden = true;
}

async function runSummarize(file) {
  const formData = new FormData();
  formData.append("pdf", file);

  const slowNotice = setTimeout(() => {
    loadingText.textContent = "Still working — larger documents take a little longer…";
  }, 15000);

  try {
    const response = await fetch(BACKEND_URL, {
      method: "POST",
      body: formData
    });

    clearTimeout(slowNotice);

    const contentType = response.headers.get("content-type") || "";
    let data;

    if (contentType.includes("application/json")) {
      data = await response.json();
    } else {
      const rawText = await response.text();
      throw new Error(`Server returned an unexpected response (${response.status}): ${rawText.slice(0, 200)}`);
    }

    if (response.ok && data.summary) {
      showSummary(data.summary);
    } else {
      showError(data.error || "No summary received.");
      console.error("Backend error:", data);
    }
  } catch (error) {
    clearTimeout(slowNotice);
    console.error(error);
    showError(error.message || "Couldn't reach the summarizer server. Make sure your local backend is running.");
  }
}

function showSummary(text) {
  scanLine.classList.remove("active");
  loadingState.hidden = true;
  summaryContent.hidden = false;
  summaryContent.innerHTML = markdownToHtml(text);
}

function markdownToHtml(md) {
  // Minimal markdown renderer: headers, bold, bullet lists, paragraphs.
  const lines = md.split("\n");
  let html = "";
  let inList = false;

  const closeList = () => {
    if (inList) { html += "</ul>"; inList = false; }
  };

  for (let rawLine of lines) {
    const line = rawLine.trim();

    if (line === "") { closeList(); continue; }

    const headerMatch = line.match(/^(#{1,4})\s+(.*)/);
    if (headerMatch) {
      closeList();
      const level = Math.min(headerMatch[1].length + 2, 6); // ## -> h4, #### -> h6
      html += `<h${level}>${inlineMd(headerMatch[2])}</h${level}>`;
      continue;
    }

    const bulletMatch = line.match(/^[-*]\s+(.*)/);
    if (bulletMatch) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${inlineMd(bulletMatch[1])}</li>`;
      continue;
    }

    if (line === "---") { closeList(); html += "<hr>"; continue; }

    closeList();
    html += `<p>${inlineMd(line)}</p>`;
  }
  closeList();
  return html;
}

function inlineMd(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>");
}

function showError(message) {
  scanLine.classList.remove("active");
  loadingState.hidden = true;
  errorState.hidden = false;
  errorText.textContent = message;
}

// ---------- Back to upload ----------
backBtn.addEventListener("click", () => {
  document.documentElement.classList.remove("locked");

  resultView.hidden = true;
  heroSection.hidden = false;
  howSection.hidden = false;

  selectedFile = null;
  pdfFile.value = "";
  dzTitle.textContent = "Drag your PDF here";
  summarizeBtn.disabled = true;
  pdfPreview.src = "";
});