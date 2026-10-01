constexpr int PIN_POWER     = 16;
constexpr int PIN_BRIGHT_DN = 17;
constexpr int PIN_BRIGHT_UP = 18;

constexpr unsigned long PULSE_MS = 200;

void pulseRelay(int pin, const char* name) {
  Serial.print("Pulsing: ");
  Serial.println(name);

  digitalWrite(pin, HIGH);
  delay(PULSE_MS);
  digitalWrite(pin, LOW);

  Serial.println("Pulse complete");
}

void setup() {
  Serial.begin(115200);

  pinMode(PIN_POWER, OUTPUT);
  pinMode(PIN_BRIGHT_DN, OUTPUT);
  pinMode(PIN_BRIGHT_UP, OUTPUT);

  // Important: all PhotoMOS channels OFF at startup
  digitalWrite(PIN_POWER, LOW);
  digitalWrite(PIN_BRIGHT_DN, LOW);
  digitalWrite(PIN_BRIGHT_UP, LOW);

  Serial.println();
  Serial.println("GestureLight button test");
  Serial.println("p = power");
  Serial.println("d = brightness down");
  Serial.println("u = brightness up");
}

void loop() {
  if (!Serial.available()) {
    return;
  }

  char command = Serial.read();

  switch (command) {
    case 'p':
      pulseRelay(PIN_POWER, "POWER");
      break;

    case 'd':
      pulseRelay(PIN_BRIGHT_DN, "BRIGHTNESS DOWN");
      break;

    case 'u':
      pulseRelay(PIN_BRIGHT_UP, "BRIGHTNESS UP");
      break;

    case '\n':
    case '\r':
      break;

    default:
      Serial.println("Unknown command");
      break;
  }
}
