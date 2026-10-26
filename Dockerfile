FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt requirements-backend.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-backend.txt
COPY . .
RUN useradd -m -u 10001 app && chown -R app /app
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,os;urllib.request.urlopen('http://localhost:'+os.getenv('PORT','8000')+'/health')"
CMD ["sh", "-c", "alembic upgrade head && uvicorn api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
