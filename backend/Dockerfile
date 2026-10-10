FROM python:3.12-slim
WORKDIR /workspace/backend
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY sample_input /workspace/sample_input
ENV PYTHONPATH=/workspace/backend RULES_DB_PATH=/data/rules.db
RUN mkdir -p /data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
