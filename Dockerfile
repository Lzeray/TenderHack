FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ktru_assist ./ktru_assist
COPY data/aliases.json ./data/aliases.json
COPY tests ./tests
COPY eval ./eval
COPY tools ./tools
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "ktru_assist.api:app", "--host", "0.0.0.0", "--port", "8000"]
