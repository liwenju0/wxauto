[![wxauto](https://github.com/cluic/wxauto/blob/WeChat3.9.11/utils/wxauto.png)](https://docs.wxauto.org)
# wxauto  (适用PC微信3.9.11.17版本）

### 欢迎指出bug，欢迎pull requests

Windows版本微信客户端自动化，可实现简单的发送、接收微信消息、保存聊天图片

**3.9.11.17版本微信安装包下载**：
[点击下载](https://github.com/tom-snow/wechat-windows-versions/releases/download/v3.9.11.17/WeChatSetup-3.9.11.17.exe)

**文档**：
[使用文档](https://docs.wxauto.org) |
[云服务器wxauto部署指南](https://docs.wxauto.org/other/deploy)

|  环境  | 版本 |
| :----: | :--: |
|   OS   | [![Windows](https://img.shields.io/badge/Windows-10\|11\|Server2016+-white?logo=windows&logoColor=white)](https://www.microsoft.com/)  |
|  微信  | [![Wechat](https://img.shields.io/badge/%E5%BE%AE%E4%BF%A1-3.9.11.X-07c160?logo=wechat&logoColor=white)](https://pan.baidu.com/s/1FvSw0Fk54GGvmQq8xSrNjA?pwd=vsmj) |
| Python | [![Python](https://img.shields.io/badge/Python-3.X-blue?logo=python&logoColor=white)](https://www.python.org/) **(不支持3.7.6和3.8.1)**|



[![Star History Chart](https://api.star-history.com/svg?repos=cluic/wxauto&type=Date)](https://star-history.com/#cluic/wxauto)

## 获取wxauto
cmd窗口：
```shell
pip install wxauto
```
python窗口：
```python
>>> import wxauto
>>> wxauto.VERSION
'3.9.11.17'
>>> wx = wxauto.WeChat()
初始化成功，获取到已登录窗口：xxx
```


## 示例
> [!NOTE]
> 如有问题请先查看[使用文档](https://docs.wxauto.org)

**请先登录PC微信客户端**

```python
from wxauto import *


# 获取当前微信客户端
wx = WeChat()


# 获取会话列表
wx.GetSessionList()

# 向某人发送消息（以`文件传输助手`为例）
msg = '你好~'
who = '文件传输助手'
wx.SendMsg(msg, who)  # 向`文件传输助手`发送消息：你好~


# 向某人发送文件（以`文件传输助手`为例，发送三个不同类型文件）
files = [
    'D:/test/wxauto.py',
    'D:/test/pic.png',
    'D:/test/files.rar'
]
who = '文件传输助手'
wx.SendFiles(filepath=files, who=who)  # 向`文件传输助手`发送上述三个文件


# 下载当前聊天窗口的聊天记录及图片
msgs = wx.GetAllMessage(savepic=True)   # 获取聊天记录，及自动下载图片
```
## 朋友圈定时抓取

项目包含一个朋友圈自动抓取工具，由 `moments_scraper.py`（主逻辑）和 `moments_ui.py`（UI 交互）组成。

### 启动抓取

因为微信运行在 **Session 1**（桌面会话），而我们通常从 Session 0 或远程连接操作，所以需要通过 **Windows 计划任务** 在正确的会话中执行脚本：

```shell
schtasks /Run /TN "MomentsExplore"
```

- `schtasks` — Windows 自带的**计划任务命令行工具**，用于创建、查询、运行和管理系统中的计划任务
- `/Run` — 立即运行指定的计划任务（不用等到预定时间）
- `/TN "MomentsExplore"` — 指定任务名称（Task Name），这里是预先创建好的 `MomentsExplore` 任务

该任务会在 Session 1 中启动 `run_explore.bat`，进而执行 `moments_scraper.py`，自动滚动朋友圈、解析内容、保存图片到 `moments_data/` 目录。

### 首次创建计划任务

如果系统中还没有 `MomentsExplore` 任务（比如新环境部署），需要先创建：

```shell
schtasks /Create /TN "MomentsExplore" /TR "C:\Users\Docker\Desktop\wxauto\run_explore.bat" /SC ONCE /ST 00:00 /RU Docker /IT /F
```

| 参数 | 含义 |
|---|---|
| `/Create` | 创建一个新的计划任务 |
| `/TN "MomentsExplore"` | 任务名称 |
| `/TR "...\run_explore.bat"` | 要执行的脚本路径 |
| `/SC ONCE /ST 00:00` | 调度类型设为"一次性"，不自动触发，仅通过 `/Run` 手动启动 |
| `/RU Docker` | 以 `Docker` 用户身份运行 |
| `/IT` | **Interactive Token**，任务在用户的交互式桌面会话（Session 1）中运行，这样才能操控微信窗口 |
| `/F` | 同名任务已存在时覆盖 |

> **为什么需要计划任务？** 微信窗口运行在桌面会话（Session 1），而通过 SSH/远程连接进来的终端通常在 Session 0。直接在 Session 0 执行 UI 自动化脚本无法操控 Session 1 的窗口。计划任务加 `/IT` 参数可以让脚本在 Session 1 中运行，从而正常操控微信。

### 其他常用命令

```shell
# 查看任务是否存在及其状态
schtasks /Query /TN "MomentsExplore"

# 停止正在运行的抓取进程
taskkill /F /IM python.exe
```

### 数据存储

抓取的数据保存在 `moments_data/` 目录下：
- `moments.json` — 所有朋友圈记录（作者、文字、时间、图片路径等）
- `checkpoint.json` — 断点信息，用于避免重复抓取
- `media/<id>/` — 每条朋友圈的图片文件
- `scraper.log` — 运行日志

## 注意事项
目前还在开发中，测试案例较少，使用过程中可能遇到各种Bug

## 交流

[微信交流群](https://wxauto.loux.cc/docs/intro#-%E4%BA%A4%E6%B5%81)

## 最后
如果对您有帮助，希望可以帮忙点个Star，如果您正在使用这个项目，可以将右上角的 Unwatch 点为 Watching，以便在我更新或修复某些 Bug 后即使收到反馈，感谢您的支持，非常感谢！

## 免责声明
代码仅用于对UIAutomation技术的交流学习使用，禁止用于实际生产项目，请勿用于非法用途和商业用途！如因此产生任何法律纠纷，均与作者无关！



