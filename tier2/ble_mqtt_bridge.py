import asyncio, json, time, signal
from bleak import BleakClient, BleakScanner
# add type hints for readability
from typing import Optional
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
import os

load_dotenv()
# Settings
DEVICE_NAME    = "SoilNode"
DEVICE_ID      = os.getenv("DEVICE_ID", "default-node")
DEVICE_ADDRESS = os.getenv("DEVICE_ADDRESS", "")
SOIL_CHAR_UUID = "19B10011-E8F2-537E-4F6C-D104768A1214"
PUMP_CHAR_UUID = "19B10012-E8F2-537E-4F6C-D104768A1214"
# MQTT Settings
BROKER_ADDRESS = os.getenv("BROKER_ADDRESS", "localhost")
PORT           = int(os.getenv("PORT", 1883))
UP_TOPIC       = "sensors/soil"
DOWN_TOPIC     = "command/pump"

# Types of global variables
MAIN_LOOP: asyncio.AbstractEventLoop
BLE_CLIENT: Optional[BleakClient] = None
MQTTC: mqtt.Client

# ---- Downstream: payload→1/0 ----
# Convert payload strings or JSON from Tier 3 into 1 (on) or 0 (off).
def parse_onoff(s: str):
    # If string from Tier 3 is "1","0","true","false","on","off"
    p = s.strip().lower()
    if p in ("1","true","on"):
        return 1
    if p in ("0","false","off"):
        return 0
    try:
        # If JSON from Tier 3 is {"on":true/false}.
        data = json.loads(s)
        if isinstance(data, dict) and "on" in data:
            return 1 if data["on"] else 0
    except Exception: pass
    return None

# ---- MQTT ----
# Callback function triggered when the client successfully connects to the MQTT broker
# 'rc' is the connection result. 0 means success. 1-5 indicate various errors.
# Using mqtt.CallbackAPIVersion.VERSION2 (MQTT v5), so on_connect must accept 'properties=None'
def on_connect(client, userdata, flags, rc, properties=None):
    print(f"[MQTT] connected rc={rc}")
    # Subscribe to downstream command topic
    client.subscribe(DOWN_TOPIC, qos=1)
    print(f"[MQTT] subscribed {DOWN_TOPIC}")

# Callback function triggered when an MQTT message is received
def on_message(client, userdata, msg):
    global BLE_CLIENT, MAIN_LOOP
    # 1. Parse payload to get 1/0 command
    # 'errors="ignore"' to avoid decode errors
    val = parse_onoff(msg.payload.decode(errors="ignore"))
    if val is None:
        print("[MQTT] ignore payload:", msg.payload)
        return

    # 2. Safely check if BLE client exists and is connected before writing.
    if not (BLE_CLIENT and BLE_CLIENT.is_connected):
        print("[BLE] not ready, skip write:", val)
        return
    # 3. Run BLE write coroutine safely from the MQTT thread via the main asyncio loop.
    # run_coroutine_threadsafe: Safely run the async BLE write task on the main event loop from another thread.
    future = asyncio.run_coroutine_threadsafe(
        # bytearray([val]): Convert 'val' to a single byte array for BLE write.
        # response=False: Do not wait for a response from the BLE device.
        BLE_CLIENT.write_gatt_char(PUMP_CHAR_UUID, bytearray([val]), response=False),
        MAIN_LOOP
    )
    try:
        # Wait up to 2 seconds for the write to complete.
        future.result(timeout=2.0)
        print("[DOWN] BLE write OK:", val)
    except Exception as e:
        print("[DOWN] BLE write NG:", e)
# Create and configure the MQTT client with callback hundlers, then return it.
def build_mqtt():
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except Exception:
        client = mqtt.Client()  # fallback for older paho-mqtt versions
    client.on_connect = on_connect
    client.on_message = on_message
    return client

def mqtt_start():
    global MQTTC
    MQTTC = build_mqtt()
    # keepalive=60: send a ping every 60 seconds to keep the connection alive.
    MQTTC.connect(BROKER_ADDRESS, PORT, 60)
    MQTTC.loop_start()
    print("[MQTT] loop started")

def mqtt_stop():
    MQTTC.loop_stop()
    MQTTC.disconnect()
    print("[MQTT] stopped")

# Publish sensor data upstream to the MQTT broker.
def mqtt_pub(d: dict):
    MQTTC.publish(UP_TOPIC, json.dumps(d), qos=1)

# ---- BLE ----
# Asynchronously find and return the BLE device by its MAC address.
# Uses async/await because BLE scanning is a time-consuming I/O operation
# that should not block other tasks. (e.g., MQTT communication)
async def find_device():
    if not DEVICE_ADDRESS:
        return None
    # Scan and find the device by its MAC address.
    device = await BleakScanner.find_device_by_address(DEVICE_ADDRESS, timeout=10.0)
    return device

# Called when Arduino sends a BLE notification with soil data.
# Parses the data add publishes it to the MQTT broker.
def on_notify(_sender, data: bytearray):
    try:
        # Convert bytearray data to an integer (little-endian).
        # little: little-endian byte order.
        # signed=False: treat the bytes as an unsigned integer.
        raw = int.from_bytes(data, "little", signed=False)
    except Exception:
        # Fallback: use the first byte if conversion fails.
        raw = data[0] if data else 0
    # Create JSON payload with device ID, timestamp, and soil raw value for MQTT publishing.
    payload = {"device": DEVICE_ID, "timestamp": int(time.time()), "soil_raw": raw}
    # Publish the payload to the MQTT broker.
    mqtt_pub(payload)
    print("[UP ] Published:", payload)

# Main BLE loop: continuously scan, connect, receive sensor data, and publish via MQTT.
# Automatically retries on disconnection or errors, and exits when stop_event is set.
async def ble_loop(stop_event: asyncio.Event):
    global BLE_CLIENT
    while not stop_event.is_set():
        try:
            print("[BLE] scanning...")
            device = await find_device()
            if not device:
                print("[BLE] device not found. retry in 5s")
                await asyncio.sleep(5)
                continue
            # Safely print device address if available, otherwise print the device object itself.
            print(f"[BLE] connecting to {getattr(device,'address',device)}")

            # Connect to the BLE device (auto-disconnects on exit from 'async with' block).
            async with BleakClient(device, timeout=20.0) as client:
                if not client.is_connected:
                    print("[BLE] connect failed, retry")
                    await asyncio.sleep(3); continue
                BLE_CLIENT = client
                # Create a Future object to wait for the BLE disconnection event.
                disconnected_future = asyncio.get_running_loop().create_future()
                # When the BLE device disconnects,
                # set the future as completed so the loop can continue.
                def handle_disconnect(_client):
                    if not disconnected_future.done():
                        disconnected_future.set_result(True)
                # Set a callback function that will be called when the BLE device disconnects.
                client = BleakClient(address_or_ble_device, disconnected_callback=handle_disconnect)
                await client.connect()

                print("[BLE] connected:", client.address)

                print(f"[BLE] start notify {SOIL_CHAR_UUID}")
                # Start receiving BLE notifications from the soil sensor data.
                await client.start_notify(SOIL_CHAR_UUID, on_notify)
                # Wait until either the BLE device disconnects or stop event is triggered.
                await asyncio.wait(
                    [disconnected_future, stop_event.wait()],
                    # `return_when`: defines when asyncio.wait should return.
                    # FIRST_COMPLETED: return as soon as any of the futures complete.
                    return_when=asyncio.FIRST_COMPLETED
                )
                try:
                    await client.stop_notify(SOIL_CHAR_UUID)
                except Exception: pass

            if stop_event.is_set(): break
            await asyncio.sleep(2)  # backoff
        except Exception as e:
            print("[BLE] error:", e)
            await asyncio.sleep(3)
    print("[BLE] loop exit")

# ---- main ----
async def main():
    global MAIN_LOOP
    # Get the current running asyncio event loop
    # andd assign it to the global variable
    # for use in other functions.
    MAIN_LOOP = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    # SIGINT: interrupt signal (Ctrl+C)
    # SIGTERM: termination signal (used by systemd or docker to stop a process)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            # add_signal_handler: Register a callback to be called when the signal is received.
            MAIN_LOOP.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    mqtt_start()
    # Start the BLE loop as a background task.
    # stop_event is used to signal when to stop the loop.
    task = asyncio.create_task(ble_loop(stop_event))
    # Wait until a stop signal is received.
    await stop_event.wait()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    mqtt_stop()
    print("[MAIN] bye")

if __name__ == "__main__":
    asyncio.run(main())
