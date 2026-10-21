FROM python:3.12-slim@sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2
WORKDIR /service
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY definitions ./definitions
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

