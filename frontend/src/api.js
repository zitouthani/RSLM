export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8080"
).replace(/\/+$/, "");

export function parseSseFrame(frame) {
  const data = frame
    .split(/\r?\n/)
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).replace(/^ /, ""))
    .join("\n");

  if (!data) return null;

  try {
    return JSON.parse(data);
  } catch {
    return null;
  }
}

export async function readChatStream(response, { onToken = () => {} } = {}) {
  if (!response.ok) {
    throw new Error(`L’API a répondu avec le statut ${response.status}.`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("La réponse de l’API ne contient pas de flux lisible.");
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let finalEvent = null;

  const handleFrame = (frame) => {
    const event = parseSseFrame(frame);
    if (!event) return;

    if (event.type === "token") {
      onToken(event.content || "");
    } else if (event.type === "final") {
      finalEvent = event;
    } else if (event.type === "error") {
      throw new Error(event.content || "Une erreur est survenue pendant la génération.");
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() || "";
    frames.forEach(handleFrame);
    if (done) break;
  }

  if (buffer.trim()) handleFrame(buffer);
  if (!finalEvent) {
    throw new Error("Le flux s’est terminé sans réponse finale.");
  }

  return finalEvent;
}

export async function streamChat(question, history, { signal, onToken } = {}) {
  const response = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, historique: history.slice(-4) }),
    signal,
  });

  return readChatStream(response, { onToken });
}

export async function sendFeedback(requestId, rating) {
  const response = await fetch(`${API_BASE_URL}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request_id: requestId, rating }),
  });

  if (!response.ok) {
    throw new Error(`L’envoi du retour a échoué (HTTP ${response.status}).`);
  }
}

async function adminRequest(path, method, adminKey) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: { "X-Admin-Key": adminKey },
  });
  const result = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(result.detail || `L’opération a échoué (HTTP ${response.status}).`);
  }

  return result;
}

export async function listDocuments(adminKey) {
  const result = await adminRequest("/admin/documents", "GET", adminKey);
  return Array.isArray(result.documents) ? result.documents : [];
}

export async function reindexDocument(documentName, adminKey) {
  const path = `/admin/documents/${encodeURIComponent(documentName)}/reindex`;
  return adminRequest(path, "POST", adminKey);
}