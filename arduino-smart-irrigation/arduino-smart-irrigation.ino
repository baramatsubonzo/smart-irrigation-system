#include <ArduinoBLE.h>

const int SOIL_PIN = A0;

// 任意の128-bit UUID（Arduino公式例と同系）
BLEService soilService("19B10010-E8F2-537E-4F6C-D104768A1214");
// 0–1023の生値を送る（16bit符号なし）/ 読み取り + Notify
BLEUnsignedShortCharacteristic soilChar(
  "19B10011-E8F2-537E-4F6C-D104768A1214",
  BLERead | BLENotify
);

void setup() {
  Serial.begin(115200);
  while (!Serial) {}

  // ⚠️配線注意：Nano 33 IoTは3.3Vロジック
  // センサーのVCCは3.3V給電推奨（A0に5Vを入れない）

  pinMode(SOIL_PIN, INPUT);
  analogReadResolution(10); // 0-1023

  if (!BLE.begin()) {
    Serial.println("BLE init failed!");
    while (1) {}
  }

  BLE.setLocalName("SoilNode");
  BLE.setAdvertisedService(soilService);
  soilService.addCharacteristic(soilChar);
  BLE.addService(soilService);

  soilChar.writeValue((unsigned short)0); // 初期値
  BLE.advertise();

  Serial.println("BLE advertising started (SoilNode)");
}

void loop() {
  // 中央（スマホ/ラズパイ）が接続するのを待つ
  BLEDevice central = BLE.central();

  if (central) {
    Serial.print("Connected: ");
    Serial.println(central.address());

    while (central.connected()) {
      unsigned short raw = (unsigned short)analogRead(SOIL_PIN);
      soilChar.writeValue(raw);          // これでNotifyが飛ぶ
      Serial.print("Soil(raw): ");
      Serial.println(raw);
      delay(1000);                       // 1秒周期
    }

    Serial.println("Disconnected");
  }
}
