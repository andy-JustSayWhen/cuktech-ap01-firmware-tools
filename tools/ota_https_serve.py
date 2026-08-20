"""在本机 443 端口提供指定 AP01 固件的自签 HTTPS 下载服务。

适用范围：本工具只服务调用时通过 --firmware 提供的固件，不保存或推断设备编号、局域网
地址和个人固件位置。设备访问格式固定为
https://<运行此工具的电脑局域网地址>/miio_fw/<固件文件名>。

证书的域名与设备在线更新兼容；它只用于当前电脑提供的临时固件服务。生成的证书、私钥与
服务日志均不应提交到仓库。
"""

from __future__ import annotations

import argparse
import datetime
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
FIRMWARE = Path()
KEY_FILE = HERE / "ota-cdn.key"
CERT_FILE = HERE / "ota-cdn.crt"
LOG_FILE = Path()
HOSTNAME = "iot-ota-cdn.io.mi.com"
RECORD_CHUNK = 4096  # 单条 TLS record 的大小，须 ≤ 设备端 mbedTLS 接收缓冲

LOG_LOCK = threading.Lock()


def log(message: str) -> None:
    line = f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {message}"
    with LOG_LOCK:
        print(line, flush=True)
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")


def ensure_certificate() -> None:
    if CERT_FILE.is_file() and KEY_FILE.is_file():
        return
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, HOSTNAME)]
    )
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow() - datetime.timedelta(days=1))
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=3650))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(HOSTNAME)]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    KEY_FILE.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    CERT_FILE.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))


def make_handler() -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "OTACDN/1.1"
        # 设备端 HTTP 客户端要求 HTTP/1.1 响应（官方 CDN 返回 HTTP/1.1）；
        # HTTP/1.0 响应头会被设备记为 ota_error，2026-08-19 实测。
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            try:
                log(
                    f"TLS {self.connection.version()} cipher={self.connection.cipher()} "
                    f"from {self.address_string()} path={path}"
                )
            except (AttributeError, ValueError):
                pass
            log(f"REQUEST_HEADERS from {self.address_string()}: {dict(self.headers.items())}")
            if path == f"/miio_fw/{FIRMWARE.name}":
                body = FIRMWARE.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                # 设备端 mbedTLS 接收缓冲小于 OpenSSL 默认的 16KB TLS record，
                # 收到 16KB record 时报 INVALID_RECORD（-0x7100）；官方 CDN
                # （nginx）通常配置 ssl_buffer_size=4KB。按 4KB 分块 write，
                # 每块生成一条 4KB record，持续流式发送，2026-08-19 实测。
                started = time.monotonic()
                sent = 0
                try:
                    for offset in range(0, len(body), RECORD_CHUNK):
                        chunk = body[offset : offset + RECORD_CHUNK]
                        self.wfile.write(chunk)
                        sent += len(chunk)
                except (OSError, ssl.SSLError) as error:
                    log(
                        f"SEND_ABORTED to {self.address_string()} at {sent} bytes"
                        f" ({time.monotonic() - started:.1f}s): {error!r}"
                    )
                    return
                log(
                    f"SERVED {path} {len(body)} bytes to {self.address_string()} "
                    f"in {time.monotonic() - started:.1f}s"
                )
                return
            self.send_error(404)
            log(f"NOT_FOUND {path} from {self.address_string()}")

        def log_message(self, fmt: str, *args: object) -> None:
            log(f"{self.address_string()} {fmt % args}")

    return Handler


def main() -> int:
    global FIRMWARE, LOG_FILE
    parser = argparse.ArgumentParser(description="本机 443 自签 HTTPS 固件服务")
    parser.add_argument(
        "--firmware",
        type=Path,
        required=True,
        help="要服务的 AP01 固件文件",
    )
    args = parser.parse_args()
    FIRMWARE = args.firmware.resolve()
    if not FIRMWARE.is_file():
        raise SystemExit(f"固件文件不存在：{FIRMWARE}")
    LOG_FILE = FIRMWARE.parent / "ota-serve.log"
    ensure_certificate()
    server = ThreadingHTTPServer(("0.0.0.0", 443), make_handler())
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(CERT_FILE, KEY_FILE)
    # 设备协商到的 ECDHE-RSA-AES256-GCM-SHA384 在第 1~4 条 record 后报
    # INVALID_RECORD（-0x7100）；改用 AES128-GCM 排查设备端 AES-256 实现
    # 问题，2026-08-19 实测。
    context.set_ciphers("ECDHE-RSA-AES128-GCM-SHA256")
    # Broad TLS compatibility for embedded clients.
    context.minimum_version = ssl.TLSVersion.TLSv1
    server.socket = context.wrap_socket(server.socket, server_side=True)
    print(
        "固件服务已启动："
        f"https://<本机局域网地址>/miio_fw/{FIRMWARE.name}（证书域名：{HOSTNAME}）"
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
