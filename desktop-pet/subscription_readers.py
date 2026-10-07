"""RSS/Atom and read-only IMAP. Return metadata, never execute remote content."""
from email import policy
from email.parser import BytesHeaderParser
from html.parser import HTMLParser
import hashlib
import imaplib
import ssl
import xml.etree.ElementTree as ET
from extension_io import ExtensionError, check_url, request_url, unseal


class Plain(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []
    def handle_data(self, data):
        self.parts.append(data)


def plain(value, limit=160):
    parser = Plain()
    parser.feed(value or '')
    return ' '.join(' '.join(parser.parts).split())[:limit]


def parse_feed(data):
    if len(data) > 2*1024*1024 or b'\x00' in data or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ExtensionError('订阅内容过大或包含不支持的 XML 定义。')
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise ExtensionError('这不是可解析的 RSS / Atom 订阅。') from None
    tag = lambda node: node.tag.rsplit('}', 1)[-1]
    if tag(root) not in ('rss', 'feed', 'RDF'):
        raise ExtensionError('地址返回的不是 RSS / Atom。')
    entries = [n for n in root.iter() if tag(n) in ('item', 'entry')]
    result = []
    for entry in entries[:2000]:
        fields = {}
        link = ''
        for child in entry:
            name = tag(child)
            fields.setdefault(name, ''.join(child.itertext()))
            if name == 'link' and child.get('rel', 'alternate') == 'alternate':
                link = child.get('href') or child.text or ''
        try:
            check_url(link)
        except ExtensionError:
            link = ''
        title = plain(fields.get('title'), 120) or '新订阅消息'
        identity = fields.get('guid') or fields.get('id') or link or title + fields.get('pubDate', fields.get('updated', ''))
        result.append({'id': hashlib.sha256(identity.encode()).hexdigest(), 'title': title,
                       'summary': plain(fields.get('description') or fields.get('summary') or fields.get('content')),
                       'url': link})
    return result


def read_rss(config, cursor):
    headers = {}
    if cursor.get('etag'): headers['If-None-Match'] = cursor['etag']
    if cursor.get('modified'): headers['If-Modified-Since'] = cursor['modified']
    status, response, data = request_url(config['url'], headers=headers, allow_local=config.get('allow_local', False))
    if status == 304:
        return [], cursor
    headers = {k.lower(): v for k, v in response.items()}
    return parse_feed(data), {**cursor, 'etag': headers.get('etag', ''), 'modified': headers.get('last-modified', '')}


def read_imap(config, cursor, factory=imaplib.IMAP4_SSL):
    client = factory(config['host'], config['port'], ssl_context=ssl.create_default_context(), timeout=15)
    try:
        client.login(config['username'], unseal(config['password_secret']))
        status, _ = client.select(config['folder'], readonly=True)
        if status != 'OK': raise ExtensionError('无法以只读方式打开邮箱文件夹。')
        validity = client.response('UIDVALIDITY')[1]
        if not validity or not validity[0]: raise ExtensionError('邮箱没有提供 UIDVALIDITY，暂不推进游标。')
        validity = validity[0].decode('ascii')
        # UIDVALIDITY changes mean old UIDs are not identities anymore: baseline again.
        baseline = cursor.get('uidvalidity') != validity
        after = 0 if baseline else int(cursor.get('uid', 0))
        status, data = client.uid('search', None, 'ALL' if baseline else 'UID %s:*' % (after + 1))
        if status != 'OK': raise ExtensionError('邮箱未能返回新邮件列表。')
        ids = sorted({int(x) for x in (data[0] or b'').split() if int(x) > after})
        if baseline:
            return [], {'uidvalidity': validity, 'uid': max(ids, default=0), 'initialized': True}
        result = []
        for uid in ids[:50]:
            status, parts = client.uid('fetch', str(uid), '(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE MESSAGE-ID)]<0.8192>)')
            if status != 'OK': raise ExtensionError('读取邮件标题失败，将在下一轮重试。')
            raw = next((p[1] for p in parts if isinstance(p, tuple) and isinstance(p[1], bytes)), None)
            if raw is None: raise ExtensionError('邮件标题暂时不可用，将在下一轮重试。')
            message = BytesHeaderParser(policy=policy.default).parsebytes(raw[:8192])
            result.append({'id': validity + ':' + str(uid), 'title': plain(str(message.get('Subject', '新邮件')), 120),
                           'summary': plain('来自 ' + str(message.get('From', '未知发件人'))), 'url': ''})
            after = uid
        return result, {'uidvalidity': validity, 'uid': after, 'initialized': True}
    finally:
        # Never CLOSE/EXPUNGE/STORE and never alter the server's read flags.
        try: client.logout()
        except (OSError, imaplib.IMAP4.error): pass
