import asyncio
import base64
import json
import pyaudio
import requests
import websockets
import cv2
import numpy as np
import time
import wave

# --- ADK Configuration ---
SERVER_URL = "http://127.0.0.1:8009"
WS_URL = "ws://127.0.0.1:8009"
APP_NAME = "geminilive"  
USER_ID = "test_user"
SESSION_ID = f"test_session_esp32_{int(time.time())}" 

# --- ESP32 Server Configuration ---
HOST = "0.0.0.0"
VIDEO_PORT = 3001
AUDIO_PORT = 3002

def create_session():
    """Create the session on the ADK server via REST API."""
    url = f"{SERVER_URL}/apps/{APP_NAME}/users/{USER_ID}/sessions/{SESSION_ID}"
    print(f"Creating session at {url}...")
    try:
        response = requests.post(url)
        if response.status_code in [200, 201]:
            print("Session created successfully.")
            return True
        else:
            print(f"Failed to create session: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"Error creating session: {e}")
        return False

async def main():
    if not create_session():
        return
        
    uri = f"{WS_URL}/run_live?app_name={APP_NAME}&user_id={USER_ID}&session_id={SESSION_ID}"
    print(f"Connecting to Gemini ADK WebSocket at {uri}...")
    
    try:
        # 1. Connect to the Gemini ADK
        async with websockets.connect(uri, origin="http://127.0.0.1:8009") as adk_websocket:
            print("Connected to Gemini Live Agent!")
            
            # Open WAV file for recording conversation
            wav_file = wave.open(f"conversation_{int(time.time())}.wav", "wb")
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2) # 16-bit
            wav_file.setframerate(24000) # Gemini output rate
            
            # 2. Setup PyAudio strictly for OUTPUT (Gemini's voice)
            p_out = pyaudio.PyAudio()
            output_stream = p_out.open(
                format=pyaudio.paInt16, 
                channels=1, 
                rate=24000, # Gemini outputs audio at 24kHz
                output=True
            )
            
            # --- TASK A: Receive Audio/Text from Gemini ---
            async def receive_from_gemini():
                try:
                    async for message in adk_websocket:
                        data = json.loads(message)
                        
                        # Play audio response if present
                        if "content" in data and "parts" in data["content"]:
                            for part in data["content"]["parts"]:
                                if "inlineData" in part and part["inlineData"]["mimeType"] == "audio/pcm":
                                    base64_data = part["inlineData"]["data"]
                                    base64_data = base64_data.replace("-", "+").replace("_", "/")
                                    padding = len(base64_data) % 4
                                    if padding: base64_data += "=" * (4 - padding)
                                    
                                    try:
                                        audio_bytes = base64.b64decode(base64_data)
                                        print(f"[Gemini -> Client] Received {len(audio_bytes)} bytes of audio")
                                        # Save to WAV file
                                        wav_file.writeframes(audio_bytes)
                                        await asyncio.to_thread(output_stream.write, audio_bytes)
                                    except Exception as e:
                                        print(f"Error decoding Gemini audio: {e}")
                                        
                        # Print transcription
                        if "outputTranscription" in data:
                            text = data["outputTranscription"]["text"]
                            finished = data["outputTranscription"].get("finished", False)
                            if finished:
                                print(f"\nGemini: {text}")
                            else:
                                print(f"\rGemini (thinking): {text}", end="", flush=True)
                                
                except websockets.exceptions.ConnectionClosed:
                    print("\nConnection closed by ADK server.")
            
            # --- TASK B: Handle ESP32 Video & Forward to Gemini ---
            last_video_send = 0
            
            async def handle_esp_video(esp_ws):
                nonlocal last_video_send
                print(f"\n[+] ESP32 Video Stream connected")
                try:
                    async for message in esp_ws:
                        if isinstance(message, str): continue
                        
                        # Decode the JPEG image from ESP32
                        nparr = np.frombuffer(message, np.uint8)
                        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        
                        if frame is not None:
                            # Rotate 180 degrees
                            frame = cv2.rotate(frame, cv2.ROTATE_180)
                            
                            # 1. Show the video locally
                            cv2.imshow("ESP32-S3 (What Gemini Sees)", frame)
                            cv2.waitKey(1)
                        
                        # 2. Forward to Gemini (Throttled to 1 FPS to prevent overloading ADK)
                        current_time = time.time()
                        if current_time - last_video_send >= 1.0 and frame is not None:
                            # Re-encode to JPEG after rotation
                            ret, buffer = cv2.imencode('.jpg', frame)
                            if ret:
                                jpg_as_text = base64.b64encode(buffer).decode('utf-8')
                                adk_msg = {
                                    "blob": {
                                        "mime_type": "image/jpeg",
                                        "data": jpg_as_text
                                    }
                                }
                                await adk_websocket.send(json.dumps(adk_msg))
                                last_video_send = current_time
                            
                except Exception as e:
                    print(f"[-] ESP32 Video disconnected.")
                finally:
                    cv2.destroyAllWindows()

            # --- TASK C: Handle ESP32 Audio & Forward to Gemini ---
            async def handle_esp_audio(esp_ws):
                print(f"\n[+] ESP32 Audio Stream connected")
                try:
                    async for message in esp_ws:
                        if isinstance(message, str): continue
                        
                        print(f"[ESP32 -> Client] Received {len(message)} bytes of raw audio")
                        
                        # Forward continuous mic audio directly to Gemini
                        audio_base64 = base64.b64encode(message).decode('utf-8')
                        adk_msg = {
                            "blob": {
                                "mime_type": "audio/pcm",
                                "data": audio_base64
                            }
                        }
                        
                        # Print details of what is being sent to Gemini
                        print(f"[Client -> Gemini] Sending {len(audio_base64)} base64 chars (mime: audio/pcm)")
                        
                        await adk_websocket.send(json.dumps(adk_msg))
                        
                        # Yield control slightly so other tasks can run
                        await asyncio.sleep(0.001) 
                except Exception as e:
                    print(f"[-] ESP32 Audio disconnected.")

            # --- LAUNCH EVERYTHING ---
            print("\nStarting ESP32 Listeners. Turn on your ESP32 now!")
            
            # Start the listener servers for the ESP32
            esp_video_server = websockets.serve(handle_esp_video, HOST, VIDEO_PORT, ping_interval=None)
            esp_audio_server = websockets.serve(handle_esp_audio, HOST, AUDIO_PORT, ping_interval=None)
            
            # Run the Gemini receiver and the ESP32 servers simultaneously
            await asyncio.gather(
                receive_from_gemini(),
                esp_video_server,
                esp_audio_server
            )

    except Exception as e:
        print(f"Critical Error: {e}")
    finally:
        print("Cleaning up audio engines...")
        try:
            output_stream.stop_stream()
            output_stream.close()
            p_out.terminate()
            cv2.destroyAllWindows()
            if 'wav_file' in locals() and wav_file:
                wav_file.close()
        except: pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBridge stopped manually.")
