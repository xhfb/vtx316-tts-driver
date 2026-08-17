#!/usr/bin/env python3
"""VTX316 语音模块快速演示.

接线：ttyS6 + 喇叭 SP+/SP- + VCC/GND + TX/RX（其它脚可不接）

用法::
    python3 demo.py
    python3 demo.py --text "发现火情，请注意"
    python3 demo.py --voice 51 --volume 8
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from vtx316 import DEFAULT_BAUD, DEFAULT_PORT, Reply, VTX316, VOICE_XIAOLING


def main() -> int:
    ap = argparse.ArgumentParser(description="VTX316 TTS 演示")
    ap.add_argument("--port", default=DEFAULT_PORT, help="串口，默认 /dev/ttyS6")
    ap.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    ap.add_argument("--text", default="你好，消防机器人语音模块测试正常")
    ap.add_argument("--voice", type=int, default=VOICE_XIAOLING, help="发音人编号")
    ap.add_argument("--volume", type=int, default=8, help="音量 0~10")
    ap.add_argument("--speed", type=int, default=None, help="语速 0~30")
    ap.add_argument("--no-wait", action="store_true", help="发完合成命令即退出，不等播完")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        tts = VTX316(port=args.port, baudrate=args.baud)
    except Exception as e:
        print(f"打开串口失败: {e}", file=sys.stderr)
        return 1

    try:
        ver = tts.query_version()
        print("版本:", ver.hex(" ") if ver else "无回传（可忽略，继续试播）")

        # 深睡后需先唤醒；上电正常一般不必，但发一次无害
        wake = tts.wake(timeout=0.5)
        if wake == Reply.INIT_OR_WAKE_OK:
            print("唤醒成功")

        ack = tts.speak(
            args.text,
            voice=args.voice,
            volume=args.volume,
            speed=args.speed,
        )
        if ack == Reply.CMD_OK:
            print("合成命令已接收")
        elif ack == Reply.CMD_FAIL:
            print("合成命令失败 (0x45)，检查波特率/接线")
            return 2
        else:
            print(f"合成 ACK 异常: {ack!r}（若喇叭有声可忽略）")

        if not args.no_wait:
            print("等待播完…")
            if tts.wait_idle(timeout=60):
                print("播报结束，模块空闲")
            else:
                print("等待超时")
                tts.stop()
        else:
            time.sleep(0.2)
    finally:
        tts.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
