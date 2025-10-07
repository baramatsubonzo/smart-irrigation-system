const int soilPin = A0;

void setup() {
  Serial.begin(9600);        // PCと通信（シリアルモニター用）
  while (!Serial);           // 接続待ち（Nano 33 IoT特有）
  Serial.println("Soil sensor test started!");
}

void loop() {
  int value = analogRead(soilPin);  // センサーから値を読む
  Serial.print("Soil moisture value: ");
  Serial.println(value);             // 値を出力
  delay(1000);                       // 1秒ごとに更新
}