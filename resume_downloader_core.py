import base64
import email
import imaplib
import logging
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from email.header import decode_header
from pathlib import Path
from typing import Optional


IMAP_CONFIG = {
    "feishu": {
        "name": "飞书邮箱",
        "server": "imap.feishu.cn",
        "port": 993,
    },
    "tencent": {
        "name": "腾讯企业邮箱",
        "server": "imap.exmail.qq.com",
        "port": 993,
    },
}


ALLOWED_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".jpg",
    ".jpeg",
    ".png",
    ".zip",
    ".rar",
    ".7z",
}


def get_runtime_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


@dataclass
class DownloadOptions:
    provider: str
    email_address: str
    credential: str
    folder: str = "简历库"
    output_dir: Path = Path(r"D:\邮件简历库")
    download_all: bool = False
    server: Optional[str] = None
    port: Optional[int] = None
    app_dir: Optional[Path] = None


class UiLogHandler(logging.Handler):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def emit(self, record):
        if self.callback:
            self.callback(self.format(record))


def create_logger(app_dir: Path, callback=None) -> logging.Logger:
    log_dir = app_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{datetime.now():%Y-%m-%d}.log"

    logger = logging.getLogger(f"resume_downloader.{id(callback)}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s %(message)s",
        datefmt="%H:%M:%S",
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if callback:
        ui_handler = UiLogHandler(callback)
        ui_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(ui_handler)

    return logger


def init_database(app_dir: Path) -> sqlite3.Connection:
    data_dir = app_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "downloaded.db"

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS downloaded_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            email_address TEXT NOT NULL,
            folder TEXT NOT NULL,
            uid TEXT NOT NULL,
            attachment_index INTEGER NOT NULL,
            filename TEXT NOT NULL,
            saved_path TEXT NOT NULL,
            downloaded_at TEXT NOT NULL,
            UNIQUE(provider, email_address, folder, uid, attachment_index)
        )
        """
    )
    conn.commit()
    return conn


def is_downloaded(
    conn: sqlite3.Connection,
    provider: str,
    email_address: str,
    folder: str,
    uid: str,
    attachment_index: int,
) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM downloaded_attachments
        WHERE provider = ?
          AND email_address = ?
          AND folder = ?
          AND uid = ?
          AND attachment_index = ?
        LIMIT 1
        """,
        (provider, email_address, folder, uid, attachment_index),
    ).fetchone()
    return row is not None


def mark_downloaded(
    conn: sqlite3.Connection,
    provider: str,
    email_address: str,
    folder: str,
    uid: str,
    attachment_index: int,
    filename: str,
    saved_path: Path,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO downloaded_attachments (
            provider,
            email_address,
            folder,
            uid,
            attachment_index,
            filename,
            saved_path,
            downloaded_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            provider,
            email_address,
            folder,
            uid,
            attachment_index,
            filename,
            str(saved_path),
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()


def decode_mime_text(value) -> str:
    if not value:
        return ""

    result = []
    for content, charset in decode_header(value):
        if isinstance(content, bytes):
            encodings = [charset, "utf-8", "gb18030", "gbk", "latin1"]
            decoded = None
            for encoding in encodings:
                if not encoding:
                    continue
                try:
                    decoded = content.decode(encoding)
                    break
                except (UnicodeDecodeError, LookupError):
                    continue
            if decoded is None:
                decoded = content.decode("utf-8", errors="replace")
            result.append(decoded)
        else:
            result.append(content)

    return "".join(result)


def decode_imap_utf7(value: str) -> str:
    result = []
    index = 0

    while index < len(value):
        if value[index] != "&":
            result.append(value[index])
            index += 1
            continue

        end = value.find("-", index)
        if end == -1:
            result.append(value[index:])
            break

        encoded = value[index + 1:end]
        if encoded == "":
            result.append("&")
        else:
            encoded = encoded.replace(",", "/")
            padding = "=" * ((4 - len(encoded) % 4) % 4)
            raw = base64.b64decode(encoded + padding)
            result.append(raw.decode("utf-16-be"))

        index = end + 1

    return "".join(result)


def parse_folder_line(raw_line):
    line = raw_line.decode("utf-8", errors="replace").strip()
    match = re.search(r'\)\s+"[^"]*"\s+(.+)$', line)
    if not match:
        return line, line

    raw_name = match.group(1).strip()
    if raw_name.startswith('"') and raw_name.endswith('"'):
        raw_name = raw_name[1:-1]

    try:
        decoded_name = decode_imap_utf7(raw_name)
    except Exception:
        decoded_name = raw_name

    return raw_name, decoded_name


def sanitize_filename(filename: str) -> str:
    filename = filename.strip()
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", filename)
    filename = filename.rstrip(". ")
    return filename or "unnamed_attachment"


def get_unique_path(output_dir: Path, filename: str) -> Path:
    filename = sanitize_filename(filename)
    target = output_dir / filename
    if not target.exists():
        return target

    stem = target.stem
    suffix = target.suffix
    index = 1

    while True:
        new_target = output_dir / f"{stem}_{index}{suffix}"
        if not new_target.exists():
            return new_target
        index += 1


def list_mail_folders(client) -> list[dict]:
    status, folders = client.list()
    if status != "OK" or not folders:
        raise RuntimeError("获取邮箱文件夹列表失败")

    result = []
    for folder_line in folders:
        if not isinstance(folder_line, bytes):
            continue
        raw_name, decoded_name = parse_folder_line(folder_line)
        display_name = decoded_name.strip().strip('"')
        result.append({"raw_name": raw_name, "display_name": display_name})

    return result


def find_target_folder(client, target_folder: str, logger: logging.Logger):
    logger.info("邮箱服务器中的文件夹：")
    logger.info("-" * 50)

    matched_folders = []
    folders = list_mail_folders(client)

    for index, folder in enumerate(folders, start=1):
        display_name = folder["display_name"]
        normalized_name = display_name.replace("\\", "/").strip().rstrip("/")
        folder_last_name = normalized_name.split("/")[-1]
        logger.info("  [%s] %s", index, display_name)

        if folder_last_name == target_folder:
            matched_folders.append(folder)

    logger.info("-" * 50)

    if not matched_folders:
        return None

    if len(matched_folders) > 1:
        logger.info("发现多个名为“%s”的文件夹，默认使用第一个。", target_folder)
        for item in matched_folders:
            logger.info("  - %s", item["display_name"])

    return matched_folders[0]["raw_name"]


def extract_attachments(
    message,
    output_dir: Path,
    conn: sqlite3.Connection,
    options: DownloadOptions,
    uid: str,
    logger: logging.Logger,
) -> dict:
    stats = {
        "downloaded": 0,
        "duplicate_skipped": 0,
        "format_skipped": 0,
        "failed_attachments": 0,
    }

    attachment_index = 0

    for part in message.walk():
        if part.is_multipart():
            continue

        raw_filename = part.get_filename()
        if not raw_filename:
            continue

        attachment_index += 1
        filename = sanitize_filename(decode_mime_text(raw_filename))
        extension = Path(filename).suffix.lower()

        if extension not in ALLOWED_EXTENSIONS:
            logger.info("      - 格式跳过：%s", filename)
            stats["format_skipped"] += 1
            continue

        if (
            not options.download_all
            and is_downloaded(
                conn,
                options.provider,
                options.email_address,
                options.folder,
                uid,
                attachment_index,
            )
        ):
            logger.info("      - 已下载跳过：%s", filename)
            stats["duplicate_skipped"] += 1
            continue

        try:
            attachment_data = part.get_payload(decode=True)
            if not attachment_data:
                raise RuntimeError("附件内容为空")

            save_path = get_unique_path(output_dir, filename)
            save_path.write_bytes(attachment_data)

            mark_downloaded(
                conn,
                options.provider,
                options.email_address,
                options.folder,
                uid,
                attachment_index,
                filename,
                save_path,
            )

            logger.info("      ✓ %s", save_path.name)
            stats["downloaded"] += 1

        except Exception as exc:
            logger.info("      ✗ 附件失败：%s，原因：%s", filename, exc)
            stats["failed_attachments"] += 1

    return stats


def download_resumes(options: DownloadOptions, log_callback=None) -> dict:
    app_dir = options.app_dir or get_runtime_app_dir()
    output_dir = Path(options.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger = create_logger(app_dir, log_callback)
    conn = init_database(app_dir)

    config = IMAP_CONFIG[options.provider]
    provider_name = config["name"]
    imap_server = options.server or config["server"]
    imap_port = options.port or config["port"]

    stats = {
        "messages": 0,
        "downloaded": 0,
        "duplicate_skipped": 0,
        "format_skipped": 0,
        "failed_attachments": 0,
        "failed_messages": 0,
    }

    client = None

    try:
        logger.info("=" * 60)
        logger.info("邮箱简历附件抓取开始")
        logger.info("=" * 60)
        logger.info("邮箱类型：%s", provider_name)
        logger.info("邮箱账号：%s", options.email_address)
        logger.info("目标文件夹：%s", options.folder)
        logger.info("保存目录：%s", output_dir)
        logger.info("抓取模式：%s", "重新抓取全部历史附件" if options.download_all else "只抓取新增附件")

        logger.info("")
        logger.info("[1/4] 正在连接邮箱服务器...")
        logger.info("      服务器：%s:%s", imap_server, imap_port)
        client = imaplib.IMAP4_SSL(host=imap_server, port=imap_port, timeout=30)
        logger.info("      ✓ 连接成功")

        logger.info("")
        logger.info("[2/4] 正在登录邮箱...")
        status, _ = client.login(options.email_address, options.credential)
        if status != "OK":
            raise RuntimeError("邮箱登录失败")
        logger.info("      ✓ 登录成功")

        logger.info("")
        logger.info("[3/4] 正在查找邮箱文件夹...")
        raw_folder_name = find_target_folder(client, options.folder, logger)
        if raw_folder_name is None:
            raise RuntimeError(f"未找到目标文件夹：{options.folder}")
        logger.info("      ✓ 已找到：%s", options.folder)

        status, message_count = client.select(f'"{raw_folder_name}"', readonly=True)
        if status != "OK":
            raise RuntimeError(f"无法进入邮箱文件夹：{options.folder}")

        try:
            total_messages = int(message_count[0])
        except Exception:
            total_messages = 0

        logger.info("      邮件数量：%s 封", total_messages)

        logger.info("")
        logger.info("[4/4] 正在读取邮件并下载附件...")

        status, uid_data = client.uid("search", None, "ALL")
        if status != "OK":
            raise RuntimeError("搜索邮件失败")

        uid_list = uid_data[0].split()
        stats["messages"] = len(uid_list)

        if not uid_list:
            logger.info("目标文件夹中没有邮件。")
            log_summary(stats, logger.info)
            return stats

        for index, uid_bytes in enumerate(uid_list, start=1):
            uid = uid_bytes.decode(errors="replace")

            try:
                status, message_data = client.uid("fetch", uid, "(RFC822)")
                if status != "OK":
                    logger.info("")
                    logger.info("[%s/%s] 读取邮件失败，UID：%s", index, len(uid_list), uid)
                    stats["failed_messages"] += 1
                    continue

                raw_message = None
                for item in message_data:
                    if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes):
                        raw_message = item[1]
                        break

                if raw_message is None:
                    logger.info("")
                    logger.info("[%s/%s] 邮件内容为空，UID：%s", index, len(uid_list), uid)
                    stats["failed_messages"] += 1
                    continue

                message = email.message_from_bytes(raw_message)
                subject = decode_mime_text(message.get("Subject")) or "无主题"

                logger.info("")
                logger.info("[%s/%s] %s", index, len(uid_list), subject)

                message_stats = extract_attachments(
                    message,
                    output_dir,
                    conn,
                    options,
                    uid,
                    logger,
                )

                for key, value in message_stats.items():
                    stats[key] += value

                if sum(message_stats.values()) == 0:
                    logger.info("      - 没有附件")

            except Exception as exc:
                logger.info("")
                logger.info("[%s/%s] 处理邮件失败：%s", index, len(uid_list), exc)
                stats["failed_messages"] += 1

        log_summary(stats, logger.info)
        return stats

    except imaplib.IMAP4.error as exc:
        raise RuntimeError(build_imap_error_message(exc)) from exc

    finally:
        try:
            conn.close()
        except Exception:
            pass

        if client is not None:
            try:
                client.logout()
            except Exception:
                pass


def build_imap_error_message(exc: Exception) -> str:
    return (
        f"IMAP 操作失败：{exc}\n\n"
        "请检查：\n"
        "1. 邮箱类型是否选对，例如飞书邮箱不要选成腾讯企业邮箱；\n"
        "2. 邮箱账号是否填写完整；\n"
        "3. 客户端专用密码/授权码是否正确；\n"
        "4. 当前账号是否已开启 IMAP 或第三方客户端访问。"
    )


def test_mail_connection(options: DownloadOptions, log_callback=None) -> None:
    app_dir = options.app_dir or get_runtime_app_dir()
    logger = create_logger(app_dir, log_callback)

    config = IMAP_CONFIG[options.provider]
    provider_name = config["name"]
    imap_server = options.server or config["server"]
    imap_port = options.port or config["port"]
    client = None

    try:
        logger.info("=" * 60)
        logger.info("开始测试邮箱连接")
        logger.info("=" * 60)
        logger.info("邮箱类型：%s", provider_name)
        logger.info("邮箱账号：%s", options.email_address)
        logger.info("目标文件夹：%s", options.folder)

        logger.info("")
        logger.info("[1/3] 正在连接邮箱服务器...")
        logger.info("      服务器：%s:%s", imap_server, imap_port)
        client = imaplib.IMAP4_SSL(host=imap_server, port=imap_port, timeout=30)
        logger.info("      ✓ 连接成功")

        logger.info("")
        logger.info("[2/3] 正在登录邮箱...")
        status, _ = client.login(options.email_address, options.credential)
        if status != "OK":
            raise RuntimeError("邮箱登录失败")
        logger.info("      ✓ 登录成功")

        logger.info("")
        logger.info("[3/3] 正在检查目标文件夹...")
        raw_folder_name = find_target_folder(client, options.folder, logger)
        if raw_folder_name is None:
            raise RuntimeError(f"登录成功，但未找到目标文件夹：{options.folder}")
        logger.info("      ✓ 已找到：%s", options.folder)

        logger.info("")
        logger.info("测试连接成功，可以开始抓取。")

    except imaplib.IMAP4.error as exc:
        raise RuntimeError(build_imap_error_message(exc)) from exc

    finally:
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass


def log_summary(stats: dict, callback) -> None:
    lines = [
        "",
        "=" * 60,
        "抓取完成",
        "=" * 60,
        f"扫描邮件：{stats.get('messages', 0)} 封",
        f"新下载附件：{stats.get('downloaded', 0)} 个",
        f"已下载跳过：{stats.get('duplicate_skipped', 0)} 个",
        f"格式跳过附件：{stats.get('format_skipped', 0)} 个",
        f"失败附件：{stats.get('failed_attachments', 0)} 个",
        f"失败邮件：{stats.get('failed_messages', 0)} 封",
        "=" * 60,
    ]
    for line in lines:
        callback(line)
