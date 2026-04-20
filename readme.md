# Agentic AI Glasses: ESP32-S3 Real-Time Bridge

This repository contains the firmware and bridging software to turn an ESP32-S3 (with camera and I2S microphone) into a real-time, voice-interactive, agentic AI peripheral. The system streams low-latency audio and video from the glasses to a local bridge script, which then pipes the data into the Google Gemini ADK (Agent Development Kit).

## 🚀 Architecture Overview

The system uses a dual-core streaming architecture to ensure fluid interaction:

### ESP32-S3 Firmware (`esp32code.ino`)
- **Core 1**: Captures video frames (QVGA @ 4 FPS) and streams them via WebSocket.
- **Core 0**: Captures I2S audio (16kHz, 16-bit) and streams them via a separate WebSocket.

### Bridge Script (`new.py`)
- Acts as a high-performance WebSocket server.
- Routes ESP32 sensor data into the Gemini ADK WebSocket.
- Decodes Gemini's audio response, plays it through the host machine's output, and saves the conversation to a WAV file.

### Gemini Agent (`agent.py`)
- Manages the agent persona (AI Glasses Assistant).
- Handles tools like Google Search and a hardcoded Gmail sender.

## 🛠 Prerequisites

### Hardware
- ESP32-S3 (N16R8 recommended for PSRAM support).
- INMP441 I2S Microphone.
- ESP32-S3 Camera Module.

### Software
- Python 3.12+
- Arduino IDE (with ESP32 board support).
- Gemini ADK (Local server running on `http://127.0.0.1:8009`).

## ⚙️ Setup Instructions

### 1. Firmware Configuration
1. Open `esp32code.ino` in the Arduino IDE.
2. Set Board to **ESP32S3 Dev Module**.
3. **Critical**: Set PSRAM to **OPI PSRAM** and Flash Size to **16MB**.
4. Update the network credentials (`ssid`, `password`) and `server_host` (your machine's IP on the local network).
5. Upload the firmware to your ESP32-S3.

### 2. Bridge Setup
1. Install the required dependencies:
   ```bash
   pip install websockets opencv-python numpy pyaudio requests
   ```
2. Ensure your Gemini ADK server is running locally on port `8009`.
3. Run the bridge script:
   ```bash
   python3 new.py
   ```

## 📋 File Reference

- `esp32code.ino`: Handles real-time hardware IO using FreeRTOS tasks to keep audio and video streams independent.
- `new.py`: Manages the WebSocket server, forwards data to the ADK, rotates video, and handles audio playback/recording.
- `agent.py`: Defines the agent's behavior, personality, and tool-use capabilities (Search, Gmail).

## ⚠️ Known Optimizations

- **Thermal Control**: The firmware uses a 10MHz XCLK for the camera to prevent overheating.
- **Bandwidth Management**: Video is throttled to 1 FPS for Gemini ingestion to prevent API rate limits, while maintaining a smooth preview locally on your machine.
- **Audio Integrity**: DMA buffers are set to 8 to prevent audio crackling during high Wi-Fi activity.

---
*Created for the Agentic AI Glasses project.*
