const STORAGE_KEY = "rslm.react.conversations.v1";

export function loadConversations(storage = globalThis.localStorage) {
  try {
    const saved = JSON.parse(storage.getItem(STORAGE_KEY) || "[]");
    return Array.isArray(saved) ? saved : [];
  } catch {
    return [];
  }
}

export function saveConversation(conversation, storage = globalThis.localStorage) {
  const conversations = loadConversations(storage).filter(
    (item) => item.id !== conversation.id,
  );
  conversations.push(conversation);
  conversations.sort((first, second) => second.updatedAt.localeCompare(first.updatedAt));
  storage.setItem(STORAGE_KEY, JSON.stringify(conversations));
  return conversations;
}

export function removeConversation(id, storage = globalThis.localStorage) {
  const conversations = loadConversations(storage).filter((item) => item.id !== id);
  storage.setItem(STORAGE_KEY, JSON.stringify(conversations));
  return conversations;
}