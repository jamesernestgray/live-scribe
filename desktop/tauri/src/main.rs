// Prevents an additional console window on Windows in release.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use live_scribe::{
    dispatch, get_status, start_recording, stop_recording, AppState,
    start_python_backend, stop_python_backend,
};
use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    Manager,
};

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
                        "start" => {
                            let _ = start_recording_internal(&state);
                        }
                        "stop" => {
                            let _ = stop_recording_internal(&state);
                        }
                        "dispatch" => {
                            // Emit an event to the frontend to trigger dispatch
                            let _ = app_handle.emit("dispatch-requested", ());
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
            // Cmd+Shift+D (macOS) / Ctrl+Shift+D (Windows/Linux) for dispatch
            use tauri_plugin_global_shortcut::GlobalShortcutExt;
            let app_handle_shortcut = app_handle.clone();
            app_handle.global_shortcut().on_shortcut(
                {
                    #[cfg(target_os = "macos")]
                    { "CommandOrControl+Shift+D".parse().unwrap() }
                    #[cfg(not(target_os = "macos"))]
                    { "Ctrl+Shift+D".parse().unwrap() }
                },
                move |_app, _shortcut, _event| {
                    let _ = app_handle_shortcut.emit("dispatch-requested", ());
                },
            )?;

            // ── Wait for backend, then navigate to it ───────────────
            // Give the Python server a moment to start up.
            // The window URL is already set to http://localhost:8765 in
            // tauri.conf.json, so the webview will load it automatically.
            // If the backend isn't ready yet, the frontend placeholder
            // will show a loading state and retry.

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                // Clean up the Python backend when the window is closed
                let state = window.state::<AppState>();
                let _ = stop_python_backend(state.inner());
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Live Scribe");
}

/// Build the system tray context menu.
fn build_tray_menu(app: &tauri::App) -> Result<Menu<tauri::Wry>, Box<dyn std::error::Error>> {
    let start = MenuItem::with_id(app, "start", "Start Recording", true, None::<&str>)?;
    let stop = MenuItem::with_id(app, "stop", "Stop Recording", true, None::<&str>)?;
    let dispatch_item =
        MenuItem::with_id(app, "dispatch", "Dispatch to Claude", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;

    let menu = Menu::with_items(app, &[&start, &stop, &dispatch_item, &quit])?;
    Ok(menu)
}

/// Internal helper for tray menu: start recording.
fn start_recording_internal(state: &AppState) -> Result<(), String> {
    let mut recording = state.is_recording.lock().map_err(|e| e.to_string())?;
    *recording = true;
    Ok(())
}

/// Internal helper for tray menu: stop recording.
fn stop_recording_internal(state: &AppState) -> Result<(), String> {
    let mut recording = state.is_recording.lock().map_err(|e| e.to_string())?;
    *recording = false;
    Ok(())
}
