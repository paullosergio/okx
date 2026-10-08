FROM python:3.12-slim
WORKDIR /app
COPY okx_client.py monitor.py ./
ENV PYTHONUNBUFFERED=1
CMD ["python", "monitor.py"]