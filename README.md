# Stream Audio Monitor

A simple application to monitor streams and detect songs from your local MP3 library.

---

## Setup on Windows (via WSL)

### 1. Install WSL (Windows Subsystem for Linux)
If not already installed, open **PowerShell (as Administrator)** and run:

```powershell
wsl --install
```

---

### 2. Install all dependencies in WSL
Launch **Ubuntu (WSL)** from the Start menu and run:

```bash
sudo apt update && sudo apt install -y openjdk-17-jdk ffmpeg python3 python3-venv python3-pip git
```

This installs:
- Java (for fingerprinting)
- FFmpeg (for audio processing)
- Python 3 + venv + pip (for running the app)
- Git (to clone the repository)

---

### 3. Clone the repository

```bash
git clone https://github.com/asmi-g25/stream-audio-monitor
cd stream-audio-monitor
```

---

### 4. Set up Python virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Important:** You must activate the virtual environment each time before running the app. At least for now later, I can integrate everything in the app only


---

### 5. Run the application

```bash
python stream_monitor.py
```

---

### 7. Configure the app

- Update paths in the app setup to point to your MP3 folder.
- Fingerprint your songs (some warnings may appear in logs – usually safe to ignore).
- Set the stream URL.
- Click **Monitoring** to see detections in real time.

---

## Notes

- Always activate your virtual environment before running:
  ```bash
  source venv/bin/activate
  ```
- Always run inside **WSL**, not Windows CMD/PowerShell.
- The `DB` folder is optional; no need to create it manually.
- FFmpeg and Java must remain installed in WSL.

---

## License

This project is licensed under the MIT License.
