# Build stage
FROM golang:1.24-alpine AS builder

# Install dependencies (git for go mod, curl for buf)
RUN apk add --no-cache git curl

# Install buf for proto generation
RUN curl -sSL "https://github.com/bufbuild/buf/releases/download/v1.28.1/buf-$(uname -s)-$(uname -m)" \
    -o /usr/local/bin/buf && chmod +x /usr/local/bin/buf

WORKDIR /app

# Copy proto files and generate Go code first
COPY protos ./protos
WORKDIR /app/protos
RUN buf generate

# Copy go mod files from orchestrator directory
WORKDIR /app
COPY go/orchestrator/go.mod go/orchestrator/go.sum ./go/orchestrator/
WORKDIR /app/go/orchestrator
RUN go mod download

# Copy source code (generated pb files already in place from proto step)
WORKDIR /app
COPY go/orchestrator ./go/orchestrator

# Build the application
WORKDIR /app/go/orchestrator
RUN CGO_ENABLED=0 GOOS=linux go build -mod=mod -a -installsuffix cgo -o orchestrator .

# Runtime stage
FROM alpine:3.19

RUN apk --no-cache add ca-certificates

WORKDIR /app

# Copy the binary from builder
COPY --from=builder /app/go/orchestrator/orchestrator .

EXPOSE 50052

CMD ["./orchestrator"]
