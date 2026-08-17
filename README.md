# VTX316 TTS 语音合成模块 · Python 驱动

宇音天下 **VTX316** 串口文字转语音（TTS）模块驱动，兼容 SYN6658 / SYN6288 类串口协议。  
在 **RDK X5（sunrise）** 上默认使用 `/dev/ttyS6` @ **115200** 实测通过，也可用于其它 Linux 板卡的 TTL 串口。

---

## 购买链接（请注明）

模块淘宝购买页（VTX316 TTS 语音模块 / 文字转语音合成芯片，兼容 SYN6658、6288 串口协议）：

- **短链直达：** https://e.tb.cn/h.8iObjVH9gQlGIFU?tk=h0EGTYnhQ32  
- 口令：`CZ321`  
- 搜索关键词：`VTX316TTS语音模块文字转语音合成芯片兼容SYN6658\6288串口协议`

> 商品页标注「7 天无理由退货」。链接失效时请用关键词在淘宝重新搜索「VTX316 TTS」。

---

## 功能特性

- UART 帧协议：`0xFD` + 长度(2B 大端) + 命令字 + [编码] + [文本]
- 合成播报 / 停止 / 暂停 / 恢复
- 忙闲查询、播完等待、唤醒 / 深睡、版本查询
- 发音人、音量、语速、语调等控制标记便捷封装
- UTF-8 / GBK / GB2312 / Unicode 编码可选

---

## 硬件接线

板载 **3W 功放**，喇叭直接接 `SP+` / `SP-`（建议 8Ω、≤3W）。

| 模块引脚 | 定义 | 接到板端 |
|----------|------|----------|
| 11 | TXD | 串口 RX（RDK：`ttyS6` RX） |
| 10 | RXD | 串口 TX（RDK：`ttyS6` TX） |
| 09 | VCC | **5V** |
| 08 | GND | GND（与板共地） |
| 07 | SP- | 喇叭负极 |
| 06 | SP+ | 喇叭正极 |
| 01 / 02 | BAUD0 / BAUD1 | 可不接（悬空默认 **115200**） |
| 03 | AO | 可选，外接更大功放 |
| 04 | R/B | 可选，忙闲电平（低=空闲） |
| 05 | RESET | 可不接 |

**波特率硬件配置（BAUD0 / BAUD1）：**

| BAUD0 | BAUD1 | 波特率 |
|-------|-------|--------|
| 0 | 0 | 4800 |
| 0 | 1 | 9600 |
| 1 | 0 | 57600 |
| 1 | 1 | 115200（默认） |

---

## 环境依赖

```bash
pip3 install pyserial
# 或
pip3 install -r requirements.txt
```

- Python 3.8+
- 串口设备权限：RDK 上用户 `sunrise` 一般已在 `dialout` 组；否则：

```bash
sudo usermod -aG dialout $USER   # 重新登录后生效
# 或临时：
sudo chmod 666 /dev/ttyS6
```

---

## 快速开始

```bash
git clone https://github.com/xhfb/vtx316-tts-driver.git
cd vtx316-tts-driver

# 默认播报自检
python3 demo.py

# 自定义文案 / 发音人 / 音量
python3 demo.py --text "发现火情，请注意" --voice 51 --volume 8

# 依次试听全部发音人
python3 demo_voices.py
python3 demo_voices.py --only 3,51,55
```

指定其它串口：

```bash
python3 demo.py --port /dev/ttyUSB0 --baud 115200
```

驱动自检：

```bash
python3 vtx316.py --text "你好，宇音天下语音合成模块测试成功"
```

---

## API 示例

```python
from vtx316 import VTX316, VOICE_XIAOLING, VOICE_YINXIAOJIAN

with VTX316("/dev/ttyS6") as tts:
    tts.speak("你好，消防机器人已就绪", voice=VOICE_XIAOLING, volume=8)
    tts.wait_idle()

    tts.speak("检测到火源，开始灭火", voice=VOICE_YINXIAOJIAN, volume=9)
    tts.wait_idle()

    tts.stop()
    # tts.pause() / tts.resume()
    # tts.query_status()   # 0x4E 忙 / 0x4F 闲
    # tts.wake() / tts.deep_sleep()
```

也可在文本中直接内嵌控制标记：

```python
tts.speak("[m3][v8][s5]你好[p500]世界")
```

### 常用发音人 `[m*]`

| 编号 | 名称 |
|------|------|
| 3 | 晓玲（女声，默认） |
| 51 | 尹小坚（男声） |
| 52 | 易小强（男声） |
| 53 | 田蓓蓓（女声） |
| 54 | 唐老鸭（效果器） |
| 55 | 小燕子（女童声） |
| 56 | 贝童（男童声） |
| 57 | 晓可（男童声） |

更多标记（语速 `[s*]`、语调 `[t*]`、音量 `[v*]`、静音 `[p*]` 等）见 [`docs/VTX316_taobao_manual.md`](docs/VTX316_taobao_manual.md)。

---

## 仓库结构

```text
vtx316-tts-driver/
├── README.md           # 本说明（含购买链接）
├── requirements.txt
├── vtx316.py           # 驱动主库
├── demo.py             # 快速试播
├── demo_voices.py      # 全部发音人试听
└── docs/
    └── VTX316_淘宝资料.md   # 淘宝图文资料整理版
```

---

## 协议摘要

**合成命令帧：**

| 帧头 | 数据长度 | 命令字 | 编码 | 文本 |
|------|----------|--------|------|------|
| `0xFD` | 2 字节大端 | `0x01` | `0x00` GB2312 / `0x01` GBK / `0x05` UTF-8 … | 文本字节 |

示例（GBK「宇音天下」）：

```text
FD 00 0A 01 01 D3 EE D2 F4 CC EC CF C2
```

**部分回传：** `0x4A` 初始化/唤醒成功 · `0x41` 命令成功 · `0x45` 命令失败 · `0x4E` 播音中 · `0x4F` 空闲

---

## 故障排查

| 现象 | 排查 |
|------|------|
| 打开串口失败 | 检查 `--port`、权限、是否被其它进程占用 |
| 合成回 `0x45` / 无声 | 核对波特率是否与 BAUD 脚一致；TX/RX 是否交叉；是否共地 |
| 有 ACK 无声 | 检查喇叭接 `SP+/SP-`、5V 供电电流是否够（建议 ≥500mA） |
| 深睡后无声 | 先调用 `tts.wake()` |

---

## 许可证

MIT License（见 [LICENSE](LICENSE)）

## 致谢

- 芯片/模块：宇音天下 VTX316  
- 协议与引脚资料整理自淘宝商品说明书截图  
- 实测平台：RDK X5（`dz-03` / `/home/sunrise/ttl_voice`）
