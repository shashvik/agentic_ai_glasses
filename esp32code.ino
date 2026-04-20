#include "esp_camera.h"
#include <WiFi.h>
#include <ArduinoWebsockets.h>
#include <driver/i2s.h>

// --- Network Configuration ---
const char* ssid     = "";     
const char* password = ""; // Re-hide this if sharing publicly!

const char* server_host = "192.168.29.95"; 
const uint16_t video_port = 3001; 
const uint16_t audio_port = 3002;

using namespace websockets;
WebsocketsClient videoClient;
WebsocketsClient audioClient;

// --- Microphone Pins ---
#define I2S_WS 42
#define I2S_SCK 41
#define I2S_SD 40
#define I2S_PORT I2S_NUM_0

// --- ESP32-S3 Camera Pins ---
#define PWDN_GPIO_NUM  -1
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM  15
#define SIOD_GPIO_NUM  4
#define SIOC_GPIO_NUM  5
#define Y9_GPIO_NUM    16
#define Y8_GPIO_NUM    17
#define Y7_GPIO_NUM    18
#define Y6_GPIO_NUM    12
#define Y5_GPIO_NUM    10
#define Y4_GPIO_NUM    8
#define Y3_GPIO_NUM    9
#define Y2_GPIO_NUM    11
#define VSYNC_GPIO_NUM 6
#define HREF_GPIO_NUM  7
#define PCLK_GPIO_NUM  13

TaskHandle_t VideoTaskHandle;
TaskHandle_t AudioTaskHandle;

// Task Forward Declarations
void videoTask(void * parameter);
void audioTask(void * parameter);

void setup() {
  Serial.begin(115200);

  // 1. Init WiFi
  WiFi.begin(ssid, password);
  Serial.print("\nConnecting WiFi");
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println("\nWiFi Connected!");

  // OPTIMIZATION 1: Disable Wi-Fi power saving for zero-latency audio streaming
  WiFi.setSleep(false); 

  // 2. Init Camera
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0; config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM; config.pin_d1 = Y3_GPIO_NUM; config.pin_d2 = Y4_GPIO_NUM; config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM; config.pin_d5 = Y7_GPIO_NUM; config.pin_d6 = Y8_GPIO_NUM; config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM; config.pin_pclk = PCLK_GPIO_NUM; config.pin_vsync = VSYNC_GPIO_NUM; config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM; config.pin_sccb_scl = SIOC_GPIO_NUM; config.pin_pwdn = PWDN_GPIO_NUM; config.pin_reset = RESET_GPIO_NUM;
  
  // OPTIMIZATION 2: Lower camera clock to 10MHz for cooler operation at QVGA resolution
  config.xclk_freq_hz = 10000000; 
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_QVGA; config.jpeg_quality = 15; config.fb_count = 2;
  esp_camera_init(&config);

  // 3. Init Microphone
  i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = 16000,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT, 
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    // OPTIMIZATION 3: Increased DMA buffers slightly to prevent audio drops during Wi-Fi spikes
    .dma_buf_count = 8, 
    .dma_buf_len = 512,
    .use_apll = false
  };
  i2s_pin_config_t pin_config = { .bck_io_num = I2S_SCK, .ws_io_num = I2S_WS, .data_out_num = I2S_PIN_NO_CHANGE, .data_in_num = I2S_SD };
  i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
  i2s_set_pin(I2S_PORT, &pin_config);

  // 4. Start the dual-core tasks
  xTaskCreatePinnedToCore(videoTask, "VideoTask", 10000, NULL, 1, &VideoTaskHandle, 1); 
  xTaskCreatePinnedToCore(audioTask, "AudioTask", 10000, NULL, 2, &AudioTaskHandle, 0); 
}

void loop() {
  delay(1000); 
}

// ==========================================
// CORE 1: VIDEO TASK
// ==========================================
void videoTask(void * parameter) {
  for(;;) {
    if (!videoClient.available()) {
      Serial.println("Video connecting...");
      videoClient.connect(server_host, video_port, "/");
      delay(2000);
      continue;
    }

    camera_fb_t *fb = esp_camera_fb_get();
    if (fb) {
      videoClient.sendBinary((const char*) fb->buf, fb->len);
      esp_camera_fb_return(fb);
    }
    videoClient.poll();
    
    // OPTIMIZATION 4: Limit video to ~4 FPS (250ms delay). 
    // This frees up massive Wi-Fi bandwidth for the audio stream since Gemini only needs 1 FPS anyway.
    delay(250); 
  }
}

// ==========================================
// CORE 0: AUDIO TASK
// ==========================================
void audioTask(void * parameter) {
  int32_t raw_samples[256]; 
  int16_t tx_samples[256];  
  size_t bytes_read;

  for(;;) {
    if (!audioClient.available()) {
      Serial.println("Audio connecting...");
      audioClient.connect(server_host, audio_port, "/");
      delay(2000);
      continue;
    }

    // i2s_read is blocking. It naturally yields to the RTOS while waiting for sound.
    esp_err_t result = i2s_read(I2S_PORT, &raw_samples, sizeof(raw_samples), &bytes_read, portMAX_DELAY);
    
    if (result == ESP_OK && bytes_read > 0) {
      int samples_read = bytes_read / 4; 
      
      for(int i = 0; i < samples_read; i++) {
        tx_samples[i] = raw_samples[i] >> 14; 
      }
      
      audioClient.sendBinary((const char*)tx_samples, samples_read * 2); 
    }
    audioClient.poll();
    
    // OPTIMIZATION 5: Removed delay(1). It caused artificial jitter. 
  }
}
