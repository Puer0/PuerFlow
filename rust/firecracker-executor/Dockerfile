# Use Amazon Linux 2 for glibc compatibility with EC2 instances
# Force arm64 platform for ARM EC2 instances (Graviton)
FROM --platform=linux/arm64 amazonlinux:2 AS builder
RUN amazon-linux-extras enable rust1 && \
    yum install -y gcc openssl-devel protobuf-compiler && \
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"
WORKDIR /build
COPY rust/firecracker-executor ./rust/firecracker-executor
COPY protos ./protos
WORKDIR /build/rust/firecracker-executor
RUN cargo build --release

FROM scratch AS export
COPY --from=builder /build/rust/firecracker-executor/target/release/firecracker-executor /firecracker-executor
