const STORAGE_KEY = "cosmic_mail_api_key";

export const state = {
  apiKey: null,
  activeView: "overview",
  authContext: null,
  readyState: null,
  syncWorkerStatus: null,

  organizations: [],
  domains: [],
  mailboxes: [],
  agents: [],
  apiKeys: [],
  webhooks: [],

  // Conversations
  selectedMailboxId: null,
  threads: [],
  selectedThreadId: null,
  messages: [],

  // Domain detail
  selectedDomainId: null,
  domainDeliverability: null,

  // Ephemeral display state
  issuedCredential: null,   // { address, password } shown once after inbox creation
  createdApiKey: null,       // { api_key, plaintext_key } shown once
};

export function hydrateApiKey() {
  state.apiKey = localStorage.getItem(STORAGE_KEY) || null;
}

export function persistApiKey(key) {
  state.apiKey = key || null;
  if (key) { localStorage.setItem(STORAGE_KEY, key); }
  else { localStorage.removeItem(STORAGE_KEY); }
}

export function clearWorkspaceState() {
  state.authContext = null;
  state.readyState = null;
  state.syncWorkerStatus = null;
  state.organizations = [];
  state.domains = [];
  state.mailboxes = [];
  state.agents = [];
  state.apiKeys = [];
  state.webhooks = [];
  state.threads = [];
  state.messages = [];
  state.selectedMailboxId = null;
  state.selectedThreadId = null;
  state.selectedDomainId = null;
  state.domainDeliverability = null;
  state.issuedCredential = null;
  state.createdApiKey = null;
}

// Helpers
export function currentOrganization() {
  return state.organizations[0] || null;
}

export function getAgent(id) {
  return state.agents.find(a => a.id === id) || null;
}

export function getMailbox(id) {
  return state.mailboxes.find(m => m.id === id) || null;
}

export function linkedAgentsForMailbox(mailboxId) {
  return state.agents.filter(a =>
    (a.mailboxes || []).some(m => m.mailbox_id === mailboxId)
  );
}

export function availableMailboxesForAgent(agent) {
  const linked = new Set((agent.mailboxes || []).map(m => m.mailbox_id));
  return state.mailboxes.filter(m => !linked.has(m.id));
}

export function getDomainForMailbox(mailboxId) {
  const mb = getMailbox(mailboxId);
  if (!mb) return null;
  return state.domains.find(d => d.id === mb.domain_id) || null;
}
