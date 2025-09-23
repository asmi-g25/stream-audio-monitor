
# Stream Audio Monitor

A simple application to monitor streams and detect songs from your local MP3 library.

## How to Run on Windows

### 1. Install WSL (Windows Subsystem for Linux)
If not already installed, run:

```bash
wsl --install
```

### 2. Open WSL and install dependencies
- **Install Java**:

```bash
sudo apt install openjdk-17-jdk -y
```

- **Install FFmpeg**:

```bash
sudo apt install ffmpeg -y
```

### 3. Clone the repository

```bash
git clone https://github.com/asmi-g25/stream-audio-monitor
cd stream-audio-monitor
```

### 4. Set up Python virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 5. Prepare your music files
Place your MP3s or songs in a folder of your choice.

### 6. Run the application

```bash
python stream_monitor.py
```

### 7. Configure the app
- In the app setup, update paths as needed.  
- Fingerprint your songs.  (You will some warnings in logs when fingerprinting, but you can ignore them if everything is done correctly the app will run successfully (you can share the logs with me to confirm but mostly there won't be an issue)
- Set the stream URL.  
- Click on **Monitoring** to see detections in real time.

## To make sure it runs correctly:
- Make sure your virtual environment is activated whenever you run the app otherwise there will errors in install requirements and also please make sure you are in WSL only 
- Paths in the app should point correctly to your songs and any required folders. The DB folder is not mandatory so you can leave it as it is, no need to create or anything  
- FFmpeg and Java must be installed in WSL for the app to function properly.
