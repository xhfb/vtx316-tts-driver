#!/usr/bin/env python3
"""依次用各发音人播报：编号 + 名称，便于对比听感.

用法::
    python3 demo_voices.py
    python3 demo_voices.py --volume 8
    python3 demo_voices.py --only 3,51,55
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from vtx316 import DEFAULT_BAUD, DEFAULT_PORT, Reply, VTX316

# 资料 §7：发音人选择 [m*]
VOICES: list[tuple[int, str]] = [
    (3, "晓玲"),
    (51, "尹小坚"),
    (52, "易小强"),
    (53, "田蓓蓓"),
    (54, "唐老鸭"),
    (55, "小燕子"),
    (56, "贝童"),
    (57, "晓可"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="VTX316 全部发音人试听")
    ap.add_argument("--port", default=DEFAULT_PORT)
    ap.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    ap.add_argument("--volume", type=int, default=8, help="音量 0~10")
    ap.add_argument("--speed", type=int, default=None, help="语速 0~30")
    ap.add_argument("--gap", type=float, default=0.6, help="两条之间额外间隔秒")
    ap.add_argument(
        "--only",
        default="",
        help="只测指定编号，逗号分隔，如 3,51,55",
    )
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    only: set[int] | None = None
    if args.only.strip():
        only = {int(x) for x in args.only.split(",") if x.strip()}

    voices = [(vid, name) for vid, name in VOICES if only is None or vid in only]
    if not voices:
        print("没有匹配的发音人", file=sys.stderr)
        return 1

    try:
        tts = VTX316(port=args.port, baudrate=args.baud)
    except Exception as e:
        print(f"打开串口失败: {e}", file=sys.stderr)
        return 1

    try:
        tts.wake(timeout=0.5)
        print(f"共 {len(voices)} 个发音人，音量={args.volume}")
        for i, (vid, name) in enumerate(voices, 1):
            # 读出编号和发音人名称，便于对照
            text = f"编号{vid}，发音人{name}"
            print(f"[{i}/{len(voices)}] [m{vid}] {name} → {text}")
            ack = tts.speak(
                text,
                voice=vid,
                volume=args.volume,
                speed=args.speed,
            )
            if ack == Reply.CMD_FAIL:
                print(f"  失败 0x45，跳过")
                continue
            if not tts.wait_idle(timeout=30):
                print("  等待超时，停止后继续")
                tts.stop()
                time.sleep(0.2)
            if args.gap > 0:
                time.sleep(args.gap)
        print("全部播完")
    finally:
        tts.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
