#include <WebServer.h>
#include <WiFi.h>
#include <cstring>

#include "wifi_secrets.h"

constexpr int PIN_POWER = 16;
constexpr int PIN_BRIGHT_DN = 17;
constexpr int PIN_BRIGHT_UP = 18;
constexpr unsigned long PULSE_MS = 200;

WebServer server(80);

void pulseRelay(int pin, const char* name) {
  Serial.print("Pulsing: ");
  Serial.println(name);

  digitalWrite(pin, HIGH);
  delay(PULSE_MS);
  digitalWrite(pin, LOW);

  Serial.println("Pulse complete");
}

bool configurationIsSafe() {
  if (strcmp(WIFI_SSID, "YOUR_WIFI_SSID") == 0 ||
      strcmp(WIFI_PASSWORD, "YOUR_WIFI_PASSWORD") == 0) {
    Serial.println("Configure wifi_secrets.h before using GestureLight.");
    return false;
  }
  return true;
}

void connectToWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print('.');
  }
  Serial.println();
  Serial.print("Connected. ESP32 URL: http://");
  Serial.println(WiFi.localIP());
}

void handleHealth() {
  server.send(200, "text/plain", "ok\n");
}

void handleCommand() {
  if (!server.hasArg("command")) {
    server.send(400, "text/plain", "Missing command\n");
    return;
  }

  const String command = server.arg("command");
  if (command == "p") {
    pulseRelay(PIN_POWER, "POWER");
  } else if (command == "d") {
    pulseRelay(PIN_BRIGHT_DN, "BRIGHTNESS DOWN");
  } else if (command == "u") {
    pulseRelay(PIN_BRIGHT_UP, "BRIGHTNESS UP");
  } else {
    server.send(400, "text/plain", "Unknown command\n");
    return;
  }
  server.send(200, "text/plain", "ok\n");
}

void setup() {
  Serial.begin(115200);

  pinMode(PIN_POWER, OUTPUT);
  pinMode(PIN_BRIGHT_DN, OUTPUT);
  pinMode(PIN_BRIGHT_UP, OUTPUT);
  // All PhotoMOS channels remain OFF until a Wi-Fi command arrives.
  digitalWrite(PIN_POWER, LOW);
  digitalWrite(PIN_BRIGHT_DN, LOW);
  digitalWrite(PIN_BRIGHT_UP, LOW);

  if (!configurationIsSafe()) {
    return;
  }
  connectToWiFi();

  server.on("/health", HTTP_GET, handleHealth);
  server.on("/command", HTTP_POST, handleCommand);
  server.onNotFound([]() { server.send(404, "text/plain", "Not found\n"); });
  server.begin();

  Serial.println("GestureLight Wi-Fi server ready");
}

void loop() {
  server.handleClient();
}
