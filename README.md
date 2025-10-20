# Seonser-Driven Smart Irrigation System

## 1. Project Overview
- This Project is a **3-tier IoT system** designed to replace **guesswork** with data-driven farming, allowing for remote irrigation only when plants are actually thirsty.
- A soil moisture sensor detects dryness, triggering an email notification and enabling remote control of a water pump.
- The primary goal is to build a proof-of-concept for a future remote strawberry farm, where precise water management is critical.

## 2. Architecture
The system is built on a **3-tier architecture** to ensure scalability and separation of concerns.

* **Tier 1: Sensor & Actuator (Arduino Nano 33 IoT)**
    - Measures soil moisture and transmits the data via BLE.
    - Receives commands via BLE to control the water pump.
* **Tier 2: Gateway (Raspberry Pi)**
    - Gateway converts BLE to MQTT
        - BLE data to MQTT messages for the cloud (Upstream)
        - MQTT commands to BLE writes for the Arduino (Downstream).
* **Tier 3: Cloud (AWS EC2)**
    - Hosts the MQTT broker (Mosquitto) for communication.
    - ①Subscribes to sensor data, ②evaluates it against a threshold, and ③sends email alerts.

## 3. Setup & Installation
### Tier 1: Arduino
1.  Connect the soil moisture sensor to pin `A0` and the water pump control circuit to pin `D8`.
2.  Upload the `arduino-smart-irrigation.ino` sketch using the Arduino IDE.

### Tier 2: Raspberry Pi Gateway
1.  Clone `ble_mqtt_bridge.py` to your Raspberry Pi.
2.  Install the required Python libraries:
    ```bash
    pip install bleak paho-mqtt python-dotenv
    ```
3.  Create a `.env` file in the same directory as `ble_mqtt_bridge.py` and add the following settings:
    ```bash
    # The MAC address of your Arduino
    DEVICE_ADDRESS="YOUR_ARDUINO_MAC_ADDRESS"
    # The public IP address of your EC2 instance
    BROKER_ADDRESS="YOUR_EC2_PUBLIC_IP"
    DEVICE_ID="soil-node-01"
    ```

### Tier 3: AWS EC2 Service
1.  Clone `iot_service.py` to your EC2 instance.
2.  Install the required Python libraries and MQTT broker:
    ```bash
    # For Python service
    pip install paho-mqtt python-dotenv
    # For MQTT broker
    sudo apt update && sudo apt install mosquitto mosquitto-clients -y
    ```
3.  Create a `.env` file in the same directory as `iot_service.py` with your Gmail App Password and other settings:
    ```bash
    MQTT_BROKER=localhost
    SOIL_THRESHOLD=300 # Example raw value threshold
    SMTP_SERVER=smtp.gmail.com
    SMTP_PORT=587
    EMAIL_ADDRESS="your_email@gmail.com"
    EMAIL_PASSWORD="your-16-digit-app-password"
    TO_EMAIL_ADDRESS="your_destination_email@example.com"
    ```
4.  Configure the EC2 Security Group to allow inbound traffic on port `1883` (for MQTT) and outbound traffic on port `587` (for SMTP/email).

## 4. How to Run

### 1. Start the Cloud Service (EC2)
On your EC2 instance, run the notification service. It will run indefinitely.
```bash
python3 iot_service.py
```
### 2. Start the Gateway (Raspberry Pi)
On your Raspberry Pi, run the bridge script. It will automatically connect to the Arduino and the MQTT broker.
```Bash
python3 ble_mqtt_bridge.py
```
### 3. Remote Control (from any machine)
To manually trigger the pump for 5 seconds, publish a message to the MQTT broker from any machine with `mosquitto-clients` installed.
```Bash
# Replace with your EC2 IP address
mosquitto_pub -h YOUR_EC2_PUBLIC_IP -t "command/pump" -m "1"
```

## 5. License
This project is developed for academic purposes as part of QUT IFN649 coursework.