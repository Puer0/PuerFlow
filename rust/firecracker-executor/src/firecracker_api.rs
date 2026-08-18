use anyhow::{anyhow, Result};
use http_body_util::Full;
use hyper::{body::Bytes, Method, Request};
use hyper_util::rt::TokioIo;
use hyper::client::conn::http1;
use serde::Serialize;
use std::time::Duration;
use tokio::net::UnixStream;
use tokio::time::timeout;

#[derive(Clone)]
pub struct FirecrackerApi {
    socket_path: String,
    timeout: Duration,
}

impl FirecrackerApi {
    pub fn new(socket_path: String, timeout_ms: u64) -> Self {
        Self {
            socket_path,
            timeout: Duration::from_millis(timeout_ms),
        }
    }

    pub async fn put_json<T: Serialize>(&self, path: &str, body: &T) -> Result<()> {
        self.request_json(Method::PUT, path, body).await
    }

    pub async fn patch_json<T: Serialize>(&self, path: &str, body: &T) -> Result<()> {
        self.request_json(Method::PATCH, path, body).await
    }

    pub async fn post_json<T: Serialize>(&self, path: &str, body: &T) -> Result<()> {
        self.request_json(Method::POST, path, body).await
    }

    async fn request_json<T: Serialize>(&self, method: Method, path: &str, body: &T) -> Result<()> {
        let payload = serde_json::to_vec(body)?;

        let req = Request::builder()
            .method(method)
            .uri(path)
            .header("Host", "localhost")
            .header("Content-Type", "application/json")
            .body(Full::<Bytes>::from(payload))?;

        let stream = UnixStream::connect(&self.socket_path).await?;
        let io = TokioIo::new(stream);
        let (mut sender, conn) = http1::handshake(io).await?;
        tokio::spawn(async move {
            let _ = conn.await;
        });

        let resp = timeout(self.timeout, sender.send_request(req)).await??;
        let status = resp.status();
        if !status.is_success() {
            return Err(anyhow!("firecracker API error: {} {}", status, path));
        }
        Ok(())
    }
}
