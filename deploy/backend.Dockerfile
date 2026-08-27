FROM python:3.12-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -e . -e ./backend
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "-m", "medical_evals_api.cli", "api"]
