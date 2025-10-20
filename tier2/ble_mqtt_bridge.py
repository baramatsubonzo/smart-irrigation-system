import asyncio, json, time, signal
from bleak import BleakClient, BleakScanner
from typing import Optional
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
import os

load_dotenv()
# Settings
DEVICE_NAME    = "SoilNode"
DEVICE_ID      = "soil-node-01"
DEVICE_ADDRESS = "B0:B2:1C:49:BF:62"
SOIL_CHAR_UUID = "19B10011-E8F2-537E-4F6C-D104768A1214"
PUMP_CHAR_UUID = "19B10012-E8F2-537E-4F6C-D104768A1214"
# MQTT Settings
BROKER_ADDRESS = "3.107.29.55"
PORT           = 1883
UP_TOPIC       = "sensors/soil"
DOWN_TOPIC     = "command/pump"

# Globals
MAIN_LOOP: asyncio.AbstractEventLoop
BLE_CLIENT: Optional[BleakClient] = None
MQTTC: mqtt.Client
_connect_lock = asyncio.Lock()  # ★接続直列化ロック

# ---- Downstream: payload→1/0 ----
def parse_onoff(s: str):
    p = s.strip().lower()
    if p in ("1","true","on"):
        return 1
    if p in ("0","false","off"):
        return 0
    try:
        data = json.loads(s)
        if isinstance(data, dict) and "on" in data:
            return 1 if data["on"] else 0
    except Exception:
        pass
    return None

# ---- MQTT ----
def on_connect(client, userdata, flags, rc, properties=None):
    print(f"[MQTT] connected rc={rc}")
    client.subscribe(DOWN_TOPIC, qos=1)
    print(f"[MQTT] subscribed {DOWN_TOPIC}")

def on_message(client, userdata, msg):
    global BLE_CLIENT, MAIN_LOOP
    val = parse_onoff(msg.payload.decode(errors="ignore"))
    if val is None:
        print("[MQTT] ignore payload:", msg.payload)
        return
    if not (BLE_CLIENT and BLE_CLIENT.is_connected):  # ★propertyでOK
        print("[BLE] not ready, skip write:", val)
        return
    fut = asyncio.run_coroutine_threadsafe(
        # Linux/BlueZは response=True のほうが安定することが多い
        BLE_CLIENT.write_gatt_char(PUMP_CHAR_UUID, bytearray([val]), response=True),
        MAIN_LOOP
    )
    try:
        fut.result(timeout=2.0)
        print("[DOWN] BLE write OK:", val)
    except Exception as e:
        print("[DOWN] BLE write NG:", e)

def build_mqtt():
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except Exception:
        client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    return client

def mqtt_start():
    global MQTTC
    MQTTC = build_mqtt()
    MQTTC.connect(BROKER_ADDRESS, PORT, 60)
    MQTTC.loop_start()
    print("[MQTT] loop started")

def mqtt_stop():
    MQTTC.loop_stop()
    MQTTC.disconnect()
    print("[MQTT] stopped")

def mqtt_pub(d: dict):
    MQTTC.publish(UP_TOPIC, json.dumps(d), qos=1)

# ---- BLE ----
async def find_device():
    # 1) 既知MACで素早く
    if DEVICE_ADDRESS:
        dev = await BleakScanner.find_device_by_address(DEVICE_ADDRESS, timeout=6.0)
        if dev:
            return dev
    # 2) 見つからなければ名前で（RPA対策）
    print("[BLE] Address not found, falling back to name scan...")
    return await BleakScanner.find_device_by_filter(
        lambda d, ad: (d.name is not None and DEVICE_NAME in d.name),
        timeout=10.0
    )

def on_notify(_sender, data: bytearray):
    try:
        raw = int.from_bytes(data, "little", signed=False)
    except Exception:
        raw = data[0] if data else 0
    payload = {"device": DEVICE_ID, "timestamp": int(time.time()), "soil_raw": raw}
    mqtt_pub(payload)
    print("[UP ] Published:", payload)

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

            print(f"[BLE] connecting to {getattr(device,'address',device)}")

            # ★接続は直列化（Operation already in progress 回避）
            async with _connect_lock:
                # ★ここで作るクライアントに disconnected_callback を付ける
                disconnected_future = asyncio.get_running_loop().create_future()

                def handle_disconnect(_client):
                    if not disconnected_future.done():
                        disconnected_future.set_result(True)
                    print(f"[BLE] disconnected: {getattr(_client,'address','?')}")

                async with BleakClient(device, timeout=20.0,
                    disconnected_callback=handle_disconnect) as client:
                    if not client.is_connected:
                        print("[BLE] connect failed, retry")
                        await asyncio.sleep(3)
                        continue

                    BLE_CLIENT = client
                    print("[BLE] connected:", getattr(client, "address", "?"))

                    # ★get_services()は不要。必要なら client.services を参照

                    print(f"[BLE] start notify {SOIL_CHAR_UUID}")
                    await client.start_notify(SOIL_CHAR_UUID, on_notify)

                    stop_task = asyncio.create_task(stop_event.wait())
                    # ★どちらかが完了したら抜ける
                    done, pending = await asyncio.wait(
                        {disconnected_future, stop_task},
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    # 後片付け
                    try:
                        await client.stop_notify(SOIL_CHAR_UUID)
                    except Exception:
                        pass

            BLE_CLIENT = None
            if stop_event.is_set():
                break
            await asyncio.sleep(2)  # backoff
        except Exception as e:
            print("[BLE] error:", e)
            BLE_CLIENT = None
            await asyncio.sleep(3)
    print("[BLE] loop exit")

# ---- main ----
async def main():
    global MAIN_LOOP
    MAIN_LOOP = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            MAIN_LOOP.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    mqtt_start()
    task = asyncio.create_task(ble_loop(stop_event))
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
