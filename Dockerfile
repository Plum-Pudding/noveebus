FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8089
CMD ["gunicorn", "-b", "0.0.0.0:8089", "-w", "1", "-k", "eventlet", "--timeout", "120", "app:app"]
