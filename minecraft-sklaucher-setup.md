================================================================================
MINECRAFT SECURE LINUX MINT SETUP GUIDE (SKLAUNCHER + FIREJAIL)
================================================================================

1. OVERVIEW & CONTEXT
--------------------------------------------------------------------------------
- Launcher Used: SKlauncher (v3.2.18) - Selected as a safe, clean, non-Microsoft 
  offline launcher to avoid spyware issues linked with programs like TLauncher.
- Sandbox Used: Firejail - Implemented to create a security wall. It prevents 
  Minecraft, third-party mods, or external game servers from accessing your 
  personal home files, browser data, or photos.
- OS Environment: Linux Mint (Uses the APT package manager).
- Java Requirement: Java 21 (OpenJDK 21) is strictly required by modern 
  SKlauncher versions. Older versions like Java 11 will cause a "Fatal Error."


2. SYSTEM INSTALLATION AND CONFIGURATION
--------------------------------------------------------------------------------
Open your terminal (Ctrl+Alt+T) and run these native commands to prepare your 
operating system:

# Step A: Update your system packages and install Java 21 and Firejail
sudo apt update && sudo apt install openjdk-21-jre firejail -y

# Step B: Configure Linux Mint to prioritize Java 21 over older versions
sudo update-alternatives --config java
*(When the list appears, type the number corresponding to 'java-21-openjdk' 
and press Enter).*


3. SANDBOX FILE DIRECTORY LOGIC
--------------------------------------------------------------------------------
When using the '--private=~/.safe-minecraft' flag, Firejail masks your actual 
home directory. The folder '~/.safe-minecraft' effectively BECOMES your root 
home folder ('/home/vallutto/') inside the sandbox execution loop. 

To view this hidden directory natively in the Linux Mint Files manager, navigate 
to your user Home folder and press 'Ctrl + H'. 

Inside the sandbox, the execution path to your launcher file is:
/home/vallutto/SKlauncher-3.2.18.jar


4. TERMINAL MANIFEST LAUNCH COMMAND
--------------------------------------------------------------------------------
To run the game securely with full network access (bypassing strict default 
firejail network profile blocks) while keeping your personal files strictly 
isolated, use this command:

firejail --noprofile --private=~/.safe-minecraft java -jar /home/vallutto/SKlauncher-3.2.18.jar


5. DESKTOP SHORTCUT AUTOMATION (.DESKTOP FILE)
--------------------------------------------------------------------------------
To generate a permanent, clickable launcher shortcut directly on your Linux Mint 
Desktop, paste this full block into your terminal:

cat <<EOF > ~/Desktop/Minecraft-Secure.desktop
[Desktop Entry]
Version=1.0
Type=Application
Name=Minecraft (Secure)
Comment=Launch SKlauncher inside a Firejail sandbox
Exec=firejail --noprofile --private=~/.safe-minecraft java -jar /home/vallutto/SKlauncher-3.2.18.jar
Icon=minecraft
Terminal=false
Categories=Game;
EOF

# Give execution permissions to make the desktop icon interactive:
chmod +x ~/Desktop/Minecraft-Secure.desktop

# Optional: Add the launcher to your Linux Mint Start Menu:
cp ~/Desktop/Minecraft-Secure.desktop ~/.local/share/applications/
================================================================================
