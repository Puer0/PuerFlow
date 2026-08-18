#!/usr/bin/env bash
# Generate Python protobuf files for llm-service
# This script should be run from the project root

set -euo pipefail

# Ensure we're in the project root
if [ ! -f "Makefile" ] || [ ! -d "protos" ]; then
    echo "Error: This script must be run from the Shannon project root directory"
    exit 1
fi

echo "Generating Python protobuf files for llm-service..."

# Check if grpcio-tools is installed (version must match requirements.txt)
# Using pinned version to avoid protobuf version mismatches
GRPCIO_VERSION="1.68.1"
if ! python3 -c "import grpc_tools" 2>/dev/null; then
    echo "Installing grpcio-tools==$GRPCIO_VERSION..."
    pip3 install "grpcio-tools==$GRPCIO_VERSION"
fi

# Create output directory
mkdir -p python/llm-service/llm_service/grpc_gen

# Generate protobuf files
cd protos
for dir in common agent orchestrator session llm sandbox; do
    if [ -d "$dir" ]; then
        echo "Processing $dir/*.proto..."
        python3 -m grpc_tools.protoc \
            --python_out=../python/llm-service/llm_service/grpc_gen \
            --grpc_python_out=../python/llm-service/llm_service/grpc_gen \
            --pyi_out=../python/llm-service/llm_service/grpc_gen \
            -I . \
            $dir/*.proto 2>/dev/null || true
    fi
done

# Create __init__.py files for Python packages
cd ../python/llm-service/llm_service/grpc_gen
for dir in common agent orchestrator session llm sandbox; do
    if [ -d "$dir" ]; then
        touch "$dir/__init__.py"
    fi
done

echo "Python protobuf generation complete!"
echo "Files generated in: python/llm-service/llm_service/grpc_gen/"