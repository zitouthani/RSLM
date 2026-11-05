# RSLM

RSLM là trợ lý tài liệu mã nguồn mở, chạy cục bộ và sử dụng RAG (tạo sinh tăng cường truy xuất). Dự án kết hợp Streamlit, FastAPI, Qdrant, Sentence Transformers và Ollama.

**Ngôn ngữ khác:** [Danh mục ngôn ngữ](README.md) · [Tài liệu đầy đủ bằng tiếng Pháp](../../README.md) · [Tài liệu đầy đủ bằng tiếng Anh](../../README.en.md)

## Tính năng

- Tìm kiếm trong PDF được phép sử dụng và trích dẫn tài liệu cùng số trang.
- Quản lý kho tài liệu cục bộ, lịch sử hội thoại và bản sao lưu.
- Kiểm tra các kết quả truy xuất, ngữ cảnh gửi cho mô hình và nguồn của câu trả lời.
- Đánh giá truy xuất và câu trả lời bằng bộ dữ liệu của riêng bạn.

## Bắt đầu

Cần Python 3.11 trở lên và Ollama chạy cục bộ. Có thể chọn Docker Compose. Xem [hướng dẫn cài đặt bằng tiếng Pháp](../guide-reproduction.md) hoặc [tiếng Anh](../reproduction-guide.en.md) để biết các bước chi tiết.

RSLM là ứng dụng cục bộ, không phải dịch vụ công khai được lưu trữ. Kho mã không bao gồm PDF, trọng số mô hình hoặc chỉ mục. Chỉ xử lý tài liệu bạn được phép sử dụng; không commit bí mật trong `.env` hoặc dữ liệu riêng tư.

Mã nguồn theo giấy phép MIT; giấy phép này không áp dụng cho tài liệu người dùng hoặc mô hình bên thứ ba. Bản dịch ngắn này chưa được người bản ngữ đánh giá độc lập.
