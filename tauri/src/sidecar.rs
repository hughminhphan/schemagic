use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use tauri::{AppHandle, Manager};

pub struct SidecarState {
    pub port: u16,
    child: Option<Child>,
}

impl SidecarState {
    pub fn shutdown(&mut self) {
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

/// Resolve the sidecar binary path.
/// In dev mode: next to the Rust binary (target/debug/)
/// In production: next to the app binary (inside the .app bundle or install dir)
fn resolve_sidecar_path(app: &AppHandle) -> Result<std::path::PathBuf, Box<dyn std::error::Error>> {
    let exe_dir = app
        .path()
        .resource_dir()
        .unwrap_or_else(|_| {
            std::env::current_exe()
                .unwrap()
                .parent()
                .unwrap()
                .to_path_buf()
        });

    let triple = if cfg!(target_os = "macos") {
        if cfg!(target_arch = "aarch64") {
            "aarch64-apple-darwin"
        } else {
            "x86_64-apple-darwin"
        }
    } else if cfg!(target_os = "windows") {
        "x86_64-pc-windows-msvc"
    } else {
        "x86_64-unknown-linux-gnu"
    };

    let ext = if cfg!(target_os = "windows") { ".exe" } else { "" };
    let binary_name = format!("schemagic-server-{}{}", triple, ext);

    // Try multiple locations
    let exe_parent = std::env::current_exe()?
        .parent()
        .unwrap()
        .to_path_buf();

    // In dev, also check the tauri/sidecar/ directory (2 levels up from target/debug/)
    let dev_sidecar_dir = exe_parent.join("../../sidecar");

    let candidates: Vec<PathBuf> = vec![
        // Production: bundled next to the app binary
        exe_dir.join("binaries").join(&binary_name),
        exe_dir.join(&binary_name),
        exe_parent.join("binaries").join(&binary_name),
        exe_parent.join(&binary_name),
        // Dev mode: in the tauri/sidecar/ directory (original PyInstaller output)
        dev_sidecar_dir.join(&binary_name),
    ];

    for path in &candidates {
        eprintln!("[sidecar] Checking: {:?}", path);
        if path.exists() {
            eprintln!("[sidecar] Found at: {:?}", path);
            return Ok(path.clone());
        }
    }

    Err(format!(
        "Sidecar binary not found. Checked:\n{}",
        candidates
            .iter()
            .map(|p| format!("  - {:?}", p))
            .collect::<Vec<_>>()
            .join("\n")
    )
    .into())
}

/// Start the Python sidecar and wait for it to report its port.
pub fn start_sidecar(app: &AppHandle) -> Result<SidecarState, Box<dyn std::error::Error>> {
    let sidecar_path = resolve_sidecar_path(app)?;

    let mut child = Command::new(&sidecar_path)
        .env("SCHEMAGIC_SIDECAR", "1")
        .env("SCHEMAGIC_PORT", "0")
        .env("SCHEMAGIC_STANDALONE", "1")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to spawn sidecar at {:?}: {}", sidecar_path, e))?;

    // Read stdout for the port announcement
    let stdout = child.stdout.take().ok_or("No stdout from sidecar")?;
    let reader = BufReader::new(stdout);
    let mut port: u16 = 0;

    // Spawn stderr reader in background
    if let Some(stderr) = child.stderr.take() {
        std::thread::spawn(move || {
            let reader = BufReader::new(stderr);
            for line in reader.lines() {
                if let Ok(line) = line {
                    eprintln!("[sidecar stderr] {}", line);
                }
            }
        });
    }

    // Read lines with a timeout
    let start = std::time::Instant::now();
    let timeout = std::time::Duration::from_secs(30);

    for line in reader.lines() {
        if start.elapsed() > timeout {
            break;
        }
        if let Ok(line) = line {
            eprintln!("[sidecar stdout] {}", line);
            if let Some(port_str) = line.trim().strip_prefix("SCHEMAGIC_PORT:") {
                if let Ok(p) = port_str.parse::<u16>() {
                    port = p;
                    break;
                }
            }
        }
    }

    if port == 0 {
        let _ = child.kill();
        return Err("Sidecar failed to report its port within 30 seconds".into());
    }

    eprintln!("[sidecar] Started on port {}", port);

    Ok(SidecarState {
        port,
        child: Some(child),
    })
}
