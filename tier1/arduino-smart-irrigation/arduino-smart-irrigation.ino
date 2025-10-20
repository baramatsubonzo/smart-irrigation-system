#include <ArduinoBLE.h>

const int SOIL_PIN = A0;
// I use the digital pin 8 to control the pump.
const int PUMP_PIN = 8;

BLEService soilService("19B10010-E8F2-537E-4F6C-D104768A1214");

// Notify Soil Moisture Level (16bit)
BLEUnsignedShortCharacteristic soilChar(
  "19B10011-E8F2-537E-4F6C-D104768A1214",
  BLERead | BLENotify
);

// Write (1 byte: 0=OFF, 1=ON) Control Pump
BLEByteCharacteristic pumpChar(
  "19B10012-E8F2-537E-4F6C-D104768A1214",
  BLERead | BLEWrite | BLEWriteWithoutResponse
);

// Configurable intervals
const unsigned long SOIL_NOTIFY_INTERVAL_MS = 1000;
const unsigned long PUMP_AUTO_OFF_MS        = 5000;

// State variables
unsigned long lastSoilNotifyMs = 0;
unsigned long pumpStartTime = 0;
bool pumpIsOn = false;

// Downstream: Handle pump control commands from BLE central
void handleDownstreamPumpCommand() {
  if (!pumpChar.written()) return;

  byte cmd = 0;
  pumpChar.readValue(cmd); // 0=OFF, 1=ON
  if (cmd == 1 && !pumpIsOn) {
    digitalWrite(PUMP_PIN, HIGH);
    pumpIsOn = true;
    pumpStartTime = millis();
    pumpChar.writeValue((byte)1);
    Serial.println("PUMP: ON (for 5 seconds)");
  }
  else if (cmd == 0 && pumpIsOn){
    digitalWrite(PUMP_PIN, LOW);
    pumpIsOn = false;
    pumpChar.writeValue((byte)0);
    Serial.println("PUMP: OFF (manual operation)");
  }
}

void handleAutoPumpOff() {
  // Automatically turn OFF the pump after 5 seconds to save power and prevent motor damage
  if (pumpIsOn && (millis() - pumpStartTime >= PUMP_AUTO_OFF_MS)) {
    digitalWrite(PUMP_PIN, LOW);
    pumpIsOn = false;
    pumpChar.writeValue((byte)0);
    Serial.println("PUMP: OFF (auto timer)");
  }
}

void handleUpstreamSoilNotify() {
  // Notify soil moisture level every second
  if (millis() - lastSoilNotifyMs >= SOIL_NOTIFY_INTERVAL_MS) {
    lastSoilNotifyMs = millis();
    unsigned short raw = (unsigned short)analogRead(SOIL_PIN);
    soilChar.writeValue(raw);
  }
}

void handleDisconnectSafety() {
  // Ensure the pump is turned off when the BLE central disconnects
  if(pumpIsOn) {
    digitalWrite(PUMP_PIN, LOW);
    pumpIsOn = false;
    Serial.println("PUMP: OFF (disconnected)");
  }
}

void setup() {
  // Initialize serial communication for debugging (115200 baud)
  Serial.begin(115200);
  while (!Serial) {}

  pinMode(SOIL_PIN, INPUT);
  pinMode(PUMP_PIN, OUTPUT);
  digitalWrite(PUMP_PIN, LOW);
  // Set analog read resolution to 10 bits (0-1023)
  analogReadResolution(10);

  // If BLE initialization fails, print error and stop the program.
  if (!BLE.begin()) {
    Serial.println("BLE init failed!");
    // Infinite loop to halt execution.
    while (1) {}
  }

  BLE.setLocalName("SoilNode");
  BLE.setAdvertisedService(soilService);
  soilService.addCharacteristic(soilChar);
  soilService.addCharacteristic(pumpChar);
  BLE.addService(soilService);

  // Set initial BLE values (soil=0, pump=OFF)
  soilChar.writeValue((unsigned short)0);
  pumpChar.writeValue((byte)0);

  BLE.advertise();
  Serial.println("BLE advertising started (SoilNode)");
  Serial.print("Device MAC: ");
  Serial.println(BLE.address());
}

void loop() {
  BLEDevice central = BLE.central();
  if (!central) return;

  Serial.print("Connected: ");
  Serial.println(central.address());

  while (central.connected()) {
    handleDownstreamPumpCommand();
    handleAutoPumpOff();
    handleUpstreamSoilNotify();
  }

  Serial.println("Disconnected");
  handleDisconnectSafety();
}