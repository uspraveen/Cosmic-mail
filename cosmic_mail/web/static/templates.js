// ── Helpers ───────────────────────────────────────────────────────────────────

export function esc(v) {
  return String(v ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

export function fmtDate(v) {
  if (!v) return "—";
  const d = new Date(v);
  const now = new Date();
  const diff = now - d;
  if (diff < 60000) return "just now";
  if (diff < 3600000) return `${Math.floor(diff/60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff/3600000)}h ago`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function fmtDateFull(v) {
  if (!v) return "—";
  return new Date(v).toLocaleString(undefined, { year:"numeric", month:"short", day:"numeric", hour:"2-digit", minute:"2-digit" });
}

function badge(label, color = "muted") {
  return `<span class="badge badge-${color}"><span class="badge-dot"></span>${esc(label)}</span>`;
}

function emptyState(icon, title, desc) {
  return `<div class="empty-state"><div class="empty-icon">${icon}</div><div class="empty-title">${esc(title)}</div><div class="empty-desc">${esc(desc)}</div></div>`;
}

function copyBtn(value, title = "Copy") {
  return `<button class="btn btn-ghost btn-icon" data-copy="${esc(value)}" title="${title}">
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
  </button>`;
}

function agentInitials(name) {
  return (name || "?").split(" ").slice(0,2).map(w => w[0]).join("").toUpperCase();
}

function agentAvatarHtml(agent, size = 32) {
  if (agent?.avatar_url) {
    return `<img src="${esc(agent.avatar_url)}" alt="${esc(agentInitials(agent.name))}" class="agent-avatar agent-avatar-img" style="width:${size}px;height:${size}px;border-radius:50%;object-fit:cover" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"><div class="agent-avatar" style="background:${esc(agent.accent_color||"#f97316")};width:${size}px;height:${size}px;display:none">${esc(agentInitials(agent.name))}</div>`;
  }
  return `<div class="agent-avatar" style="background:${esc(agent?.accent_color||"#f97316")};width:${size}px;height:${size}px">${esc(agentInitials(agent?.name||"?"))}</div>`;
}

function fmtBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes/1024).toFixed(1)} KB`;
  return `${(bytes/(1024*1024)).toFixed(1)} MB`;
}

function attachmentIcon(contentType) {
  if (contentType?.startsWith("image/")) return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`;
  if (contentType?.includes("pdf")) return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`;
  return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`;
}

const ICONS = {
  agent:   `<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>`,
  inbox:   `<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></svg>`,
  globe:   `<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>`,
  mail:    `<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>`,
  webhook: `<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>`,
};

function checkIcon(done) {
  return done
    ? `<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" fill="rgba(34,197,94,.15)" stroke="#22c55e" stroke-width="1.5"/><polyline points="8 12 11 15 16 9" stroke="#22c55e" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`
    : `<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="#383838" stroke-width="1.5" stroke-dasharray="3 2"/></svg>`;
}

// ── Stats ─────────────────────────────────────────────────────────────────────

export function renderStats({ agents, mailboxes, domains, syncWorkerStatus }) {
  const activeAgents  = agents.filter(a => a.status === "active").length;
  const activeDomains = domains.filter(d => d.status === "active").length;
  const syncVal = syncWorkerStatus
    ? syncWorkerStatus.running ? "Running" : syncWorkerStatus.enabled ? "Armed" : "Paused"
    : "Scoped";

  document.getElementById("stat-agents").textContent  = agents.length;
  document.getElementById("stat-inboxes").textContent = mailboxes.length;
  document.getElementById("stat-domains").textContent = `${activeDomains}/${domains.length}`;
  document.getElementById("stat-sync").textContent    = syncVal;

  // nav badges
  document.getElementById("nav-badge-agents").textContent  = agents.length;
  document.getElementById("nav-badge-inboxes").textContent = mailboxes.length;
  document.getElementById("nav-badge-domains").textContent = domains.length;
}

// ── Checklist ─────────────────────────────────────────────────────────────────

export function renderChecklist({ agents, mailboxes, domains, readyState }) {
  const checks = [
    { done: readyState?.status === "ok",             title: "Control plane",   desc: readyState?.status === "ok" ? "API and database are healthy." : "Resolve readiness failures." },
    { done: domains.some(d => d.status === "active"),title: "Domain verified", desc: "At least one domain with valid DNS." },
    { done: mailboxes.length > 0,                    title: "Inbox created",   desc: "At least one mailbox provisioned." },
    { done: agents.length > 0,                       title: "Agent created",   desc: "At least one agent profile exists." },
  ];
  return checks.map(c => `
    <div class="check-item">
      <span class="check-icon">${checkIcon(c.done)}</span>
      <div class="check-text"><strong>${esc(c.title)}</strong><span>${esc(c.desc)}</span></div>
    </div>
  `).join("");
}

// ── System Status ─────────────────────────────────────────────────────────────

export function renderSystemStatus({ readyState, syncWorkerStatus, authContext }) {
  const dbOk = readyState?.details?.database === "ok";
  const mailOk = readyState?.details?.mail_engine === "ok";
  return `
    <div class="detail-section">
      <div class="detail-label">Infrastructure</div>
      <div class="detail-row"><span class="detail-key">Database</span><span class="detail-val">${badge(dbOk ? "ok" : "error", dbOk ? "green" : "red")}</span></div>
      <div class="detail-row"><span class="detail-key">Mail engine</span><span class="detail-val">${badge(mailOk ? "ok" : "error", mailOk ? "green" : "red")}</span></div>
      ${syncWorkerStatus ? `<div class="detail-row"><span class="detail-key">Sync worker</span><span class="detail-val">${badge(syncWorkerStatus.enabled ? (syncWorkerStatus.running ? "running" : "armed") : "paused", syncWorkerStatus.enabled ? "green" : "muted")}</span></div>` : ""}
    </div>
    ${authContext ? `
    <div class="detail-section">
      <div class="detail-label">Session</div>
      <div class="detail-row"><span class="detail-key">Key type</span><span class="detail-val">${badge(authContext.is_admin ? "Admin" : "Organization", authContext.is_admin ? "orange" : "muted")}</span></div>
      ${authContext.api_key_name ? `<div class="detail-row"><span class="detail-key">Key name</span><span class="detail-val">${esc(authContext.api_key_name)}</span></div>` : ""}
    </div>` : ""}
  `;
}

// ── Overview agents list ──────────────────────────────────────────────────────

export function renderOverviewAgents(agents) {
  if (!agents.length) return emptyState(ICONS.agent, "No agents yet", "Create your first agent to get started.");
  return `<table class="table"><tbody>` +
    agents.slice(0,5).map(a => `
      <tr>
        <td><div class="flex items-center gap-8">
          ${agentAvatarHtml(a)}
          <div><strong>${esc(a.name)}</strong><div class="text-muted" style="font-size:11.5px">${esc(a.title || "Agent")}</div></div>
        </div></td>
        <td>${badge(a.status, a.status === "active" ? "green" : "muted")}</td>
        <td style="font-size:11.5px; color:var(--text-3)">${a.mailboxes?.length || 0} inbox${a.mailboxes?.length !== 1 ? "es" : ""}</td>
      </tr>
    `).join("") +
    `</tbody></table>`;
}

// ── Agents Table ──────────────────────────────────────────────────────────────

export function renderAgentsTable(agents) {
  if (!agents.length) return emptyState(ICONS.agent, "No agents yet", "Create your first agent profile.");
  return `<div class="table-wrap"><table class="table">
    <thead><tr>
      <th>Agent</th><th>Email</th><th>Status</th><th>Default domain</th><th style="text-align:right">Actions</th>
    </tr></thead>
    <tbody>
    ${agents.map(a => {
      const primary = (a.mailboxes || []).find(m => m.is_primary) || a.mailboxes?.[0];
      return `<tr>
        <td><div class="flex items-center gap-8">
          ${agentAvatarHtml(a)}
          <div><strong>${esc(a.name)}</strong><div class="text-muted mt-4" style="font-size:11.5px">${esc(a.title || "Agent profile")}</div></div>
        </div></td>
        <td class="td-mono">${primary ? esc(primary.address) : '<span class="text-muted">No inbox</span>'}</td>
        <td>${badge(a.status, a.status === "active" ? "green" : "muted")}</td>
        <td class="text-muted">${esc(a.default_domain_name || "—")}</td>
        <td class="td-actions"><div class="td-actions-inner">
          <button class="btn btn-ghost btn-xs" data-action="edit-agent" data-agent-id="${a.id}">Edit</button>
          <button class="btn btn-ghost btn-xs" data-action="manage-inboxes" data-agent-id="${a.id}">Inboxes</button>
          <button class="btn btn-ghost btn-xs" data-action="toggle-agent" data-agent-id="${a.id}" data-status="${a.status}">${a.status === "active" ? "Pause" : "Activate"}</button>
        </div></td>
      </tr>`;
    }).join("")}
    </tbody></table></div>`;
}

// ── Create/Edit Agent Modal Body ──────────────────────────────────────────────

export function renderAgentModalBody(agent, domains) {
  const domainOpts = [
    `<option value="">No default domain</option>`,
    ...domains.map(d => `<option value="${d.id}" ${agent?.default_domain_id === d.id ? "selected" : ""}>${esc(d.name)}</option>`)
  ].join("");
  return `
    <div class="form-grid">
      <div class="form-grid form-grid-2">
        <div class="field"><label class="field-label">Name *</label>
          <input class="input" id="modal-agent-name" value="${esc(agent?.name||"")}" placeholder="Alice"></div>
        <div class="field"><label class="field-label">Title</label>
          <input class="input" id="modal-agent-title" value="${esc(agent?.title||"")}" placeholder="Customer Support"></div>
      </div>
      <div class="form-grid form-grid-2">
        <div class="field"><label class="field-label">Slug</label>
          <input class="input input-mono" id="modal-agent-slug" value="${esc(agent?.slug||"")}" placeholder="alice"></div>
        <div class="field"><label class="field-label">Default domain</label>
          <select class="select" id="modal-agent-domain">${domainOpts}</select></div>
      </div>
      <div class="field"><label class="field-label">Persona summary</label>
        <textarea class="textarea" id="modal-agent-persona" rows="2" placeholder="Brief description of who this agent is…">${esc(agent?.persona_summary||"")}</textarea></div>
      <div class="field"><label class="field-label">System prompt</label>
        <textarea class="textarea" id="modal-agent-prompt" rows="4" placeholder="Full system prompt for this agent…">${esc(agent?.system_prompt||"")}</textarea></div>
      <div class="field"><label class="field-label">Email signature</label>
        <textarea class="textarea" id="modal-agent-signature" rows="2" placeholder="Best,\nAlice">${esc(agent?.signature||"")}</textarea></div>
      <div class="form-grid form-grid-2">
        <div class="field"><label class="field-label">Accent color</label>
          <input class="input" type="color" id="modal-agent-color" value="${esc(agent?.accent_color||"#f97316")}" style="height:36px;padding:2px 4px;cursor:pointer"></div>
        <div class="field"><label class="field-label">Profile photo</label>
          <div class="flex items-center gap-8" style="padding-top:2px">
            <div id="avatar-preview-container">${agentAvatarHtml(agent, 40)}</div>
            <input type="file" id="modal-agent-avatar-file" accept="image/*" style="display:none">
            <input type="hidden" id="modal-agent-avatar" value="${esc(agent?.avatar_url||"")}">
            <div class="flex" style="gap:6px;flex-wrap:wrap">
              <button type="button" class="btn btn-ghost btn-sm" id="avatar-upload-btn">${agent?.avatar_url ? "Change photo" : "Upload photo"}</button>
              ${agent?.avatar_url ? `<button type="button" class="btn btn-ghost btn-sm" id="avatar-clear-btn" style="color:var(--red)">Remove</button>` : ""}
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
}

// ── Manage Inboxes Modal ──────────────────────────────────────────────────────

export function renderManageInboxesModal(agent, availableMailboxes) {
  const linked = (agent.mailboxes || []);
  const linksHtml = linked.length
    ? `<div class="table-wrap mb-16"><table class="table"><thead><tr><th>Address</th><th>Label</th><th>Primary</th><th></th></tr></thead><tbody>
      ${linked.map(m => `<tr>
        <td class="td-mono">${esc(m.address)}</td>
        <td class="text-muted">${esc(m.label||"—")}</td>
        <td>${m.is_primary ? badge("primary","orange") : ""}</td>
        <td class="td-actions"><div class="td-actions-inner">
          <button class="btn btn-danger btn-xs" data-action="modal-unlink-inbox" data-agent-id="${agent.id}" data-mailbox-id="${m.mailbox_id}">Remove</button>
        </div></td>
      </tr>`).join("")}
      </tbody></table></div>`
    : `<p class="text-muted mb-16" style="font-size:12px">No inboxes linked yet.</p>`;

  const availOpts = availableMailboxes.length
    ? availableMailboxes.map(m => `<option value="${m.id}">${esc(m.address)}</option>`).join("")
    : `<option value="">No unlinked inboxes available</option>`;

  return `
    ${linksHtml}
    <div class="card">
      <div class="card-header"><div class="card-title" style="font-size:12.5px">Link an inbox</div></div>
      <div class="form-grid">
        <div class="form-grid form-grid-2">
          <div class="field"><label class="field-label">Inbox</label>
            <select class="select" id="modal-link-inbox-select">${availOpts}</select></div>
          <div class="field"><label class="field-label">Label</label>
            <input class="input" id="modal-link-inbox-label" placeholder="support, escalations…"></div>
        </div>
        <label class="flex items-center gap-8" style="font-size:12.5px;cursor:pointer">
          <input type="checkbox" id="modal-link-inbox-primary"> Set as primary inbox
        </label>
      </div>
    </div>
  `;
}

// ── Inboxes Table ─────────────────────────────────────────────────────────────

export function renderInboxesTable(mailboxes, linkedAgentsForMailbox) {
  if (!mailboxes.length) return emptyState(ICONS.inbox, "No inboxes yet", "Create an inbox under an active domain.");
  return `<div class="table-wrap"><table class="table">
    <thead><tr>
      <th>Address</th><th>Agent</th><th>Sync</th><th>Last synced</th><th style="text-align:right">Actions</th>
    </tr></thead>
    <tbody>
    ${mailboxes.map(m => {
      const agents = linkedAgentsForMailbox(m.id);
      const agentLabel = agents.length ? agents.map(a => a.name).join(", ") : "—";
      return `<tr>
        <td><div>
          <strong class="text-mono">${esc(m.address)}</strong>
          ${m.display_name ? `<div class="text-muted mt-4" style="font-size:11.5px">${esc(m.display_name)}</div>` : ""}
        </div></td>
        <td class="text-muted">${esc(agentLabel)}</td>
        <td>
          ${m.last_sync_error ? badge("error","red") : badge(m.inbound_sync_enabled ? "enabled" : "disabled", m.inbound_sync_enabled ? "green" : "muted")}
        </td>
        <td class="text-muted" style="font-size:12px">${fmtDate(m.last_synced_at)}</td>
        <td class="td-actions"><div class="td-actions-inner">
          <button class="btn btn-ghost btn-xs" data-action="view-threads" data-mailbox-id="${m.id}">Threads</button>
          <button class="btn btn-ghost btn-xs" data-action="sync-mailbox" data-mailbox-id="${m.id}">Sync</button>
          <button class="btn btn-ghost btn-xs" data-action="toggle-sync" data-mailbox-id="${m.id}" data-enabled="${m.inbound_sync_enabled}">${m.inbound_sync_enabled ? "Disable sync" : "Enable sync"}</button>
        </div></td>
      </tr>`;
    }).join("")}
    </tbody></table></div>`;
}

// ── Create Inbox Modal ────────────────────────────────────────────────────────

export function renderCreateInboxModal(domains) {
  const domainOpts = domains.length
    ? domains.map(d => `<option value="${d.id}" ${d.status !== "active" ? "disabled" : ""}>${esc(d.name)}${d.status !== "active" ? " (not verified)" : ""}</option>`).join("")
    : `<option value="">No active domains — verify a domain first</option>`;
  return `
    <div class="form-grid">
      <div class="field"><label class="field-label">Domain *</label>
        <select class="select" id="modal-inbox-domain">${domainOpts}</select></div>
      <div class="form-grid form-grid-2">
        <div class="field"><label class="field-label">Local part *</label>
          <input class="input input-mono" id="modal-inbox-local" placeholder="alice"></div>
        <div class="field"><label class="field-label">Display name</label>
          <input class="input" id="modal-inbox-display" placeholder="Alice"></div>
      </div>
      <div class="field"><label class="field-label">Quota (MB)</label>
        <input class="input" type="number" id="modal-inbox-quota" value="1024" min="1"></div>
    </div>
  `;
}

// ── Credential Banner ─────────────────────────────────────────────────────────

export function renderCredBanner({ address, password }) {
  return `<div class="cred-banner">
    <div class="cred-banner-title">Save these credentials — shown once</div>
    <div class="cred-row"><span class="cred-label">Address</span><span class="cred-value">${esc(address)}</span>${copyBtn(address,"Copy address")}</div>
    <div class="cred-row"><span class="cred-label">Password</span><span class="cred-value">${esc(password)}</span>${copyBtn(password,"Copy password")}</div>
  </div>`;
}

// ── Domains Table ─────────────────────────────────────────────────────────────

export function renderDomainsTable(domains, selectedId) {
  if (!domains.length) return emptyState(ICONS.globe, "No domains linked", "Link your sending domain to get started.");
  return `<div class="table-wrap"><table class="table">
    <thead><tr>
      <th>Domain</th><th>Status</th><th>Mail engine</th><th style="text-align:right">Actions</th>
    </tr></thead>
    <tbody>
    ${domains.map(d => `<tr class="${d.id === selectedId ? "active" : ""}">
      <td><strong>${esc(d.name)}</strong></td>
      <td>${badge(d.status, d.status === "active" ? "green" : "yellow")}</td>
      <td>${badge(d.james_domain_created ? "provisioned" : "pending", d.james_domain_created ? "green" : "muted")}</td>
      <td class="td-actions"><div class="td-actions-inner">
        <button class="btn btn-ghost btn-xs" data-action="inspect-domain" data-domain-id="${d.id}">Inspect</button>
        <button class="btn btn-ghost btn-xs" data-action="verify-domain" data-domain-id="${d.id}">Verify DNS</button>
      </div></td>
    </tr>`).join("")}
    </tbody></table></div>`;
}

// ── Domain Detail ─────────────────────────────────────────────────────────────

export function renderDomainDetail(detail) {
  if (!detail) return "";
  const dnsRows = (detail.dns_records || []).map(r => `
    <div class="dns-record">
      <div class="dns-record-header">
        <span class="dns-badge">${esc(r.type)}</span>
        <span class="dns-host">${esc(r.host)}</span>
      </div>
      <div class="copy-block"><code>${esc(r.value)}</code>${copyBtn(r.value,"Copy record")}</div>
    </div>
  `).join("");

  return `<div class="card">
    <div class="card-header">
      <div><div class="card-title">${esc(detail.mx_target||"Domain detail")}</div></div>
      ${badge(detail.status, detail.status === "active" ? "green" : "yellow")}
    </div>
    <div class="detail-section">
      <div class="detail-label">Connection</div>
      <div class="detail-row"><span class="detail-key">SMTP host</span><span class="detail-val mono">${esc(detail.connection_profile?.submission?.host||"—")}:${detail.connection_profile?.submission?.port||""}</span></div>
      <div class="detail-row"><span class="detail-key">IMAP host</span><span class="detail-val mono">${esc(detail.connection_profile?.imap?.host||"—")}:${detail.connection_profile?.imap?.port||""}</span></div>
      <div class="detail-row"><span class="detail-key">DKIM selector</span><span class="detail-val mono">${esc(detail.dkim_selector||"—")}</span></div>
    </div>
    <div class="detail-section">
      <div class="detail-label">DNS Records</div>
      ${dnsRows}
    </div>
    ${detail.dkim_public_key ? `<div class="detail-section">
      <div class="detail-label">DKIM Public Key</div>
      <div class="copy-block" style="align-items:flex-start"><code style="word-break:break-all;font-size:10.5px">${esc(detail.dkim_public_key)}</code>${copyBtn(detail.dkim_public_key,"Copy key")}</div>
    </div>` : ""}
  </div>`;
}

// ── Thread List ───────────────────────────────────────────────────────────────

export function renderThreadList(threads, selectedId) {
  if (!threads.length) return emptyState(ICONS.mail, "No threads yet", "Sync an inbox or send an email to see threads here.");
  return threads.map(t => `
    <button class="thread-item ${t.id === selectedId ? "active" : ""}" data-thread-id="${t.id}">
      <div class="thread-item-top">
        <span class="thread-item-from">${esc(t.subject || "(no subject)")}</span>
        <span class="thread-item-time">${fmtDate(t.last_message_at)}</span>
      </div>
      <div class="thread-item-subject">${esc(t.snippet || "No preview")}</div>
      <div class="thread-item-snippet">${t.message_count} message${t.message_count !== 1 ? "s" : ""}</div>
    </button>
  `).join("");
}

// ── Message Pane ──────────────────────────────────────────────────────────────

export function renderMessagePane(thread, messages) {
  const msgsHtml = messages.length
    ? messages.map(m => {
        const body = m.text_body || m.html_body || "(empty)";
        const isHtml = !m.text_body && m.html_body;
        const attachmentsHtml = (m.attachments || []).length
          ? `<div class="message-attachments">
              ${(m.attachments).map(a => `
                <a href="/v1/attachments/${esc(a.id)}/download" class="attachment-chip" target="_blank" download="${esc(a.filename)}">
                  ${attachmentIcon(a.content_type)}
                  <span class="attachment-name">${esc(a.filename)}</span>
                  <span class="attachment-size">${fmtBytes(a.size_bytes)}</span>
                </a>`).join("")}
            </div>`
          : "";
        return `<div class="message-bubble ${esc(m.direction)}">
          <div class="message-header">
            <div class="message-from-block">
              <span class="message-from">${esc(m.from_name || m.from_address)}</span>
              <span class="message-addr">${esc(m.from_address)}</span>
            </div>
            <div class="flex items-center gap-8">
              ${badge(m.direction, m.direction === "outbound" ? "orange" : "muted")}
              <span class="message-time">${fmtDateFull(m.received_at || m.sent_at || m.created_at)}</span>
            </div>
          </div>
          ${m.to_recipients?.length ? `<div style="font-size:11.5px;color:var(--text-3);margin-bottom:8px">To: ${esc(m.to_recipients.map(r=>r.email).join(", "))}</div>` : ""}
          ${isHtml
            ? `<div class="message-body" style="background:var(--surface-2);padding:10px;border-radius:6px;max-height:400px;overflow:auto">${body}</div>`
            : `<div class="message-body">${esc(body)}</div>`
          }
          ${attachmentsHtml}
        </div>`;
      }).join("")
    : `<div class="empty-state"><div class="empty-title">No messages</div></div>`;

  return `
    <div class="message-pane-header">
      <div>
        <div class="message-pane-subject">${esc(thread.subject || "(no subject)")}</div>
        <div class="message-pane-meta">${thread.message_count} message${thread.message_count !== 1 ? "s" : ""}</div>
      </div>
      <button class="btn btn-secondary btn-sm" data-action="open-reply" data-thread-id="${thread.id}">Reply</button>
    </div>
    <div class="messages-list">${msgsHtml}</div>
    <div class="compose-panel" id="reply-panel" style="display:none">
      <div class="compose-panel-header">
        <span>Reply</span>
        <button class="btn btn-ghost btn-xs" id="close-reply-btn">Close</button>
      </div>
      <div class="form-grid" style="gap:10px">
        <textarea class="textarea" id="reply-body" rows="4" placeholder="Write your reply…"></textarea>
        <button class="btn btn-primary btn-sm" id="send-reply-btn" data-thread-id="${thread.id}">Send reply</button>
      </div>
    </div>
  `;
}

// ── Compose Modal ─────────────────────────────────────────────────────────────

export function renderComposeModal(mailboxes) {
  const opts = mailboxes.map(m => `<option value="${m.id}">${esc(m.address)}</option>`).join("");
  return `<div class="form-grid">
    <div class="field"><label class="field-label">From inbox *</label>
      <select class="select" id="modal-compose-mailbox">${opts || "<option value=''>No inboxes</option>"}</select></div>
    <div class="field"><label class="field-label">To *</label>
      <input class="input" type="email" id="modal-compose-to" placeholder="recipient@example.com"></div>
    <div class="field"><label class="field-label">Subject *</label>
      <input class="input" id="modal-compose-subject" placeholder="Your subject"></div>
    <div class="field"><label class="field-label">Body *</label>
      <textarea class="textarea" id="modal-compose-body" rows="5" placeholder="Message body…"></textarea></div>
    <div class="field"><label class="field-label">Attachments <span style="color:var(--text-3);font-weight:400">(max 25 MB each)</span></label>
      <input class="input" type="file" id="modal-compose-files" multiple style="padding:6px"></div>
    <div id="modal-compose-attachments" style="display:flex;flex-wrap:wrap;gap:6px"></div>
  </div>`;
}

// ── Webhooks Table ────────────────────────────────────────────────────────────

export function renderWebhooksTable(webhooks) {
  if (!webhooks.length) return emptyState(ICONS.webhook, "No webhooks registered", "Register an endpoint to receive real-time events.");
  return `<div class="table-wrap"><table class="table">
    <thead><tr>
      <th>URL</th><th>Event</th><th>Scope</th><th>Status</th><th style="text-align:right">Actions</th>
    </tr></thead>
    <tbody>
    ${webhooks.map(w => `<tr>
      <td class="td-mono truncate" style="max-width:240px" title="${esc(w.url)}">${esc(w.url)}</td>
      <td>${badge(w.event_type, "orange")}</td>
      <td class="text-muted">${w.mailbox_id ? "mailbox" : "all inboxes"}</td>
      <td>${badge(w.is_active ? "active" : "inactive", w.is_active ? "green" : "muted")}</td>
      <td class="td-actions"><div class="td-actions-inner">
        <button class="btn btn-danger btn-xs" data-action="delete-webhook" data-webhook-id="${w.id}">Delete</button>
      </div></td>
    </tr>`).join("")}
    </tbody></table></div>`;
}

// ── API Keys ──────────────────────────────────────────────────────────────────

export function renderApiKeys(apiKeys) {
  if (!apiKeys.length) return `<p class="text-muted" style="font-size:12.5px;padding:12px 0">No API keys yet.</p>`;
  return `<div class="table-wrap"><table class="table">
    <thead><tr><th>Name</th><th>Prefix</th><th>Status</th><th>Last used</th><th style="text-align:right">Actions</th></tr></thead>
    <tbody>
    ${apiKeys.map(k => `<tr>
      <td><strong>${esc(k.name)}</strong></td>
      <td class="td-mono">${esc(k.key_prefix)}…</td>
      <td>${badge(k.revoked_at ? "revoked" : "active", k.revoked_at ? "red" : "green")}</td>
      <td class="text-muted" style="font-size:12px">${fmtDate(k.last_used_at)}</td>
      <td class="td-actions"><div class="td-actions-inner">
        ${!k.revoked_at ? `<button class="btn btn-danger btn-xs" data-action="revoke-api-key" data-key-id="${k.id}">Revoke</button>` : ""}
      </div></td>
    </tr>`).join("")}
    </tbody></table></div>`;
}

export function renderApiKeyBanner({ api_key, plaintext_key }) {
  return `<div class="cred-banner mt-12">
    <div class="cred-banner-title">New API key — copy now, not shown again</div>
    <div class="cred-row"><span class="cred-label">Name</span><span class="cred-value">${esc(api_key.name)}</span></div>
    <div class="cred-row"><span class="cred-label">Key</span><span class="cred-value">${esc(plaintext_key)}</span>${copyBtn(plaintext_key,"Copy key")}</div>
  </div>`;
}

// ── Sync Worker ───────────────────────────────────────────────────────────────

export function renderSyncWorker(status, isAdmin) {
  if (!isAdmin) return `<p class="text-muted" style="font-size:12px">Admin key required to view sync worker controls.</p>`;
  if (!status) return `<p class="text-muted" style="font-size:12px">Loading…</p>`;
  return `
    <div class="detail-section">
      <div class="detail-row"><span class="detail-key">Status</span><span class="detail-val">${badge(status.enabled ? (status.running ? "running" : "armed") : "paused", status.enabled ? "green" : "muted")}</span></div>
      <div class="detail-row"><span class="detail-key">Interval</span><span class="detail-val">${status.interval_seconds}s</span></div>
      <div class="detail-row"><span class="detail-key">Last run</span><span class="detail-val">${fmtDate(status.last_completed_at)}</span></div>
      <div class="detail-row"><span class="detail-key">Imported</span><span class="detail-val">${status.last_run_imported_count} messages</span></div>
      ${status.last_run_failed_count ? `<div class="detail-row"><span class="detail-key">Failed</span><span class="detail-val">${badge(status.last_run_failed_count + " mailboxes","red")}</span></div>` : ""}
      ${status.last_error ? `<div class="detail-row"><span class="detail-key">Error</span><span class="detail-val" style="color:var(--red);font-size:11.5px">${esc(status.last_error)}</span></div>` : ""}
    </div>
  `;
}

// ── New API Key Modal ─────────────────────────────────────────────────────────

export function renderNewApiKeyModal() {
  return `<div class="field">
    <label class="field-label">Key name *</label>
    <input class="input" id="modal-api-key-name" placeholder="e.g. production-worker">
    <span class="field-hint">This name is for your reference only.</span>
  </div>`;
}
