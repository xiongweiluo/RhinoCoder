# v0.3.0 演示素材包

目标时长：2 分 35 秒。演示只使用空白、可丢弃的 Rhino 文档和仓库内合成 Replay，不录制真实用户身份、项目文件、密钥、终端环境变量或完整本地 Trace。

## 已准备资产

- [镜头表与中英文旁白](demo-script.md)
- [中文字幕](rhinocoder-demo.zh-CN.srt)
- [英文字幕](rhinocoder-demo.en.srt)
- [可重复生成的合成 Replay GIF](../assets/replay-demo.gif)
- [真实 Rhino 单窗口证据短片](../assets/rhinocoder-real-rhino-demo.mov)
- [真实 Rhino 结果帧](../assets/rhinocoder-real-rhino-result.png)
- [演示资产哈希清单](demo-assets-manifest.json)
- [P1 三个固定演示场景清单](p1-scenarios.json)
- [P1 招聘者演示链路验收](../p1-recruiter-demo.md)

GIF 的来源固定为 `eval/replays/self_correction.json`，其中坐标、对象 ID、图层和模型名均为合成值。真实 Rhino 短片则来自空白可丢弃文档中的真实执行，明确标注为执行前/后单窗口帧序列；两类素材不混淆。

真实短片为 15 秒、1280×720、无音频 H.264 MOV。发布前抽查执行前、转场、执行后多个时间点，并核对源帧：只包含 Rhino 窗口、任务结果和最小化运行编号，不包含桌面、身份、通知、文件路径、密钥或真实项目数据。资产清单锁定其 SHA-256、时长、尺寸和隐私复核声明。

无需录屏即可使用三个公开只读入口：`/?demo=normal-loop&mode=replay`、`/?demo=self-correction&mode=replay`、`/?demo=privacy-route&mode=replay`。这些页面只发 GET，不建立 WebSocket，也不会触发 Rhino、模型或反馈写入。浏览器端到端验收命令：

```bash
npm run build --prefix agent/ui
npm run test:e2e --prefix agent/ui
python tools/check_ui_performance.py
python tools/audit_p1_demo.py
```

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

真实单窗口短片已在项目所有者授权下完成并进入仓库；它是隐私安全的证据短片，不宣称为连续桌面操作录屏。任何未来更长版本仍必须逐帧复核，未经明确授权不得上传新素材或创建新版本发布。

## GIF 再生成

生成器只接受显式声明 `synthetic` 且已经隐私复核的 Replay。Pillow 仅用于维护演示图片，不是应用运行依赖：

```bash
python tools/generate_demo_gif.py
python tools/check_demo_assets.py
```

重新生成后只有在逐帧复核通过并更新 `demo-assets-manifest.json` 的 SHA-256 后，演示资产检查才会通过。
