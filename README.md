# J.A.R.V.I.S. — Personal AI Voice Assistant

> Double-clap. Jarvis wakes up, greets you with the weather and your tasks, answers your questions like a sharp, friendly colleague, controls your browser, and sees your screen.

Built entirely with [Claude Code](https://claude.ai/code) — no code written manually.

---

## Youtube Video

[Demo & Explaination](https://youtu.be/XsceN-hEit4)

---

## Features

- **Double-Clap Trigger** — Clap twice and your entire workspace launches: VS Code, Obsidian, Chrome with Jarvis UI
- **Voice Conversation** — Speak freely with Jarvis through your microphone. He listens, thinks, and responds with voice
- **Smart Colleague** — Jarvis speaks German like a competent coworker: friendly, direct, professional, and always one step ahead
- **Weather & Tasks** — On startup, Jarvis greets you with the current weather and a quick summary of your open tasks from Obsidian
- **Browser Automation** — "Search for MiroFish" → Jarvis opens a real browser, navigates to the page, reads the content, and summarizes it for you
- **Screen Vision** — "What's on my screen?" → Jarvis takes a screenshot, analyzes it with Claude Vision, and describes what he sees
- **World News** — "What's happening in the world?" → Jarvis opens worldmonitor.app and summarizes current global events
- **Window Snapping** — All launched apps automatically snap into quadrants on your screen

---

## Architecture

```
You (speak) → Chrome Browser (Web Speech API) → FastAPI Server (local)
                                                       ↓
                                                Claude Haiku (thinks)
                                                       ↓
                                    ┌──────────────────┼───────────────────┐
                                    ↓                  ↓                   ↓
                             ElevenLabs TTS     Playwright Browser    Screen Capture
                             (speaks back)      (searches/opens)     (Claude Vision)
                                    ↓
                             Audio → Chrome → You (hear)
```

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Speech Input | Web Speech API (Chrome) | Converts your voice to text |
| Server | FastAPI (Python) | Local orchestration — runs on your machine |
| Brain | Claude Haiku (Anthropic) | Thinks, decides, formulates responses |
| Voice | ElevenLabs TTS | Converts text to natural German speech |
| Browser Control | Playwright | Automates a real browser you can see |
| Screen Vision | Claude Vision + Pillow | Screenshots and describes your screen |
| Clap Detection | sounddevice + numpy | Listens for double-clap to launch everything |
| Window Management | PowerShell + Win32 API | Snaps windows into screen quadrants |

---

## Prerequisites

- **Windows 10/11**
- **Python 3.10+**
- **Google Chrome**
- **[Claude Code](https://claude.ai/code)** (recommended for setup)

### API Keys Needed

| Service | What For | Cost | Link |
|---------|----------|------|------|
| Anthropic | Claude Haiku (the brain) | ~$0.25 / 1M tokens | [console.anthropic.com](https://console.anthropic.com) |
| ElevenLabs | Voice (text-to-speech) | Free tier: 10k chars/month | [elevenlabs.io](https://elevenlabs.io) |

---

## Quick Start

### Option A: Setup with Claude Code (Recommended)

1. Clone the repo:
   ```bash
   git clone https://github.com/Julian-Ivanov/jarvis-voice-assistant.git
   cd jarvis-voice-assistant
   ```

2. Open in VS Code, start Claude Code, and say:
   ```
   Set up Jarvis for me.
   ```

3. Claude Code will ask for your API keys, name, preferences, and configure everything automatically.

### Option B: Manual Setup

1. **Clone and install dependencies:**
   ```bash
   git clone https://github.com/Julian-Ivanov/jarvis-voice-assistant.git
   cd jarvis-voice-assistant
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Create `config.json`** from the template:
   ```bash
   cp config.example.json config.json
   ```

3. **Edit `config.json`** with your API keys and preferences:
   ```json
   {
     "anthropic_api_key": "sk-ant-...",
     "elevenlabs_api_key": "sk_...",
     "elevenlabs_voice_id": "YOUR_VOICE_ID",
     "user_name": "Your Name",
     "user_address": "Your Name",
     "city": "Hamburg",
     "workspace_path": "C:\\path\\to\\jarvis-voice-assistant",
     "browser_url": "https://your-website.com",
     "obsidian_inbox_path": "C:\\path\\to\\obsidian\\inbox",
     "apps": ["obsidian://open"]
   }
   ```

4. **Start Jarvis:**
   ```bash
   python server.py
   ```

5. **Open Chrome** and go to `http://localhost:8340`

6. **Click anywhere** on the page, then speak!

---

## Usage

### Start Jarvis manually
```bash
python server.py
```
Then open `http://localhost:8340` in Chrome.

### Start everything with a double-clap
```bash
python scripts/clap-trigger.py
```
Clap twice → VS Code opens, Obsidian opens, Chrome opens with Jarvis. All windows snap into quadrants.

### Auto-start on Windows login
1. Open Task Scheduler (`Win + R` → `taskschd.msc`)
2. Create Task → Trigger: "At log on"
3. Action: `powershell` with argument:
   ```
   -ExecutionPolicy Bypass -Command "python C:\path\to\scripts\clap-trigger.py"
   ```

---

## What You Can Say

| Command | What Happens |
|---------|-------------|
| *"Good morning, Jarvis"* | Jarvis greets you with weather + tasks |
| *"Search for AI news"* | Opens browser, searches, summarizes results |
| *"Open skool.com"* | Opens the URL in your browser |
| *"What's on my screen?"* | Takes screenshot, describes what he sees |
| *"What's happening in the world?"* | Opens worldmonitor.app, summarizes global news |
| *"Recherchiere zu …"* | Reads 3–5 sources, speaks a summary, lists sources in the transcript |
| *"Notiere: …"* | Writes a categorized entry into today's Obsidian Brain Dump |
| *"Merk dir dauerhaft: …"* | Saves to `Jarvis Memory.md` — a plain Markdown file you can edit anytime |
| *"Stopp"* (or Esc / stop button) | Immediately stops speech and cancels a running action |
| *Any question* | Jarvis answers like a friendly, direct colleague |

---

## Project Structure

```
jarvis-voice-assistant/
├── server.py              # FastAPI layer — routes, WebSocket, settings API
├── assistant_core.py      # The brain — system prompt, LLM calls, actions
├── actions.py             # Action registry + parsing + safety policies
├── tts.py                 # ElevenLabs text-to-speech
├── memory.py              # Obsidian inbox/vault + long-term memory file
├── health.py              # /health diagnostics
├── browser_tools.py       # Playwright browser automation + HTML search fallback
├── screen_capture.py      # Screenshot + Claude Vision
├── clipboard_tools.py     # Windows clipboard access
├── config.json            # Your personal config (gitignored)
├── config.example.json    # Template for new users
├── requirements.txt       # Python dependencies
├── frontend/
│   ├── index.html         # Jarvis web UI
│   ├── main.js            # Speech recognition + WebSocket + audio + stop
│   ├── settings.js        # Settings overlay
│   └── style.css          # Dark theme with animated orb
├── tests/                 # unittest suite (python -m unittest discover -s tests)
├── scripts/
│   ├── clap-trigger.py    # Double-clap detection
│   ├── smoke-test.py      # One-command health check
│   └── launch-session.ps1 # Launches all apps + window snapping
├── CLAUDE.md              # Instructions for Claude Code
└── SETUP.md               # Detailed setup guide
```

---

## Customization

### Change Jarvis's personality
Edit the system prompt in `assistant_core.py` → `build_system_prompt()`. The personality, greeting behavior, and action instructions are all defined there. Name, role, and how Jarvis addresses you come from `config.json` (editable in the settings UI).

### Change which apps launch
Edit `config.json`:
```json
{
  "browser_url": "https://your-website.com",
  "apps": ["obsidian://open", "slack://"]
}
```

### Change the voice
Find a voice on [elevenlabs.io](https://elevenlabs.io), copy the Voice ID, and set it in `config.json`:
```json
{
  "elevenlabs_voice_id": "YOUR_VOICE_ID"
}
```

### Change the weather city
```json
{
  "city": "Berlin"
}
```

### Adjust clap sensitivity
In `scripts/clap-trigger.py`:
```python
THRESHOLD = 0.15  # Lower = more sensitive
MAX_GAP = 1.2     # Seconds between claps
```

---

## Memory & Privacy

Everything runs locally; only Claude (thinking/vision) and ElevenLabs (voice) receive data over the network.

- **Daily notes** go into today's *Brain Dump* file in your Obsidian inbox (`[ACTION:INBOX_WRITE]`).
- **Long-term memory** lives in `Jarvis Memory.md` in your vault (or `memory.md` in the workspace if no vault is configured). Jarvis writes to it **only when you explicitly ask** ("Merk dir dauerhaft …"). It's plain Markdown — read, edit, or delete it anytime; its content is shown to the model as part of the system prompt.
- **Session history** is kept in memory only (capped) and discarded on disconnect.
- **API keys** never leave `config.json` — the settings API refuses to read or write them.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Jarvis doesn't speak | Check if server is running. Kill old process: `taskkill /f /im python.exe` then restart |
| "Connection lost" in browser | Old server still running on port 8340. Kill it and restart |
| Clap not detected | Lower `THRESHOLD` in `clap-trigger.py` (try 0.10) |
| Browser search fails | Run `playwright install chromium` |
| No audio in Chrome | Click anywhere on the page first (Chrome autoplay policy) |
| Jarvis uses the wrong name or tone | Adjust `user_address` in `config.json` or the persona in `assistant_core.py` (`build_system_prompt`) |
| Jarvis won't stop talking | Say *"Stopp"*, press **Esc**, or click the stop button — this also cancels a running action |
| Research finds no sources | Research falls back to DuckDuckGo's HTML endpoint if the browser fails — check your internet connection and run `python scripts/smoke-test.py` |

---

## Mac Users

This template is built for Windows. If you're on macOS, clone the repo and tell Claude Code:

```
Convert this project to work on macOS.
```

Claude Code will adapt the PowerShell scripts to shell scripts, adjust paths, and handle macOS-specific differences.

---

## Tech Stack

- **[FastAPI](https://fastapi.tiangolo.com/)** — Python web framework for the local server
- **[Claude Haiku](https://anthropic.com)** — Fast, affordable AI model (the brain)
- **[ElevenLabs](https://elevenlabs.io)** — Natural text-to-speech (the voice)
- **[Playwright](https://playwright.dev)** — Browser automation
- **[Web Speech API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API)** — Browser-native speech recognition
- **[sounddevice](https://python-sounddevice.readthedocs.io/)** — Audio input for clap detection

---

## Credits

Built by [Julian](https://skool.com/ki-automatisierung) with [Claude Code](https://claude.ai/code).

Inspired by Iron Man's J.A.R.V.I.S. — *"Ready when you are."*

---

## License

MIT — use it, modify it, build on it. If you build something cool, let me know!
