Stream Audio Monitor – Windows Setup (WSL)

A simple application to monitor streams and detect songs from your local MP3 library.

1. Install WSL (Windows Subsystem for Linux)

If not already installed, open PowerShell (as Administrator) and run:

wsl --install


Restart your computer if prompted.
By default, WSL will install Ubuntu.

2. Open WSL and install all dependencies

Launch Ubuntu (WSL) from the Start menu and run this one command:

sudo apt update && sudo apt install -y openjdk-17-jdk ffmpeg python3 python3-venv python3-pip git


This installs:

Java (for fingerprinting)

FFmpeg (for audio processing)

Python 3 + venv + pip (for running the app)

Git (to clone the repository)

3. Clone the repository
git clone https://github.com/asmi-g25/stream-audio-monitor
cd stream-audio-monitor

4. Set up Python virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt


⚠️ Remember: you must activate the virtual environment every time you run the app.

5. Prepare your music files

Place your MP3s in a folder of your choice.
(If they are on Windows, you can access them in WSL under /mnt/c/...)

6. Run the application
python stream_monitor.py

7. Configure the app

Update paths in the app setup to point to your MP3 folder.

Fingerprint your songs (some warnings may appear in logs – usually safe to ignore).

Set the stream URL.

Click Monitoring to see detections in real time.

Notes

Always activate your virtual environment before running:

source venv/bin/activate


Always run inside WSL, not Windows CMD/PowerShell.

The DB folder is optional; no need to create it manually.

FFmpeg and Java must remain installed in WSL.
