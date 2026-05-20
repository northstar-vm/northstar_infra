# Secure Minecraft Launcher On Linux

This guide sets up a safer local Minecraft launcher workflow on Linux Mint/Ubuntu.
It keeps launcher files in predictable folders, runs the launcher in a Firejail
sandbox, and gives you one stable desktop shortcut.

Use the launcher profile/name that is allowed by the server whitelist when joining
offline-mode servers such as:

```text
mc.attentionisallineed.xyz
```

## 1. Install System Packages

```bash
sudo apt update
sudo apt install openjdk-21-jre firejail -y
```

Notes:

- Java 21 is fine for many modern launcher/client setups.
- Very new Minecraft versions may require newer Java. If the launcher or game
  says Java is too old, install the required OpenJDK version and update the
  wrapper script below to use that Java binary directly.
- Avoid changing the global Java default unless you really need to. A wrapper
  script is cleaner because it affects only Minecraft.

## 2. Create Stable Folders

```bash
mkdir -p ~/Games/Minecraft
mkdir -p ~/.local/bin
mkdir -p ~/.local/share/minecraft-secure
```

Put your launcher jar here:

```text
~/Games/Minecraft/SKlauncher.jar
```

Renaming the jar to `SKlauncher.jar` means the desktop shortcut does not break
every time the launcher version changes.

## 3. Create The Wrapper Script

Create:

```bash
nano ~/.local/bin/minecraft-secure
```

Paste:

```bash
#!/usr/bin/env bash
set -euo pipefail

LAUNCHER_JAR="$HOME/Games/Minecraft/SKlauncher.jar"
SANDBOX_HOME="$HOME/.local/share/minecraft-secure"
JAVA_BIN="/usr/bin/java"

if [ ! -f "$LAUNCHER_JAR" ]; then
  echo "Launcher not found: $LAUNCHER_JAR" >&2
  exit 1
fi

mkdir -p "$SANDBOX_HOME"

exec firejail \
  --noprofile \
  --private="$SANDBOX_HOME" \
  "$JAVA_BIN" -jar "$LAUNCHER_JAR"
```

Make it executable:

```bash
chmod +x ~/.local/bin/minecraft-secure
```

Test it:

```bash
~/.local/bin/minecraft-secure
```

## 4. Create A Desktop Shortcut

Create:

```bash
nano ~/Desktop/Minecraft-Secure.desktop
```

Paste:

```ini
[Desktop Entry]
Version=1.0
Type=Application
Name=Minecraft Secure
Comment=Launch Minecraft in a Firejail sandbox
Exec=/home/vallutto/.local/bin/minecraft-secure
Icon=minecraft
Terminal=false
Categories=Game;
```

Make it executable and add it to the app menu:

```bash
chmod +x ~/Desktop/Minecraft-Secure.desktop
mkdir -p ~/.local/share/applications
cp ~/Desktop/Minecraft-Secure.desktop ~/.local/share/applications/
```

If your Linux desktop blocks launching it at first, right-click the desktop icon
and allow launching/trust the launcher.

## 5. Where Files Go

Your real home folder stays mostly hidden from the launcher because Firejail uses:

```text
~/.local/share/minecraft-secure
```

Inside the sandbox, that folder behaves like the launcher's home directory. This
is where launcher settings, game files, and downloaded versions will live.

To inspect it in the file manager, open your home folder and press `Ctrl+H` to
show hidden folders, then go to:

```text
.local/share/minecraft-secure
```

## 6. Useful Commands

Run launcher from terminal:

```bash
~/.local/bin/minecraft-secure
```

Check Java:

```bash
java -version
```

Check Firejail exists:

```bash
firejail --version
```

Connect to your server from Minecraft Java:

```text
mc.attentionisallineed.xyz
```

## 7. Troubleshooting

If the launcher says Java is too old:

1. Install the required OpenJDK version.
2. Find the Java binary:

```bash
ls /usr/lib/jvm
```

3. Update `JAVA_BIN` in `~/.local/bin/minecraft-secure` to the full Java path.

If the launcher cannot find downloaded game files, remember they are inside the
sandbox folder, not your normal home folder.

If multiplayer cannot connect, first test the official Minecraft Launcher or a
non-sandboxed launch once. If that works, the issue is the local sandbox. If it
also fails, check the server DNS/firewall/port instead.
