# v0.3.0 演示素材包

目标时长：2 分 35 秒。演示只使用空白、可丢弃的 Rhino 文档和仓库内合成 Replay，不录制真实用户身份、项目文件、密钥、终端环境变量或完整本地 Trace。

## 已准备资产

- [镜头表与中英文旁白](demo-script.md)
- [中文字幕](rhinocoder-demo.zh-CN.srt)
- [英文字幕](rhinocoder-demo.en.srt)
- [可重复生成的合成 Replay GIF](../assets/replay-demo.gif)
- [演示资产哈希清单](demo-assets-manifest.json)

GIF 是可立即公开的替代素材：来源固定为 `eval/replays/self_correction.json`，其中坐标、对象 ID、图层和模型名均为合成值。它不冒充真实 Rhino 录屏。

## 录制前检查

1. 新建空白、可丢弃的 Rhino 文档，并隐藏最近文件、用户名、文件路径与通知。
2. 启动 Listener 与 UI，运行 `python tools/doctor.py`；只展示通过/失败状态，不展示 `.env`。
3. 使用 `basic_stack.json` 和 `self_correction.json` 预演；不要加载本地真实 Trace。
4. 将浏览器设为 1440×900 左右，终端字号至少 16 px，Rhino 视口使用默认图层。
5. 录制前运行 `python tools/audit_release_data.py` 和 `python tools/check_demo_assets.py`。

## macOS 录制命令

系统交互式录屏可直接写入本地 Git 忽略目录：

```bash
mkdir -p data/demo-recordings
screencapture -v -V 155 data/demo-recordings/rhinocoder-v0.3.0.mov
```

首次运行可能要求“屏幕与系统音频录制”权限。若系统版本不支持计时参数，可使用 `Shift+Command+5` 开始/停止录制。录制后先人工复核每一帧可能出现的身份、路径和通知，再导出公开版本。

如果本机已有 `ffmpeg`，可烧录中文字幕并生成网页友好的 MP4；命令不会上传文件：

```bash
ffmpeg -i data/demo-recordings/rhinocoder-v0.3.0.mov \
  -vf "subtitles=docs/demo/rhinocoder-demo.zh-CN.srt" \
  -c:v libx264 -crf 20 -preset medium -pix_fmt yuv420p -an \
  data/demo-recordings/rhinocoder-v0.3.0-captioned.mp4
```

真实视频必须由项目所有者完成最终屏幕复核与录制；仓库不包含真实项目画面。未经明确授权，不上传视频、不创建 Tag 或 GitHub Release。

## GIF 再生成

生成器只接受显式声明 `synthetic` 且已经隐私复核的 Replay。Pillow 仅用于维护演示图片，不是应用运行依赖：

```bash
python tools/generate_demo_gif.py
python tools/check_demo_assets.py
```

重新生成后只有在逐帧复核通过并更新 `demo-assets-manifest.json` 的 SHA-256 后，演示资产检查才会通过。
