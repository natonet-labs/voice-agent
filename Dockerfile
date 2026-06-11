FROM python:3.12-slim

WORKDIR /app

# Install the package (deps resolved from pyproject.toml).
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1
EXPOSE 8080

CMD ["uvicorn", "voice_agent.server:app", "--host", "0.0.0.0", "--port", "8080"]
