#include <ArduinoBLE.h>

const int SOIL_PIN = A0;
const int PUMP_PIN = LED_BUILTIN;  // 物理ポンプが無い間はLEDで代用

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
        if (cmd == 1) { digitalWrite(PUMP_PIN, HIGH); Serial.println("PUMP: ON"); }
        else          { digitalWrite(PUMP_PIN, LOW);  Serial.println("PUMP: OFF"); }
      }

      // 1秒ごとに土壌値Notify
      if (millis() - lastMs >= 1000) {
        lastMs = millis();
        unsigned short raw = (unsigned short)analogRead(SOIL_PIN);
        soilChar.writeValue(raw);
      }
    }
    Serial.println("Disconnected");
  }
}
