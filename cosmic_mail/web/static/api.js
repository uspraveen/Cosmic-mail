import { state } from "./state.js";

async function request(path, { method = "GET", body, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth && state.apiKey) headers["X-API-Key"] = state.apiKey;
  const res = await fetch(path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { const d = await res.json(); detail = d.detail || JSON.stringify(d); } catch {}
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  // Auth / Health
  getReady:           () => request("/ready", { auth: false }),
  getAuthContext:     () => request("/v1/system/auth-context"),

  // Organizations
  listOrganizations:  () => request("/v1/organizations"),
  createOrganization: (body) => request("/v1/organizations", { method: "POST", body }),
  listOrgApiKeys:     (orgId) => request(`/v1/organizations/${orgId}/api-keys`),
  createOrgApiKey:    (orgId, body) => request(`/v1/organizations/${orgId}/api-keys`, { method: "POST", body }),
  revokeOrgApiKey:    (orgId, keyId) => request(`/v1/organizations/${orgId}/api-keys/${keyId}`, { method: "DELETE" }),
  syncOrgMailboxes:   (orgId) => request(`/v1/organizations/${orgId}/sync-mailboxes`, { method: "POST" }),

  // Agents
  listAgents:         () => request("/v1/agents"),
  createAgent:        (body) => request("/v1/agents", { method: "POST", body }),
  getAgent:           (id) => request(`/v1/agents/${id}`),
  updateAgent:        (id, body) => request(`/v1/agents/${id}`, { method: "PATCH", body }),
  linkAgentMailbox:   (id, body) => request(`/v1/agents/${id}/mailboxes`, { method: "POST", body }),
  unlinkAgentMailbox: (agentId, mailboxId) => request(`/v1/agents/${agentId}/mailboxes/${mailboxId}`, { method: "DELETE" }),
  uploadAgentAvatar:  (agentId, formData) => {
    const headers = {};
    if (state.apiKey) headers["X-API-Key"] = state.apiKey;
    return fetch(`/v1/agents/${agentId}/avatar`, { method: "POST", headers, body: formData })
      .then(async res => {
        if (!res.ok) {
          let detail = `HTTP ${res.status}`;
          try { const d = await res.json(); detail = d.detail || JSON.stringify(d); } catch {}
          throw new Error(detail);
        }
        return res.json();
      });
  },

  // Domains
  listDomains:        () => request("/v1/domains"),
  createDomain:       (body) => request("/v1/domains", { method: "POST", body }),
  verifyDomain:       (id) => request(`/v1/domains/${id}/verify-dns`, { method: "POST" }),
  getDomainDeliverability: (id) => request(`/v1/domains/${id}/deliverability`),
  updateDomainDeliverability: (id, body) => request(`/v1/domains/${id}/deliverability`, { method: "PATCH", body }),
  rotateDkim:         (id, body) => request(`/v1/domains/${id}/rotate-dkim`, { method: "POST", body }),

  // Mailboxes
  listMailboxes:      () => request("/v1/mailboxes"),
  createMailbox:      (body) => request("/v1/mailboxes", { method: "POST", body }),
  getSyncPolicy:      (id) => request(`/v1/mailboxes/${id}/sync-policy`),
  updateSyncPolicy:   (id, body) => request(`/v1/mailboxes/${id}/sync-policy`, { method: "PATCH", body }),
  syncMailbox:        (id) => request(`/v1/mailboxes/${id}/sync-inbox`, { method: "POST" }),

  // Threads & Messages
  listThreads:        (mailboxId) => request(`/v1/threads?mailbox_id=${mailboxId}`),
  listMessages:       (threadId) => request(`/v1/threads/${threadId}/messages`),
  replyToThread:      (threadId, body) => request(`/v1/threads/${threadId}/reply`, { method: "POST", body }),
  markMessageRead:    (threadId, messageId) => request(`/v1/threads/${threadId}/messages/${messageId}/read`, { method: "PATCH" }),

  // Drafts
  createDraft:        (body) => request("/v1/drafts", { method: "POST", body }),
  sendDraft:          (id) => request(`/v1/drafts/${id}/send`, { method: "POST" }),

  // Attachments
  uploadDraftAttachment: (draftId, formData) => {
    const headers = {};
    if (state.apiKey) headers["X-API-Key"] = state.apiKey;
    return fetch(`/v1/attachments/drafts/${draftId}`, {
      method: "POST", headers, body: formData,
    }).then(async res => {
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try { const d = await res.json(); detail = d.detail || JSON.stringify(d); } catch {}
        throw new Error(detail);
      }
      return res.json();
    });
  },
  deleteAttachment: (id) => request(`/v1/attachments/${id}`, { method: "DELETE" }),

  // Webhooks
  listWebhooks:       () => request("/v1/webhooks"),
  createWebhook:      (body) => request("/v1/webhooks", { method: "POST", body }),
  deleteWebhook:      (id) => request(`/v1/webhooks/${id}`, { method: "DELETE" }),

  // System
  getSyncWorkerStatus: () => request("/v1/system/sync-worker"),
  runSyncWorker:       (orgId) => request("/v1/system/sync-worker/run-once", { method: "POST", body: orgId ? { organization_id: orgId } : {} }),
};
