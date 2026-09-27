/**
 * Marsh Pitch Generator — Frontend Engine
 * Handles policy selection, drag-and-drop uploads, pipeline orchestration,
 * interactive carousel rendering, and factual audit inspection.
 */

// State
let state = {
  policies: [],
  selectedPolicies: [],
  currentSlideIdx: 0,
  pitchData: null,
  auditReport: null,
  companyProfile: null,
  pptxUrl: null,
  chunksCache: {}
};

// Initialize on DOM load
document.addEventListener("DOMContentLoaded", () => {
  lucide.createIcons();
  fetchPolicies();
});

// Set company from quick presets
function setCompany(name) {
  document.getElementById("companyNameInput").value = name;
}

// ---------------------------------------------------------------------------
// 1. Policy Management & Uploads
// ---------------------------------------------------------------------------
async function fetchPolicies() {
  try {
    const res = await fetch("/api/policies");
    if (!res.ok) throw new Error("Failed to load policies");
    const data = await res.json();
    state.policies = data.policies || [];
    state.selectedPolicies = state.policies.map(p => p.doc_name);
    
    document.getElementById("headerClauseCount").innerText = `${data.total_chunks} Clauses Indexed`;
    renderPolicyList();
  } catch (err) {
    showAlert("Error loading policy documents: " + err.message, "error");
  }
}

function renderPolicyList() {
  const container = document.getElementById("policiesList");
  if (!state.policies.length) {
    container.innerHTML = '<div class="text-xs text-slate-400 py-2">No policies indexed. Upload one below.</div>';
    return;
  }

  container.innerHTML = state.policies.map(p => {
    const isChecked = state.selectedPolicies.includes(p.doc_name);
    const cleanName = p.doc_name.replace(/_/g, " ");
    return `
      <label class="flex items-center justify-between p-2 rounded-lg hover:bg-slate-100 border border-slate-200/80 bg-white cursor-pointer transition text-xs shadow-xs">
        <div class="flex items-center space-x-2">
          <input 
            type="checkbox" 
            value="${p.doc_name}" 
            ${isChecked ? 'checked' : ''} 
            onchange="togglePolicy('${p.doc_name}', this.checked)"
            class="rounded border-slate-300 text-marsh-blue focus:ring-marsh-blue w-3.5 h-3.5"
          >
          <span class="font-medium text-slate-700">${cleanName}</span>
        </div>
        <span class="text-[10px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-500 font-semibold">${p.chunk_count} clauses</span>
      </label>
    `;
  }).join("");

  updatePolicyOverflowNotice();
  
  // Attach scroll listener to update notice when scrolled
  container.onscroll = () => {
    updatePolicyOverflowNotice();
  };

  lucide.createIcons();
}

function updatePolicyOverflowNotice() {
  const container = document.getElementById("policiesList");
  const summaryEl = document.getElementById("policySelectedSummary");
  const noticeEl = document.getElementById("policyScrollNotice");
  if (!summaryEl || !noticeEl || !container) return;

  summaryEl.innerText = `${state.selectedPolicies.length} of ${state.policies.length} selected`;

  const total = state.policies.length;
  // Estimate visible items based on height (approx 2.5 items visible at 144px height)
  const isScrollable = container.scrollHeight > container.clientHeight;
  const isAtBottom = (container.scrollHeight - container.scrollTop - container.clientHeight) < 10;

  if (isScrollable) {
    if (isAtBottom) {
      noticeEl.innerHTML = `<span class="text-slate-400">✓ All ${total} shown</span>`;
    } else {
      const remaining = Math.max(1, total - 2);
      noticeEl.innerHTML = `<span class="text-marsh-blue font-bold animate-pulse">↓ +${remaining} more below (scroll)</span>`;
    }
  } else {
    noticeEl.innerHTML = `<span class="text-slate-400">✓ All visible</span>`;
  }
}

function togglePolicy(docName, isChecked) {
  if (isChecked) {
    if (!state.selectedPolicies.includes(docName)) state.selectedPolicies.push(docName);
  } else {
    state.selectedPolicies = state.selectedPolicies.filter(d => d !== docName);
  }
  updatePolicyOverflowNotice();
}

async function handleFileUpload(event) {
  const file = event.target.files[0];
  if (!file) return;

  const feedback = document.getElementById("uploadFeedback");
  feedback.classList.remove("hidden", "text-rose-600", "text-emerald-600");
  feedback.classList.add("text-marsh-blue");
  feedback.innerText = `Uploading and indexing ${file.name}...`;

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/upload-policy", {
      method: "POST",
      body: formData
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload failed");

    feedback.classList.remove("text-marsh-blue");
    feedback.classList.add("text-emerald-600");
    feedback.innerText = `✓ Successfully indexed ${data.details.new_chunk_count} new sections from ${file.name}!`;

    await fetchPolicies();
  } catch (err) {
    feedback.classList.remove("text-marsh-blue");
    feedback.classList.add("text-rose-600");
    feedback.innerText = `Upload failed: ${err.message}`;
  }
}

// ---------------------------------------------------------------------------
// 2. Main Generation & Audit Pipeline
// ---------------------------------------------------------------------------
async function startPipeline() {
  const companyName = document.getElementById("companyNameInput").value.trim();
  if (!companyName) {
    showAlert("Please enter a target company name.", "warning");
    return;
  }
  if (!state.selectedPolicies.length) {
    showAlert("Please select at least one policy document to ground the pitch in.", "warning");
    return;
  }

  // Reset & UI setup
  hideAlert();
  document.getElementById("generateBtn").disabled = true;
  document.getElementById("generateBtn").classList.add("opacity-50", "cursor-not-allowed");
  document.getElementById("stepperContainer").classList.remove("hidden");
  document.getElementById("resultsWorkspace").classList.add("hidden");

  let startTime = Date.now();
  const timerInterval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    document.getElementById("stepperTimer").innerText = `${elapsed}s elapsed`;
  }, 1000);

  try {
    // ---- STEP 1: Company Profile ----
    setStepActive("step-profile", "Profiling Client...");
    const profileRes = await fetch("/api/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_name: companyName })
    });
    if (!profileRes.ok) {
      const err = await profileRes.json();
      throw new Error(err.detail || "Failed to generate company profile");
    }
    state.companyProfile = await profileRes.json();
    setStepDone("step-profile", "Profile Complete");

    // ---- STEP 2: Grounded Pitch Synthesis ----
    setStepActive("step-pitch", "Synthesizing Slides...");
    const pitchRes = await fetch("/api/pitch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        company_profile: state.companyProfile,
        selected_policies: state.selectedPolicies
      })
    });
    if (!pitchRes.ok) {
      const err = await pitchRes.json();
      throw new Error(err.detail || "Failed to generate pitch slides");
    }
    state.pitchData = await pitchRes.json();
    setStepDone("step-pitch", `${state.pitchData.slides.length} Slides Created`);

    // ---- STEP 3: Two-Step Factual Audit ----
    setStepActive("step-audit", "Running Audit...");
    const auditRes = await fetch("/api/audit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pitch_data: state.pitchData,
        selected_policies: state.selectedPolicies
      })
    });
    if (!auditRes.ok) {
      const err = await auditRes.json();
      throw new Error(err.detail || "Failed to audit pitch");
    }
    state.auditReport = await auditRes.json();
    setStepDone("step-audit", `Status: ${state.auditReport.overall_status.toUpperCase()}`);

    clearInterval(timerInterval);
    renderResults(companyName);
  } catch (err) {
    clearInterval(timerInterval);
    showAlert(`Pipeline failed: ${err.message}`, "error");
  } finally {
    document.getElementById("generateBtn").disabled = false;
    document.getElementById("generateBtn").classList.remove("opacity-50", "cursor-not-allowed");
  }
}

function setStepActive(stepId, label) {
  const el = document.getElementById(stepId);
  el.className = "flex items-center space-x-3 p-3 rounded-xl bg-blue-50 border border-blue-200 text-marsh-blue font-bold";
  el.querySelector(".step-icon").className = "step-icon w-6 h-6 rounded-full bg-marsh-blue text-white flex items-center justify-center font-bold animate-pulse text-xs";
  el.querySelector("span").innerText = label;
}

function setStepDone(stepId, label) {
  const el = document.getElementById(stepId);
  el.className = "flex items-center space-x-3 p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 font-semibold";
  el.querySelector(".step-icon").className = "step-icon w-6 h-6 rounded-full bg-emerald-600 text-white flex items-center justify-center font-bold text-xs";
  el.querySelector(".step-icon").innerText = "✓";
  el.querySelector("span").innerText = label;
}

// ---------------------------------------------------------------------------
// 3. Render Results & Slides
// ---------------------------------------------------------------------------
function renderResults(companyName) {
  document.getElementById("resultsWorkspace").classList.remove("hidden");
  document.getElementById("resultCompanyName").innerText = companyName;

  // Recommended Policy Banner
  const rec = state.pitchData.recommended_policy;
  const cleanDoc = (rec.doc_name || "Preferred Policy").replace(/_/g, " ");
  document.getElementById("resultRecommendedSummary").innerText = `Recommended Carrier: ${cleanDoc} — ${rec.reason}`;

  // Audit Status Badge in Header
  const badge = document.getElementById("resultAuditBadge");
  const status = state.auditReport.overall_status.toLowerCase();
  if (status === "pass") {
    badge.className = "px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-emerald-500 text-white";
    badge.innerText = "✓ AUDIT PASSED";
  } else if (status === "fail") {
    badge.className = "px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-rose-600 text-white";
    badge.innerText = "✗ AUDIT FAILED";
  } else {
    badge.className = "px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-amber-400 text-slate-900";
    badge.innerText = "⚠ NEEDS REVIEW";
  }

  // Populate Slide Deck
  state.currentSlideIdx = 0;
  renderCurrentSlide();
  renderSlideThumbs();

  // Populate Audit Report
  renderAuditReport();

  // Populate Profile
  renderCompanyProfile();

  switchTab("slides");
  lucide.createIcons();

  // Scroll to results
  document.getElementById("resultsWorkspace").scrollIntoView({ behavior: "smooth" });
}

// Slide Viewer
function renderCurrentSlide() {
  const slides = state.pitchData.slides || [];
  if (!slides.length) return;

  const current = slides[state.currentSlideIdx];
  document.getElementById("currentSlideTracker").innerText = `Slide ${state.currentSlideIdx + 1} of ${slides.length}`;
  document.getElementById("currentSlideTitle").innerText = current.title;

  const bulletsContainer = document.getElementById("currentSlideBullets");
  bulletsContainer.innerHTML = (current.bullets || []).map((b, i) => {
    const text = typeof b === "object" ? b.text : b;
    const sourceId = typeof b === "object" ? b.source_chunk_id : null;

    let sourceChip = "";
    if (sourceId) {
      sourceChip = `
        <button onclick="inspectClause('${sourceId}')" class="text-[11px] px-2 py-0.5 rounded bg-blue-50 hover:bg-blue-100 text-marsh-blue border border-blue-200 font-medium inline-flex items-center space-x-1 mt-1 transition">
          <i data-lucide="shield-check" class="w-3 h-3 text-emerald-600"></i>
          <span>Verified Clause: <strong>${sourceId}</strong></span>
        </button>
      `;
    } else {
      sourceChip = `
        <span class="text-[11px] px-2 py-0.5 rounded bg-slate-100 text-slate-500 font-medium inline-block mt-1">
          Strategic Context (Profile-Grounded)
        </span>
      `;
    }

    return `
      <div class="slide-card p-4 rounded-xl bg-marsh-ice border border-slate-200 hover:border-marsh-sky shadow-sm transition">
        <div class="flex items-start space-x-3">
          <div class="w-6 h-6 rounded-md bg-white border border-slate-300 text-marsh-navy flex items-center justify-center font-bold text-xs shrink-0 mt-0.5">
            ${i + 1}
          </div>
          <div class="flex-grow">
            <p class="text-sm font-medium text-slate-800 leading-snug">${text}</p>
            ${sourceChip}
          </div>
        </div>
      </div>
    `;
  }).join("");

  lucide.createIcons();
}

function nextSlide() {
  const slides = state.pitchData.slides || [];
  if (state.currentSlideIdx < slides.length - 1) {
    state.currentSlideIdx++;
    renderCurrentSlide();
    updateThumbActive();
  }
}

function prevSlide() {
  if (state.currentSlideIdx > 0) {
    state.currentSlideIdx--;
    renderCurrentSlide();
    updateThumbActive();
  }
}

function setSlide(idx) {
  state.currentSlideIdx = idx;
  renderCurrentSlide();
  updateThumbActive();
}

function renderSlideThumbs() {
  const container = document.getElementById("slideThumbsGrid");
  const slides = state.pitchData.slides || [];
  container.innerHTML = slides.map((s, i) => `
    <button 
      id="thumb-${i}"
      onclick="setSlide(${i})" 
      class="p-2.5 rounded-xl border text-left transition ${i === state.currentSlideIdx ? 'bg-blue-50 border-marsh-blue shadow-sm' : 'bg-white border-slate-200 hover:bg-slate-50'}"
    >
      <span class="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Slide ${i + 1}</span>
      <span class="text-xs font-semibold text-slate-700 line-clamp-1">${s.title}</span>
    </button>
  `).join("");
}

function updateThumbActive() {
  const slides = state.pitchData.slides || [];
  slides.forEach((_, i) => {
    const el = document.getElementById(`thumb-${i}`);
    if (!el) return;
    if (i === state.currentSlideIdx) {
      el.className = "p-2.5 rounded-xl border text-left transition bg-blue-50 border-marsh-blue shadow-sm";
    } else {
      el.className = "p-2.5 rounded-xl border text-left transition bg-white border-slate-200 hover:bg-slate-50";
    }
  });
}

// ---------------------------------------------------------------------------
// 4. Audit Reporting & Compliance
// ---------------------------------------------------------------------------
function renderAuditReport() {
  const r = state.auditReport;
  const status = r.overall_status.toLowerCase();

  const statusEl = document.getElementById("kpiAuditStatus");
  statusEl.innerText = r.overall_status;
  if (status === "pass") {
    statusEl.className = "text-xl font-extrabold text-emerald-600 mt-1 uppercase";
    document.getElementById("kpiStatusDesc").innerText = "All figures verified against policy filings";
  } else if (status === "fail") {
    statusEl.className = "text-xl font-extrabold text-rose-600 mt-1 uppercase";
    document.getElementById("kpiStatusDesc").innerText = "Discrepancy or unsupported claims flagged";
  } else {
    statusEl.className = "text-xl font-extrabold text-amber-500 mt-1 uppercase";
    document.getElementById("kpiStatusDesc").innerText = "Advisor review recommended";
  }

  const scorePct = Math.round((r.confidence_score || 0) * 100);
  document.getElementById("kpiConfidenceScore").innerText = `${scorePct}%`;
  document.getElementById("kpiVerifiedCount").innerText = `${r.verified_claims_count} / ${r.total_sourced_claims || r.verified_claims_count}`;
  
  const flagged = r.flagged_claims || [];
  document.getElementById("kpiFlaggedCount").innerText = flagged.length;
  document.getElementById("auditTabFlagCount").innerText = flagged.length;

  const container = document.getElementById("flaggedClaimsContainer");
  if (!flagged.length) {
    container.innerHTML = `
      <div class="p-6 text-center bg-emerald-50 rounded-xl border border-emerald-100 text-emerald-800">
        <i data-lucide="check-circle-2" class="w-8 h-8 mx-auto text-emerald-600 mb-2"></i>
        <h4 class="font-bold text-sm">Perfect Audit Traceability</h4>
        <p class="text-xs text-emerald-700 mt-1">Every benefit claim, waiting period, and sum insured figure traces back directly to IRDAI source filings.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = flagged.map(f => {
    let badgeClass = "bg-amber-100 text-amber-800 border-amber-200";
    if (f.status === "not_supported" || f.status === "invalid_reference") {
      badgeClass = "bg-rose-100 text-rose-800 border-rose-200";
    }

    return `
      <div class="p-4 rounded-xl border border-slate-200 bg-slate-50 flex items-start justify-between gap-4 text-xs">
        <div class="space-y-1 flex-grow">
          <div class="flex items-center space-x-2">
            <span class="font-bold text-slate-800">Slide ${f.slide}</span>
            <span class="px-2 py-0.5 rounded-full border text-[10px] font-semibold uppercase ${badgeClass}">${f.status}</span>
          </div>
          <p class="text-slate-700 font-medium">"${f.bullet_text}"</p>
          <p class="text-slate-500 italic"><strong class="not-italic text-slate-700">Audit Finding:</strong> ${f.reason}</p>
        </div>
      </div>
    `;
  }).join("");
  lucide.createIcons();
}

function approvePitch() {
  showAlert("✓ Pitch approved by Advisor for client delivery.", "success");
}

function rejectPitch() {
  showAlert("Pitch rejected. Adjust policy selections or re-run generator.", "warning");
}

// ---------------------------------------------------------------------------
// 5. Company Risk Profile
// ---------------------------------------------------------------------------
function renderCompanyProfile() {
  const p = state.companyProfile;
  if (!p) return;

  document.getElementById("profCompanyName").innerText = p.company_name;
  document.getElementById("profIndustry").innerText = p.industry;
  document.getElementById("profSize").innerText = p.size;
  document.getElementById("profDataSource").innerText = p.data_source || "Wikipedia";

  // Assumptions
  const assumpContainer = document.getElementById("profAssumptions");
  if (!p.assumptions || !p.assumptions.length) {
    assumpContainer.innerHTML = '<span class="text-slate-400">Zero assumptions made; profile fully confident.</span>';
  } else {
    assumpContainer.innerHTML = p.assumptions.map(a => `
      <div class="p-2.5 rounded-lg bg-amber-50 border border-amber-200">
        <div class="font-bold text-amber-900">${a.field.toUpperCase()}: ${a.assumed_value}</div>
        <div class="text-amber-800 mt-0.5">${a.justification}</div>
      </div>
    `).join("");
  }

  // Risks
  const risksContainer = document.getElementById("profRisksList");
  risksContainer.innerHTML = (p.key_risks || []).map(r => `
    <div class="p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-700 font-medium flex items-start space-x-2">
      <i data-lucide="activity" class="w-4 h-4 text-marsh-blue shrink-0 mt-0.5"></i>
      <span>${r}</span>
    </div>
  `).join("");
  lucide.createIcons();
}

// ---------------------------------------------------------------------------
// 6. Clause Inspector Modal
// ---------------------------------------------------------------------------
async function inspectClause(chunkId) {
  document.getElementById("modalClauseTitle").innerText = `Policy Clause: ${chunkId}`;
  document.getElementById("modalClauseBody").innerHTML = '<div class="text-xs text-slate-400 py-4 text-center">Loading verified clause from policy index...</div>';
  document.getElementById("clauseModal").classList.remove("hidden");

  try {
    const res = await fetch(`/api/clause/${encodeURIComponent(chunkId)}`);
    if (!res.ok) throw new Error("Clause not found");
    const data = await res.json();
    
    document.getElementById("modalClauseTitle").innerText = `${data.section_title} [${data.doc_name.replace(/_/g, ' ')}]`;
    document.getElementById("modalClauseBody").innerHTML = `
      <div class="space-y-3">
        <div class="flex items-center space-x-2 text-xs text-slate-500 pb-2 border-b">
          <span><strong>Document:</strong> ${data.doc_name}</span>
          <span>•</span>
          <span><strong>Section:</strong> ${data.section_title}</span>
          <span>•</span>
          <span><strong>Page:</strong> ${data.page_number || 'N/A'}</span>
        </div>
        <div class="text-slate-800 text-xs font-mono whitespace-pre-wrap leading-relaxed bg-white p-3 rounded-lg border border-slate-200">
${data.text}
        </div>
      </div>
    `;
  } catch (err) {
    document.getElementById("modalClauseBody").innerText = `Clause ID: ${chunkId} (Details unavailable: ${err.message})`;
  }
}

function closeClauseModal() {
  document.getElementById("clauseModal").classList.add("hidden");
}

// ---------------------------------------------------------------------------
// 7. Tabs & Alert Utilities
// ---------------------------------------------------------------------------
function switchTab(tab) {
  const tabs = ['slides', 'audit', 'profile'];
  tabs.forEach(t => {
    document.getElementById(`tab-content-${t}`).classList.add("hidden");
    const btn = document.getElementById(`tab-btn-${t}`);
    btn.className = "py-3 px-4 font-medium text-sm border-b-2 border-transparent text-slate-500 hover:text-slate-800 flex items-center space-x-2";
  });

  document.getElementById(`tab-content-${tab}`).classList.remove("hidden");
  const activeBtn = document.getElementById(`tab-btn-${tab}`);
  activeBtn.className = "py-3 px-4 font-semibold text-sm border-b-2 border-marsh-navy text-marsh-navy flex items-center space-x-2";
}

function showAlert(message, type = "info") {
  const alertEl = document.getElementById("statusAlert");
  alertEl.classList.remove("hidden", "bg-rose-50", "border-rose-200", "text-rose-800", "bg-emerald-50", "border-emerald-200", "text-emerald-800", "bg-amber-50", "border-amber-200", "text-amber-800");

  let icon = "alert-circle";
  if (type === "error") {
    alertEl.classList.add("bg-rose-50", "border-rose-200", "text-rose-800");
    icon = "alert-octagon";
  } else if (type === "success") {
    alertEl.classList.add("bg-emerald-50", "border-emerald-200", "text-emerald-800");
    icon = "check-circle";
  } else if (type === "warning") {
    alertEl.classList.add("bg-amber-50", "border-amber-200", "text-amber-800");
    icon = "alert-triangle";
  } else {
    alertEl.classList.add("bg-blue-50", "border-blue-200", "text-marsh-blue");
  }

  alertEl.innerHTML = `
    <i data-lucide="${icon}" class="w-5 h-5 shrink-0"></i>
    <span class="font-medium">${message}</span>
  `;
  lucide.createIcons();
}

function hideAlert() {
  document.getElementById("statusAlert").classList.add("hidden");
}

// ---------------------------------------------------------------------------
// 4. On-Demand Lazy Downloads (PPTX & Audit PDF)
// ---------------------------------------------------------------------------
async function downloadPptx() {
  if (!state.pitchData) {
    showAlert("No pitch data available to export.", "warning");
    return;
  }
  const companyName = document.getElementById("companyNameInput").value.trim() || "Client";
  const btn = document.getElementById("downloadPptxBtn");
  const labelEl = document.getElementById("downloadPptxLabel");
  const origText = labelEl ? labelEl.innerText : "Download Pitch Deck (.pptx)";

  try {
    btn.disabled = true;
    btn.classList.add("opacity-75", "cursor-wait");
    if (labelEl) labelEl.innerText = "Generating Deck...";

    const res = await fetch("/api/render-pptx", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pitch_data: state.pitchData,
        company_name: companyName
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to render PowerPoint deck");
    }

    const data = await res.json();

    // Fetch file directly as binary blob to eliminate browser navigation/404 issues
    const fileRes = await fetch(data.download_url);
    if (!fileRes.ok) {
      throw new Error(`File retrieval failed (HTTP ${fileRes.status})`);
    }
    const blob = await fileRes.blob();
    const blobUrl = window.URL.createObjectURL(blob);

    const link = document.createElement("a");
    link.href = blobUrl;
    link.download = data.filename;
    document.body.appendChild(link);
    link.click();

    setTimeout(() => {
      window.URL.revokeObjectURL(blobUrl);
      link.remove();
    }, 500);
  } catch (err) {
    showAlert(`PowerPoint export failed: ${err.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.classList.remove("opacity-75", "cursor-wait");
    if (labelEl) labelEl.innerText = origText;
    lucide.createIcons();
  }
}

async function downloadAuditPdf() {
  if (!state.pitchData || !state.auditReport) {
    showAlert("No audit data available to export.", "warning");
    return;
  }
  const companyName = document.getElementById("companyNameInput").value.trim() || "Client";
  const btn = document.getElementById("downloadAuditPdfBtn");
  const labelEl = document.getElementById("downloadAuditPdfLabel");
  const origText = labelEl ? labelEl.innerText : "Download Audit Report (.pdf)";

  try {
    btn.disabled = true;
    btn.classList.add("opacity-75", "cursor-wait");
    if (labelEl) labelEl.innerText = "Generating Audit PDF...";

    const res = await fetch("/api/render-audit-pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        company_name: companyName,
        company_profile: state.companyProfile,
        pitch_data: state.pitchData,
        audit_report: state.auditReport,
        selected_policies: state.selectedPolicies
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to render Audit PDF");
    }

    const data = await res.json();

    // Fetch file directly as binary blob to eliminate browser navigation/404 issues
    const fileRes = await fetch(data.download_url);
    if (!fileRes.ok) {
      throw new Error(`Audit report retrieval failed (HTTP ${fileRes.status})`);
    }
    const blob = await fileRes.blob();
    const blobUrl = window.URL.createObjectURL(blob);

    const link = document.createElement("a");
    link.href = blobUrl;
    link.download = data.filename;
    document.body.appendChild(link);
    link.click();

    setTimeout(() => {
      window.URL.revokeObjectURL(blobUrl);
      link.remove();
    }, 500);
  } catch (err) {
    showAlert(`Audit PDF export failed: ${err.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.classList.remove("opacity-75", "cursor-wait");
    if (labelEl) labelEl.innerText = origText;
    lucide.createIcons();
  }
}


