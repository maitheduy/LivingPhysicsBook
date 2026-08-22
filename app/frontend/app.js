/**
 * GIÁO TRÌNH AI - Frontend
 */

const API_BASE = ""; // same origin

// DOM
const els = {
  userRequest: document.getElementById("userRequest"),
  templateText: document.getElementById("templateText"),
  grammarText: document.getElementById("grammarText"),
  templateFile: document.getElementById("templateFile"),
  grammarFile: document.getElementById("grammarFile"),
  templateFileName: document.getElementById("templateFileName"),
  grammarFileName: document.getElementById("grammarFileName"),
  clearTemplateFile: document.getElementById("clearTemplateFile"),
  clearGrammarFile: document.getElementById("clearGrammarFile"),
  submitBtn: document.getElementById("submitBtn"),
  progressCard: document.getElementById("progressCard"),
  progressSteps: document.getElementById("progressSteps"),
  answerCard: document.getElementById("answerCard"),
  answerContent: document.getElementById("answerContent"),
  sourcesCard: document.getElementById("sourcesCard"),
  sourcesList: document.getElementById("sourcesList"),
  errorCard: document.getElementById("errorCard"),
  errorMessage: document.getElementById("errorMessage"),
  emptyState: document.getElementById("emptyState"),
  healthStatus: document.getElementById("healthStatus"),
};

// ---------- Health check ----------
async function checkHealth() {
  const dot = els.healthStatus.querySelector(".status-dot");
  const text = els.healthStatus.querySelector(".status-text");
  try {
    const res = await fetch(`${API_BASE}/health`);
    const data = await res.json();
    if (data.status === "ok") {
      dot.classList.add("ok");
      text.textContent = `Sẵn sàng · ${data.vectors} vectors`;
    } else {
      dot.classList.add("error");
      text.textContent = "ChromaDB lỗi";
    }
  } catch (e) {
    dot.classList.add("error");
    text.textContent = "Không kết nối được API";
  }
}

// ---------- File name display ----------
els.templateFile.addEventListener("change", () => {
  const f = els.templateFile.files[0];
  els.templateFileName.textContent = f ? f.name : "";
});

els.grammarFile.addEventListener("change", () => {
  const f = els.grammarFile.files[0];
  els.grammarFileName.textContent = f ? f.name : "";
});

els.clearTemplateFile.addEventListener("click", () => {
  els.templateFile.value = "";
  els.templateFileName.textContent = "";
});

els.clearGrammarFile.addEventListener("click", () => {
  els.grammarFile.value = "";
  els.grammarFileName.textContent = "";
});

// ---------- Progress UI ----------
function showProgress() {
  els.emptyState.hidden = true;
  els.answerCard.hidden = true;
  els.sourcesCard.hidden = true;
  els.errorCard.hidden = true;
  els.progressCard.hidden = false;

  const steps = els.progressSteps.querySelectorAll(".step");
  steps.forEach((s) => {
    s.classList.remove("active", "done");
  });

  // Animate steps
  let current = 0;
  const total = steps.length;

  function advance() {
    if (current > 0) steps[current - 1].classList.remove("active");
    if (current > 0) steps[current - 1].classList.add("done");
    if (current < total) {
      steps[current].classList.add("active");
      current++;
      if (current < total) {
        window._progressTimer = setTimeout(advance, 900);
      }
    }
  }
  advance();
}

function stopProgress() {
  if (window._progressTimer) clearTimeout(window._progressTimer);
  const steps = els.progressSteps.querySelectorAll(".step");
  steps.forEach((s) => {
    s.classList.remove("active");
    s.classList.add("done");
  });
}

// ---------- Render answer (Markdown + MathJax) ----------
function renderAnswer(markdown) {
  // Configure marked
  if (typeof marked !== "undefined") {
    marked.setOptions({
      breaks: true,
      gfm: true,
    });
    els.answerContent.innerHTML = marked.parse(markdown || "");
  } else {
    els.answerContent.textContent = markdown || "";
  }

  // Typeset MathJax
  if (window.MathJax && window.MathJax.typesetPromise) {
    MathJax.typesetPromise([els.answerContent]).catch((err) =>
      console.warn("MathJax error:", err)
    );
  }
}

// ---------- Render sources ----------
function renderSources(sources) {
  if (!sources || sources.length === 0) {
    els.sourcesList.innerHTML =
      '<p style="color:#718096;font-size:0.9rem;">Không tìm thấy nguồn cụ thể trong giáo trình.</p>';
    return;
  }

  els.sourcesList.innerHTML = sources
    .map((s) => {
      const chapterLine = s.chapter_title
        ? `${escapeHtml(s.chapter)} — ${escapeHtml(s.chapter_title)}`
        : escapeHtml(s.chapter);

      let sectionLine = "";
      if (s.section || s.section_title) {
        sectionLine = s.section_title
          ? `Section ${escapeHtml(s.section)} — ${escapeHtml(s.section_title)}`
          : `Section ${escapeHtml(s.section)}`;
      }

      const pagesLine = s.pages
        ? `PDF pages: ${escapeHtml(s.pages)}`
        : "";

      const sourceLine = s.source
        ? `Source: ${escapeHtml(s.source)}`
        : "";

      return `
        <div class="source-item">
          <div class="chapter">${chapterLine}</div>
          ${sectionLine ? `<div class="section">${sectionLine}</div>` : ""}
          ${pagesLine ? `<div class="pages">${pagesLine}</div>` : ""}
          ${sourceLine ? `<div class="source-file">${sourceLine}</div>` : ""}
        </div>
      `;
    })
    .join("");
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ---------- Submit ----------
els.submitBtn.addEventListener("click", async () => {
  const request = els.userRequest.value.trim();
  if (!request) {
    alert("Vui lòng nhập câu hỏi hoặc yêu cầu của bạn.");
    els.userRequest.focus();
    return;
  }

  els.submitBtn.disabled = true;
  showProgress();

  const formData = new FormData();
  formData.append("request", request);
  formData.append("n_results", "8");

  const templateText = els.templateText.value.trim();
  if (templateText) formData.append("template_text", templateText);

  const grammarText = els.grammarText.value.trim();
  if (grammarText) formData.append("response_grammar_text", grammarText);

  if (els.templateFile.files[0]) {
    formData.append("template_file", els.templateFile.files[0]);
  }
  if (els.grammarFile.files[0]) {
    formData.append("grammar_file", els.grammarFile.files[0]);
  }

  try {
    const res = await fetch(`${API_BASE}/api/query-with-files`, {
      method: "POST",
      body: formData,
    });

    const data = await res.json();

    stopProgress();
    els.progressCard.hidden = true;

    if (!res.ok || data.success === false) {
      const msg =
        data.detail ||
        data.message ||
        (typeof data.detail === "string" ? data.detail : "Lỗi không xác định");
      showError(typeof msg === "string" ? msg : JSON.stringify(msg));
      return;
    }

    // Success
    els.answerCard.hidden = false;
    renderAnswer(data.answer);

    if (data.sources && data.sources.length > 0) {
      els.sourcesCard.hidden = false;
      renderSources(data.sources);
    } else {
      els.sourcesCard.hidden = true;
    }

    // Scroll to answer
    els.answerCard.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    stopProgress();
    els.progressCard.hidden = true;
    showError(
      "Không thể kết nối tới máy chủ. Vui lòng kiểm tra backend đang chạy và thử lại."
    );
    console.error(err);
  } finally {
    els.submitBtn.disabled = false;
  }
});

function showError(message) {
  els.emptyState.hidden = true;
  els.answerCard.hidden = true;
  els.sourcesCard.hidden = true;
  els.errorCard.hidden = false;
  els.errorMessage.textContent = message;
}

// ---------- Init ----------
checkHealth();
