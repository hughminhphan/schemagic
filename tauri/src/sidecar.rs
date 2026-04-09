use tauri::AppHandle;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

pub struct SidecarState {
    pub port: u16,
    child: Option<CommandChild>,
}

impl SidecarState {
    pub fn shutdown(&mut self) {
        if let Some(child) = self.child.take() {
            let _ = child.kill();
        }
    }
}

/// Start the Python sidecar and wait for it to report its port.
pub fn start_sidecar(app: &AppHandle) -> Result<SidecarState, Box<dyn std::error::Error>> {
    let sidecar_cmd = app
        .shell()
        .sidecar("sidecar/schemagic-server")
        .map_err(|e| format!("Failed to create sidecar command: {}", e))?
        .env("SCHEMAGIC_SIDECAR", "1")
        .env("SCHEMAGIC_PORT", "0")
        .env("SCHEMAGIC_STANDALONE", "1");

    let (mut rx, child) = sidecar_cmd
        .spawn()
        .map_err(|e| format!("Failed to spawn sidecar: {}", e))?;

    // Read stdout lines until we find the port announcement.
    // Use a blocking approach since we're in setup() before the event loop starts.
    let port = tauri::async_runtime::block_on(async {
        let mut port: u16 = 0;
        // Give it up to 30 seconds to start
        let deadline = tokio::time::Instant::now() + tokio::time::Duration::from_secs(30);

        loop {
            let remaining = deadline.saturating_duration_since(tokio::time::Instant::now());
            if remaining.is_zero() {
                break;
            }

            match tokio::time::timeout(remaining, rx.recv()).await {
                Ok(Some(CommandEvent::Stdout(line_bytes))) => {
                    let line = String::from_utf8_lossy(&line_bytes);
                    if let Some(port_str) = line.trim().strip_prefix("SCHEMAGIC_PORT:") {
                        if let Ok(p) = port_str.parse::<u16>() {
                            port = p;
                            break;
                        }
                    }
                }
                Ok(Some(CommandEvent::Stderr(line_bytes))) => {
                    let line = String::from_utf8_lossy(&line_bytes);
                    eprintln!("[sidecar stderr] {}", line.trim());
                }
                Ok(Some(_)) => {}
                Ok(None) => {
                    // Channel closed - sidecar exited
                    break;
                }
                Err(_) => {
                    // Timeout
                    break;
                }
            }
        }
        port
    });

    if port == 0 {
        return Err("Sidecar failed to start or report its port within 30 seconds".into());
    }

    log::info!("Sidecar started on port {}", port);

    Ok(SidecarState {
        port,
        child: Some(child),
    })
}
