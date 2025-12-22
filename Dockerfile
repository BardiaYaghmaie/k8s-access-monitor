FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ .

# Copy input data
COPY input.json .

# Create directory for logs
RUN mkdir -p /app/logs

# Set environment variables
ENV PYTHONPATH=/app

# Run the application
CMD ["python", "main.py"]
