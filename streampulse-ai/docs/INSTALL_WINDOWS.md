# Installing StreamPulse AI on Windows 11

## 1. Prerequisites
| Component | Notes |
|---|---|
| Windows 11 (or 10 2004+) | Windows Graphics Capture needs build 19041+ |
| WSL2 + Docker Desktop | Settings → General → "Use the WSL 2 based engine" |
| Git, Python 3.12 (python.org installer, "Add to PATH") | for the capture agent |
| Google Chrome | the agent drives your installed Chrome (proprietary codecs, normal Google sign-in) |
| FFmpeg **8.0+** full build for Windows | e.g. gyan.dev "ffmpeg-release-full". Needed for `gfxcapture`. Unzip to `C:\ffmpeg` |
| VB-Audio Virtual Cable | one cable per concurrent stream (VB-Cable, plus VB-Cable A+B for 3 streams) |
| NVIDIA GPU (optional) | latest Game Ready/Studio driver. Docker Desktop passes it through WSL2 automatically |

Check your hardware: `nvidia-smi` (GPU), `ffmpeg -version` (FFmpeg), `docker info` (Docker).

## 2. Get the code and configure
```powershell
git clone <your repo url> C:\StreamPulse
cd C:\StreamPulse\streampulse-ai
copy .env.example .env
python scripts\generate_secrets.py
```
Paste the three generated values into `.env`, then fill in:
* `YOUTUBE_API_KEY` (required for live detection and chat), see docs/API_SETUP.md
* `GEMINI_API_KEY` (or enter it later in Settings → AI)
* `CAPTURE_STORAGE_ROOT=C:\StreamPulse\streampulse-ai\storage`
* `CAPTURE_FFMPEG=C:\ffmpeg\bin\ffmpeg.exe`
* `CAPTURE_AUDIO_ROUTES`, see section 5

## 3. Start the Docker stack
```powershell
docker compose up -d --build
# with an NVIDIA GPU (Whisper on CUDA + NVENC in the worker):
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
docker compose ps          # all services "healthy"
```
Open http://localhost:3000 and create the owner account. The first Whisper run downloads the model
(`WHISPER_MODEL`, default `small`) into the `models` volume.

Keep the project on the Windows filesystem (e.g. `C:\StreamPulse`). The Windows agent and the Linux
containers both access `storage/` through the bind mount. Docker Desktop shares `C:\` by default.

## 4. Install the capture agent
```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-capture-agent.ps1
.venv-agent\Scripts\python -m capture.agent login    # Chrome opens: sign in to Google yourself, then close it
.venv-agent\Scripts\python -m capture.agent doctor   # every line should be [ok]
.venv-agent\Scripts\python -m capture.agent run
```
To start the agent automatically at sign-in, run `scripts\install-agent-task.ps1`. It registers a
Scheduled Task that runs **in your interactive session**, which is required because window capture needs
your desktop.

## 5. Audio routing (per-stream isolation)
1. Install VB-Audio Virtual Cable. Windows then has a playback device **"CABLE Input"** and a recording
   device **"CABLE Output (VB-Audio Virtual Cable)"**.
2. Keep your normal speakers as the default output. The agent routes only the stream's `<video>` element
   to the cable with `setSinkId`, so other desktop audio is never recorded.
3. Run `ffmpeg -list_devices true -f dshow -i dummy` and copy the exact recording device name.
4. In `.env`:
   ```
   CAPTURE_AUDIO_ROUTES=[{"sink": "CABLE Input", "source": "CABLE Output (VB-Audio Virtual Cable)"}]
   ```
   Add one entry per additional cable to capture several streams at once. Also raise
   *Settings → Capture → Max concurrent captures* to match.
5. If you don't want to monitor the stream, leave it as is: audio on the cable isn't audible. To listen too,
   enable "Listen to this device" on CABLE Output in Windows Sound settings.

## 6. Windows permissions and interaction
* Windows Graphics Capture asks for **no** consent dialog when capture is started by a desktop app on
  Windows 11. On some Windows 10 builds a yellow capture border is drawn around the window (it is not
  recorded).
* The agent must run in your logged-in desktop session, not as a Windows service.
* Don't **minimise** capture windows. Covering them with other windows is fine with `gfxcapture`. With
  `gdigrab` the window must stay visible and uncovered.
* Turn off sleep and display-off while streams are captured (Settings → System → Power).
* Windows Defender may ask whether Python can access the network the first time. Allow **private** networks only.

## 7. Updating
```powershell
git pull
docker compose up -d --build     # migrations run automatically on backend start
.venv-agent\Scripts\pip install -r capture\requirements-agent.txt
```
