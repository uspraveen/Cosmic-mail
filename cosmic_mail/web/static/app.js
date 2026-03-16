import { api } from "./api.js";
import {
  state, hydrateApiKey, persistApiKey, clearWorkspaceState,
  currentOrganization, linkedAgentsForMailbox, availableMailboxesForAgent, getMailbox,
} from "./state.js";
import {
  renderStats, renderChecklist, renderSystemStatus, renderOverviewAgents,
  renderAgentsTable, renderAgentModalBody, renderManageInboxesModal,
  renderInboxesTable, renderCreateInboxModal, renderCredBanner,
  renderDomainsTable, renderDomainDetail,
  renderThreadList, renderMessagePane, renderComposeModal,
  renderWebhooksTable, renderApiKeys, renderApiKeyBanner,
  renderSyncWorker, renderNewApiKeyModal,
} from "./templates.js";

// ── Boot ──────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  hydrateApiKey();
  bindStaticEvents();
  if (state.apiKey) {
    showApp();
    void loadWorkspace();
  } else {
    showAuth();
  }
});

function showAuth() {
  document.getElementById("auth-overlay").classList.remove("hidden");
}

function showApp() {
  document.getElementById("auth-overlay").classList.add("hidden");
  renderAll();
}

// ── Static Event Binding ──────────────────────────────────────────────────────

function bindStaticEvents() {
  // Auth
  document.getElementById("auth-form").addEventListener("submit", handleAuthSubmit);
  document.getElementById("clear-key-btn").addEventListener("click", handleDisconnect);
  document.getElementById("disconnect-btn")?.addEventListener("click", handleDisconnect);

  // Navigation
  document.getElementById("sidebar").addEventListener("click", handleNavClick);
  document.getElementById("main").addEventListener("click", handleMainClick);

  // Topbar
  document.getElementById("refresh-btn").addEventListener("click", () => void loadWorkspace());
  document.getElementById("sidebar-toggle").addEventListener("click", () => {
    const app = document.getElementById("app");
    const collapsed = app.classList.toggle("sidebar-collapsed");
    const icon = document.getElementById("sidebar-toggle-icon");
    icon.innerHTML = collapsed
      ? `<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="15" y1="3" x2="15" y2="21"/>`
      : `<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/>`;
  });

  // Domain form
  document.getElementById("domain-form").addEventListener("submit", handleDomainCreate);
  document.getElementById("deliverability-form").addEventListener("submit", handleDeliverabilityUpdate);
  document.getElementById("rotate-dkim-btn").addEventListener("click", handleRotateDkim);

  // Webhook form
  document.getElementById("webhook-form").addEventListener("submit", handleWebhookCreate);

  // Conversations
  document.getElementById("thread-mailbox-select").addEventListener("change", handleMailboxSelectChange);
  document.getElementById("thread-list").addEventListener("click", handleThreadListClick);
  document.getElementById("compose-btn").addEventListener("click", handleComposeClick);

  // Inboxes / Agents tables (delegated)
  document.getElementById("new-agent-btn").addEventListener("click", () => openAgentModal(null));
  document.getElementById("new-inbox-btn").addEventListener("click", openCreateInboxModal);
  document.getElementById("sync-all-btn").addEventListener("click", handleSyncAll);

  // Settings
  document.getElementById("new-api-key-btn").addEventListener("click", openNewApiKeyModal);
  document.getElementById("run-sync-btn").addEventListener("click", handleRunSync);

  // Modal
  document.getElementById("modal-close").addEventListener("click", closeModal);
  document.getElementById("modal-overlay").addEventListener("click", e => {
    if (e.target === document.getElementById("modal-overlay")) closeModal();
  });

  // Copy delegation (bubbled)
  document.addEventListener("click", handleCopyClick);

  // Data view button shortcut from overview
  document.querySelectorAll("[data-view]").forEach(el => {
    if (el.classList.contains("btn")) {
      el.addEventListener("click", () => setView(el.dataset.view));
    }
  });
}

// ── Auth ──────────────────────────────────────────────────────────────────────

async function handleAuthSubmit(e) {
  e.preventDefault();
  const key = document.getElementById("api-key-input").value.trim();
  if (!key) { toast("Enter an API key first.", "error"); return; }
  persistApiKey(key);
  showApp();
  await loadWorkspace();
}

function handleDisconnect() {
  persistApiKey("");
  clearWorkspaceState();
  document.getElementById("auth-overlay").classList.remove("hidden");
  document.getElementById("api-key-input").value = "";
}

// ── Workspace Loading ─────────────────────────────────────────────────────────

async function loadWorkspace() {
  try {
    const [readyState, authContext, organizations, domains, mailboxes, agents] = await Promise.all([
      api.getReady(),
      api.getAuthContext(),
      api.listOrganizations(),
      api.listDomains(),
      api.listMailboxes(),
      api.listAgents(),
    ]);
    state.readyState = readyState;
    state.authContext = authContext;
    state.organizations = organizations;
    state.domains = domains;
    state.mailboxes = mailboxes;
    state.agents = agents;

    // Default mailbox selection
    if (!state.selectedMailboxId && mailboxes.length) {
      state.selectedMailboxId = mailboxes[0].id;
    }

    await Promise.all([
      loadSettingsState(),
      loadWebhooks(),
      loadConversationState(),
      state.selectedDomainId ? loadDomainDetail() : Promise.resolve(),
    ]);
    renderAll();
  } catch (err) {
    toast(err.message || "Failed to load workspace.", "error");
    renderAll();
  }
}

async function loadSettingsState() {
  const org = currentOrganization();
  if (!org) { state.apiKeys = []; state.syncWorkerStatus = null; return; }
  const tasks = [api.listOrgApiKeys(org.id)];
  if (state.authContext?.is_admin) tasks.push(api.getSyncWorkerStatus());
  const [apiKeys, syncStatus] = await Promise.all(tasks);
  state.apiKeys = apiKeys;
  state.syncWorkerStatus = syncStatus || null;
}

async function loadWebhooks() {
  try { state.webhooks = await api.listWebhooks(); } catch { state.webhooks = []; }
}

async function loadDomainDetail() {
  if (!state.selectedDomainId) { state.domainDeliverability = null; return; }
  state.domainDeliverability = await api.getDomainDeliverability(state.selectedDomainId);
}

async function loadConversationState() {
  if (!state.selectedMailboxId) { state.threads = []; state.messages = []; state.selectedThreadId = null; return; }
  state.threads = await api.listThreads(state.selectedMailboxId);
  if (state.selectedThreadId && !state.threads.find(t => t.id === state.selectedThreadId)) {
    state.selectedThreadId = null;
  }
  if (!state.selectedThreadId && state.threads.length) state.selectedThreadId = state.threads[0].id;
  state.messages = state.selectedThreadId ? await api.listMessages(state.selectedThreadId) : [];
}

// ── Render All ────────────────────────────────────────────────────────────────

function renderAll() {
  const org = currentOrganization();

  // Sidebar status
  const ok = state.readyState?.status === "ok";
  const dot = document.getElementById("status-dot");
  const label = document.getElementById("status-label");
  if (dot && label) {
    dot.className = "status-dot " + (state.apiKey ? (ok ? "ok" : "degraded") : "");
    label.textContent = state.apiKey ? (ok ? "System ready" : "Degraded") : "Disconnected";
  }
  const keyInfo = document.getElementById("key-info");
  if (keyInfo) {
    keyInfo.innerHTML = state.authContext
      ? `<strong>${state.authContext.is_admin ? "Admin" : "Org"}</strong> ${state.authContext.api_key_name || ""}`
      : "";
  }

  // Stats
  renderStats({ agents: state.agents, mailboxes: state.mailboxes, domains: state.domains, syncWorkerStatus: state.syncWorkerStatus });

  // Nav active state
  document.querySelectorAll(".nav-item[data-view]").forEach(el => {
    el.classList.toggle("active", el.dataset.view === state.activeView);
  });
  document.querySelectorAll("[data-view-panel]").forEach(el => {
    el.classList.toggle("active", el.dataset.viewPanel === state.activeView);
  });

  const title = { overview:"Overview", agents:"Agents", inboxes:"Inboxes", conversations:"Conversations", domains:"Domains", webhooks:"Webhooks", settings:"Settings" };
  document.getElementById("topbar-title").textContent = title[state.activeView] || "Console";

  renderOverviewPanel();
  renderAgentsPanel();
  renderInboxesPanel();
  renderConversationsPanel();
  renderDomainsPanel();
  renderWebhooksPanel();
  renderSettingsPanel();
}

// ── Panel Renderers ───────────────────────────────────────────────────────────

function renderOverviewPanel() {
  const org = currentOrganization();
  const banner = document.getElementById("org-setup-banner");
  if (banner) {
    if (!org) {
      banner.innerHTML = `
        <div class="card" style="border-color:var(--orange-border);background:var(--orange-bg);margin-bottom:1.5rem">
          <div class="card-header"><div class="card-title" style="color:var(--orange)">One-time setup — create your organization</div></div>
          <form id="org-create-form" style="padding:1rem 1.25rem;display:flex;gap:.75rem;align-items:flex-end;flex-wrap:wrap">
            <div style="flex:1;min-width:180px">
              <label class="form-label">Organization name</label>
              <input class="input" id="org-name-input" placeholder="Acme AI" required>
            </div>
            <div style="flex:1;min-width:140px">
              <label class="form-label">Slug <span style="color:var(--text-3);font-weight:400">(url-safe, lowercase)</span></label>
              <input class="input" id="org-slug-input" placeholder="acme-ai" required>
            </div>
            <button type="submit" class="btn btn-primary">Create organization</button>
          </form>
        </div>`;
      document.getElementById("org-create-form").addEventListener("submit", handleOrgCreate);
    } else {
      banner.innerHTML = "";
    }
  }
  const el = document.getElementById("checklist");
  if (el) el.innerHTML = renderChecklist({ agents: state.agents, mailboxes: state.mailboxes, domains: state.domains, readyState: state.readyState });
  const sys = document.getElementById("system-status-card");
  if (sys) sys.innerHTML = renderSystemStatus({ readyState: state.readyState, syncWorkerStatus: state.syncWorkerStatus, authContext: state.authContext });
  const agList = document.getElementById("overview-agents-list");
  if (agList) agList.innerHTML = renderOverviewAgents(state.agents);
}

async function handleOrgCreate(e) {
  e.preventDefault();
  const name = document.getElementById("org-name-input").value.trim();
  const slug = document.getElementById("org-slug-input").value.trim();
  if (!name || !slug) return;
  try {
    await api.createOrganization({ name, slug });
    await loadWorkspace();
    toast("Organization created!", "success");
  } catch (err) {
    toast(err.message, "error");
  }
}

function renderAgentsPanel() {
  const el = document.getElementById("agents-table-container");
  if (el) el.innerHTML = renderAgentsTable(state.agents);
}

function renderInboxesPanel() {
  const banner = document.getElementById("cred-banner-container");
  if (banner) {
    banner.innerHTML = state.issuedCredential ? renderCredBanner(state.issuedCredential) : "";
  }
  const el = document.getElementById("inboxes-table-container");
  if (el) el.innerHTML = renderInboxesTable(state.mailboxes, linkedAgentsForMailbox);
}

function renderConversationsPanel() {
  // Mailbox select
  const sel = document.getElementById("thread-mailbox-select");
  if (sel) {
    const cur = sel.value;
    sel.innerHTML = state.mailboxes.length
      ? state.mailboxes.map(m => `<option value="${m.id}" ${m.id === state.selectedMailboxId ? "selected" : ""}>${m.address}</option>`).join("")
      : `<option value="">No inboxes</option>`;
    if (!sel.value && cur) sel.value = cur;
  }

  // Thread list
  const tl = document.getElementById("thread-list");
  if (tl) tl.innerHTML = renderThreadList(state.threads, state.selectedThreadId);

  // Message pane
  const mp = document.getElementById("message-pane");
  if (!mp) return;
  if (state.selectedThreadId) {
    const thread = state.threads.find(t => t.id === state.selectedThreadId);
    if (thread) {
      mp.innerHTML = renderMessagePane(thread, state.messages);
      document.getElementById("open-reply-btn")?.addEventListener("click", () => {
        document.getElementById("reply-panel").style.display = "";
      });
      bindReplyEvents();
    }
  } else {
    mp.innerHTML = `<div class="message-pane-empty"><div class="empty-state"><div class="empty-icon"><svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg></div><div class="empty-title">No thread selected</div><div class="empty-desc">Select a thread to read messages.</div></div></div>`;
  }
}

function bindReplyEvents() {
  document.querySelector("[data-action='open-reply']")?.addEventListener("click", (e) => {
    const panel = document.getElementById("reply-panel");
    if (panel) panel.style.display = "";
  });
  document.getElementById("close-reply-btn")?.addEventListener("click", () => {
    const panel = document.getElementById("reply-panel");
    if (panel) panel.style.display = "none";
  });
  document.getElementById("send-reply-btn")?.addEventListener("click", handleSendReply);
}

function renderDomainsPanel() {
  const tbl = document.getElementById("domains-table-container");
  if (tbl) tbl.innerHTML = renderDomainsTable(state.domains, state.selectedDomainId);

  const detail = document.getElementById("domain-detail-container");
  if (detail) detail.innerHTML = renderDomainDetail(state.domainDeliverability);

  const delivCard = document.getElementById("deliverability-card");
  if (delivCard) {
    if (state.domainDeliverability) {
      delivCard.style.display = "";
      const d = state.domainDeliverability;
      const p = readDmarcTag(d.dmarc_value, "p");
      document.getElementById("dmarc-policy-select").value = p || "none";
      document.getElementById("dmarc-report-email").value = (readDmarcTag(d.dmarc_value, "rua") || "").replace(/^mailto:/, "");
      document.getElementById("dkim-selector-input").value = d.dkim_selector || "";
    } else {
      delivCard.style.display = "none";
    }
  }
}

function renderWebhooksPanel() {
  const mboxOpts = state.mailboxes.length
    ? [`<option value="">All inboxes</option>`, ...state.mailboxes.map(m => `<option value="${m.id}">${m.address}</option>`)].join("")
    : `<option value="">No inboxes</option>`;
  const mboxSel = document.getElementById("webhook-mailbox-select");
  if (mboxSel) mboxSel.innerHTML = mboxOpts;

  const el = document.getElementById("webhooks-table-container");
  if (el) el.innerHTML = renderWebhooksTable(state.webhooks);
}

function renderSettingsPanel() {
  const keysEl = document.getElementById("api-keys-container");
  if (keysEl) keysEl.innerHTML = renderApiKeys(state.apiKeys);

  const banner = document.getElementById("api-key-banner");
  if (banner) {
    if (state.createdApiKey) {
      banner.innerHTML = renderApiKeyBanner(state.createdApiKey);
      banner.classList.remove("hidden");
    } else {
      banner.classList.add("hidden");
    }
  }

  const syncEl = document.getElementById("sync-worker-container");
  if (syncEl) syncEl.innerHTML = renderSyncWorker(state.syncWorkerStatus, Boolean(state.authContext?.is_admin));

  const keyDisp = document.getElementById("current-key-display");
  if (keyDisp) keyDisp.textContent = state.apiKey ? state.apiKey.slice(0, 20) + "…" : "—";

  const orgEl = document.getElementById("org-detail-container");
  const org = currentOrganization();
  if (orgEl && org) orgEl.innerHTML = `
    <div class="detail-row"><span class="detail-key">Name</span><span class="detail-val">${org.name}</span></div>
    <div class="detail-row"><span class="detail-key">Slug</span><span class="detail-val text-mono">${org.slug}</span></div>
    <div class="detail-row"><span class="detail-key">ID</span><span class="detail-val text-mono">${org.id}</span></div>
  `;
}

// ── Navigation ────────────────────────────────────────────────────────────────

function setView(view) {
  state.activeView = view;
  renderAll();
}

function handleNavClick(e) {
  const item = e.target.closest("[data-view]");
  if (item?.dataset?.view) setView(item.dataset.view);
}

// ── Main delegated click handler ──────────────────────────────────────────────

async function handleMainClick(e) {
  // Nav buttons that switch views
  const viewEl = e.target.closest("[data-view].btn");
  if (viewEl) { setView(viewEl.dataset.view); return; }

  const action = e.target.closest("[data-action]")?.dataset?.action;
  if (!action) return;

  const el = e.target.closest("[data-action]");

  switch (action) {
    case "edit-agent":         openAgentModal(el.dataset.agentId); break;
    case "manage-inboxes":     openManageInboxesModal(el.dataset.agentId); break;
    case "toggle-agent":       await handleToggleAgent(el.dataset.agentId, el.dataset.status); break;
    case "view-threads":       setView("conversations"); state.selectedMailboxId = el.dataset.mailboxId; await loadConversationState(); renderAll(); break;
    case "sync-mailbox":       await handleSyncMailbox(el.dataset.mailboxId); break;
    case "toggle-sync":        await handleToggleSync(el.dataset.mailboxId, el.dataset.enabled === "true"); break;
    case "inspect-domain":     state.selectedDomainId = el.dataset.domainId; await loadDomainDetail(); renderAll(); break;
    case "verify-domain":      await handleVerifyDomain(el.dataset.domainId); break;
    case "delete-webhook":     await handleDeleteWebhook(el.dataset.webhookId); break;
    case "revoke-api-key":     await handleRevokeApiKey(el.dataset.keyId); break;
    case "modal-unlink-inbox": await handleModalUnlinkInbox(el.dataset.agentId, el.dataset.mailboxId); break;
    case "open-reply":         document.getElementById("reply-panel").style.display = ""; break;
  }
}

// ── Agents ────────────────────────────────────────────────────────────────────

function _updateAvatarPreview(url, name) {
  const container = document.getElementById("avatar-preview-container");
  if (!container) return;
  const initials = (name || "?").split(" ").slice(0, 2).map(w => w[0]).join("").toUpperCase();
  if (url) {
    container.innerHTML = `<img src="${url}" style="width:40px;height:40px;border-radius:50%;object-fit:cover;border:1px solid var(--border-2)" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'agent-avatar',style:'width:40px;height:40px',textContent:'${initials}'}))">`;
  } else {
    container.innerHTML = `<div class="agent-avatar" style="width:40px;height:40px">${initials}</div>`;
  }
}

function _updateSigGraphicPreview(url) {
  const container = document.getElementById("sig-graphic-preview");
  if (!container) return;
  if (url) {
    container.innerHTML = `<img src="${url}" alt="Signature graphic" style="width:48px;height:48px;border-radius:8px;object-fit:cover">`;
  } else {
    container.innerHTML = `<div style="width:48px;height:48px;border-radius:8px;background:var(--surface-2);display:flex;align-items:center;justify-content:center;font-size:11px;color:var(--muted)">None</div>`;
  }
}

function openAgentModal(agentId) {
  const agent = agentId ? state.agents.find(a => a.id === agentId) : null;
  window._pendingAvatarFile = null;
  window._pendingSigGraphicFile = null;
  openModal(agent ? "Edit agent" : "New agent", renderAgentModalBody(agent, state.domains), [
    { label: agent ? "Save changes" : "Create agent", cls: "btn-primary", id: "modal-submit" },
    { label: "Cancel", cls: "btn-ghost", id: "modal-cancel" },
  ]);
  document.getElementById("modal-submit").addEventListener("click", () => submitAgentModal(agentId));
  document.getElementById("modal-cancel").addEventListener("click", closeModal);

  const uploadBtn = document.getElementById("avatar-upload-btn");
  const fileInput = document.getElementById("modal-agent-avatar-file");
  const clearBtn  = document.getElementById("avatar-clear-btn");
  if (uploadBtn && fileInput) {
    uploadBtn.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      if (agentId) {
        const fd = new FormData();
        fd.append("file", file);
        try {
          await api.uploadAgentAvatar(agentId, fd);
          const bust = `?t=${Date.now()}`;
          document.getElementById("modal-agent-avatar").value = `/v1/agents/${agentId}/avatar`;
          _updateAvatarPreview(`/v1/agents/${agentId}/avatar${bust}`, agent?.name || "");
          uploadBtn.textContent = "Change photo";
          toast("Photo updated.", "success");
          void loadWorkspace();
        } catch (err) { toast(err.message, "error"); }
      } else {
        window._pendingAvatarFile = file;
        _updateAvatarPreview(URL.createObjectURL(file), document.getElementById("modal-agent-name").value || "");
        uploadBtn.textContent = "Change photo";
      }
    });
  }
  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      document.getElementById("modal-agent-avatar").value = "";
      window._pendingAvatarFile = null;
      _updateAvatarPreview("", agent?.name || "");
      clearBtn.remove();
      if (uploadBtn) uploadBtn.textContent = "Upload photo";
    });
  }

  // Signature graphic upload
  const sigUploadBtn = document.getElementById("sig-graphic-upload-btn");
  const sigFileInput = document.getElementById("modal-agent-sig-graphic-file");
  const sigClearBtn  = document.getElementById("sig-graphic-clear-btn");
  if (sigUploadBtn && sigFileInput) {
    sigUploadBtn.addEventListener("click", () => sigFileInput.click());
    sigFileInput.addEventListener("change", async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      if (agentId) {
        const fd = new FormData();
        fd.append("file", file);
        try {
          await api.uploadSignatureGraphic(agentId, fd);
          const bust = `?t=${Date.now()}`;
          _updateSigGraphicPreview(`/v1/agents/${agentId}/signature-graphic${bust}`);
          sigUploadBtn.textContent = "Change";
          toast("Signature graphic updated.", "success");
          void loadWorkspace();
        } catch (err) { toast(err.message, "error"); }
      } else {
        window._pendingSigGraphicFile = file;
        _updateSigGraphicPreview(URL.createObjectURL(file));
        sigUploadBtn.textContent = "Change";
      }
    });
  }
  if (sigClearBtn) {
    sigClearBtn.addEventListener("click", async () => {
      if (agentId) {
        try {
          await api.updateAgent(agentId, { signature_graphic_url: null });
          void loadWorkspace();
        } catch {}
      }
      _updateSigGraphicPreview(null);
      sigClearBtn.remove();
      if (sigUploadBtn) sigUploadBtn.textContent = "Upload";
    });
  }
}

async function submitAgentModal(agentId) {
  const org = currentOrganization();
  if (!org) { toast("No organization found.", "error"); return; }
  const payload = {
    organization_id: org.id,
    name:            document.getElementById("modal-agent-name").value.trim(),
    title:           document.getElementById("modal-agent-title").value.trim() || null,
    slug:            document.getElementById("modal-agent-slug").value.trim() || null,
    default_domain_id: document.getElementById("modal-agent-domain").value || null,
    persona_summary: document.getElementById("modal-agent-persona").value.trim() || null,
    system_prompt:   document.getElementById("modal-agent-prompt").value.trim() || null,
    signature:       document.getElementById("modal-agent-signature").value.trim() || null,
    accent_color:    document.getElementById("modal-agent-color").value || "#f97316",
    avatar_url:      document.getElementById("modal-agent-avatar")?.value.trim() || null,
  };
  if (!payload.name) { toast("Name is required.", "error"); return; }
  try {
    if (agentId) {
      await api.updateAgent(agentId, payload);
      toast("Agent updated.", "success");
    } else {
      const newAgent = await api.createAgent(payload);
      if (window._pendingAvatarFile) {
        const fd = new FormData();
        fd.append("file", window._pendingAvatarFile);
        window._pendingAvatarFile = null;
        try { await api.uploadAgentAvatar(newAgent.id, fd); } catch {}
      }
      if (window._pendingSigGraphicFile) {
        const fd = new FormData();
        fd.append("file", window._pendingSigGraphicFile);
        window._pendingSigGraphicFile = null;
        try { await api.uploadSignatureGraphic(newAgent.id, fd); } catch {}
      }
      toast("Agent created.", "success");
    }
    closeModal();
    await loadWorkspace();
  } catch (err) { toast(err.message, "error"); }
}

function openManageInboxesModal(agentId) {
  const agent = state.agents.find(a => a.id === agentId);
  if (!agent) return;
  const available = availableMailboxesForAgent(agent);
  openModal(`Inboxes — ${agent.name}`, renderManageInboxesModal(agent, available), [
    { label: "Link inbox", cls: "btn-primary", id: "modal-link-submit" },
    { label: "Done", cls: "btn-ghost", id: "modal-done" },
  ], "modal-lg");
  document.getElementById("modal-link-submit").addEventListener("click", () => submitLinkInbox(agentId));
  document.getElementById("modal-done").addEventListener("click", closeModal);
  // bind unlink buttons inside modal
  document.getElementById("modal-body").addEventListener("click", handleMainClick);
}

async function submitLinkInbox(agentId) {
  const mailboxId = document.getElementById("modal-link-inbox-select")?.value;
  if (!mailboxId) { toast("Choose an inbox.", "error"); return; }
  const label = document.getElementById("modal-link-inbox-label")?.value.trim() || null;
  const isPrimary = document.getElementById("modal-link-inbox-primary")?.checked || false;
  try {
    await api.linkAgentMailbox(agentId, { mailbox_id: mailboxId, label, is_primary: isPrimary });
    toast("Inbox linked.", "success");
    await loadWorkspace();
    // Re-render modal content
    const agent = state.agents.find(a => a.id === agentId);
    if (agent) {
      const available = availableMailboxesForAgent(agent);
      document.getElementById("modal-body").innerHTML = renderManageInboxesModal(agent, available);
      document.getElementById("modal-body").addEventListener("click", handleMainClick);
    }
  } catch (err) { toast(err.message, "error"); }
}

async function handleModalUnlinkInbox(agentId, mailboxId) {
  try {
    await api.unlinkAgentMailbox(agentId, mailboxId);
    toast("Inbox unlinked.", "success");
    await loadWorkspace();
    const agent = state.agents.find(a => a.id === agentId);
    if (agent) {
      const available = availableMailboxesForAgent(agent);
      document.getElementById("modal-body").innerHTML = renderManageInboxesModal(agent, available);
    }
  } catch (err) { toast(err.message, "error"); }
}

async function handleToggleAgent(agentId, currentStatus) {
  try {
    await api.updateAgent(agentId, { status: currentStatus === "active" ? "paused" : "active" });
    await loadWorkspace();
  } catch (err) { toast(err.message, "error"); }
}

// ── Inboxes ───────────────────────────────────────────────────────────────────

function openCreateInboxModal() {
  openModal("New inbox", renderCreateInboxModal(state.domains.filter(d => d.status === "active")), [
    { label: "Create inbox", cls: "btn-primary", id: "modal-submit" },
    { label: "Cancel", cls: "btn-ghost", id: "modal-cancel" },
  ]);
  document.getElementById("modal-submit").addEventListener("click", submitCreateInbox);
  document.getElementById("modal-cancel").addEventListener("click", closeModal);
}

async function submitCreateInbox() {
  const domainId   = document.getElementById("modal-inbox-domain").value;
  const localPart  = document.getElementById("modal-inbox-local").value.trim();
  const displayName= document.getElementById("modal-inbox-display").value.trim() || null;
  const quotaMb    = parseInt(document.getElementById("modal-inbox-quota").value) || 1024;
  if (!domainId || !localPart) { toast("Domain and local part are required.", "error"); return; }
  try {
    const mailbox = await api.createMailbox({ domain_id: domainId, local_part: localPart, display_name: displayName, quota_mb: quotaMb });
    state.issuedCredential = mailbox.issued_password ? { address: mailbox.address, password: mailbox.issued_password } : null;
    closeModal();
    setView("inboxes");
    await loadWorkspace();
    toast("Inbox created.", "success");
  } catch (err) { toast(err.message, "error"); }
}

async function handleSyncMailbox(mailboxId) {
  try {
    await api.syncMailbox(mailboxId);
    await loadWorkspace();
    toast("Sync complete.", "success");
  } catch (err) { toast(err.message, "error"); }
}

async function handleSyncAll() {
  const org = currentOrganization();
  if (!org) { toast("No organization.", "error"); return; }
  try {
    await api.syncOrgMailboxes(org.id);
    await loadWorkspace();
    toast("Sync complete.", "success");
  } catch (err) { toast(err.message, "error"); }
}

async function handleToggleSync(mailboxId, currentEnabled) {
  try {
    await api.updateSyncPolicy(mailboxId, { enabled: !currentEnabled });
    await loadWorkspace();
    toast(`Sync ${!currentEnabled ? "enabled" : "disabled"}.`, "success");
  } catch (err) { toast(err.message, "error"); }
}

// ── Domains ───────────────────────────────────────────────────────────────────

async function handleDomainCreate(e) {
  e.preventDefault();
  const org = currentOrganization();
  const name = document.getElementById("domain-name-input").value.trim();
  if (!org || !name) { toast("Organization and domain name are required.", "error"); return; }
  try {
    const domain = await api.createDomain({ organization_id: org.id, domain: name });
    state.selectedDomainId = domain.id;
    document.getElementById("domain-form").reset();
    await loadWorkspace();
    toast("Domain linked.", "success");
  } catch (err) { toast(err.message, "error"); }
}

async function handleVerifyDomain(domainId) {
  try {
    await api.verifyDomain(domainId);
    state.selectedDomainId = domainId;
    await loadWorkspace();
    toast("Verification refreshed.", "success");
  } catch (err) { toast(err.message, "error"); }
}

async function handleDeliverabilityUpdate(e) {
  e.preventDefault();
  if (!state.selectedDomainId) { toast("Select a domain first.", "error"); return; }
  try {
    await api.updateDomainDeliverability(state.selectedDomainId, {
      dmarc_policy: document.getElementById("dmarc-policy-select").value || null,
      dmarc_aggregate_report_email: document.getElementById("dmarc-report-email").value.trim() || null,
    });
    await loadDomainDetail();
    renderAll();
    toast("Settings saved.", "success");
  } catch (err) { toast(err.message, "error"); }
}

async function handleRotateDkim() {
  if (!state.selectedDomainId) { toast("Select a domain first.", "error"); return; }
  const selector = document.getElementById("dkim-selector-input").value.trim() || null;
  try {
    await api.rotateDkim(state.selectedDomainId, { selector });
    await loadDomainDetail();
    renderAll();
    toast("DKIM key rotated.", "success");
  } catch (err) { toast(err.message, "error"); }
}

// ── Conversations ─────────────────────────────────────────────────────────────

async function handleMailboxSelectChange(e) {
  state.selectedMailboxId = e.target.value || null;
  state.selectedThreadId = null;
  await loadConversationState();
  renderAll();
}

async function handleThreadListClick(e) {
  const btn = e.target.closest("[data-thread-id]");
  if (!btn) return;
  state.selectedThreadId = btn.dataset.threadId;
  try {
    state.messages = await api.listMessages(state.selectedThreadId);
    renderAll();
  } catch (err) { toast(err.message, "error"); }
}

function handleComposeClick() {
  if (!state.mailboxes.length) { toast("Create an inbox first.", "error"); return; }
  openModal("New message", renderComposeModal(state.mailboxes), [
    { label: "Send", cls: "btn-primary", id: "modal-submit" },
    { label: "Cancel", cls: "btn-ghost", id: "modal-cancel" },
  ]);
  document.getElementById("modal-submit").addEventListener("click", submitCompose);
  document.getElementById("modal-cancel").addEventListener("click", closeModal);
}

async function submitCompose() {
  const mailboxId = document.getElementById("modal-compose-mailbox").value;
  const to        = document.getElementById("modal-compose-to").value.trim();
  const subject   = document.getElementById("modal-compose-subject").value.trim();
  const body      = document.getElementById("modal-compose-body").value.trim();
  if (!mailboxId || !to || !subject || !body) { toast("All fields are required.", "error"); return; }
  try {
    const draft = await api.createDraft({ mailbox_id: mailboxId, to_recipients: [{ email: to }], subject, text_body: body });

    // Upload attachments if any
    const fileInput = document.getElementById("modal-compose-files");
    if (fileInput?.files?.length) {
      const maxBytes = 25 * 1024 * 1024;
      for (const file of Array.from(fileInput.files)) {
        if (file.size > maxBytes) { toast(`${file.name} exceeds 25 MB — skipped.`, "error"); continue; }
        const formData = new FormData();
        formData.append("file", file);
        await api.uploadDraftAttachment(draft.id, formData);
      }
    }

    await api.sendDraft(draft.id);
    closeModal();
    if (state.selectedMailboxId === mailboxId) await loadConversationState();
    await loadWorkspace();
    toast("Message sent.", "success");
  } catch (err) { toast(err.message, "error"); }
}

async function handleSendReply(e) {
  const threadId = e.currentTarget.dataset.threadId || state.selectedThreadId;
  const body = document.getElementById("reply-body")?.value.trim();
  if (!body) { toast("Write a reply first.", "error"); return; }
  if (!state.selectedMailboxId) { toast("No mailbox selected.", "error"); return; }
  try {
    await api.replyToThread(threadId, { mailbox_id: state.selectedMailboxId, text_body: body });
    state.messages = await api.listMessages(threadId);
    const panel = document.getElementById("reply-panel");
    if (panel) panel.style.display = "none";
    document.getElementById("reply-body").value = "";
    renderAll();
    toast("Reply sent.", "success");
  } catch (err) { toast(err.message, "error"); }
}

// ── Webhooks ──────────────────────────────────────────────────────────────────

async function handleWebhookCreate(e) {
  e.preventDefault();
  const org = currentOrganization();
  if (!org) { toast("No organization.", "error"); return; }
  const url = document.getElementById("webhook-url-input").value.trim();
  if (!url) { toast("URL is required.", "error"); return; }
  const mailboxId = document.getElementById("webhook-mailbox-select").value || null;
  const eventType = document.getElementById("webhook-event-select").value;
  const secret = document.getElementById("webhook-secret-input").value.trim() || null;
  try {
    await api.createWebhook({ mailbox_id: mailboxId, event_type: eventType, url, secret });
    document.getElementById("webhook-form").reset();
    await loadWebhooks();
    renderAll();
    toast("Webhook registered.", "success");
  } catch (err) { toast(err.message, "error"); }
}

async function handleDeleteWebhook(webhookId) {
  try {
    await api.deleteWebhook(webhookId);
    await loadWebhooks();
    renderAll();
    toast("Webhook deleted.", "success");
  } catch (err) { toast(err.message, "error"); }
}

// ── Settings ──────────────────────────────────────────────────────────────────

function openNewApiKeyModal() {
  const org = currentOrganization();
  if (!org) { toast("No organization.", "error"); return; }
  openModal("New API key", renderNewApiKeyModal(), [
    { label: "Create key", cls: "btn-primary", id: "modal-submit" },
    { label: "Cancel", cls: "btn-ghost", id: "modal-cancel" },
  ]);
  document.getElementById("modal-submit").addEventListener("click", submitNewApiKey);
  document.getElementById("modal-cancel").addEventListener("click", closeModal);
}

async function submitNewApiKey() {
  const org = currentOrganization();
  const name = document.getElementById("modal-api-key-name").value.trim();
  if (!name) { toast("Key name is required.", "error"); return; }
  try {
    const result = await api.createOrgApiKey(org.id, { name });
    state.createdApiKey = result;
    closeModal();
    await loadSettingsState();
    renderAll();
    toast("API key created.", "success");
  } catch (err) { toast(err.message, "error"); }
}

async function handleRevokeApiKey(keyId) {
  const org = currentOrganization();
  if (!org) return;
  try {
    await api.revokeOrgApiKey(org.id, keyId);
    await loadSettingsState();
    renderAll();
    toast("API key revoked.", "success");
  } catch (err) { toast(err.message, "error"); }
}

async function handleRunSync() {
  const org = currentOrganization();
  try {
    await api.runSyncWorker(org?.id || null);
    await loadSettingsState();
    renderAll();
    toast("Sync worker run complete.", "success");
  } catch (err) { toast(err.message, "error"); }
}

// ── Modal ─────────────────────────────────────────────────────────────────────

function openModal(title, bodyHtml, buttons = [], extraClass = "") {
  document.getElementById("modal-title").textContent = title;
  document.getElementById("modal-body").innerHTML = bodyHtml;
  const footer = document.getElementById("modal-footer");
  footer.innerHTML = buttons.map(b => `<button class="btn ${b.cls}" id="${b.id}">${b.label}</button>`).join("");
  const modal = document.getElementById("modal");
  modal.className = `modal ${extraClass}`;
  document.getElementById("modal-overlay").classList.remove("hidden");
}

function closeModal() {
  document.getElementById("modal-overlay").classList.add("hidden");
  document.getElementById("modal-body").innerHTML = "";
  document.getElementById("modal-footer").innerHTML = "";
}

// ── Copy ──────────────────────────────────────────────────────────────────────

function handleCopyClick(e) {
  const btn = e.target.closest("[data-copy]");
  if (!btn) return;
  navigator.clipboard.writeText(btn.dataset.copy).then(() => toast("Copied!", "success")).catch(() => {});
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function readDmarcTag(value, tag) {
  if (!value) return null;
  const entry = value.split(";").map(s => s.trim()).find(s => s.toLowerCase().startsWith(tag.toLowerCase() + "="));
  return entry ? entry.split("=", 2)[1] : null;
}

function toast(message, kind = "success") {
  const t = document.createElement("div");
  t.className = `toast ${kind}`;
  t.textContent = message;
  document.getElementById("toast-stack").appendChild(t);
  setTimeout(() => t.remove(), 4000);
}
