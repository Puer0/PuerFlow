FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends findutils \
    && rm -rf /var/lib/apt/lists/*

COPY python/langgraph-worker/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY python/langgraph-worker /app
COPY protos /protos

RUN mkdir -p /app/puerflow_worker/grpc_gen \
    && python -m grpc_tools.protoc \
        --python_out=/app/puerflow_worker/grpc_gen \
        --grpc_python_out=/app/puerflow_worker/grpc_gen \
        --pyi_out=/app/puerflow_worker/grpc_gen \
        -I /protos \
        $(find /protos -name '*.proto' -type f)

ENV PYTHONPATH=/app:/app/puerflow_worker/grpc_gen
ENV GRPC_PORT=50053
EXPOSE 50053

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import socket; s=socket.create_connection(('127.0.0.1', 50053), 2); s.close()"

CMD ["python", "-m", "puerflow_worker"]
