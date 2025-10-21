# Sensor-Driven Smart Irrigation System

## 1. Project Overview
- This project is a **3-tier IoT system** designed to replace **guesswork** with data-driven farming, allowing for remote irrigation only when plants are actually thirsty.
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
    - ①Subscribes to sensor data, ②evaluates it against a threshold, ③sends email alerts ④control water pump.
    - Hosts the `MQTT broker (Mosquitto)` for communication.
        * **Collects** soil moisture data by subscribing to the `sensors/soil/#` MQTT topic.
        * **Control pump commands** published to the `command/pump/#` MQTT topic (for logging purposes, actual control is handled by Tier 2).

    * Runs the `iot_service.py` notification service, which:
        * **Evaluates** the data against a threshold ([see code](https://github.com/baramatsubonzo/smart-irrigation-system/blob/master/tier3/iot_service.py#L71-L86)).
        * **Notifies** the user via email if the soil is too dry ([see code](https://github.com/baramatsubonzo/smart-irrigation-system/blob/master/tier3/iot_service.py#L88-L114)).


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

## 5. Physical Circuit Design
This section details the wiring for the Tier 1 device, which consists of the Arduino, a water pump, and the control circuit.
Components
- MCU: Arduino Nano 33 IoT
- Actuator: DC Water Pump
- Power Source: External Battery Pack
- Switch: NPN Transistor (2N2222A)
- Protection: Diode (1N5819)
- Current Limiter: 270Ω Resistor
### Wiring Connections
**Transistor (2N2222A)**
The transistor acts as an electronic switch, allowing the Arduino's small signal to control the large current needed by the pump.
- **Pin 1 (Left Leg - Emitter)**: Connects to **Common GND**.
- **Pin 2 (Middle Leg - Base)**: Connects to the **270Ω Resistor**.
- **Pin 3 (Right Leg - Collector)**: Connects to the** Motor's Negative (-)** wire.
Arduino Nano 33 IoT
- **Pin `D8`**: Connects to the other end of the **270Ω Resistor**.
- **Pin `GND`**: Connects to **Common GND**.

**Motor & Diode**
- **Motor Positive (+) Wire**: Connects to the **Battery's Positive (+)** terminal.
- **Motor Negative (-) Wire**: Connects to the **Transistor's Collector**(right leg).
- **Diode (1N5819)**: This is essential for protecting the transistor from voltage spikes when the motor turns off. **Connect it in parallel with the motor**.
    - **IMPORTANT**: The **silver stripe** on the diode must face the **motor's positive (+)** side.

**Common GND**<br>

For the circuit to function correctly, the following three points **must be connected together** in the same row on the breadboard:<br>
- **Arduino's `GND` Pin**
- **Battery's Negative (-)** Terminal
- **Transistor's Emitter** (left leg)
