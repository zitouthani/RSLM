# RSLM

RSLM 是一款开源的本地文档问答应用，使用检索增强生成（RAG）技术。它结合了 Streamlit、FastAPI、Qdrant、Sentence Transformers 和 Ollama。

**其他语言：**[语言索引](README.md) · [法语完整文档](../../README.md) · [英语完整文档](../../README.en.md)

## 功能

- 搜索获准使用的 PDF，并引用文档及页码。
- 管理本地文档库、对话历史和备份。
- 查看检索结果、模型上下文及回答来源。
- 使用自定义数据集评估检索和回答。

## 开始使用

需要 Python 3.11 或更高版本和本地运行的 Ollama。也可选择使用 Docker Compose。请参阅[法语安装指南](../guide-reproduction.md)或[英语安装指南](../reproduction-guide.en.md)，了解详细步骤。

RSLM 是本地应用，不是托管的公共服务。仓库不包含 PDF、模型权重或索引。只处理你有权使用的文档，并且不要提交 `.env` 密钥或私人数据。

源代码采用 MIT 许可证；该许可证不涵盖用户文档或第三方模型。本文为简要翻译，未经母语人士独立审校。
