"""Bounded network reads and Windows account-bound secret storage."""
import base64
import ctypes
from ctypes import wintypes
import http.client
import ipaddress
import os
import socket
import ssl
from urllib.parse import urlsplit, quote


class ExtensionError(ValueError):
    """A safe, user-facing error without remote response bodies or credentials."""


def check_url(value, model=False):
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 33 for c in value):
        raise ExtensionError('请输入完整的 HTTP / HTTPS 地址。')
    try:
        u = urlsplit(value)
        port = u.port
    except ValueError:
        raise ExtensionError('地址或端口无效。') from None
    if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password or u.fragment:
        raise ExtensionError('地址不支持内嵌账号、密码或片段。')
    if model and (u.query or u.scheme == 'http' and u.hostname not in ('localhost', '127.0.0.1', '::1')):
        raise ExtensionError('云端模型请使用 HTTPS；本机模型可用 http://127.0.0.1。')
    return u


def request_url(url, *, body=None, headers=None, allow_local=False, timeout=15, limit=2*1024*1024):
    """Pin the resolved address, do not follow redirects or use ambient proxies."""
    u = check_url(url)
    port = u.port or (443 if u.scheme == 'https' else 80)
    addresses = socket.getaddrinfo(u.hostname, port, type=socket.SOCK_STREAM)
    if not addresses:
        raise ExtensionError('无法解析服务地址。')
    if not allow_local and any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ExtensionError('订阅地址指向内网；如确实是本机订阅，请开启“允许内网”。')
    conn = http.client.HTTPConnection(u.hostname, port, timeout=timeout)
    sock = None
    try:
        last = None
        for family, socktype, proto, _, address in addresses[:4]:
            try:
                sock = socket.socket(family, socktype, proto)
                sock.settimeout(timeout)
                sock.connect(address)
                break
            except OSError as error:
                last = error
                sock.close()
                sock = None
        if sock is None:
            raise last or OSError('connect failed')
        if u.scheme == 'https':
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=u.hostname)
        conn.sock = sock
        path = quote(u.path or '/', safe="/:@!$&'()*+,;=-._~%")
        if u.query:
            path += '?' + quote(u.query, safe="/?:@!$&'()*+,;=-._~%")
        conn.request('POST' if body is not None else 'GET', path, body=body,
                     headers={'User-Agent': 'WangBun/1.0', **(headers or {})})
        response = conn.getresponse()
        if response.status == 304:
            return 304, dict(response.getheaders()), b''
        if not 200 <= response.status < 300:
            raise ExtensionError('服务返回 HTTP %s；请检查地址、权限或额度。' % response.status)
        if int(response.getheader('Content-Length', '0')) > limit:
            raise ExtensionError('响应过大，已停止读取。')
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ExtensionError('响应过大，已停止读取。')
        return response.status, dict(response.getheaders()), data
    finally:
        conn.close()
        if sock:
            sock.close()


def _dpapi(data, decrypt=False):
    if os.name != 'nt':
        raise ExtensionError('此版本密钥保存使用 Windows 账户加密。')
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(data)
    incoming = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = Blob()
    api = ctypes.windll.crypt32
    function = api.CryptUnprotectData if decrypt else api.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
        raise ExtensionError('Windows 无法处理密钥，请使用当前登录账户重新保存。')
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        free = ctypes.windll.kernel32.LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        free(outgoing.data)


def seal(secret):
    if not isinstance(secret, str) or len(secret) > 4096 or '\r' in secret or '\n' in secret:
        raise ExtensionError('密钥格式不正确。')
    return base64.b64encode(_dpapi(secret.encode('utf-8'))).decode('ascii') if secret else ''


def unseal(value):
    return _dpapi(base64.b64decode(value), True).decode('utf-8') if value else ''
