#!/usr/bin/env python3
import asyncio, json, time, signal
from typing import Optional
from bleak import BleakClient, BleakScanner
import paho.mqtt.client as mqtt

# ==== 設定 ====
DEVICE_NAME    = "SoilNode"
DEVICE_ADDRESS = ""
SOIL_CHAR_UUID = "19B10011-E8F2-537E-4F6C-D104768A1214"
PUMP_CHAR_UUID = "19B10012-E8F2-537E-4F6C-D104768A1214"
DEVICE_ID      = "soil-node-01"

BROKER_ADDRESS = ""
PORT           = 1883
UP_TOPIC       = "sensors/soil"
DOWN_TOPIC     = "command/pump"

# ==== グローバル ====
MAIN_LOOP: asyncio.AbstractEventLoop
BLE_CLIENT: Optional[BleakClient] = None
MQTTC: mqtt.Client

# ---- Downstream: payload→1/0 ----
def parse_onoff(s: str):
    p = s.strip().lower()
    if p in ("1","true","on"):  return 1
    if p in ("0","false","off"): return 0
    try:
        j = json.loads(s)
        if isinstance(j, dict) and "on" in j: return 1 if j["on"] else 0
    except Exception: pass
    return None

# ---- MQTT ----
def build_mqtt():
    try:
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except Exception:
        c = mqtt.Client()  # fallback
    def on_connect(cli, u, flags, rc, properties=None):
        print(f"[MQTT] connected rc={rc}")
        cli.subscribe(DOWN_TOPIC, qos=1)
        print(f"[MQTT] subscribed {DOWN_TOPIC}")
    def on_message(cli, u, msg):
        global BLE_CLIENT, MAIN_LOOP
        val = parse_onoff(msg.payload.decode(errors="ignore"))
        if val is None:
            print("[MQTT] ignore payload:", msg.payload)
            return
        if not (BLE_CLIENT and BLE_CLIENT.is_connected):
            print("[BLE] not ready, skip write:", val)
            return
        fut = asyncio.run_coroutine_threadsafe(
            BLE_CLIENT.write_gatt_char(PUMP_CHAR_UUID, bytearray([val]), response=False),
            MAIN_LOOP
        )
        try:
            fut.result(timeout=2.0)
            print("[DOWN] BLE write OK:", val)
        except Exception as e:
            print("[DOWN] BLE write NG:", e)
    c.on_connect = on_connect
    c.on_message = on_message
    return c

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
    if DEVICE_NAME:
        dev = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=6)
        if dev: return dev
    if DEVICE_ADDRESS:
        dev = await BleakScanner.find_device_by_address(DEVICE_ADDRESS, timeout=6)
        if dev: return dev
    return None

async def ble_loop(stop_evt: asyncio.Event):
    global BLE_CLIENT
    while not stop_evt.is_set():
        try:
            print("[BLE] scanning...")
            dev = await find_device()
            if not dev:
                print("[BLE] device not found. retry in 5s")
                await asyncio.sleep(5)
                continue
            print(f"[BLE] connecting to {getattr(dev,'address',dev)}")
            async with BleakClient(dev, timeout=20.0) as client:
                if not client.is_connected:
                    print("[BLE] connect failed, retry")
                    await asyncio.sleep(3); continue
                BLE_CLIENT = client
                disc_fut = asyncio.get_running_loop().create_future()
                client.set_disconnected_callback(lambda _: (not disc_fut.done()) and disc_fut.set_result(True))
                print("[BLE] connected:", client.address)

                def on_notify(_sender, data: bytearray):
                    try:
                        raw = int.from_bytes(data, "little", signed=False)
                    except Exception:
                        raw = data[0] if data else 0
                    payload = {"device": DEVICE_ID, "timestamp": int(time.time()), "soil_raw": raw}
                    mqtt_pub(payload)
                    print("[UP ] Published:", payload)

                print(f"[BLE] start notify {SOIL_CHAR_UUID}")
                await client.start_notify(SOIL_CHAR_UUID, on_notify)

                done, _ = await asyncio.wait({disc_fut, stop_evt.wait()}, return_when=asyncio.FIRST_COMPLETED)
                try: await client.stop_notify(SOIL_CHAR_UUID)
                except Exception: pass

            if stop_evt.is_set(): break
            await asyncio.sleep(2)  # backoff
        except Exception as e:
            print("[BLE] error:", e)
            await asyncio.sleep(3)
    print("[BLE] loop exit")

# ---- main ----
async def main():
    global MAIN_LOOP
    MAIN_LOOP = asyncio.get_running_loop()
    stop_evt = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try: MAIN_LOOP.add_signal_handler(sig, stop_evt.set)
        except NotImplementedError: pass

    mqtt_start()
    task = asyncio.create_task(ble_loop(stop_evt))
    await stop_evt.wait()
    task.cancel()
    try: await task
    except asyncio.CancelledError: pass
    mqtt_stop()
    print("[MAIN] bye")

if __name__ == "__main__":
    asyncio.run(main())
