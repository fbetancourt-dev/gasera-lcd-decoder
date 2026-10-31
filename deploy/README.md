# Deployment helpers

- `install_dependencies.sh`: installs the headless runtime; add `--kiosk` to
  install Chromium.
- `check_runtime.sh`: verifies commands, files, native compilation, and USB
  analyzer discovery.
- `run_kiosk.sh`: starts one variant and Chromium in fullscreen kiosk mode.
- `build_runtime_kit.sh`: creates a small archive without `legacy/`.
- `lcd-decoder@.service`: optional systemd user-service template.

Examples:

```bash
./deploy/install_dependencies.sh --kiosk
./deploy/check_runtime.sh
./deploy/run_kiosk.sh 2
```
