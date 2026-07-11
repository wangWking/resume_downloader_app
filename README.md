# 邮箱简历附件抓取工具

这是面向人事同事使用的 Windows 桌面小工具，用于从邮箱的“简历库”文件夹读取邮件附件，并保存到本地目录。

## 启动 UI

在本目录打开命令行，执行：

```powershell
python resume_downloader_ui.py
```

## 使用方式

1. 在“邮箱类型”下拉框选择“飞书邮箱”或“腾讯企业邮箱”。
2. 输入邮箱账号。
3. 输入邮箱客户端专用密码。
4. 确认目标文件夹，默认是“简历库”。
5. 确认保存目录，默认是 `D:\邮件简历库`。
6. 点击“开始抓取”。

右侧日志框会显示连接、登录、扫描、下载、跳过和失败信息。

也可以先点击“测试连接”，确认邮箱类型、邮箱账号、客户端专用密码和目标文件夹都正确，再开始抓取。

## 防重复抓取

默认只抓取新增附件。工具会在 `data/downloaded.db` 中记录已下载附件：

```text
邮箱类型 + 邮箱账号 + 文件夹 + 邮件 UID + 附件序号
```

再次抓取时，已经下载过的附件会自动跳过。

如果需要重新下载全部历史附件，请勾选“重新抓取全部历史附件”。

## 密码说明

客户端专用密码只在当前打开的 UI 窗口中保留在内存里：

- 不写入代码；
- 不写入日志；
- 不写入数据库；
- 关闭 UI 后不会保存。

不关闭 UI 的情况下，可以重复点击“开始抓取”，不需要重新输入密码。

## 常见提示

- 如果选择了“飞书邮箱”，但账号实际走腾讯企业邮箱服务，测试连接或抓取时会登录失败。
- 如果邮箱类型、账号、客户端专用密码都正确，但仍然登录失败，请确认该邮箱账号已经开启 IMAP 或第三方客户端访问。
- 企业邮箱可能使用自定义域名，仅凭邮箱后缀无法稳定判断属于飞书还是腾讯，因此工具会通过实际连接登录来校验。

## 命令行调试

开发或排查问题时，也可以使用命令行：

```powershell
python resume_downloader_cli.py --provider feishu --email xxx@example.com
python resume_downloader_cli.py --provider tencent --email xxx@example.com
```

重新抓取全部历史附件：

```powershell
python resume_downloader_cli.py --provider feishu --email xxx@example.com --all
```

## 运行时文件

- `data/downloaded.db`：防重复记录数据库。
- `logs/YYYY-MM-DD.log`：运行日志。

## 打包 exe

在本目录打开命令行，执行：

```powershell
python -m PyInstaller --noconfirm --clean --onefile --windowed --name 邮箱简历附件抓取工具 --distpath D:\邮件简历抓取\resume_downloader_app\dist --workpath D:\邮件简历抓取\resume_downloader_app\build --specpath D:\邮件简历抓取\resume_downloader_app D:\邮件简历抓取\resume_downloader_app\resume_downloader_ui.py
```

生成结果：

```text
D:\邮件简历抓取\resume_downloader_app\dist\邮箱简历附件抓取工具.exe
```

如果旧 exe 正在运行或被 Windows 占用，覆盖打包可能失败。可以先关闭旧程序，或临时换一个输出名称：

```powershell
python -m PyInstaller --noconfirm --clean --onefile --windowed --name 邮箱简历附件抓取工具_新版 --distpath D:\邮件简历抓取\resume_downloader_app\dist --workpath D:\邮件简历抓取\resume_downloader_app\build --specpath D:\邮件简历抓取\resume_downloader_app D:\邮件简历抓取\resume_downloader_app\resume_downloader_ui.py
```
