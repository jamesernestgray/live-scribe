# Live Scribe Icons

## Generating Icons

Tauri requires icons in multiple sizes and formats. Use the Tauri CLI to generate
all required icons from a single source image.

### Prerequisites

- A source icon image (PNG, at least 1024x1024 pixels recommended)
- The Tauri CLI: `cargo install tauri-cli`

### Steps

1. Place your source icon as `icon.png` (1024x1024 or larger) in this directory.

2. Run the icon generator from the `desktop/tauri/` directory:

   ```bash
   cd desktop/tauri
   cargo tauri icon icons/icon.png
   ```

   This generates all required formats:
   - `32x32.png`
   - `128x128.png`
   - `128x128@2x.png`
   - `icon.icns` (macOS)
   - `icon.ico` (Windows)

3. The generated files will be placed in this `icons/` directory automatically.

### Required Files

| File | Platform | Purpose |
|------|----------|---------|
| `32x32.png` | All | Small icon (taskbar, etc.) |
| `128x128.png` | All | Medium icon |
| `128x128@2x.png` | macOS | Retina display icon |
| `icon.icns` | macOS | macOS app bundle icon |
| `icon.ico` | Windows | Windows executable icon |
| `icon.png` | Linux/Tray | Linux app icon and system tray |

### Tips

- Use a simple, recognizable design that works at small sizes.
- Ensure the icon has a transparent background for best results.
- For the system tray (macOS), the icon is used as a template image,
  so it should be a monochrome silhouette that works in both light
  and dark menu bars.
