import { describe, expect, it } from "vitest";

import { loadConversations, removeConversation, saveConversation } from "./storage.js";

function createStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };
}

describe("browser conversation storage", () => {
  it("returns an empty list for missing or invalid data", () => {
    const storage = createStorage();
    expect(loadConversations(storage)).toEqual([]);
    storage.setItem("rslm.react.conversations.v1", "not-json");
    expect(loadConversations(storage)).toEqual([]);
  });

  it("upserts, orders, and removes conversations", () => {
    const storage = createStorage();
    saveConversation({ id: "old", title: "Ancienne", updatedAt: "2026-01-01", messages: [] }, storage);
    saveConversation({ id: "new", title: "Récente", updatedAt: "2026-02-01", messages: [] }, storage);
    saveConversation({ id: "old", title: "Mise à jour", updatedAt: "2026-03-01", messages: [] }, storage);

    expect(loadConversations(storage).map((item) => item.id)).toEqual(["old", "new"]);
    expect(loadConversations(storage)[0].title).toBe("Mise à jour");
    expect(removeConversation("old", storage).map((item) => item.id)).toEqual(["new"]);
  });

  it("preserves the graph with its answer", () => {
    const storage = createStorage();
    const graph = { question: "Question fictive", candidates: [{ id: "a", reason: "selected" }] };
    saveConversation({ id: "chat", title: "Question", updatedAt: "2026-01-01", messages: [{ role: "assistant", retrieval_graph: graph }] }, storage);
    expect(loadConversations(storage)[0].messages[0].retrieval_graph).toEqual(graph);
  });
});