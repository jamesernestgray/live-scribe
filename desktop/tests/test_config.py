"""
Tests for validating the desktop app configuration and directory structure.

These tests verify that configuration files are well-formed and contain
the required fields, without needing to actually build the Tauri app.

Run with:
    pytest desktop/tests/ -v
"""

import json
import os
import stat
from pathlib import Path

import pytest

# ── Paths ────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DESKTOP_DIR = PROJECT_ROOT / "desktop"
TAURI_DIR = DESKTOP_DIR / "tauri"


# ── Directory Structure Tests ────────────────────────────────────────


class TestDirectoryStructure:
    """Verify the expected directory structure exists."""

    @pytest.mark.parametrize(
        "path",
        [
            "desktop",
            "desktop/tauri",
            "desktop/tauri/src",
            "desktop/tauri/capabilities",
            "desktop/tauri/icons",
            "desktop/src",
            "desktop/scripts",
            "desktop/tests",
        ],
    )
    def test_directory_exists(self, path: str):
        full_path = PROJECT_ROOT / path
        assert full_path.is_dir(), f"Directory not found: {path}"

    @pytest.mark.parametrize(
        "path",
        [
            "desktop/README.md",
            "desktop/tauri/Cargo.toml",
            "desktop/tauri/Cargo.lock",
            "desktop/tauri/tauri.conf.json",
            "desktop/tauri/build.rs",
            "desktop/tauri/src/main.rs",
            "desktop/tauri/src/lib.rs",
            "desktop/tauri/capabilities/default.json",
            "desktop/tauri/icons/README.md",
            "desktop/src/index.html",
            "desktop/scripts/setup.sh",
            "desktop/scripts/build-macos.sh",
            "desktop/scripts/build-linux.sh",
            "desktop/scripts/build-windows.ps1",
        ],
    )
    def test_file_exists(self, path: str):
        full_path = PROJECT_ROOT / path
        assert full_path.is_file(), f"File not found: {path}"


# ── tauri.conf.json Tests ────────────────────────────────────────────


class TestTauriConfig:
    """Verify tauri.conf.json is valid and has required fields."""

    @pytest.fixture
    def config(self) -> dict:
        config_path = TAURI_DIR / "tauri.conf.json"
        with open(config_path) as f:
            return json.load(f)

    def test_valid_json(self, config: dict):
        """tauri.conf.json should parse as valid JSON."""
        assert isinstance(config, dict)

    def test_product_name(self, config: dict):
        assert config.get("productName") == "Live Scribe"

    def test_identifier(self, config: dict):
        assert config.get("identifier") == "com.livescribe.desktop"

    def test_version(self, config: dict):
        version = config.get("version")
        assert version is not None
        # Should be semver format
        parts = version.split(".")
        assert len(parts) == 3
        assert all(part.isdigit() for part in parts)

    def test_window_config(self, config: dict):
        windows = config.get("app", {}).get("windows", [])
        assert len(windows) >= 1, "At least one window must be configured"

        window = windows[0]
        assert window.get("width") == 1200
        assert window.get("height") == 800
        assert window.get("minWidth") == 800
        assert window.get("minHeight") == 600
        assert window.get("resizable") is True

    def test_bundle_targets(self, config: dict):
        targets = config.get("bundle", {}).get("targets", [])
        expected_targets = {"dmg", "deb", "appimage", "msi", "nsis"}
        actual_targets = set(targets)
        assert expected_targets.issubset(actual_targets), (
            f"Missing bundle targets: {expected_targets - actual_targets}"
        )

    def test_macos_minimum_version(self, config: dict):
        macos_config = config.get("bundle", {}).get("macOS", {})
        min_version = macos_config.get("minimumSystemVersion")
        assert min_version == "10.15"

    def test_linux_deps(self, config: dict):
        deb_config = config.get("bundle", {}).get("linux", {}).get("deb", {})
        depends = deb_config.get("depends", [])
        assert any("libwebkit2gtk-4.1" in dep for dep in depends), (
            "libwebkit2gtk-4.1 should be in Linux deb depends"
        )
        assert any("libappindicator3" in dep for dep in depends), (
            "libappindicator3 should be in Linux deb depends"
        )

    def test_bundle_active(self, config: dict):
        assert config.get("bundle", {}).get("active") is True

    def test_has_tray_icon_config(self, config: dict):
        tray = config.get("app", {}).get("trayIcon")
        assert tray is not None, "Tray icon configuration is required"
        assert "tooltip" in tray

    def test_has_security_csp(self, config: dict):
        security = config.get("app", {}).get("security", {})
        csp = security.get("csp")
        assert csp is not None, "Content Security Policy should be set"
        assert "localhost:8765" in csp, "CSP should allow localhost:8765"


# ── Cargo.toml Tests ─────────────────────────────────────────────────


class TestCargoToml:
    """Verify Cargo.toml has correct structure and dependencies."""

    @pytest.fixture
    def cargo_content(self) -> str:
        cargo_path = TAURI_DIR / "Cargo.toml"
        with open(cargo_path) as f:
            return f.read()

    def test_package_name(self, cargo_content: str):
        assert 'name = "live-scribe"' in cargo_content

    def test_edition(self, cargo_content: str):
        assert 'edition = "2021"' in cargo_content

    def test_tauri_dependency(self, cargo_content: str):
        assert "tauri" in cargo_content
        assert 'version = "2"' in cargo_content or "version = \"2." in cargo_content

    def test_tauri_tray_feature(self, cargo_content: str):
        assert "tray-icon" in cargo_content

    def test_tauri_plugin_shell(self, cargo_content: str):
        assert "tauri-plugin-shell" in cargo_content

    def test_tauri_plugin_global_shortcut(self, cargo_content: str):
        assert "tauri-plugin-global-shortcut" in cargo_content

    def test_serde_dependency(self, cargo_content: str):
        assert "serde" in cargo_content
        assert "serde_json" in cargo_content

    def test_tauri_build_dependency(self, cargo_content: str):
        assert "tauri-build" in cargo_content
        assert "[build-dependencies]" in cargo_content


# ── Rust Source Tests ────────────────────────────────────────────────


class TestRustSource:
    """Verify Rust source files have expected content."""

    @pytest.fixture
    def main_rs(self) -> str:
        with open(TAURI_DIR / "src" / "main.rs") as f:
            return f.read()

    @pytest.fixture
    def lib_rs(self) -> str:
        with open(TAURI_DIR / "src" / "lib.rs") as f:
            return f.read()

    def test_main_has_no_console_on_windows(self, main_rs: str):
        assert "windows_subsystem" in main_rs

    def test_main_has_tray(self, main_rs: str):
        assert "TrayIconBuilder" in main_rs

    def test_main_has_global_shortcut(self, main_rs: str):
        assert "global_shortcut" in main_rs

    def test_main_has_setup(self, main_rs: str):
        assert ".setup(" in main_rs

    def test_main_registers_commands(self, main_rs: str):
        assert "start_recording" in main_rs
        assert "stop_recording" in main_rs
        assert "dispatch" in main_rs
        assert "get_status" in main_rs

    def test_main_handles_window_close(self, main_rs: str):
        assert "on_window_event" in main_rs or "WindowEvent" in main_rs

    def test_lib_has_backend_start_recording(self, lib_rs: str):
        assert "fn backend_start_recording" in lib_rs

    def test_lib_has_backend_stop_recording(self, lib_rs: str):
        assert "fn backend_stop_recording" in lib_rs

    def test_lib_has_backend_dispatch(self, lib_rs: str):
        assert "fn backend_dispatch" in lib_rs

    def test_lib_has_backend_status(self, lib_rs: str):
        assert "fn backend_status" in lib_rs

    def test_main_has_tauri_commands(self, main_rs: str):
        assert "#[tauri::command]" in main_rs

    def test_main_has_start_recording_command(self, main_rs: str):
        assert "fn start_recording" in main_rs

    def test_main_has_stop_recording_command(self, main_rs: str):
        assert "fn stop_recording" in main_rs

    def test_main_has_dispatch_command(self, main_rs: str):
        assert "fn dispatch" in main_rs

    def test_main_has_get_status_command(self, main_rs: str):
        assert "fn get_status" in main_rs

    def test_lib_has_python_backend_management(self, lib_rs: str):
        assert "start_python_backend" in lib_rs
        assert "stop_python_backend" in lib_rs

    def test_build_rs_calls_tauri_build(self):
        with open(TAURI_DIR / "build.rs") as f:
            content = f.read()
        assert "tauri_build::build()" in content


# ── Script Tests ─────────────────────────────────────────────────────


class TestScripts:
    """Verify build scripts exist and are well-formed."""

    def test_setup_is_executable_or_bash(self):
        script = DESKTOP_DIR / "scripts" / "setup.sh"
        with open(script) as f:
            first_line = f.readline()
        assert first_line.startswith("#!"), "setup.sh should have a shebang line"
        assert "bash" in first_line, "setup.sh should use bash"

    def test_build_macos_is_executable_or_bash(self):
        script = DESKTOP_DIR / "scripts" / "build-macos.sh"
        with open(script) as f:
            first_line = f.readline()
        assert first_line.startswith("#!"), "build-macos.sh should have a shebang line"
        assert "bash" in first_line

    def test_build_linux_is_executable_or_bash(self):
        script = DESKTOP_DIR / "scripts" / "build-linux.sh"
        with open(script) as f:
            first_line = f.readline()
        assert first_line.startswith("#!"), "build-linux.sh should have a shebang line"
        assert "bash" in first_line

    def test_build_windows_is_powershell(self):
        script = DESKTOP_DIR / "scripts" / "build-windows.ps1"
        with open(script) as f:
            content = f.read()
        # PowerShell scripts should have param block or comment header
        assert "param(" in content.lower() or "build" in content.lower()

    def test_setup_checks_prerequisites(self):
        with open(DESKTOP_DIR / "scripts" / "setup.sh") as f:
            content = f.read()
        assert "rustc" in content, "setup.sh should check for Rust"
        assert "cargo" in content, "setup.sh should check for Cargo"
        assert "python3" in content, "setup.sh should check for Python"

    def test_build_macos_uses_cargo_tauri(self):
        with open(DESKTOP_DIR / "scripts" / "build-macos.sh") as f:
            content = f.read()
        assert "cargo tauri build" in content

    def test_build_linux_uses_cargo_tauri(self):
        with open(DESKTOP_DIR / "scripts" / "build-linux.sh") as f:
            content = f.read()
        assert "cargo tauri build" in content

    def test_build_windows_uses_cargo_tauri(self):
        with open(DESKTOP_DIR / "scripts" / "build-windows.ps1") as f:
            content = f.read()
        assert "cargo tauri build" in content

    @pytest.mark.parametrize(
        "script",
        [
            "scripts/setup.sh",
            "scripts/build-macos.sh",
            "scripts/build-linux.sh",
        ],
    )
    def test_shell_scripts_use_set_e(self, script: str):
        """Shell scripts should use 'set -e' or equivalent for error handling."""
        with open(DESKTOP_DIR / script) as f:
            content = f.read()
        assert "set -e" in content, f"{script} should use 'set -e' for error handling"


# ── Capabilities Tests ───────────────────────────────────────────────


class TestCapabilities:
    """Verify the Tauri capabilities configuration."""

    @pytest.fixture
    def capabilities(self) -> dict:
        cap_path = TAURI_DIR / "capabilities" / "default.json"
        with open(cap_path) as f:
            return json.load(f)

    def test_valid_json(self, capabilities: dict):
        assert isinstance(capabilities, dict)

    def test_has_identifier(self, capabilities: dict):
        assert "identifier" in capabilities

    def test_has_permissions(self, capabilities: dict):
        permissions = capabilities.get("permissions", [])
        assert len(permissions) > 0, "Capabilities should have permissions"

    def test_has_core_permissions(self, capabilities: dict):
        permissions = capabilities.get("permissions", [])
        assert any("core:" in p for p in permissions), (
            "Should have core permissions"
        )

    def test_has_shell_permissions(self, capabilities: dict):
        permissions = capabilities.get("permissions", [])
        assert any("shell:" in p for p in permissions), (
            "Should have shell permissions for running Python"
        )

    def test_has_shortcut_permissions(self, capabilities: dict):
        permissions = capabilities.get("permissions", [])
        assert any("global-shortcut:" in p for p in permissions), (
            "Should have global-shortcut permissions"
        )


# ── Frontend Placeholder Tests ───────────────────────────────────────


class TestFrontendPlaceholder:
    """Verify the frontend placeholder HTML."""

    @pytest.fixture
    def html_content(self) -> str:
        with open(DESKTOP_DIR / "src" / "index.html") as f:
            return f.read()

    def test_valid_html_structure(self, html_content: str):
        assert "<!DOCTYPE html>" in html_content
        assert "<html" in html_content
        assert "</html>" in html_content

    def test_references_backend_url(self, html_content: str):
        assert "localhost:8765" in html_content

    def test_has_loading_state(self, html_content: str):
        assert "Connecting" in html_content or "Loading" in html_content or "Starting" in html_content


# ── Comprehensive Config Validation Tests ───────────────────────────


class TestTauriConfigRequired:
    """Validate tauri.conf.json has all required fields."""

    @pytest.fixture
    def config(self) -> dict:
        config_path = TAURI_DIR / "tauri.conf.json"
        with open(config_path) as f:
            return json.load(f)

    def test_has_identifier(self, config: dict):
        identifier = config.get("identifier")
        assert identifier is not None, "identifier is required"
        assert "." in identifier, "identifier should be in reverse-domain format"

    def test_has_build_config(self, config: dict):
        build = config.get("build", {})
        assert "frontendDist" in build, "build.frontendDist is required"

    def test_bundle_resources_defined(self, config: dict):
        resources = config.get("bundle", {}).get("resources", [])
        assert len(resources) > 0, "bundle.resources must list files to bundle"

    def test_window_url_set(self, config: dict):
        windows = config.get("app", {}).get("windows", [])
        assert len(windows) >= 1
        window = windows[0]
        assert "url" in window, "Window must have a url"
        assert "localhost:8765" in window["url"], "Window url should point to backend"

    def test_tray_icon_has_icon_path(self, config: dict):
        tray = config.get("app", {}).get("trayIcon", {})
        assert "iconPath" in tray, "trayIcon must have iconPath"

    def test_bundle_icon_list(self, config: dict):
        icons = config.get("bundle", {}).get("icon", [])
        assert len(icons) >= 1, "bundle must define at least one icon"

    def test_macos_entitlements_path(self, config: dict):
        entitlements = config.get("bundle", {}).get("macOS", {}).get("entitlements")
        assert entitlements is not None, "macOS entitlements path is required"

    def test_plugins_section_exists(self, config: dict):
        plugins = config.get("plugins", {})
        assert "shell" in plugins, "shell plugin config is required"


class TestEntitlementsPlist:
    """Validate Entitlements.plist exists and contains audio-input key."""

    def test_entitlements_file_exists(self):
        path = TAURI_DIR / "Entitlements.plist"
        assert path.is_file(), "Entitlements.plist must exist"

    def test_entitlements_has_audio_input(self):
        path = TAURI_DIR / "Entitlements.plist"
        content = path.read_text()
        assert "com.apple.security.device.audio-input" in content, (
            "Entitlements.plist must contain the audio-input entitlement"
        )

    def test_entitlements_audio_input_enabled(self):
        path = TAURI_DIR / "Entitlements.plist"
        content = path.read_text()
        # The <true/> should follow the audio-input key
        audio_idx = content.index("com.apple.security.device.audio-input")
        remainder = content[audio_idx:]
        assert "<true/>" in remainder, (
            "audio-input entitlement must be set to true"
        )


class TestInfoPlist:
    """Validate Info.plist exists and contains NSMicrophoneUsageDescription."""

    def test_info_plist_exists(self):
        path = TAURI_DIR / "Info.plist"
        assert path.is_file(), "Info.plist must exist"

    def test_info_plist_has_microphone_description(self):
        path = TAURI_DIR / "Info.plist"
        content = path.read_text()
        assert "NSMicrophoneUsageDescription" in content, (
            "Info.plist must contain NSMicrophoneUsageDescription"
        )

    def test_info_plist_microphone_description_nonempty(self):
        path = TAURI_DIR / "Info.plist"
        content = path.read_text()
        # After the key there should be a non-empty <string>...</string>
        key_idx = content.index("NSMicrophoneUsageDescription")
        remainder = content[key_idx:]
        assert "<string>" in remainder, "NSMicrophoneUsageDescription must have a string value"
        start = remainder.index("<string>") + len("<string>")
        end = remainder.index("</string>")
        value = remainder[start:end].strip()
        assert len(value) > 0, "NSMicrophoneUsageDescription must not be empty"


class TestCargoTomlRequired:
    """Validate Cargo.toml has all required dependencies."""

    @pytest.fixture
    def cargo_content(self) -> str:
        cargo_path = TAURI_DIR / "Cargo.toml"
        with open(cargo_path) as f:
            return f.read()

    def test_reqwest_dependency(self, cargo_content: str):
        assert "reqwest" in cargo_content, "reqwest dependency is required"

    def test_reqwest_blocking_feature(self, cargo_content: str):
        assert "blocking" in cargo_content, "reqwest must have blocking feature"

    def test_reqwest_json_feature(self, cargo_content: str):
        assert "json" in cargo_content, "reqwest must have json feature"

    def test_open_dependency(self, cargo_content: str):
        assert "open" in cargo_content, "open crate is required for URL opening"

    def test_tauri_dependency(self, cargo_content: str):
        assert "tauri" in cargo_content, "tauri dependency is required"

    def test_serde_dependency(self, cargo_content: str):
        assert "serde" in cargo_content, "serde dependency is required"

    def test_serde_json_dependency(self, cargo_content: str):
        assert "serde_json" in cargo_content, "serde_json dependency is required"


class TestBundledResources:
    """Validate that all bundled resource paths resolve to existing files."""

    @pytest.fixture
    def config(self) -> dict:
        config_path = TAURI_DIR / "tauri.conf.json"
        with open(config_path) as f:
            return json.load(f)

    def test_live_scribe_py_exists(self):
        assert (PROJECT_ROOT / "live_scribe.py").is_file(), (
            "live_scribe.py must exist at project root"
        )

    def test_web_server_py_exists(self):
        assert (PROJECT_ROOT / "web_server.py").is_file(), (
            "web_server.py must exist at project root"
        )

    def test_llm_providers_py_exists(self):
        assert (PROJECT_ROOT / "llm_providers.py").is_file(), (
            "llm_providers.py must exist at project root"
        )

    def test_requirements_txt_exists(self):
        assert (PROJECT_ROOT / "requirements.txt").is_file(), (
            "requirements.txt must exist at project root"
        )

    def test_web_index_html_exists(self):
        assert (PROJECT_ROOT / "web" / "index.html").is_file(), (
            "web/index.html must exist"
        )

    def test_web_directory_has_content(self):
        web_dir = PROJECT_ROOT / "web"
        assert web_dir.is_dir(), "web/ directory must exist"
        files = list(web_dir.rglob("*"))
        assert len(files) > 0, "web/ directory must not be empty"

    def test_resource_paths_resolve(self, config: dict):
        """Each non-glob resource path in tauri.conf.json should resolve to an existing file."""
        resources = config.get("bundle", {}).get("resources", [])
        for resource in resources:
            if "*" in resource:
                # Glob pattern — just check the base directory exists
                import glob as globmod

                base_dir = resource.split("*")[0].rstrip("/")
                resolved = TAURI_DIR / base_dir
                assert resolved.is_dir(), (
                    f"Base directory for glob resource {resource!r} not found at {resolved}"
                )
            else:
                resolved = TAURI_DIR / resource
                assert resolved.is_file(), (
                    f"Bundled resource {resource!r} not found at {resolved}"
                )


class TestCapabilitiesRequired:
    """Validate capabilities/default.json has required permissions."""

    @pytest.fixture
    def capabilities(self) -> dict:
        cap_path = TAURI_DIR / "capabilities" / "default.json"
        with open(cap_path) as f:
            return json.load(f)

    def test_has_description(self, capabilities: dict):
        assert "description" in capabilities, "Capabilities must have a description"

    def test_has_windows_scope(self, capabilities: dict):
        windows = capabilities.get("windows", [])
        assert len(windows) > 0, "Capabilities must specify target windows"

    def test_has_core_default(self, capabilities: dict):
        permissions = capabilities.get("permissions", [])
        assert "core:default" in permissions, (
            "core:default permission is required"
        )

    def test_has_shell_execute(self, capabilities: dict):
        permissions = capabilities.get("permissions", [])
        assert "shell:allow-execute" in permissions, (
            "shell:allow-execute permission is required for running Python"
        )

    def test_has_global_shortcut_register(self, capabilities: dict):
        permissions = capabilities.get("permissions", [])
        assert "global-shortcut:allow-register" in permissions, (
            "global-shortcut:allow-register permission is required"
        )
