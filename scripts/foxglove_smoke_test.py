#!/usr/bin/env python3
"""Check that foxglove_bridge serves the /vehicle/* topics the way Foxglove sees them.

Connects to the bridge's WebSocket like the Foxglove app does, waits for the
topics to be advertised, subscribes, and decodes a few std_msgs/Float64
messages. Exits non-zero if any topic is missing or silent.

  python3 scripts/foxglove_smoke_test.py --url ws://localhost:8765
"""

import argparse
import asyncio
import json
import struct
import sys
import time
from collections import Counter, defaultdict

import websockets

TOPICS = ['/vehicle/rpm', '/vehicle/speed', '/vehicle/pressure']
SUBPROTOCOLS = ['foxglove.sdk.v1', 'foxglove.websocket.v1']
OP_MESSAGE_DATA = 0x01


def decode_float64(payload: bytes) -> float:
    """std_msgs/Float64 in CDR: 4-byte encapsulation header, then the double."""
    little = payload[1] in (1, 3)
    return struct.unpack('<d' if little else '>d', payload[4:12])[0]


async def run(url: str, topics, min_msgs: int, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    channels = {}             # channel id -> topic
    sub_topic = {}            # subscription id -> topic
    counts = Counter()
    samples = defaultdict(list)

    # The bridge may still be starting; retry the connection until the deadline.
    while True:
        try:
            ws = await websockets.connect(url, subprotocols=SUBPROTOCOLS, max_size=None)
            break
        except OSError:
            if time.monotonic() > deadline:
                raise
            await asyncio.sleep(1)

    try:
        print(f'connected to {url} (subprotocol {ws.subprotocol})')
        while time.monotonic() < deadline:
            try:
                msg = await asyncio.wait_for(ws.recv(), deadline - time.monotonic())
            except asyncio.TimeoutError:
                break
            if isinstance(msg, str):
                op = json.loads(msg)
                if op.get('op') == 'serverInfo':
                    print(f"server: {op.get('name')}")
                elif op.get('op') == 'advertise':
                    for ch in op['channels']:
                        channels[ch['id']] = ch['topic']
                        if ch['topic'] in topics:
                            print(f"advertised {ch['topic']} [{ch.get('schemaName')}, "
                                  f"{ch.get('encoding')}]")
                missing = [t for t in topics if t not in sub_topic.values()]
                subs = []
                for cid, topic in channels.items():
                    if topic in missing:
                        sid = len(sub_topic) + 1
                        sub_topic[sid] = topic
                        subs.append({'id': sid, 'channelId': cid})
                if subs:
                    await ws.send(json.dumps({'op': 'subscribe', 'subscriptions': subs}))
            elif msg and msg[0] == OP_MESSAGE_DATA:
                sid = int.from_bytes(msg[1:5], 'little')
                topic = sub_topic.get(sid)
                if topic:
                    counts[topic] += 1
                    if len(samples[topic]) < 3:
                        samples[topic].append(round(decode_float64(msg[13:]), 2))
            if all(counts[t] >= min_msgs for t in topics):
                break
    finally:
        await ws.close()

    ok = True
    for t in topics:
        status = 'OK' if counts[t] >= min_msgs else 'FAIL'
        ok &= status == 'OK'
        print(f'{status:4} {t:<18} {counts[t]:>5} msgs  first values {samples[t]}')
    return ok


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--url', default='ws://localhost:8765')
    p.add_argument('--min-msgs', type=int, default=20)
    p.add_argument('--timeout', type=float, default=60.0)
    args = p.parse_args()
    ok = asyncio.run(run(args.url, TOPICS, args.min_msgs, args.timeout))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
