# Use an official lightweight Python image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy ALL app code (not just app.py)
COPY . .

# Expose port (Render uses 10000 by default, but we'll use PORT env var)
EXPOSE 10000

# Start the Flask app with gunicorn for production
CMD gunicorn --bind 0.0.0.0:$PORT app:app --workers 2 --timeout 0