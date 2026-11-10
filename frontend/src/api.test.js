import { describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { RetrievalGraph } from "./App.jsx";

import {
  listDocuments,
  parseSseFrame,
  readChatStream,
  reindexDocument,
  streamChat,
} from "./api.js";

function createResponse(chunks, options = {}) {
  const encoder = new TextEncoder();
  let index = 0;
  return {
    ok: options.ok ?? true,
    status: options.status ?? 200,
    body: {
      getReader: () => ({
        read: async () => {
          if (index >= chunks.length) return { done: true, value: undefined };
          return { done: false, value: encoder.encode(chunks[index++]) };
        },
      }),
    },
  };
}

describe("retrieval graph", () => {
  it("explains when a technical identifier is missing", () => {
    const graph = { question: "Comment configurer tSortRow ?", search_query: "configurer tSortRow", question_terms: ["configurer", "tsortrow"], shared_terms: ["configurer"], guardrail_allowed: false, best_vector_score: 0.8, minimum_vector_score: 0.5, missing_identifiers: ["tsortrow"], candidates: [] };
    const html = renderToStaticMarkup(createElement(RetrievalGraph, { graph }));
    expect(html).toContain("Identifiants absents du contexte");
    expect(html).toContain("tsortrow");
  });
  it("renders real ranks, selected passages and lexical checks", () => {
    const graph = {
      question: "Comment trier ?", search_query: "trier",
      question_terms: ["trier"], shared_terms: ["trier"], guardrail_allowed: true,
      best_vector_score: 0.8, minimum_vector_score: 0.5, reranker_used: true,
      candidates: [{ id: "a", document: "guide.pdf", page: 2, preview: "Texte fictif", vector_rank: 2, vector_score: 0.8, rerank_rank: 1, reranker_score: 0.9, reason: "selected" }],
    };
    const html = renderToStaticMarkup(createElement(RetrievalGraph, { graph, sources: [] }));
    expect(html).toContain("Comment trier ?");
    expect(html).toContain("Transmis au modèle");
    expect(html).toContain("classement #1");
    expect(html).toContain("Contrôle lexical");
  });

  it("explains social replies without inventing sources", () => {
    const html = renderToStaticMarkup(createElement(RetrievalGraph, { graph: { question: "Bonjour", search_query: null, candidates: [] } }));
    expect(html).toContain("pas utilisé de recherche documentaire");
  });
});

describe("SSE chat client", () => {
  it("parses data lines and ignores non-data fields", () => {
    expect(parseSseFrame('event: message\ndata: {"type":"token","content":"Salut"}'))
      .toEqual({ type: "token", content: "Salut" });
  });

  it("handles events split across network chunks and returns final metadata", async () => {
    const response = createResponse([
      'data: {"type":"token","content":"Bon',
      'jour"}\n\ndata: {"type":"final","reponse":"Bonjour","sources":[{"document":"guide.pdf","page":2}],"retrieval_graph":{"question":"Question","candidates":[]},"score_confiance":0.7,"request_id":"req-1"}\n\n',
    ]);
    const onToken = vi.fn();

    const result = await readChatStream(response, { onToken });

    expect(onToken).toHaveBeenCalledWith("Bonjour");
    expect(result.request_id).toBe("req-1");
    expect(result.sources[0].page).toBe(2);
    expect(result.retrieval_graph.question).toBe("Question");
  });

  it("surfaces API stream errors and incomplete streams", async () => {
    await expect(readChatStream(createResponse([
      'data: {"type":"error","content":"Génération impossible"}\n\n',
    ]))).rejects.toThrow("Génération impossible");

    await expect(readChatStream(createResponse([
      'data: {"type":"token","content":"partiel"}\n\n',
    ]))).rejects.toThrow("sans réponse finale");
  });

  it("sends the API's bounded history field", async () => {
    const fetchMock = vi.fn().mockResolvedValue(createResponse([
      'data: {"type":"final","reponse":"OK","sources":[],"request_id":"req-2"}\n\n',
    ]));
    vi.stubGlobal("fetch", fetchMock);
    const history = Array.from({ length: 5 }, (_, index) => ({
      role: "user",
      content: `Message ${index}`,
    }));

    await streamChat("Question", history);

    const request = fetchMock.mock.calls[0][1];
    expect(JSON.parse(request.body)).toEqual({
      question: "Question",
      historique: history.slice(-4),
    });
    vi.unstubAllGlobals();
  });

  it("loads corpus entries with the admin key", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ documents: [{ document: "guide.pdf", status: "not_indexed" }] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(listDocuments("local-admin-key")).resolves.toEqual([
      { document: "guide.pdf", status: "not_indexed" },
    ]);
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/admin\/documents$/);
    expect(fetchMock.mock.calls[0][1]).toEqual({
      method: "GET",
      headers: { "X-Admin-Key": "local-admin-key" },
    });
    vi.unstubAllGlobals();
  });

  it("encodes document names and surfaces admin API errors", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({ chunks_indexed: 4 }),
    }).mockResolvedValueOnce({
      ok: false,
      status: 403,
      json: async () => ({ detail: "Clé administrateur invalide." }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await reindexDocument("guide d’été.pdf", "local-admin-key");
    expect(fetchMock.mock.calls[0][0]).toContain("guide%20d%E2%80%99%C3%A9t%C3%A9.pdf/reindex");
    await expect(listDocuments("bad-key")).rejects.toThrow("Clé administrateur invalide.");
    vi.unstubAllGlobals();
  });
});