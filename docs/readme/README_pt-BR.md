# RSLM

RSLM é um assistente documental local e de código aberto que usa geração aumentada por recuperação (RAG). O projeto combina Streamlit, FastAPI, Qdrant, Sentence Transformers e Ollama.

**Outros idiomas:** [Índice de idiomas](README.md) · [Documentação completa em francês](../../README.md) · [Documentação completa em inglês](../../README.en.md)

## Recursos

- Pesquisa em PDFs autorizados, com referências aos documentos e às páginas.
- Gerenciamento do acervo local, do histórico de conversas e de backups.
- Inspeção dos resultados recuperados, do contexto enviado ao modelo e das fontes das respostas.
- Avaliação da recuperação e das respostas com conjuntos de dados próprios.

## Primeiros passos

É necessário ter Python 3.11 ou superior e o Ollama em execução local. Docker Compose também é uma opção. Consulte o [guia de instalação em francês](../guide-reproduction.md) ou o [guia em inglês](../reproduction-guide.en.md) para ver as etapas completas.

RSLM é um aplicativo local, não um serviço público hospedado. O repositório não inclui PDFs, pesos de modelos nem índices. Processe apenas documentos que você tem autorização para usar e não envie segredos de `.env` nem dados privados ao Git.

O código-fonte usa a licença MIT; ela não cobre documentos dos usuários nem modelos de terceiros. Esta tradução resumida não foi revisada de forma independente por uma pessoa nativa.
