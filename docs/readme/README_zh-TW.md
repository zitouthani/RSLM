# RSLM

RSLM 是一款開源的本機文件問答應用程式，採用檢索增強生成（RAG）。它整合 Streamlit、FastAPI、Qdrant、Sentence Transformers 與 Ollama。

**其他語言：**[語言索引](README.md) · [法文完整文件](../../README.md) · [英文完整文件](../../README.en.md)

## 功能

- 搜尋獲准使用的 PDF，並引用文件與頁碼。
- 管理本機文件庫、對話紀錄與備份。
- 檢視檢索結果、模型上下文及回答來源。
- 使用自訂資料集評估檢索與回答。

## 開始使用

需要 Python 3.11 或更新版本，以及本機執行的 Ollama。亦可選擇 Docker Compose。詳細步驟請參閱[法文安裝指南](../guide-reproduction.md)或[英文安裝指南](../reproduction-guide.en.md)。

RSLM 是本機應用程式，不是託管的公開服務。儲存庫不包含 PDF、模型權重或索引。只處理你有權使用的文件，且不要提交 `.env` 密鑰或私人資料。

原始碼採用 MIT 授權；該授權不涵蓋使用者文件或第三方模型。本文為簡要翻譯，未經母語人士獨立審校。
