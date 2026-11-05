FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
RUN mkdir -p ./data ./documents ./logs

EXPOSE 8080

CMD ["uvicorn", "src.api_stream3:app", "--host", "0.0.0.0", "--port", "8080"]