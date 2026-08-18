# Build stage
FROM golang:1.24-alpine AS builder

WORKDIR /app

# Install dependencies (git for go mod, curl for buf)
RUN apk add --no-cache git curl

# Install buf for proto generation
RUN curl -sSL "https://github.com/bufbuild/buf/releases/download/v1.28.1/buf-$(uname -s)-$(uname -m)" \
    -o /usr/local/bin/buf && chmod +x /usr/local/bin/buf

# Copy proto files and generate Go code
COPY protos ./protos
WORKDIR /app/protos
RUN buf generate

# Copy go mod files and download dependencies
WORKDIR /app
COPY go/orchestrator/go.mod go/orchestrator/go.sum ./go/orchestrator/
WORKDIR /app/go/orchestrator
RUN go mod download

# Copy source code (includes generated pb files from proto step)
WORKDIR /app
COPY go/orchestrator ./go/orchestrator

# Build the gateway
WORKDIR /app/go/orchestrator
RUN CGO_ENABLED=0 GOOS=linux go build -o gateway cmd/gateway/main.go

# Final stage
FROM alpine:3.19

RUN apk --no-cache add ca-certificates

WORKDIR /app

# Copy binary from builder
COPY --from=builder /app/go/orchestrator/gateway /app/gateway

# Expose port
EXPOSE 8080

# Run the gateway
CMD ["/app/gateway"]