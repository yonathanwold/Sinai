/*
  Sinai Grove Light Sensor bridge

  Hardware:
  - Grove Light Sensor signal pin connected to Arduino A0
  - Arduino connected to Raspberry Pi over USB serial

  Output:
  JSON Lines at 9600 baud, one sample per second.
*/

const int LIGHT_SENSOR_PIN = A0;
const unsigned long SAMPLE_INTERVAL_MS = 1000;

unsigned long lastSampleTime = 0;

float estimateLux(int rawValue) {
  if (rawValue <= 0) {
    return 0.0;
  }

  // Approximation for the Grove light sensor voltage divider.
  float sensorResistance = (1023.0 - rawValue) * 10.0 / rawValue;
  float lux = 5250.0 * pow(sensorResistance, -1.4);
  if (isnan(lux) || isinf(lux)) {
    return 0.0;
  }
  return lux;
}

void setup() {
  Serial.begin(9600);
  pinMode(LIGHT_SENSOR_PIN, INPUT);
}

void loop() {
  unsigned long now = millis();
  if (now - lastSampleTime < SAMPLE_INTERVAL_MS) {
    return;
  }

  lastSampleTime = now;
  int rawValue = analogRead(LIGHT_SENSOR_PIN);
  float lux = estimateLux(rawValue);

  Serial.print("{\"light_raw\":");
  Serial.print(rawValue);
  Serial.print(",\"light_lux\":");
  Serial.print(lux, 1);
  Serial.println("}");
}
