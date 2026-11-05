# RSLM

RSLM, artırılmış üretim (RAG) kullanan açık kaynaklı ve yerel bir belge asistanıdır. Streamlit, FastAPI, Qdrant, Sentence Transformers ve Ollama bileşenlerini bir araya getirir.

**Diğer diller:** [Dil dizini](README.md) · [Fransızca tam dokümantasyon](../../README.md) · [İngilizce tam dokümantasyon](../../README.en.md)

## Özellikler

- Kullanma iznine sahip olduğunuz PDF'lerde arama yapar ve belge/sayfa kaynakları gösterir.
- Yerel belge koleksiyonunu, konuşma geçmişini ve yedekleri yönetir.
- Bulunan adayları, modele gönderilen bağlamı ve yanıt kaynaklarını incelemenizi sağlar.
- Arama ve yanıtları kendi değerlendirme veri kümelerinizle ölçer.

## Başlarken

Python 3.11 veya üzeri ve yerel olarak çalışan Ollama gerekir. İsteğe bağlı olarak Docker Compose kullanılabilir. Ayrıntılı adımlar için [Fransızca kurulum kılavuzuna](../guide-reproduction.md) veya [İngilizce kurulum kılavuzuna](../reproduction-guide.en.md) bakın.

RSLM yerel bir uygulamadır; barındırılan herkese açık bir hizmet değildir. Depoda PDF'ler, model ağırlıkları veya dizinler bulunmaz. Yalnızca kullanma hakkınız olan belgeleri işleyin; `.env` gizli bilgilerini veya özel verileri commit etmeyin.

Kaynak kodu MIT lisanslıdır; kullanıcı belgeleri ve üçüncü taraf modeller bu lisansa dahil değildir. Bu kısa çeviri ana dili konuşan biri tarafından bağımsız olarak incelenmemiştir.
