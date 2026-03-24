use serde::{Deserialize, Serialize};
use std::process::{Child, Command};
use std::sync::Mutex;

pub const BACKEND_URL: &str = "http://127.0.0.1:8765";

/// Shared state for the Python backend process and recording status.
pub struct AppState {
    pub python_process: Mutex<Option<Child>>,
    pub http_client: reqwest::blocking::Client,
}

impl AppState {
    pub fn new() -> Self {
        Self {
            python_process: Mutex::new(None),
            http_client: reqwest::blocking::Client::builder()
                .timeout(std::time::Duration::from_secs(5))
                .build()
                .expect("failed to create HTTP client"),
        }
    }
}

impl Default for AppState {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Debug, Serialize, Deserialize)]
pub struct StatusResponse {
    pub recording: bool,
    pub backend_running: bool,
}

/// Response from the Python backend's /api/status endpoint.
#[derive(Debug, Deserialize)]
pub struct BackendStatusResponse {
    pub recording: bool,
}

// ── HTTP helpers to communicate with the Python backend ──────────────

/// Query the Python backend for current recording status.
pub fn backend_status(state: &AppState) -> Result<BackendStatusResponse, String> {
    let resp = state
        .http_client
        .get(format!("{}/api/status", BACKEND_URL))
        .send()
        .map_err(|e| format!("Backend status request failed: {}", e))?;

    resp.json::<BackendStatusResponse>()
        .map_err(|e| format!("Failed to parse status response: {}", e))
}

/// Tell the Python backend to start recording.
pub fn backend_start_recording(state: &AppState) -> Result<(), String> {
    state
        .http_client
        .post(format!("{}/api/start", BACKEND_URL))
        .json(&serde_json::json!({}))
        .send()
        .map_err(|e| format!("Backend start request failed: {}", e))?;
    Ok(())
}

/// Tell the Python backend to stop recording.
pub fn backend_stop_recording(state: &AppState) -> Result<(), String> {
    state
        .http_client
        .post(format!("{}/api/stop", BACKEND_URL))
        .json(&serde_json::json!({}))
        .send()
        .map_err(|e| format!("Backend stop request failed: {}", e))?;
    Ok(())
}

/// Tell the Python backend to dispatch the transcript to Claude.
pub fn backend_dispatch(state: &AppState) -> Result<(), String> {
    state
        .http_client
        .post(format!("{}/api/dispatch", BACKEND_URL))
        .json(&serde_json::json!({}))
        .send()
        .map_err(|e| format!("Backend dispatch request failed: {}", e))?;
    Ok(())
}

/// Toggle recording: queries current state, then starts or stops accordingly.
/// Returns the new recording state (true = now recording).
pub fn backend_toggle_recording(state: &AppState) -> Result<bool, String> {
    match backend_status(state) {
        Ok(status) => {
            if status.recording {
                backend_stop_recording(state)?;
                Ok(false)
            } else {
                backend_start_recording(state)?;
                Ok(true)
            }
        }
        Err(_) => {
            // Backend might not be ready; try to start recording optimistically
            backend_start_recording(state)?;
            Ok(true)
        }
    }
}

// ── Python backend process management ────────────────────────────────

/// Start the Python web server (web_server.py) as a sidecar process.
///
/// The web server provides the HTTP/WebSocket backend that the Tauri
/// webview connects to. It is expected to listen on localhost:8765.
pub fn start_python_backend(state: &AppState) -> Result<(), String> {
    let mut proc = state.python_process.lock().map_err(|e| e.to_string())?;

    if proc.is_some() {
        return Ok(()); // Already running
    }

    let server_script = find_backend_script()?;
    let python = find_python(&server_script)?;

    let child = Command::new(&python)
        .arg(&server_script)
        .arg("--port")
        .arg("8765")
        .spawn()
        .map_err(|e| format!("Failed to start Python backend: {}", e))?;

    *proc = Some(child);
    Ok(())
}

/// Stop the Python backend process.
pub fn stop_python_backend(state: &AppState) -> Result<(), String> {
    let mut proc = state.python_process.lock().map_err(|e| e.to_string())?;

    if let Some(ref mut child) = *proc {
        let _ = child.kill();
        let _ = child.wait();
    }

    *proc = None;
    Ok(())
}

/// Locate a Python interpreter, preferring a venv next to the server script.
pub fn find_python(server_script: &str) -> Result<String, String> {
    let script_dir = std::path::Path::new(server_script)
        .parent()
        .unwrap_or(std::path::Path::new("."));

    // Check for .venv/bin/python3 next to the server script
    let venv_python = script_dir.join(".venv/bin/python3");
    if venv_python.exists() {
        return venv_python
            .to_str()
            .map(|s| s.to_string())
            .ok_or_else(|| "Invalid venv path encoding".to_string());
    }

    // Fall back to system python3
    Ok("python3".to_string())
}

/// Locate the web_server.py script.
///
/// Search order:
/// 1. Sibling to live_scribe.py in bundled resources
/// 2. Relative to the project root (development)
pub fn find_backend_script() -> Result<String, String> {
    let candidates = vec![
        // Development: project root
        std::env::current_dir()
            .map(|d| d.join("web_server.py"))
            .unwrap_or_default(),
        // Development: up from desktop/tauri/
        std::env::current_dir()
            .map(|d| d.join("../../web_server.py"))
            .unwrap_or_default(),
        // Bundled: next to the executable
        std::env::current_exe()
            .map(|e| e.parent().unwrap_or(e.as_path()).join("web_server.py"))
            .unwrap_or_default(),
        // Bundled macOS: inside .app bundle Resources (flat)
        std::env::current_exe()
            .map(|e| {
                e.parent()
                    .unwrap_or(e.as_path())
                    .join("../Resources/web_server.py")
            })
            .unwrap_or_default(),
        // Bundled macOS: Tauri resource dir (../../file.py -> _up_/_up_/file.py)
        std::env::current_exe()
            .map(|e| {
                e.parent()
                    .unwrap_or(e.as_path())
                    .join("../Resources/_up_/_up_/web_server.py")
            })
            .unwrap_or_default(),
    ];

    for path in &candidates {
        if path.exists() {
            return path
                .to_str()
                .map(|s| s.to_string())
                .ok_or_else(|| "Invalid path encoding".to_string());
        }
    }

    Err(format!(
        "Could not find web_server.py. Searched: {:?}",
        candidates
    ))
}
