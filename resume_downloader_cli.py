import argparse
import sys
from getpass import getpass
from pathlib import Path

from resume_downloader_core import DownloadOptions, download_resumes, get_runtime_app_dir


def parse_args():
    parser = argparse.ArgumentParser(description="邮箱简历附件抓取工具")
    parser.add_argument(
        "--provider",
        choices=["feishu", "tencent"],
        required=True,
        help="邮箱类型：feishu 或 tencent",
    )
    parser.add_argument("--email", required=True, help="邮箱完整账号")
    parser.add_argument("--folder", default="简历库", help='目标邮箱文件夹，默认："简历库"')
    parser.add_argument("--output", default=r"D:\邮件简历库", help=r"附件保存目录，默认：D:\邮件简历库")
    parser.add_argument("--all", action="store_true", help="重新抓取全部历史附件")
    parser.add_argument("--server", default=None, help="自定义 IMAP 服务器地址")
    parser.add_argument("--port", type=int, default=None, help="自定义 IMAP 端口")
    return parser.parse_args()


def main():
    args = parse_args()
    credential = getpass("请输入邮箱客户端专用密码：")

    if not credential:
        print("客户端专用密码不能为空")
        return 1

    app_dir = get_runtime_app_dir()
    options = DownloadOptions(
        provider=args.provider,
        email_address=args.email,
        credential=credential,
        folder=args.folder,
        output_dir=Path(args.output),
        download_all=args.all,
        server=args.server,
        port=args.port,
        app_dir=app_dir,
    )

    try:
        download_resumes(options, log_callback=print)
        return 0
    except Exception as exc:
        print()
        print(f"抓取失败：{exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
