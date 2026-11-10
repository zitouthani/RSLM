import { useEffect, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  BookOpen,
  Check,
  Clock3,
  Database,
  FileText,
  KeyRound,
  Menu,
  MessageSquareText,
  Network,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  X,
  Copy,
  MessageCircleQuestion,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { listDocuments, reindexDocument, sendFeedback, streamChat } from "./api.js";
import { loadConversations, removeConversation, saveConversation } from "./storage.js";

const SUGGESTIONS = [
  "Comment configurer tSortRow ?",
  "À quoi sert tMap dans un outil ETL ?",
  "Comment utiliser une regex Java ?",
];

function replaceLastAssistant(messages, changes) {
  const lastIndex = messages.length - 1;
  if (lastIndex < 0 || messages[lastIndex].role !== "assistant") return messages;
  return messages.map((message, index) =>
    index === lastIndex ? { ...message, ...changes } : message,
  );
}

function safeSourceUrl(value) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function newConversationId() {
  return globalThis.crypto?.randomUUID?.() || `chat-${Date.now()}-${Math.random()}`;
}

function conversationTitle(messages) {
  const question = messages.find((message) => message.role === "user")?.content;
  return question?.trim().slice(0, 46) || "Nouvelle conversation";
}

const GRAPH_REASONS = {
  selected: "Transmis au modèle",
  excluded: "Document exclu",
  guardrail: "Recherche refusée par le contrôle de pertinence",
  context_limit: "Limite de taille du contexte atteinte",
  rank_limit: "Au-delà des passages retenus",
};

export function RetrievalGraph({ graph, sources = [] }) {
  const candidates = Array.isArray(graph.candidates) ? graph.candidates : [];
  const terms = Array.isArray(graph.question_terms) ? graph.question_terms : [];
  const sharedTerms = Array.isArray(graph.shared_terms) ? graph.shared_terms : [];
  return (
    <details className="graph-panel">
      <summary><Network size={15} /><span>Graphe de recherche</span><span className="source-open-label">Consulter</span></summary>
      <div className="graph-content">
        <div className="graph-node graph-question"><span>Question</span><strong>{graph.question}</strong></div>
        {graph.search_query ? (
          <>
            <div className="graph-edge">Requête de recherche</div>
            <div className="graph-node"><span>Requête recherchée</span><strong>{graph.search_query}</strong></div>
            <div className="graph-edge">Recherche vectorielle · {graph.reranker_used ? "reranker pour les documents non exclus" : "classement vectoriel sans reranker"}</div>
            {candidates.length ? (
              <ol className="graph-candidates">
                {candidates.map((candidate) => {
                  const source = sources.find((item) => item.document === candidate.document && String(item.page) === String(candidate.page));
                  const href = safeSourceUrl(source?.url);
                  return (
                    <li className={`graph-candidate ${candidate.reason === "selected" ? "is-selected" : ""}`} key={candidate.id}>
                      <div className="graph-candidate-heading">
                        <strong>{href ? <a href={href} rel="noreferrer" target="_blank">{candidate.document} · page {candidate.page}</a> : <>{candidate.document} · page {candidate.page}</>}</strong>
                        <span>{GRAPH_REASONS[candidate.reason] || "Non retenu"}</span>
                      </div>
                      <div className="graph-scores">Recherche #{candidate.vector_rank} · score {candidate.vector_score}{candidate.rerank_rank != null ? ` · classement #${candidate.rerank_rank}` : ""}{candidate.reranker_score != null ? ` · score reranker ${candidate.reranker_score}` : ""}</div>
                      {candidate.preview && <><div className="graph-scores">{candidate.reason === "selected" ? "Passage transmis" : "Aperçu du candidat"}</div><p>{candidate.preview}</p></>}
                    </li>
                  );
                })}
              </ol>
            ) : <p className="graph-empty">{graph.withheld_count ? "Détails des passages non affichés après refus." : "Aucun passage disponible."}</p>}
            {graph.excluded_count > 0 && <p className="graph-empty">{graph.excluded_count} passage{graph.excluded_count > 1 ? "s" : ""} provenant de documents exclus.</p>}
            <div className="graph-edge">Contrôle lexical : {terms.length ? terms.join(", ") : "aucun terme significatif"}</div>
            <div className="graph-node graph-check">
              <span>Contrôle de pertinence</span>
              <strong>{graph.guardrail_allowed === true ? "Accepté" : graph.guardrail_allowed === false ? "Refusé" : "Non effectué"}</strong>
              {graph.guardrail_allowed != null && <small>Mots communs aux passages examinés : {sharedTerms.length ? sharedTerms.join(", ") : "aucun"}</small>}
              {graph.best_vector_score != null && graph.minimum_vector_score != null && <small>Meilleur score vectoriel : {graph.best_vector_score} · seuil : {graph.minimum_vector_score}</small>}
              {graph.guardrail_allowed === false && graph.best_vector_score < graph.minimum_vector_score && <small>Score vectoriel inférieur au seuil.</small>}
              {graph.guardrail_allowed === false && graph.best_vector_score >= graph.minimum_vector_score && terms.length > 0 && sharedTerms.length === 0 && <small>Aucun terme significatif commun.</small>}
              {graph.guardrail_allowed === false && graph.missing_identifiers?.length > 0 && <small>Identifiants absents du contexte : {graph.missing_identifiers.join(", ")}</small>}
            </div>
            <div className="graph-edge">{graph.guardrail_allowed === true ? "Passages retenus pour le contexte" : "Aucun passage transmis au modèle"}</div>
            <div className="graph-node"><span>Réponse</span><strong>{graph.guardrail_allowed === true ? "Générée avec le contexte sélectionné" : "Sans contexte documentaire"}</strong></div>
          </>
        ) : <p className="graph-empty">Cette réponse n’a pas utilisé de recherche documentaire.</p>}
        <p className="graph-note">Les mots servent au contrôle lexical, pas à la recherche vectorielle. Les scores et sources ne prouvent pas chaque affirmation.</p>
      </div>
    </details>
  );
}

function App() {
  const [initialConversations] = useState(loadConversations);
  const [conversations, setConversations] = useState(initialConversations);
  const [activeId, setActiveId] = useState(initialConversations[0]?.id || null);
  const [messages, setMessages] = useState(initialConversations[0]?.messages || []);
  const [draft, setDraft] = useState("");
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [feedbackBusy, setFeedbackBusy] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [adminKey, setAdminKey] = useState("");
  const [corpusDocuments, setCorpusDocuments] = useState(null);
  const [corpusBusy, setCorpusBusy] = useState("");
  const [corpusError, setCorpusError] = useState("");
  const abortController = useRef(null);
  const requestSequence = useRef(0);
  const bottomRef = useRef(null);
  const conversationRef = useRef(null);
  const textareaRef = useRef(null);
  const selectionMenuRef = useRef(null);
  const [selectionMenu, setSelectionMenu] = useState({
    visible: false,
    text: "",
    x: 0,
    y: 0,
  });
  const [copySuccess, setCopySuccess] = useState(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "auto", block: "end" });
  }, [messages]);

  useEffect(() => {
    if (!selectionMenu.visible) return undefined;

    function hideMenuOnOutsideClick(event) {
      if (selectionMenuRef.current?.contains(event.target)) return;
      setSelectionMenu((current) => ({ ...current, visible: false }));
    }

    function hideMenuOnEscape(event) {
      if (event.key === "Escape") {
        setSelectionMenu((current) => ({ ...current, visible: false }));
      }
    }

    document.addEventListener("mousedown", hideMenuOnOutsideClick);
    document.addEventListener("keydown", hideMenuOnEscape);
    return () => {
      document.removeEventListener("mousedown", hideMenuOnOutsideClick);
      document.removeEventListener("keydown", hideMenuOnEscape);
    };
  }, [selectionMenu.visible]);

  useEffect(() => {
    if (!copySuccess) return undefined;
    const timer = setTimeout(() => setCopySuccess(false), 1200);
    return () => clearTimeout(timer);
  }, [copySuccess]);

  function persistConversation(id, nextMessages) {
    const conversation = {
      id,
      title: conversationTitle(nextMessages),
      updatedAt: new Date().toISOString(),
      messages: nextMessages,
    };
    setConversations(saveConversation(conversation));
  }

  function startNewConversation() {
    requestSequence.current += 1;
    abortController.current?.abort();
    setActiveId(null);
    setMessages([]);
    setDraft("");
    setError("");
    setIsStreaming(false);
    setSidebarOpen(false);
  }

  function openConversation(conversation) {
    if (isStreaming) {
      requestSequence.current += 1;
      abortController.current?.abort();
    }
    setActiveId(conversation.id);
    setMessages(conversation.messages || []);
    setError("");
    setIsStreaming(false);
    setSidebarOpen(false);
  }

  function deleteChat(id) {
    const next = removeConversation(id);
    setConversations(next);
    if (activeId === id) {
      requestSequence.current += 1;
      abortController.current?.abort();
      setIsStreaming(false);
      setActiveId(next[0]?.id || null);
      setMessages(next[0]?.messages || []);
      setError("");
    }
  }

  async function handleSubmit(event) {
    event?.preventDefault();
    const question = draft.trim();
    if (!question || isStreaming) return;

    const id = activeId || newConversationId();
    const history = messages
      .filter((message) => message.content)
      .slice(-4)
      .map(({ role, content }) => ({ role, content }));
    const nextMessages = [
      ...messages,
      { role: "user", content: question },
      { role: "assistant", content: "", sources: [], request_id: null },
    ];
    const controller = new AbortController();
    const sequence = ++requestSequence.current;
    let partialResponse = "";

    setActiveId(id);
    setMessages(nextMessages);
    setDraft("");
    setError("");
    setIsStreaming(true);
    abortController.current = controller;

    try {
      const final = await streamChat(question, history, {
        signal: controller.signal,
        onToken(token) {
          partialResponse += token;
          setMessages((current) =>
            replaceLastAssistant(current, { content: partialResponse }),
          );
        },
      });
      const completedMessages = replaceLastAssistant(nextMessages, {
        content: final.reponse || partialResponse,
        sources: Array.isArray(final.sources) ? final.sources : [],
        retrieval_graph: final.retrieval_graph || null,
        score_confiance: final.score_confiance,
        request_id: final.request_id,
      });
      setMessages(completedMessages);
      persistConversation(id, completedMessages);
    } catch (requestError) {
      if (sequence !== requestSequence.current) return;
      const interruptedMessages = replaceLastAssistant(nextMessages, {
        content: partialResponse,
      });
      setMessages(interruptedMessages);
      persistConversation(id, interruptedMessages);
      if (requestError.name !== "AbortError") {
        setError(requestError.message || "Impossible de joindre l’API locale.");
      }
    } finally {
      if (sequence === requestSequence.current) {
        abortController.current = null;
        setIsStreaming(false);
      }
    }
  }

  async function rateAnswer(messageIndex, rating) {
    const message = messages[messageIndex];
    if (!message?.request_id || feedbackBusy !== null) return;
    setFeedbackBusy(message.request_id);
    setError("");
    try {
      await sendFeedback(message.request_id, rating);
      const updatedMessages = messages.map((item, index) =>
        index === messageIndex ? { ...item, feedback: rating } : item,
      );
      setMessages(updatedMessages);
      if (activeId) persistConversation(activeId, updatedMessages);
    } catch (requestError) {
      setError(requestError.message || "Impossible d’enregistrer le retour.");
    } finally {
      setFeedbackBusy(null);
    }
  }

  async function refreshCorpus() {
    if (!adminKey.trim() || corpusBusy) return;
    setCorpusBusy("list");
    setCorpusError("");
    try {
      setCorpusDocuments(await listDocuments(adminKey.trim()));
    } catch (requestError) {
      setCorpusError(requestError.message || "Impossible de charger le corpus.");
    } finally {
      setCorpusBusy("");
    }
  }

  async function indexDocument(document) {
    if (!adminKey.trim() || corpusBusy) return;
    setCorpusBusy(document.document);
    setCorpusError("");
    try {
      await reindexDocument(document.document, adminKey.trim());
      setCorpusDocuments(await listDocuments(adminKey.trim()));
    } catch (requestError) {
      setCorpusError(requestError.message || `Impossible d’indexer ${document.document}.`);
    } finally {
      setCorpusBusy("");
    }
  }

  function exportConversation() {
    const file = new Blob([JSON.stringify(messages, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(file);
    const link = document.createElement("a");
    link.href = url;
    link.download = "conversation-rslm.json";
    link.click();
    URL.revokeObjectURL(url);
  }

  function captureSelection() {
    const selection = globalThis.getSelection?.();
    if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
      setSelectionMenu((current) => ({ ...current, visible: false }));
      return;
    }

    const selectedText = selection.toString().trim();
    if (!selectedText) {
      setSelectionMenu((current) => ({ ...current, visible: false }));
      return;
    }

    const anchorNode = selection.anchorNode;
    if (!anchorNode || !conversationRef.current?.contains(anchorNode)) {
      setSelectionMenu((current) => ({ ...current, visible: false }));
      return;
    }

    const activeElement = document.activeElement;
    const isInsideInput = activeElement && (
      activeElement.tagName === "INPUT"
      || activeElement.tagName === "TEXTAREA"
      || activeElement.isContentEditable
    );
    if (isInsideInput) {
      setSelectionMenu((current) => ({ ...current, visible: false }));
      return;
    }

    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    if (!rect.width && !rect.height) {
      setSelectionMenu((current) => ({ ...current, visible: false }));
      return;
    }

    setSelectionMenu({
      visible: true,
      text: selectedText,
      x: rect.left + (rect.width / 2),
      y: rect.top - 10,
    });
    setCopySuccess(false);
  }

  function askRslmFromSelection() {
    if (!selectionMenu.text) return;
    setDraft((current) => {
      if (current.trim()) {
        return `${current.trim()}\n\nPassage sélectionné : "${selectionMenu.text}"`;
      }
      return `Peux-tu expliquer ce passage : "${selectionMenu.text}"`;
    });
    setSelectionMenu((current) => ({ ...current, visible: false }));
    textareaRef.current?.focus();
  }

  async function copySelection() {
    if (!selectionMenu.text) return;
    try {
      if (globalThis.navigator?.clipboard?.writeText) {
        await globalThis.navigator.clipboard.writeText(selectionMenu.text);
      } else {
        const helper = document.createElement("textarea");
        helper.value = selectionMenu.text;
        helper.setAttribute("readonly", "");
        helper.style.position = "fixed";
        helper.style.top = "-1000px";
        document.body.appendChild(helper);
        helper.select();
        document.execCommand("copy");
        document.body.removeChild(helper);
      }
      setCopySuccess(true);
      setSelectionMenu((current) => ({ ...current, visible: false }));
    } catch {
      setError("Impossible de copier la sélection.");
    }
  }

  const visibleConversations = conversations.filter((conversation) =>
    conversation.title.toLocaleLowerCase("fr").includes(search.toLocaleLowerCase("fr")),
  );

  return (
    <div className="app-shell">
      <button
        aria-label="Fermer la navigation"
        className={`sidebar-scrim ${sidebarOpen ? "is-visible" : ""}`}
        onClick={() => setSidebarOpen(false)}
        tabIndex={sidebarOpen ? 0 : -1}
      />
      <aside className={`sidebar ${sidebarOpen ? "sidebar-open" : ""}`}>
        <div className="brand-lockup">
          <div className="brand-mark">R</div>
          <div>
            <strong>RSLM</strong>
            <span>LOCAL KNOWLEDGE</span>
          </div>
          <button
            aria-label="Fermer la navigation"
            className="icon-button sidebar-close"
            onClick={() => setSidebarOpen(false)}
            title="Fermer"
          >
            <X size={18} />
          </button>
        </div>

        <button className="new-chat-button" onClick={startNewConversation}>
          <Plus size={17} strokeWidth={2.2} />
          <span>Nouvelle conversation</span>
          <span className="shortcut">N</span>
        </button>

        <div className="history-heading">
          <span>Récents</span>
          <Clock3 size={15} />
        </div>
        <label className="history-search">
          <Search size={15} aria-hidden="true" />
          <span className="sr-only">Rechercher dans l’historique</span>
          <input
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Rechercher"
            value={search}
          />
        </label>
        <nav aria-label="Historique des conversations" className="history-list">
          {visibleConversations.length ? (
            visibleConversations.map((conversation) => (
              <div
                className={`history-item ${activeId === conversation.id ? "is-active" : ""}`}
                key={conversation.id}
              >
                <button onClick={() => openConversation(conversation)}>
                  <MessageSquareText size={15} aria-hidden="true" />
                  <span>{conversation.title}</span>
                </button>
                <button
                  aria-label={`Supprimer ${conversation.title}`}
                  className="history-delete icon-button"
                  onClick={() => deleteChat(conversation.id)}
                  title="Supprimer"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))
          ) : (
            <p className="empty-history">
              {search ? "Aucun résultat." : "Vos conversations apparaîtront ici."}
            </p>
          )}
        </nav>

        <section className="corpus-panel" aria-labelledby="corpus-heading">
          <div className="corpus-heading">
            <h2 id="corpus-heading">Corpus documentaire</h2>
            <Database size={15} aria-hidden="true" />
          </div>
          <p className="corpus-help">Indexer les PDF déjà placés dans documents/</p>
          <label className="admin-key-field">
            <KeyRound size={14} aria-hidden="true" />
            <span className="sr-only">Clé administrateur de l’API</span>
            <input
              autoComplete="off"
              onChange={(event) => setAdminKey(event.target.value)}
              placeholder="Clé administrateur"
              type="password"
              value={adminKey}
            />
          </label>
          <button
            className="corpus-load-button"
            disabled={!adminKey.trim() || Boolean(corpusBusy)}
            onClick={() => void refreshCorpus()}
            type="button"
          >
            {corpusBusy === "list" ? <RefreshCw className="spin" size={14} /> : null}
            Charger les documents
          </button>
          {corpusError && <p className="corpus-error" role="alert">{corpusError}</p>}
          {corpusDocuments && (
            <div className="corpus-document-list" aria-live="polite">
              {corpusDocuments.length ? corpusDocuments.map((document) => {
                const missing = document.status === "file_missing";
                const indexed = document.status === "indexed";
                const busy = corpusBusy === document.document;
                return (
                  <div className="corpus-document" key={document.document}>
                    <div className="corpus-document-info">
                      <strong title={document.document}>{document.document}</strong>
                      <span>{missing ? "PDF introuvable" : indexed ? `${document.chunks_indexed} passages indexés` : "À indexer"}</span>
                    </div>
                    {!missing && (
                      <button
                        aria-label={`${indexed ? "Réindexer" : "Indexer"} ${document.document}`}
                        className="corpus-index-button"
                        disabled={Boolean(corpusBusy)}
                        onClick={() => void indexDocument(document)}
                        title={indexed ? "Créer une sauvegarde et réindexer" : "Indexer ce PDF"}
                        type="button"
                      >
                        {busy ? <RefreshCw className="spin" size={14} /> : indexed ? "Réindexer" : "Indexer"}
                      </button>
                    )}
                  </div>
                );
              }) : <p className="corpus-empty">Aucun PDF trouvé dans documents/.</p>}
            </div>
          )}
        </section>

        <div className="sidebar-bottom">
          <div className="local-storage-note">
            <ShieldCheck size={16} />
            <span>Historique enregistré dans ce navigateur</span>
          </div>
          <div className="profile-row">
            <div className="profile-avatar">R</div>
            <div className="profile-copy">
              <strong>RSLM local</strong>
              <span>Interface expérimentale</span>
            </div>
            <span className="online-dot" aria-label="Interface active" />
          </div>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <button
            aria-label="Ouvrir la navigation"
            className="icon-button mobile-menu"
            onClick={() => setSidebarOpen(true)}
            title="Ouvrir la navigation"
          >
            <Menu size={19} />
          </button>
          <div className="topbar-title">
            <span className="topbar-eyebrow">ESPACE DOCUMENTAIRE</span>
            <span className="topbar-name">Assistant RSLM</span>
          </div>
          <div className="api-status">
            <span className="status-dot" />
            <span>API locale</span>
          </div>
          {messages.length > 0 && (
            <button
              aria-label="Exporter la conversation"
              className="icon-button export-button"
              onClick={exportConversation}
              title="Exporter la conversation"
            >
              <ArrowDown size={18} />
            </button>
          )}
        </header>

        <section
          aria-live="polite"
          className="conversation-view"
          onMouseUp={captureSelection}
          onTouchEnd={captureSelection}
          ref={conversationRef}
        >
          {messages.length === 0 ? (
            <div className="welcome-view">
              <div className="welcome-symbol"><BookOpen size={23} /></div>
              <div className="welcome-kicker"><Sparkles size={14} /> RECHERCHE DOCUMENTAIRE</div>
              <h1>Vos documents.<br /><span>Des réponses sourcées.</span></h1>
              <p className="welcome-copy">
                Posez une question au corpus local et retrouvez les passages qui étayent la réponse.
              </p>
              <div className="suggestion-list" aria-label="Questions suggérées">
                {SUGGESTIONS.map((suggestion, index) => (
                  <button
                    className="suggestion-button"
                    key={suggestion}
                    onClick={() => setDraft(suggestion)}
                  >
                    <span className="suggestion-number">0{index + 1}</span>
                    <span>{suggestion}</span>
                    <ArrowUp size={15} />
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="message-list">
              {messages.map((message, index) => (
                <article className={`message-row ${message.role}`} key={`${activeId}-${index}`}>
                  {message.role === "assistant" && (
                    <div className="assistant-avatar" aria-hidden="true">R</div>
                  )}
                  <div className="message-column">
                    <div className="message-author">
                      {message.role === "assistant" ? "RSLM" : "Vous"}
                      {message.role === "assistant" && message.request_id && (
                        <span className="answer-tag"><Check size={12} /> SOURCES VÉRIFIABLES</span>
                      )}
                    </div>
                    <div className="message-body">
                      {message.content ? (
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {message.content}
                        </ReactMarkdown>
                      ) : isStreaming && index === messages.length - 1 ? (
                        <span className="typing-indicator" aria-label="Réponse en cours">
                          <i /><i /><i />
                        </span>
                      ) : null}
                    </div>
                    {message.role === "assistant" && message.sources?.length > 0 && (
                      <details className="sources-panel">
                        <summary>
                          <FileText size={15} />
                          <span>{message.sources.length} source{message.sources.length > 1 ? "s" : ""}</span>
                          <span className="source-open-label">Consulter</span>
                        </summary>
                        <div className="source-list">
                          {message.sources.map((source, sourceIndex) => {
                            const href = safeSourceUrl(source.url);
                            const title = `${source.document || "Document"} · page ${source.page ?? "?"}`;
                            return (
                              <div className="source-item" key={`${title}-${sourceIndex}`}>
                                <span className="source-index">{String(sourceIndex + 1).padStart(2, "0")}</span>
                                <div>
                                  {href ? (
                                    <a href={href} rel="noreferrer" target="_blank">{title}</a>
                                  ) : <strong>{title}</strong>}
                                  {source.extrait && <p>{source.extrait}</p>}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </details>
                    )}
                    {message.role === "assistant" && message.retrieval_graph && (
                      <RetrievalGraph graph={message.retrieval_graph} sources={message.sources} />
                    )}
                    {message.role === "assistant" && message.request_id && !message.retrieval_graph && (
                      <p className="graph-unavailable">Graphe indisponible pour cette réponse antérieure.</p>
                    )}
                    {message.role === "assistant" && message.score_confiance != null && (
                      <div className="answer-footer">
                        <span>Score de recherche : {Number(message.score_confiance).toFixed(2)}</span>
                        {message.request_id && (
                          <div className="feedback-controls" aria-label="Évaluer cette réponse">
                            <button
                              aria-label="Réponse utile"
                              aria-pressed={message.feedback === 1}
                              className={message.feedback === 1 ? "is-selected" : ""}
                              disabled={feedbackBusy === message.request_id || message.feedback != null}
                              onClick={() => rateAnswer(index, 1)}
                              title="Réponse utile"
                            ><ThumbsUp size={15} /></button>
                            <button
                              aria-label="Réponse à améliorer"
                              aria-pressed={message.feedback === 0}
                              className={message.feedback === 0 ? "is-selected" : ""}
                              disabled={feedbackBusy === message.request_id || message.feedback != null}
                              onClick={() => rateAnswer(index, 0)}
                              title="Réponse à améliorer"
                            ><ThumbsDown size={15} /></button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </article>
              ))}
              <div ref={bottomRef} />
            </div>
          )}

          {selectionMenu.visible && (
            <div
              className="selection-menu"
              ref={selectionMenuRef}
              role="dialog"
              style={{ left: `${selectionMenu.x}px`, top: `${selectionMenu.y}px` }}
            >
              <button onClick={askRslmFromSelection} type="button">
                <MessageCircleQuestion size={14} />
                Demander à RSLM
              </button>
              <button onClick={() => void copySelection()} type="button">
                <Copy size={14} />
                {copySuccess ? "Copié" : "Copier"}
              </button>
            </div>
          )}
        </section>

        <footer className="composer-area">
          {error && (
            <div className="error-banner" role="alert">
              <span>{error}</span>
              <button aria-label="Fermer le message d’erreur" onClick={() => setError("")}>
                <X size={15} />
              </button>
            </div>
          )}
          <form className="composer" onSubmit={handleSubmit}>
            <label className="sr-only" htmlFor="chat-question">Votre question</label>
            <textarea
              autoComplete="off"
              id="chat-question"
              maxLength={4000}
              ref={textareaRef}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  if (!isStreaming) void handleSubmit();
                }
              }}
              placeholder="Interroger le corpus documentaire…"
              rows={1}
              value={draft}
            />
            <div className="composer-bottom">
              <span className="composer-hint">Entrée pour envoyer · Maj + Entrée pour une nouvelle ligne</span>
              {isStreaming ? (
                <button
                  aria-label="Arrêter la génération"
                  className="send-button stop-button"
                  onClick={() => abortController.current?.abort()}
                  title="Arrêter"
                  type="button"
                ><X size={17} /></button>
              ) : (
                <button
                  aria-label="Envoyer la question"
                  className="send-button"
                  disabled={!draft.trim()}
                  title="Envoyer"
                  type="submit"
                ><ArrowUp size={18} /></button>
              )}
            </div>
          </form>
          <p className="composer-disclaimer">
            RSLM peut se tromper. Vérifiez les informations importantes et les sources.
          </p>
        </footer>
      </main>
    </div>
  );
}

export default App;