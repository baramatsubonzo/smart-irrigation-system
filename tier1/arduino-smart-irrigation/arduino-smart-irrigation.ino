#include <ArduinoBLE.h>

const int SOIL_PIN = A0;
const int PUMP_PIN = 8;

BLEService soilService("19B10010-E8F2-537E-4F6C-D104768A1214");

// 土壌値 Notify (16bit)
BLEUnsignedShortCharacteristic soilChar(
  "19B10011-E8F2-537E-4F6C-D104768A1214",
  BLERead | BLENotify
);

// ポンプ制御 Write (1 byte: 0=OFF, 1=ON)
BLEByteCharacteristic pumpChar(
  "19B10012-E8F2-537E-4F6C-D104768A1214",
  BLEWrite | BLEWriteWithoutResponse
);

unsigned long pumpStartTime = 0;
bool pumpIsOn = false;

void setup() {
  Serial.begin(115200);
  while (!Serial) {}

  pinMode(SOIL_PIN, INPUT);
  pinMode(PUMP_PIN, OUTPUT);
  digitalWrite(PUMP_PIN, LOW);
  analogReadResolution(10);

  if (!BLE.begin()) {
    Serial.println("BLE init failed!");
    while (1) {}
  }

  BLE.setLocalName("SoilNode");
  BLE.setAdvertisedService(soilService);
  soilService.addCharacteristic(soilChar);
  soilService.addCharacteristic(pumpChar);
  BLE.addService(soilService);

  soilChar.writeValue((unsigned short)0);
  pumpChar.writeValue((byte)0);

  BLE.advertise();
  Serial.println("BLE advertising started (SoilNode)");
  Serial.print("Device MAC: ");
  Serial.println(BLE.address());
}

unsigned long lastMs = 0;

void loop() {
  BLEDevice central = BLE.central();
  if (central) {
    Serial.print("Connected: "); Serial.println(central.address());

    while (central.connected()) {
      // 下りコマンドの反映
      if (pumpChar.written()) {
        byte cmd = 0;
        pumpChar.readValue(cmd);
        if (cmd == 1 && !pumpIsOn) {
          digitalWrite(PUMP_PIN, HIGH);
          pumpIsOn = true;
          pumpStartTime = millis();
          Serial.println("PUMP: ON (for 5 seconds)");
        }
        else if (cmd == 0 && pumpIsOn){
          digitalWrite(PUMP_PIN, LOW);
          pumpIsOn = false;
          Serial.println("PUMP: OFF (manual operation)");
        }
      }

      if (pumpIsOn && (millis() - pumpStartTime >= 5000)) {
        digitalWrite(PUMP_PIN, LOW);
        pumpIsOn = false;
        pumpChar.writeValue((byte)0);
        Serial.println("PUMP: OFF (auto timer)");
      }

      // 1秒ごとに土壌値Notify
      if (millis() - lastMs >= 1000) {
        lastMs = millis();
        unsigned short raw = (unsigned short)analogRead(SOIL_PIN);
        soilChar.writeValue(raw);
      }
    }
    Serial.println("Disconnected");

    if(pumpIsOn) {
      digitalWrite(PUMP_PIN, LOW);
      pumpIsOn = false;
      Serial.println("PUMP: OFF (disconnected)");
    } 
  }
}
