import os, json, time, uuid, hmac, hashlib
import paho.mqtt.client as mqtt

SID    = "53cf4a5803c91726b892e5d0785085c6"
KEY_PATH = os.path.expanduser("~/arenabridge/arenabridge.key")
KEY    = open(KEY_PATH).read().strip() if os.path.exists(KEY_PATH) else ""
BROKER = "broker.emqx.io"
PORT   = 1883
TOPIC_CMD  = f"arenabridge/{SID}/cmd"
TOPIC_RES  = f"arenabridge/{SID}/res"

def sign_payload(data_dict):
    d_str = json.dumps(data_dict, separators=(',', ':'))
    h = hmac.new(KEY.encode(), d_str.encode(), hashlib.sha256).hexdigest()
    return json.dumps({"d": d_str, "h": h})

def verify_and_unpack(raw_bytes):
    try:
        raw = json.loads(raw_bytes.decode())
        d_str = raw.get("d", "")
        return json.loads(d_str)
    except: return None

def get_client(client_id=None):
    client_id = client_id or f"arena_agent_{uuid.uuid4().hex[:6]}"
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    client.connect(BROKER, PORT, keepalive=60)
    client.loop_start()
    return client, {"sid": SID, "key": KEY, "topic_cmd": TOPIC_CMD, "topic_res": TOPIC_RES}

def req_res(client, cfg, payload, timeout=30):
    req_id = "req_" + uuid.uuid4().hex[:6]
    payload["id"] = req_id
    payload["ts"] = time.time()
    response_data = None
    done = False
    def on_message(c, u, msg):
        nonlocal done, response_data
        if msg.topic == TOPIC_RES:
            data = verify_and_unpack(msg.payload)
            if data and data.get("id") == req_id:
                response_data = data
                done = True
    client.subscribe(TOPIC_RES, qos=1)
    client.on_message = on_message
    client.publish(TOPIC_CMD, sign_payload(payload), qos=1)
    start = time.time()
    while not done and (time.time() - start) < timeout:
        time.sleep(0.05)
    client.unsubscribe(TOPIC_RES)
    if not done:
        return {"error": "timeout", "exit_code": -1, "output": "", "stderr": f"Timed out after {timeout}s"}
    return response_data

def exec_remote(cmd, timeout=30):
    client, cfg = get_client()
    res = req_res(client, cfg, {"op": "exec", "cmd": cmd}, timeout=timeout)
    client.loop_stop()
    client.disconnect()
    return res
