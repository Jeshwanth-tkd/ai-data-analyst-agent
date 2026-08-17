# Phase 10: deployment. This builds a small, self-contained Linux
# environment to run the FastAPI backend in, so it can be hosted on
# Hugging Face Spaces (or any other Docker-compatible host) rather than
# only ever running on your own laptop.

FROM python:3.11-slim

WORKDIR /app

# Copy just the dependency list first (not the whole project) so Docker
# can cache this "install dependencies" step -- it only re-runs if
# requirements.txt actually changes, making rebuilds after a small code
# edit much faster.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the rest of the project in.
COPY . .

# Hugging Face Spaces expects a Docker Space to listen on port 7860.
EXPOSE 7860

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
