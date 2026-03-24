// Prevents an additional console window on Windows in release.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use live_scribe::{
    AppState, StatusResponse, BACKEND_URL,
    backend_dispatch, backend_start_recording, backend_status, backend_stop_recording,
    backend_toggle_recording, start_python_backend, stop_python_backend,
};
use tauri::{
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::TrayIconBuilder,
    Manager, State,
};

// ── Tauri Commands ──────────────────────────────────────────────────────

#[tauri::command]
fn start_recording(state: State<'_, AppState>) -> Result<String, String> {
    backend_start_recording(state.inner())?;
    Ok("Recording started".to_string())
}

#[tauri::command]
fn stop_recording(state: State<'_, AppState>) -> Result<String, String> {
    backend_stop_recording(state.inner())?;
    Ok("Recording stopped".to_string())
}

#[tauri::command]
fn dispatch(state: State<'_, AppState>) -> Result<String, String> {
    backend_dispatch(state.inner())?;
    Ok("Dispatch requested".to_string())
}

#[tauri::command]
fn get_status(state: State<'_, AppState>) -> Result<StatusResponse, String> {
    let recording = match backend_status(state.inner()) {
        Ok(s) => s.recording,
        Err(_) => false,
    };
    let proc = state.python_process.lock().map_err(|e| e.to_string())?;

    Ok(StatusResponse {
        recording,
        backend_running: proc.is_some(),
    })
}

// ── Main ────────────────────────────────────────────────────────────────

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .manage(AppState::new())
        .invoke_handler(tauri::generate_handler![
            start_recording,
            stop_recording,
            dispatch,
            get_status,
        ])
        .setup(|app| {
            let app_handle = app.handle().clone();

            // ── Start Python backend ────────────────────────────────
            let state = app_handle.state::<AppState>();
            if let Err(e) = start_python_backend(state.inner()) {
                eprintln!("Warning: Could not start Python backend: {}", e);
                eprintln!("The web UI may not be available. Ensure web_server.py is accessible.");
            }

            // ── System tray ─────────────────────────────────────────
            let menu = build_tray_menu(app)?;
            let _tray = TrayIconBuilder::new()
                .menu(&menu)
                .tooltip("Live Scribe")
                .on_menu_event(move |app_handle, event| {
                    let state = app_handle.state::<AppState>();
                    match event.id().as_ref() {
                        "toggle_recording" => {
                            match backend_toggle_recording(state.inner()) {
                                Ok(now_recording) => {
                                    eprintln!(
                                        "Recording toggled: {}",
                                        if now_recording { "started" } else { "stopped" }
                                    );
                                }
                                Err(e) => {
                                    eprintln!("Failed to toggle recording: {}", e);
                                }
                            }
                        }
                        "dispatch" => {
                            if let Err(e) = backend_dispatch(state.inner()) {
                                eprintln!("Failed to dispatch: {}", e);
                            }
                        }
                        "save_transcript" => {
                            // Open the web UI in the default browser for export
                            let _ = open::that("http://127.0.0.1:8765");
                        }
                        "quit" => {
                            let _ = stop_python_backend(state.inner());
                            app_handle.exit(0);
                        }
                        _ => {}
                    }
                })
                .build(app)?;

            // ── Global shortcuts ────────────────────────────────────
            use tauri_plugin_global_shortcut::GlobalShortcutExt;

            let app_handle_dispatch = app_handle.clone();
            let app_handle_toggle = app_handle.clone();

            // Cmd+Shift+D → dispatch to Claude
            app_handle.global_shortcut().on_shortcut(
                "CommandOrControl+Shift+D".parse::<tauri_plugin_global_shortcut::Shortcut>().unwrap(),
                move |_app, _shortcut, _event| {
                    let state = app_handle_dispatch.state::<AppState>();
                    if let Err(e) = backend_dispatch(state.inner()) {
                        eprintln!("Shortcut dispatch failed: {}", e);
                    }
                },
            )?;

            // Cmd+Shift+R → toggle recording
            app_handle.global_shortcut().on_shortcut(
                "CommandOrControl+Shift+R".parse::<tauri_plugin_global_shortcut::Shortcut>().unwrap(),
                move |_app, _shortcut, _event| {
                    let state = app_handle_toggle.state::<AppState>();
                    match backend_toggle_recording(state.inner()) {
                        Ok(now_recording) => {
                            eprintln!(
                                "Shortcut toggle recording: {}",
                                if now_recording { "started" } else { "stopped" }
                            );
                        }
                        Err(e) => {
                            eprintln!("Shortcut toggle recording failed: {}", e);
                        }
                    }
                },
            )?;

            // ── Wait for backend, then show window ────────────────
            // The window starts hidden (visible: false in tauri.conf.json).
            // Poll the backend until it's ready, then show the window so
            // the webview loads the web UI cleanly from localhost:8765
            // without needing the placeholder redirect hack.
            let app_handle_bg = app.handle().clone();
            std::thread::spawn(move || {
                let client = reqwest::blocking::Client::builder()
                    .timeout(std::time::Duration::from_secs(2))
                    .build()
                    .unwrap();

                // Poll up to 30 times (15 seconds total)
                let mut ready = false;
                for _ in 0..30 {
                    if client
                        .get(format!("{}/api/status", BACKEND_URL))
                        .send()
                        .is_ok()
                    {
                        ready = true;
                        break;
                    }
                    std::thread::sleep(std::time::Duration::from_millis(500));
                }

                // Show the window regardless (user should see something even if backend failed)
                if let Some(window) = app_handle_bg.get_webview_window("main") {
                    if ready {
                        // Navigate to the backend URL to ensure fresh load
                        let _ = window.navigate("http://localhost:8765".parse().unwrap());
                    }
                    let _ = window.show();
                    let _ = window.set_focus();
                }

                if !ready {
                    eprintln!("Warning: Backend did not become ready within 15 seconds");
                }
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                let state = window.state::<AppState>();
                let _ = stop_python_backend(state.inner());
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Live Scribe");
}

/// Build the system tray context menu.
fn build_tray_menu(app: &tauri::App) -> Result<Menu<tauri::Wry>, Box<dyn std::error::Error>> {
    let toggle_recording = MenuItem::with_id(
        app,
        "toggle_recording",
        "Toggle Recording",
        true,
        None::<&str>,
    )?;
    let sep1 = PredefinedMenuItem::separator(app)?;
    let dispatch_item = MenuItem::with_id(
        app,
        "dispatch",
        "Dispatch to Claude",
        true,
        None::<&str>,
    )?;
    let sep2 = PredefinedMenuItem::separator(app)?;
    let save_transcript = MenuItem::with_id(
        app,
        "save_transcript",
        "Save Transcript",
        true,
        None::<&str>,
    )?;
    let sep3 = PredefinedMenuItem::separator(app)?;
    let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;

    let menu = Menu::with_items(
        app,
        &[
            &toggle_recording,
            &sep1,
            &dispatch_item,
            &sep2,
            &save_transcript,
            &sep3,
            &quit,
        ],
    )?;
    Ok(menu)
}
