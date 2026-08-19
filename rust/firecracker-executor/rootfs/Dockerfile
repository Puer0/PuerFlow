# Firecracker microVM rootfs image
# Target: ARM64 (aarch64)
# Size target: ~500MB (with data science packages)

FROM arm64v8/python:3.11-slim-bookworm

# Install system dependencies for data science packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install data science packages
# Note: Using CPU-only torch to save space (~200MB vs 2GB with CUDA)
RUN pip install --no-cache-dir \
    pandas==2.1.4 \
    numpy==1.26.3 \
    matplotlib==3.8.2 \
    scipy==1.11.4 \
    scikit-learn==1.3.2 \
    requests==2.31.0 \
    && pip install --no-cache-dir \
    torch==2.1.2 --index-url https://download.pytorch.org/whl/cpu

# Create workspace mount point
RUN mkdir -p /workspace && chmod 777 /workspace

# Copy guest agent binary (built separately via cross-compilation)
COPY guest-agent /usr/local/bin/guest-agent
RUN chmod +x /usr/local/bin/guest-agent

# Proper init script for Firecracker VM boot
# - /dev/vda is the rootfs (already mounted as root)
# - /dev/vdb is the workspace ext4 (per-session, persistent on EFS)
# - Guest agent is started as the main process
# - PATH must include /usr/local/bin for Python
RUN printf '#!/bin/sh\n\
set -e\n\
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"\n\
mount -t proc proc /proc 2>/dev/null || true\n\
mount -t sysfs sys /sys 2>/dev/null || true\n\
mount -t devtmpfs dev /dev 2>/dev/null || true\n\
mkdir -p /workspace\n\
if [ -b /dev/vdb ]; then\n\
    echo "Mounting workspace from /dev/vdb..."\n\
    mount -t ext4 /dev/vdb /workspace\n\
    chmod 777 /workspace\n\
else\n\
    chmod 777 /workspace\n\
fi\n\
exec /usr/local/bin/guest-agent\n' > /init.sh && chmod +x /init.sh

# Guest agent as init process
CMD ["/init.sh"]
