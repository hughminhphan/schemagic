// Prevents additional console window on Windows in release.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod sidecar;

use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use std::sync::{atomic::{AtomicU16, Ordering}, Arc, Mutex};
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, RunEvent,
};
use tauri_plugin_autostart::MacosLauncher;
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut};

/// User config stored at ~/.schemagic/config.json
#[derive(Debug, Clone, Serialize, Deserialize)]
struct AppConfig {
    #[serde(default = "default_modifiers")]
    hotkey_modifiers: Vec<String>,
    #[serde(default = "default_key")]
    hotkey_key: String,
    #[serde(default)]
    start_at_login: bool,
    #[serde(default)]
    gemini_api_key: String,
    #[serde(default = "default_gemini_model")]
    gemini_model: String,
    #[serde(default)]
    email: String,
    #[serde(default = "default_license_status")]
    license_status: String,
    #[serde(default)]
    last_check: i64,
    #[serde(default)]
    license_token: String,
    #[serde(default)]
    machine_id: String,
}

fn default_modifiers() -> Vec<String> {
    vec!["ctrl".into(), "shift".into()]
}
fn default_key() -> String {
    "k".into()
}
fn default_gemini_model() -> String {
    "gemini-2.5-flash-lite".into()
}
fn default_license_status() -> String {
    "unknown".into()
}

impl Default for AppConfig {
    fn default() -> Self {
        Self {
            hotkey_modifiers: default_modifiers(),
            hotkey_key: default_key(),
            start_at_login: false,
            gemini_api_key: String::new(),
            gemini_model: default_gemini_model(),
            email: String::new(),
            license_status: default_license_status(),
            last_check: 0,
            license_token: String::new(),
            machine_id: String::new(),
        }
    }
}

fn config_dir() -> PathBuf {
    dirs::home_dir()
        .expect("Cannot determine home directory")
        .join(".schemagic")
}

fn config_path() -> PathBuf {
    config_dir().join("config.json")
}

fn setup_done_path() -> PathBuf {
    config_dir().join(".setup_done")
}

fn load_config() -> AppConfig {
    match fs::read_to_string(config_path()) {
        Ok(contents) => serde_json::from_str(&contents).unwrap_or_default(),
        Err(_) => AppConfig::default(),
    }
}

fn save_config(config: &AppConfig) -> Result<(), String> {
    let dir = config_dir();
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let json = serde_json::to_string_pretty(config).map_err(|e| e.to_string())?;
    fs::write(config_path(), json).map_err(|e| e.to_string())?;
    Ok(())
}

/// Tauri command: read config from disk
#[tauri::command]
fn read_config() -> Result<AppConfig, String> {
    Ok(load_config())
}

/// Tauri command: save config to disk
#[tauri::command]
fn save_config_cmd(config: AppConfig) -> Result<(), String> {
    save_config(&config)
}

/// Tauri command: check if first-run setup is needed
#[tauri::command]
fn is_setup_done() -> bool {
    setup_done_path().exists()
}

/// Tauri command: mark first-run setup as complete
#[tauri::command]
fn mark_setup_done() -> Result<(), String> {
    let dir = config_dir();
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    fs::write(setup_done_path(), "done\n").map_err(|e| e.to_string())?;
    Ok(())
}

/// Tauri command: get the sidecar API port
#[tauri::command]
fn get_api_port(state: tauri::State<'_, Mutex<sidecar::SidecarState>>) -> u16 {
    state.lock().unwrap().port
}

/// Get or generate a stable machine ID. Called from both the Tauri command
/// exposed to the webview and from sidecar spawn so the sidecar can enforce
/// the machine binding claim carried in JWTs.
pub(crate) fn get_or_create_machine_id() -> Result<String, String> {
    let mut config = load_config();
    if config.machine_id.is_empty() {
        config.machine_id = uuid::Uuid::new_v4().to_string();
        save_config(&config)?;
    }
    Ok(config.machine_id)
}

/// Tauri command: get or generate a stable machine ID
#[tauri::command]
fn get_machine_id() -> Result<String, String> {
    get_or_create_machine_id()
}

/// Tauri command: store a license token
#[tauri::command]
fn store_license_token(token: String) -> Result<(), String> {
    let mut config = load_config();
    config.license_token = token;
    config.last_check = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64;
    save_config(&config)
}

/// Tauri command: get the stored license token
#[tauri::command]
fn get_license_token() -> String {
    load_config().license_token
}

fn build_shortcut(config: &AppConfig) -> Option<Shortcut> {
    let mut modifiers = Modifiers::empty();
    for m in &config.hotkey_modifiers {
        match m.as_str() {
            "ctrl" | "control" => modifiers |= Modifiers::CONTROL,
            "shift" => modifiers |= Modifiers::SHIFT,
            "cmd" | "command" | "meta" | "super" => modifiers |= Modifiers::META,
            "alt" | "option" => modifiers |= Modifiers::ALT,
            _ => {}
        }
    }

    let code = match config.hotkey_key.to_lowercase().as_str() {
        "a" => Code::KeyA,
        "b" => Code::KeyB,
        "c" => Code::KeyC,
        "d" => Code::KeyD,
        "e" => Code::KeyE,
        "f" => Code::KeyF,
        "g" => Code::KeyG,
        "h" => Code::KeyH,
        "i" => Code::KeyI,
        "j" => Code::KeyJ,
        "k" => Code::KeyK,
        "l" => Code::KeyL,
        "m" => Code::KeyM,
        "n" => Code::KeyN,
        "o" => Code::KeyO,
        "p" => Code::KeyP,
        "q" => Code::KeyQ,
        "r" => Code::KeyR,
        "s" => Code::KeyS,
        "t" => Code::KeyT,
        "u" => Code::KeyU,
        "v" => Code::KeyV,
        "w" => Code::KeyW,
        "x" => Code::KeyX,
        "y" => Code::KeyY,
        "z" => Code::KeyZ,
        _ => return None,
    };

    Some(Shortcut::new(Some(modifiers), code))
}

fn show_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.set_focus();
    }
}

fn main() {
    let shared_port = Arc::new(AtomicU16::new(0));
    let port_for_pageload = shared_port.clone();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_autostart::init(
            MacosLauncher::LaunchAgent,
            Some(vec!["--autostart"]),
        ))
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_notification::init())
        .invoke_handler(tauri::generate_handler![
            read_config,
            save_config_cmd,
            is_setup_done,
            mark_setup_done,
            get_api_port,
            get_machine_id,
            store_license_token,
            get_license_token,
        ])
        .on_page_load(move |webview, _payload| {
            let p = port_for_pageload.load(Ordering::Relaxed);
            if p > 0 {
                let _ = webview.eval(&format!(
                    "window.__SCHEMAGIC_API_PORT__ = {};",
                    p
                ));
            }
        })
        .setup(move |app| {
            let handle = app.handle().clone();

            // Resolve the machine ID before spawning the sidecar so it can
            // enforce the machine_id claim embedded in license JWTs.
            let machine_id = get_or_create_machine_id().unwrap_or_default();

            // Start the Python sidecar
            let sidecar_state = match sidecar::start_sidecar(&handle, &machine_id) {
                Ok(state) => state,
                Err(e) => {
                    eprintln!("Failed to start sidecar: {}", e);
                    eprintln!("Make sure you've built the sidecar first: ./scripts/build-sidecar-macos.sh");
                    return Err(e);
                }
            };
            let port = sidecar_state.port;
            shared_port.store(port, Ordering::Relaxed);
            app.manage(Mutex::new(sidecar_state));

            // Also inject immediately for the initial page load
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.eval(&format!("window.__SCHEMAGIC_API_PORT__ = {};", port));
            }

            // Load config and register global shortcut
            let config = load_config();
            if let Some(shortcut) = build_shortcut(&config) {
                let handle_for_shortcut = handle.clone();
                let _ = app.global_shortcut().on_shortcut(
                    shortcut,
                    move |_app, _shortcut, _event| {
                        show_main_window(&handle_for_shortcut);
                    },
                );
            }

            // Build tray icon
            let open_item = MenuItem::with_id(app, "open", "Open scheMAGIC", true, None::<&str>)?;
            let prefs_item =
                MenuItem::with_id(app, "prefs", "Preferences...", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open_item, &prefs_item, &quit_item])?;

            let handle_for_tray = handle.clone();
            TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .menu(&menu)
                .show_menu_on_left_click(false)
                .tooltip("scheMAGIC")
                .on_tray_icon_event(move |_tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        show_main_window(&handle_for_tray);
                    }
                })
                .on_menu_event(|app, event| match event.id().as_ref() {
                    "open" => show_main_window(app),
                    "prefs" => {
                        // TODO: open preferences window/route
                        show_main_window(app);
                    }
                    "quit" => {
                        app.exit(0);
                    }
                    _ => {}
                })
                .build(app)?;

            // Show the main window after setup is complete
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                // Kill the sidecar on exit
                if let Some(state) = app.try_state::<Mutex<sidecar::SidecarState>>() {
                    if let Ok(mut s) = state.lock() {
                        s.shutdown();
                    }
                }
            }
        });
}
