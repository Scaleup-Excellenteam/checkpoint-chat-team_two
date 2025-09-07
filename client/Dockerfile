FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY interactive_client.py .
EXPOSE 8090
CMD ["python", "interactive_client.py"]
