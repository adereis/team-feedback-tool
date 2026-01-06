# Gunicorn configuration file
# Used by S2I (OpenShift) via APP_CONFIG environment variable

# Binding - OpenShift expects port 8080
bind = "0.0.0.0:8080"

# Workers - adjust based on expected load
workers = 3

# Timeout
timeout = 30

# Logging - stdout/stderr for container log aggregation
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Security limits
limit_request_line = 4094
limit_request_fields = 100
