# ropro-bypass

Patches the installed RoPro extension in place and applies the selected subscription, feature, validation, and request-control overrides. This unlocks behavior locked behind their paywalls.

## Features

| Control | Values or effect |
| --- | --- |
| Subscription | Free, Plus, Rex, legacy aliases, empty, or any custom value |
| Restricted settings | Real, allowed, or restricted |
| Roblox Premium | Real, present, or absent |
| Discord 13+ | Real, allowed, or denied |
| Maintenance | Real state, disable none, or disable everything |
| Settings | Real values, all enabled, all disabled, or individual JSON values |
| Verification | Real, verified, or unverified |
| Egg Collection | Real, enabled, or disabled |
| Free trial | Real value or custom remaining hours |
| Route checks | Real, allow, or deny |
| Runtime sender checks | Real, allow, or deny |
| Runtime message checks | Real, allow, or deny |
| URL checks | Real, HTTPS allowed, or denied |
| API payload checks | Real, fallback JSON, or denied |
| Versions | Hash-pinned audited builds and exact-anchor-compatible builds |
| In-place update | Replaces an already-patched install with the newest supported Web Store release and reapplies its overrides |
| Release automation | Detects compatible Web Store releases and auto-merges their audit profiles after all checks pass |

## Requirements

- Python 3.9+
- Windows, macOS, or Linux
- One of these browsers: Chrome, Edge, Brave, Opera/Opera GX, Vivaldi, Arc, Thorium, Chromium or ungoogled-chromium

## Usage

### Windows

Run `quickstart.cmd` or:

```bat
py -3 patch_ropro.py quickstart
```

Specify the source manually (example only):

```bat
py -3 patch_ropro.py quickstart --source "%LOCALAPPDATA%\Google\Chrome\User Data\Default\Extensions\adbacgifemdbhdkfppmeilbgppmhaobf\1.7.1_0"
```

Update an already-patched install:

```bat
py -3 patch_ropro.py update
```

### macOS

Run `quickstart.command` or:

```bash
python3 patch_ropro.py quickstart
```

Specify the source manually (example only):

```bash
python3 patch_ropro.py quickstart --source "$HOME/Library/Application Support/Google/Chrome/Default/Extensions/adbacgifemdbhdkfppmeilbgppmhaobf/1.7.1_0"
```

Update an already-patched install:

```bash
python3 patch_ropro.py update
```

### Linux

Run `quickstart.sh` or:

```bash
python3 patch_ropro.py quickstart
```

Specify the source manually (example only):

```bash
python3 patch_ropro.py quickstart --source "$HOME/.config/google-chrome/Default/Extensions/adbacgifemdbhdkfppmeilbgppmhaobf/1.7.1_0"
```

Update an already-patched install:

```bash
python3 patch_ropro.py update
```

### Arch Linux

Install the package build tools:

```bash
sudo pacman -S --needed base-devel
```

Build and install the local package:

```bash
makepkg --clean --syncdeps --install
```

Run the installed command:

```bash
ropro-bypass quickstart
ropro-bypass update
```

Remove the package:

```bash
sudo pacman -Rns ropro-bypass
```

### Nix / NixOS

Patch the detected installation:

```bash
nix run . -- quickstart
```

Update an already-patched installation:

```bash
nix run . -- update
```

Open the development shell or run every flake check:

```bash
nix develop
nix flake check
```

### Other commands

Patch a specified directory in place:

```bash
python3 patch_ropro.py apply /path/to/source
```

Override individual values:

```bash
python3 patch_ropro.py quickstart \
  --preset real \
  --subscription pro_tier \
  --verification true \
  --settings all-on \
  --setting declineThreshold=100
```

List, discover, or verify (use `--help` for details):

```bash
python3 patch_ropro.py scenarios
python3 patch_ropro.py discover
python3 patch_ropro.py verify /path/to/source
```

`update` exits without changing the directory if it is not already patched or if the current Web Store release is unsupported. Pass `--source /path/to/source` when auto-detection finds multiple installs.

Use `py -3` instead of `python3` for these commands on Windows.
