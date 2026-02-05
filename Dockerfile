FROM python:3.11-slim-bookworm

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn

# Copy application code
COPY app.py config.py ./
COPY lib/ lib/
COPY templates/ templates/
COPY static/ static/

# Create directories for mounted volumes
RUN mkdir -p saved_maps

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:app"]
