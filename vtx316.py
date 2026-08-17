#!/usr/bin/env python3
"""宇音天下 VTX316 语音合成模块驱动.

协议来源：淘宝资料 ``VTX316_淘宝资料.md``。
默认串口 ``/dev/ttyS6``，波特率 115200（BAUD0/BAUD1 未接时的常用默认）。

接线（本项目实测）::
    模块 SP+ / SP- → 喇叭
    模块 VCC(5V) / GND → 电源
    模块 TXD → 板端 RX
    模块 RXD → 板端 TX

帧格式::
    0xFD | 长度(2字节大端) | 命令字 | [编码] | [文本…]

长度字段 = 命令字及之后全部字节数。
"""

from __future__ import annotations

import logging
import threading
import time
from enum import IntEnum
from typing import Optional

import serial

logger = logging.getLogger(__name__)

DEFAULT_PORT = "/dev/ttyS6"
DEFAULT_BAUD = 115200
MAX_TEXT_BYTES = 4000


class Encoding(IntEnum):
    """合成文本编码格式."""

    GB2312 = 0x00
    GBK = 0x01
    UNICODE_LE = 0x03
    UNICODE_BE = 0x04
    UTF8 = 0x05


class Cmd(IntEnum):
    """控制命令字."""

    SYNTHESIZE = 0x01
    STOP = 0x02
    PAUSE = 0x03
    RESUME = 0x04
    QUERY_STATUS = 0x21
    SLEEP = 0x22
    DEEP_SLEEP = 0x88
    QUERY_VERSION = 0x58
    WAKE = 0xFF


class Reply(IntEnum):
    """模块回传字节."""

    INIT_OR_WAKE_OK = 0x4A
    CMD_OK = 0x41
    CMD_FAIL = 0x45
    DEEP_SLEEP_OK = 0x4B
    BUSY = 0x4E
    IDLE = 0x4F
    VERSION = 0x58


# 常用发音人（文本控制标记 [m*]）
VOICE_XIAOLING = 3       # 晓玲（女声，默认）
VOICE_YINXIAOJIAN = 51   # 尹小坚（男声）
VOICE_YIXIAOQIANG = 52   # 易小强（男声）
VOICE_TIANBEIBEI = 53    # 田蓓蓓（女声）
VOICE_TANG_LAOYA = 54    # 唐老鸭（效果器）
VOICE_XIAOYANZI = 55     # 小燕子（女童声）
VOICE_BEITONG = 56       # 贝童（男童声）
VOICE_XIAOKE = 57        # 晓可（男童声）


class VTX316:
    """VTX316 TTS 驱动.

    使用示例::

        with VTX316("/dev/ttyS6") as tts:
            tts.speak("你好，消防机器人已就绪")
            tts.wait_idle()
            tts.stop()
    """

    def __init__(
        self,
        port: str = DEFAULT_PORT,
        baudrate: int = DEFAULT_BAUD,
        timeout: float = 0.2,
        encoding: Encoding = Encoding.UTF8,
        open_port: bool = True,
    ):
        """初始化驱动.

        Args:
            port: 串口设备路径
            baudrate: 波特率（BAUD 脚未接时一般为 115200）
            timeout: 串口读超时（秒）
            encoding: 默认文本编码（推荐 UTF8）
            open_port: 是否立即打开串口
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.encoding = encoding
        self._ser: Optional[serial.Serial] = None
        self._lock = threading.Lock()
        self._rx_buf = bytearray()
        if open_port:
            self.open()

    # ── 生命周期 ──────────────────────────────────────────────────────────

    def open(self) -> None:
        """打开串口并清空缓冲."""
        if self._ser is not None and self._ser.is_open:
            return
        self._ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
        )
        time.sleep(0.05)
        self._ser.reset_input_buffer()
        self._ser.reset_output_buffer()
        self._rx_buf.clear()
        logger.info("VTX316 已打开 %s @ %d", self.port, self.baudrate)

    def close(self) -> None:
        """关闭串口."""
        if self._ser is not None:
            try:
                if self._ser.is_open:
                    self._ser.close()
            finally:
                self._ser = None
            logger.info("VTX316 已关闭")

    def __enter__(self) -> "VTX316":
        if self._ser is None or not self._ser.is_open:
            self.open()
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    @property
    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open

    # ── 帧构造 / 收发 ─────────────────────────────────────────────────────

    @staticmethod
    def _build_frame(payload: bytes) -> bytes:
        """payload = 命令字及之后字节；长度字段为 payload 长度."""
        if not payload:
            raise ValueError("payload 不能为空")
        length = len(payload)
        if length > 0xFFFF:
            raise ValueError(f"帧过长: {length}")
        return bytes([0xFD, (length >> 8) & 0xFF, length & 0xFF]) + payload

    def _ensure_open(self) -> serial.Serial:
        if self._ser is None or not self._ser.is_open:
            raise RuntimeError("串口未打开，请先调用 open()")
        return self._ser

    def _write(self, frame: bytes) -> None:
        ser = self._ensure_open()
        with self._lock:
            ser.write(frame)
            ser.flush()
            logger.debug("TX: %s", frame.hex(" "))

    def _read_available(self) -> bytes:
        ser = self._ensure_open()
        n = ser.in_waiting
        if n:
            data = ser.read(n)
            self._rx_buf.extend(data)
            return data
        # 阻塞读至少 1 字节（受 timeout 限制），避免空转
        data = ser.read(1)
        if data:
            self._rx_buf.extend(data)
        return data

    def _drain(self, duration: float = 0.05) -> bytes:
        """短暂拉取串口数据到内部缓冲，返回本次新读到的字节."""
        deadline = time.monotonic() + duration
        got = bytearray()
        while time.monotonic() < deadline:
            chunk = self._read_available()
            if chunk:
                got.extend(chunk)
            else:
                time.sleep(0.01)
        return bytes(got)

    def _wait_reply(
        self,
        expect: Optional[set[int]] = None,
        timeout: float = 1.0,
    ) -> Optional[int]:
        """等待单个回传字节.

        Args:
            expect: 期望的回传集合；None 表示任意已知回传
            timeout: 超时秒数

        Returns:
            匹配到的回传字节，超时返回 None
        """
        known = {
            Reply.INIT_OR_WAKE_OK,
            Reply.CMD_OK,
            Reply.CMD_FAIL,
            Reply.DEEP_SLEEP_OK,
            Reply.BUSY,
            Reply.IDLE,
            Reply.VERSION,
        }
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._read_available()
            while self._rx_buf:
                b = self._rx_buf.pop(0)
                logger.debug("RX: 0x%02X", b)
                if expect is not None:
                    if b in expect:
                        return b
                    continue
                if b in known:
                    return b
            time.sleep(0.01)
        return None

    def send_raw(self, payload: bytes, wait_ack: bool = False, timeout: float = 1.0) -> Optional[int]:
        """发送原始 payload（不含帧头/长度），可选等待 ACK."""
        frame = self._build_frame(payload)
        with self._lock:
            # 发送前清一下陈旧回传，避免误判
            ser = self._ensure_open()
            if ser.in_waiting:
                ser.read(ser.in_waiting)
            self._rx_buf.clear()
            ser.write(frame)
            ser.flush()
            logger.debug("TX: %s", frame.hex(" "))
        if not wait_ack:
            return None
        return self._wait_reply(timeout=timeout)

    # ── TTS 合成 ──────────────────────────────────────────────────────────

    def speak(
        self,
        text: str,
        encoding: Optional[Encoding] = None,
        voice: Optional[int] = None,
        volume: Optional[int] = None,
        speed: Optional[int] = None,
        pitch: Optional[int] = None,
        wait_ack: bool = True,
        timeout: float = 1.0,
    ) -> Optional[int]:
        """合成并播放文本（可打断当前播报）.

        Args:
            text: 待合成文本；可内嵌控制标记，如 ``[m3][v8]你好``
            encoding: 文本编码，默认用构造时的 encoding
            voice: 发音人编号，自动前置 ``[m*]``
            volume: 音量 0~10，自动前置 ``[v*]``
            speed: 语速 0~30，自动前置 ``[s*]``
            pitch: 语调 0~10，自动前置 ``[t*]``
            wait_ack: 是否等待 ``0x41`` 接收成功
            timeout: 等 ACK 超时

        Returns:
            回传字节（通常 ``0x41``），或 None
        """
        if not text:
            raise ValueError("text 不能为空")

        prefix = ""
        if voice is not None:
            prefix += f"[m{int(voice)}]"
        if volume is not None:
            if not 0 <= volume <= 10:
                raise ValueError("volume 范围 0~10")
            prefix += f"[v{int(volume)}]"
        if speed is not None:
            if not 0 <= speed <= 30:
                raise ValueError("speed 范围 0~30")
            prefix += f"[s{int(speed)}]"
        if pitch is not None:
            if not 0 <= pitch <= 10:
                raise ValueError("pitch 范围 0~10")
            prefix += f"[t{int(pitch)}]"

        full = prefix + text
        enc = encoding if encoding is not None else self.encoding
        raw = self._encode_text(full, enc)
        if len(raw) > MAX_TEXT_BYTES:
            raise ValueError(f"文本超过 {MAX_TEXT_BYTES} 字节: {len(raw)}")

        payload = bytes([Cmd.SYNTHESIZE, int(enc)]) + raw
        reply = self.send_raw(payload, wait_ack=wait_ack, timeout=timeout)
        if wait_ack and reply == Reply.CMD_FAIL:
            logger.warning("合成命令被拒 (0x45)")
        return reply

    @staticmethod
    def _encode_text(text: str, encoding: Encoding) -> bytes:
        if encoding == Encoding.UTF8:
            return text.encode("utf-8")
        if encoding == Encoding.GBK:
            return text.encode("gbk")
        if encoding == Encoding.GB2312:
            return text.encode("gb2312", errors="replace")
        if encoding == Encoding.UNICODE_LE:
            return text.encode("utf-16-le")
        if encoding == Encoding.UNICODE_BE:
            return text.encode("utf-16-be")
        raise ValueError(f"未知编码: {encoding}")

    # ── 播控 ──────────────────────────────────────────────────────────────

    def stop(self, wait_ack: bool = True, timeout: float = 1.0) -> Optional[int]:
        """停止播音."""
        return self.send_raw(bytes([Cmd.STOP]), wait_ack=wait_ack, timeout=timeout)

    def pause(self, wait_ack: bool = True, timeout: float = 1.0) -> Optional[int]:
        """暂停播音."""
        return self.send_raw(bytes([Cmd.PAUSE]), wait_ack=wait_ack, timeout=timeout)

    def resume(self, wait_ack: bool = True, timeout: float = 1.0) -> Optional[int]:
        """恢复播音."""
        return self.send_raw(bytes([Cmd.RESUME]), wait_ack=wait_ack, timeout=timeout)

    # ── 状态 / 电源 ───────────────────────────────────────────────────────

    def query_status(self, timeout: float = 1.0) -> Optional[int]:
        """查询忙闲：``0x4E`` 播音中，``0x4F`` 空闲."""
        return self.send_raw(
            bytes([Cmd.QUERY_STATUS]),
            wait_ack=True,
            timeout=timeout,
        )

    def is_busy(self, timeout: float = 1.0) -> Optional[bool]:
        """是否正在播音；查询失败返回 None."""
        st = self.query_status(timeout=timeout)
        if st == Reply.BUSY:
            return True
        if st == Reply.IDLE:
            return False
        return None

    def is_idle(self, timeout: float = 1.0) -> Optional[bool]:
        busy = self.is_busy(timeout=timeout)
        return None if busy is None else (not busy)

    def wait_idle(self, timeout: float = 60.0, poll: float = 0.15) -> bool:
        """轮询直到空闲或超时.

        优先用主动查询；同时吸收播完后的 ``0x4F`` 空闲回传。

        Returns:
            True 表示已空闲，False 表示超时
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            # 吸收异步空闲通知
            self._drain(0.02)
            while self._rx_buf:
                b = self._rx_buf.pop(0)
                if b == Reply.IDLE:
                    return True
            st = self.query_status(timeout=min(0.5, deadline - time.monotonic()))
            if st == Reply.IDLE:
                return True
            time.sleep(poll)
        return False

    def sleep(self) -> None:
        """普通睡眠（资料标注无回传）."""
        self.send_raw(bytes([Cmd.SLEEP]), wait_ack=False)

    def deep_sleep(self, timeout: float = 1.0) -> Optional[int]:
        """深度睡眠，成功回传 ``0x4B``."""
        return self.send_raw(
            bytes([Cmd.DEEP_SLEEP]),
            wait_ack=True,
            timeout=timeout,
        )

    def wake(self, timeout: float = 2.0) -> Optional[int]:
        """唤醒，成功回传 ``0x4A``."""
        return self.send_raw(bytes([Cmd.WAKE]), wait_ack=True, timeout=timeout)

    def query_version(self, timeout: float = 1.0) -> Optional[bytes]:
        """查询版本号.

        资料：命令 ``0x58``，回传以 ``0x58`` 开头。具体后续字节因固件而异，
        这里返回从收到 ``0x58`` 起短时间内收集到的原始字节。
        """
        with self._lock:
            ser = self._ensure_open()
            if ser.in_waiting:
                ser.read(ser.in_waiting)
            self._rx_buf.clear()
            frame = self._build_frame(bytes([Cmd.QUERY_VERSION]))
            ser.write(frame)
            ser.flush()

        deadline = time.monotonic() + timeout
        collected = bytearray()
        saw = False
        while time.monotonic() < deadline:
            self._read_available()
            while self._rx_buf:
                b = self._rx_buf.pop(0)
                if not saw:
                    if b == Reply.VERSION:
                        saw = True
                        collected.append(b)
                    continue
                collected.append(b)
            if saw:
                # 版本帧较短，收到首字节后再多吸一点
                extra = self._drain(0.05)
                collected.extend(extra)
                return bytes(collected)
            time.sleep(0.01)
        return bytes(collected) if collected else None

    # ── 便捷标记 ──────────────────────────────────────────────────────────

    @staticmethod
    def markers(
        voice: Optional[int] = None,
        volume: Optional[int] = None,
        speed: Optional[int] = None,
        pitch: Optional[int] = None,
        reset: bool = False,
    ) -> str:
        """生成控制标记字符串，可拼到文本前.

        Args:
            reset: True 时加入 ``[d]``（恢复默认，不含发音人）
        """
        parts: list[str] = []
        if reset:
            parts.append("[d]")
        if voice is not None:
            parts.append(f"[m{int(voice)}]")
        if volume is not None:
            parts.append(f"[v{int(volume)}]")
        if speed is not None:
            parts.append(f"[s{int(speed)}]")
        if pitch is not None:
            parts.append(f"[t{int(pitch)}]")
        return "".join(parts)


def _reply_name(code: Optional[int]) -> str:
    if code is None:
        return "超时/无回传"
    try:
        return f"0x{code:02X} ({Reply(code).name})"
    except ValueError:
        return f"0x{code:02X}"


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    import argparse

    ap = argparse.ArgumentParser(description="VTX316 语音模块自检")
    ap.add_argument("--port", default=DEFAULT_PORT)
    ap.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    ap.add_argument("--text", default="你好，宇音天下语音合成模块测试成功")
    ap.add_argument("--voice", type=int, default=None, help="发音人，如 3/51/52…")
    ap.add_argument("--volume", type=int, default=None)
    args = ap.parse_args()

    with VTX316(port=args.port, baudrate=args.baud) as tts:
        ver = tts.query_version()
        print("版本回传:", ver.hex(" ") if ver else "无")
        ack = tts.speak(args.text, voice=args.voice, volume=args.volume)
        print("合成 ACK:", _reply_name(ack))
        ok = tts.wait_idle(timeout=30)
        print("播完空闲:" if ok else "等待空闲超时", ok)
        st = tts.query_status()
        print("当前状态:", _reply_name(st))
