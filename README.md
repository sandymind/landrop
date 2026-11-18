# LanDrop

Chat and send files between Windows laptops on the same network (Wi-Fi/LAN) — like AirDrop or Quick Share, for Windows.

Made by **Sandy Mind** · [sandymind.my.id](http://sandymind.my.id/) · Support development on [Saweria](https://saweria.co/sandymind) ☕

## Install on each laptop
1. Download `LanDrop.exe` from the [latest release](https://github.com/sandymind/landrop/releases/latest) (or build it yourself, see below).
2. Double-click `LanDrop.exe` → choose **Yes** to install.
   - If **"Windows protected your PC"** (SmartScreen) appears: click **More info → Run anyway** (the EXE is not digitally signed yet).
   - If **Windows Firewall** asks: tick **Private networks**, then **Allow access**. Without this, other laptops can't send to this one.
3. Done. Shortcuts are added to the Desktop and Start Menu, and LanDrop runs in the background when Windows starts.

Once a laptop has LanDrop, you can send newer versions of `LanDrop.exe` to it through LanDrop itself. Installing over an older version keeps chat history and settings.

## Usage
- Other laptops running LanDrop appear automatically on the left (green dot = online).
- **Text**: type and press Enter. Click **Copy** on a message to copy it to the clipboard.
- **Images/screenshots**: press **Ctrl+V** in the chat window (e.g. after Win+Shift+S).
- **Files**: drag & drop into the chat window, or use the **+** button. No size limit.
- **Send to all devices**: pick **All devices** at the top of the list. Text, images, and files go to every online laptop at once. If some fail, the message shows ⚠ "Sent to 1/2 devices" (hover to see why).
- Received files are saved to `Downloads\LanDrop` (changeable in ⚙ Settings).
- **About LanDrop**: the ⓘ button next to ⚙, or right-click the tray icon → About LanDrop.
- **Updates**: LanDrop checks [GitHub Releases](https://github.com/sandymind/landrop/releases) for a newer version. When one is available, a red dot appears on ⓘ and the About dialog offers **Download update** — run the downloaded `LanDrop.exe` and choose **Yes**.
- Closing the window doesn't stop LanDrop — it keeps receiving files and the ⇄ icon stays in the taskbar tray.

## Tray icon
- **Left-click** the ⇄ tray icon: open the LanDrop window.
- **Right-click**: open the received files folder, see how many devices are online, toggle start with Windows, or **Quit**.
- While the window is closed, incoming messages/files show up as Windows notifications. Click one to open the chat.
- On Windows 10/11 new icons are often hidden behind the **^** button. Drag the ⇄ icon onto the taskbar to keep it visible.

## Language
English by default. Switch to **Bahasa Indonesia** in ⚙ Settings → Language; it applies instantly, including the tray menu and notifications. The page is marked *notranslate*, so Edge doesn't offer to translate it.

## Important settings (⚙)
- **Pairing key**: enter the same key on all your laptops. Other laptops on the network (e.g. office Wi-Fi) that don't know the key can't see you or send to you.
- **Add a device manually**: if a laptop doesn't show up automatically (some routers/office Wi-Fi block broadcasts), enter its IP address — it's shown in that laptop's Settings.

## If devices don't show up
- Make sure both are on the same network and the Windows network profile is **Private** (Settings → Network → Properties).
- Make sure LanDrop is allowed through the firewall (Windows Security → Firewall → Allow an app). Ports used: TCP 47801 and UDP 47800.
- Guest/public Wi-Fi often blocks device-to-device traffic ("client isolation"); use your phone's hotspot or another network.

## Uninstall
Settings → Apps → **LanDrop** → Uninstall. Received files are not deleted.

## Security note
Transfers are not encrypted. Use LanDrop on networks you trust (home, your own hotspot). The pairing key stops others from sending to you, but does not hide transfer contents from someone sniffing the network.

## Build from source
Requires Python 3.10+. Run `build.bat` → output at `dist\LanDrop.exe`.

Files: `landrop.py` (server, discovery, installer), `tray.py` (tray icon), `ui.html` (interface), `make_icon.py` (app icon), `sandymind-logo.png` (About dialog).
