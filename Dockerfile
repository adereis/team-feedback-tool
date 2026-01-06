# OpenShift-compatible Dockerfile for Team Feedback Tool
FROM registry.access.redhat.com/ubi9/python-311:latest

# Switch to root to install system dependencies
USER root

# Install WeasyPrint system dependencies (pango, cairo, etc.)
RUN dnf install -y \
    pango \
    cairo \
    gdk-pixbuf2 \
    && dnf clean all

# Switch back to default user
USER 1001

# Set working directory
WORKDIR /opt/app-root/src

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Generate demo template database
RUN python3 scripts/create_demo_template.py

# Expose port 8080 (OpenShift standard)
EXPOSE 8080

# Set environment variables
ENV HOSTED_MODE=true

# Run with gunicorn
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
