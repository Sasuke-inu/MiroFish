"""Bounded, explicit web-input collection through a self-hosted Firecrawl.

Reservations, attempts, cached text and idempotent plans survive backend restarts.
Only this adapter's requests are counted; other Firecrawl clients have separate usage.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import socket
import sqlite3
import time
from urllib.parse import urlsplit, urlunsplit
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx


class SourceImportError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code = code
        self.status = status


class SourceImporter:
    CACHE_SECONDS = 24 * 3600
    PLAN_SECONDS = 600
    MAX_CHARS = 8000
    MAX_RESPONSE_BYTES = 2 * 1024 * 1024
    LOCAL_HOSTS = {'localhost', 'host.docker.internal', 'firecrawl', 'firecrawl-local-api-1'}
    DOCUMENT_EXTENSIONS = re.compile(r'\.(pdf|docx?|xlsx?|pptx?|zip|png|jpe?g|gif|mp[34]|webp)(/|$)', re.I)

    def __init__(self, settings, *, transport=None, resolver=None, clock=None):
        self.settings = settings
        self.transport = transport
        self.resolver = resolver or socket.getaddrinfo
        self.clock = clock or time.time
        self.enabled = bool(settings.get('FIRECRAWL_ENABLED', False))
        self.base_url = str(settings.get('FIRECRAWL_BASE_URL', '')).rstrip('/')
        self.api_key = settings.get('FIRECRAWL_API_KEY', '')
        self.db_path = Path(settings['UPLOAD_FOLDER']) / 'source-imports' / 'ledger.sqlite'
        self.configured = False
        try:
            self.max_pages = int(settings.get('FIRECRAWL_MAX_PAGES_PER_JOB', 3))
            self.daily_limit = int(settings.get('FIRECRAWL_DAILY_PAGE_LIMIT', 10))
            self.timezone = ZoneInfo(settings.get('FIRECRAWL_BUDGET_TIMEZONE', 'Australia/Sydney'))
            parsed = urlsplit(self.base_url)
            host = parsed.hostname or ''
            try:
                local = ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback
            except ValueError:
                local = host in self.LOCAL_HOSTS
            self.configured = (local and parsed.scheme in {'http', 'https'}
                               and not parsed.username and not parsed.password
                               and parsed.path in {'', '/'} and not parsed.query and not parsed.fragment
                               and 1 <= self.max_pages <= 3 and 1 <= self.daily_limit <= 10)
            parsed.port  # Reject malformed ports, including when checking status.
        except (ValueError, TypeError, ZoneInfoNotFoundError):
            self.configured = False
            self.max_pages, self.daily_limit, self.timezone = 3, 10, ZoneInfo('UTC')
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS cache (
                    url TEXT PRIMARY KEY, fetched REAL NOT NULL, document TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS plans (
                    id TEXT PRIMARY KEY, created REAL NOT NULL, expires REAL NOT NULL,
                    day TEXT NOT NULL, status TEXT NOT NULL, snapshot TEXT NOT NULL,
                    reserved INTEGER NOT NULL DEFAULT 0, attempted INTEGER NOT NULL DEFAULT 0,
                    needs_provider INTEGER NOT NULL DEFAULT 0, result TEXT
                );
                CREATE INDEX IF NOT EXISTS plans_day ON plans(day);
                CREATE TABLE IF NOT EXISTS plan_projects (
                    plan_id TEXT PRIMARY KEY, project_id TEXT NOT NULL
                );
            ''')

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def client(self):
        headers = {'Authorization': f'Bearer {self.api_key}'} if self.api_key else {}
        # No SDK retries, environment proxies, Cloud fallback or redirects of API calls.
        return httpx.Client(transport=self.transport, headers=headers, trust_env=False,
                            follow_redirects=False, timeout=httpx.Timeout(50, connect=5))

    def require_configured(self):
        if not self.enabled:
            raise SourceImportError('disabled', '網頁資料擷取尚未啟用。', 503)
        if not self.configured:
            raise SourceImportError('configuration', '請設定本機 Firecrawl，且每次上限不超過 3 頁、每日上限不超過 10 次。', 503)

    def _day(self):
        return datetime.fromtimestamp(self.clock(), self.timezone).date().isoformat()

    def _expire(self, conn):
        # A crashed worker holds its unused reservation for ten minutes. Sent
        # attempts remain spent. A later/replayed POST never restarts this plan.
        conn.execute("UPDATE plans SET status='interrupted', reserved=0 WHERE status='running' AND expires<=?", (self.clock(),))

    def _budget(self, conn):
        row = conn.execute('''SELECT COALESCE(SUM(attempted), 0) AS used,
            COALESCE(SUM(CASE WHEN status='running' THEN reserved ELSE 0 END), 0) AS held
            FROM plans WHERE day=?''', (self._day(),)).fetchone()
        tomorrow = datetime.fromtimestamp(self.clock(), self.timezone).date() + timedelta(days=1)
        reset = datetime.combine(tomorrow, datetime.min.time(), self.timezone).isoformat()
        return {'day': self._day(), 'timezone': str(self.timezone), 'used': row['used'],
                'reserved': row['held'], 'daily_limit': self.daily_limit,
                'remaining': max(0, self.daily_limit - row['used'] - row['held']), 'resets_at': reset}

    def status(self, probe=False):
        with self.db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            self._expire(conn)
            budget = self._budget(conn)
        online = False
        if probe and self.enabled and self.configured:
            try:
                with self.client() as client:
                    response = client.get(self.base_url + '/', timeout=3)
                online = response.status_code == 200 and 'Firecrawl' in str(response.json().get('message', ''))
            except (httpx.HTTPError, ValueError, AttributeError):
                pass
        return {'enabled': self.enabled, 'configured': self.configured, 'online': online,
                'mode': 'local', 'cloud_credits': 0, 'max_pages_per_job': self.max_pages,
                'max_chars_per_page': self.MAX_CHARS, 'cache_hours': 24, 'budget': budget,
                'search': {'capability': 'unverified', 'status': 'disabled_authorization',
                           'enabled': False, 'provider_version': None}}

    @classmethod
    def normalize_url(cls, value):
        if not isinstance(value, str) or len(value) > 2048 or re.search(r'[\s\\\x00-\x1f]', value):
            raise SourceImportError('invalid_url', '請輸入完整的公開網站網址。')
        try:
            parsed = urlsplit(value)
            host = (parsed.hostname or '').encode('idna').decode('ascii').lower().rstrip('.')
            if parsed.scheme.lower() not in {'https', 'http'} or not host or parsed.username or parsed.password:
                raise ValueError()
            if parsed.port not in {None, 80, 443}:
                raise ValueError()
            if host in cls.LOCAL_HOSTS or host.endswith(('.localhost', '.local', '.internal')) or '.' not in host:
                raise ValueError()
            try:
                if not ipaddress.ip_address(host).is_global:
                    raise ValueError()
            except ValueError as exc:
                # A hostname is resolved and checked immediately before scraping.
                if ':' in host or re.fullmatch(r'[0-9.]+', host):
                    raise exc
            if cls.DOCUMENT_EXTENSIONS.search(parsed.path):
                raise SourceImportError('documents', '此入口只擷取網頁；PDF 等檔案請使用原有上傳功能。')
            # Browsers treat an explicit default port as the same URL. Use the
            # same cache key so pasted variants do not consume another page.
            default_port = 443 if parsed.scheme.lower() == 'https' else 80
            authority = host if parsed.port in {None, default_port} else f'{host}:{parsed.port}'
            return urlunsplit((parsed.scheme.lower(), authority, parsed.path or '/', parsed.query, ''))
        except (ValueError, UnicodeError):
            raise SourceImportError('invalid_url', '只接受公開網站的 HTTP 或 HTTPS 網址。') from None

    def assert_public_dns(self, url):
        host = urlsplit(url).hostname
        try:
            addresses = self.resolver(host, None, type=socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
                raise SourceImportError('invalid_url', '此網址指向私人網路，無法作為公開網頁來源。')
        except (OSError, ValueError):
            raise SourceImportError('invalid_url', '無法確認此網址是公開網站，請檢查網址。') from None

    @staticmethod
    def _clean_document_prelude(document):
        # Older imports included an implementation note that graph extraction
        # could mistake for a fact. Remove only that exact header line; source
        # text after the first separator must remain untouched.
        markdown = document['markdown']
        header, separator, body = markdown.partition('\n\n---\n\n')
        if not separator:
            return document
        note = '收集方式：本機 Firecrawl；以下為來源原文，尚未進行模型分析。'
        cleaned = '\n'.join(line for line in header.split('\n') if line != note)
        if cleaned == header:
            return document
        return {**document, 'markdown': cleaned + separator + body}

    def _cached(self, conn, url, *, allow_stale=False):
        row = conn.execute('SELECT * FROM cache WHERE url=?', (url,)).fetchone()
        if row and (allow_stale or self.clock() - row['fetched'] < self.CACHE_SECONDS):
            return {**self._clean_document_prelude(json.loads(row['document'])), 'cached': True}
        return None

    def plan(self, urls, *, project_id=None):
        self.require_configured()
        if project_id is not None and (not isinstance(project_id, str)
                or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', project_id)):
            raise SourceImportError('plan_scope', '無法確認此研究的網頁整理計畫。', 409)
        if not isinstance(urls, list) or not urls or len(urls) > self.max_pages:
            raise SourceImportError('page_limit', f'每次請選擇 1 至 {self.max_pages} 個網址。')
        normalized = list(dict.fromkeys(self.normalize_url(url) for url in urls))
        with self.db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            self._expire(conn)
            entries = []
            for url in normalized:
                cached = self._cached(conn, url)
                entries.append({'url': url, 'cached': bool(cached),
                                'title': cached['title'] if cached else urlsplit(url).hostname,
                                'fetched_at': cached['fetched_at'] if cached else None})
            estimated = sum(not item['cached'] for item in entries)
            budget = self._budget(conn)
            if estimated > budget['remaining']:
                raise SourceImportError('daily_limit', '已達今日擷取上限；仍可使用快取與上傳檔案。', 429)
            plan_id = uuid.uuid4().hex
            now = self.clock()
            conn.execute('INSERT INTO plans (id,created,expires,day,status,snapshot) VALUES (?,?,?,?,?,?)',
                         (plan_id, now, now + self.PLAN_SECONDS, self._day(), 'planned', json.dumps(entries)))
            if project_id is not None:
                conn.execute('INSERT INTO plan_projects (plan_id,project_id) VALUES (?,?)', (plan_id, project_id))
        return {'plan_id': plan_id, 'entries': entries, 'new_pages': estimated,
                'cached_pages': len(entries) - estimated, 'cloud_credits': 0,
                'budget': budget, 'expires_in_seconds': self.PLAN_SECONDS}

    def require_plan_project(self, plan_id, project_id):
        """Bind research adoption to its explicit plan; legacy plans stay unbound."""
        if not isinstance(plan_id, str) or not re.fullmatch(r'[a-f0-9]{32}', plan_id):
            raise SourceImportError('plan_scope', '無法確認此研究的網頁整理計畫，請重新預覽。', 409)
        with self.db() as conn:
            row = conn.execute('SELECT project_id FROM plan_projects WHERE plan_id=?', (plan_id,)).fetchone()
        if not row or row['project_id'] != project_id:
            raise SourceImportError('plan_scope', '此網頁整理計畫不屬於目前研究，請重新預覽。', 409)

    def saved_selection(self, plan_id, urls, *, project_id):
        """Read only immutable completed results; never fetch, resolve DNS or retry."""
        self.require_plan_project(plan_id, project_id)
        if not isinstance(urls, list) or not urls or len(urls) > self.max_pages:
            raise SourceImportError('page_limit', f'每次請選擇 1 至 {self.max_pages} 個已預覽的網址。')
        selected = list(dict.fromkeys(self.normalize_url(url) for url in urls))
        with self.db() as conn:
            row = conn.execute('SELECT status,result FROM plans WHERE id=?', (plan_id,)).fetchone()
        if not row or row['status'] != 'completed' or not row['result']:
            raise SourceImportError('plan_incomplete', '網頁整理尚未完整完成，不能納入研究；請先核對預覽結果。', 409)
        try:
            result = json.loads(row['result'])
            if result.get('status') != 'completed' or result.get('errors') or result.get('skipped_urls'):
                raise ValueError()
            documents = {item['url']: item for item in result['documents']}
        except (ValueError, TypeError, KeyError, AttributeError):
            raise SourceImportError('plan_incomplete', '保存的預覽結果無法確認，已停止納入研究。', 409) from None
        if any(url not in documents for url in selected):
            raise SourceImportError('invalid_selection', '只能納入這次已完成預覽的來源。')
        return [self._clean_document_prelude(documents[url]) for url in selected]

    def _claim(self, plan_id):
        with self.db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            self._expire(conn)
            row = conn.execute('SELECT * FROM plans WHERE id=?', (plan_id,)).fetchone()
            if not row:
                raise SourceImportError('plan_expired', '找不到這次網頁整理，請重新開始。', 409)
            if row['status'] in {'completed', 'failed'}:
                return json.loads(row['result']), None
            if row['status'] == 'running':
                raise SourceImportError('busy', '這次擷取正在進行，請勿重複送出。', 409)
            if row['status'] != 'planned' or row['expires'] <= self.clock() or row['day'] != self._day():
                raise SourceImportError('plan_expired', '這次網頁整理已過期，請重新開始。', 409)
            work = []
            for entry in json.loads(row['snapshot']):
                # A cached page shown at preview remains usable during the short
                # plan lifetime, even if its 24h TTL expires in the meantime.
                cached = self._cached(conn, entry['url'], allow_stale=entry['cached'])
                if entry['cached'] and not cached:
                    raise SourceImportError('plan_expired', '網頁快取已變更，請重新開始整理。', 409)
                work.append((entry, cached))
            needed = sum(doc is None for _, doc in work)
            if needed and conn.execute("SELECT 1 FROM plans WHERE status='running' AND needs_provider=1").fetchone():
                raise SourceImportError('busy', '已有網頁擷取正在進行，請等它完成後再送出。', 409)
            if needed > self._budget(conn)['remaining']:
                raise SourceImportError('daily_limit', '已達今日擷取上限；仍可使用快取與上傳檔案。', 429)
            conn.execute("UPDATE plans SET status='running', reserved=?, needs_provider=?, expires=? WHERE id=?",
                         (needed, int(needed > 0), self.clock() + self.PLAN_SECONDS, plan_id))
            return None, work

    def _mark_attempt(self, plan_id):
        with self.db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            changed = conn.execute("""UPDATE plans SET attempted=attempted+1, reserved=reserved-1
                WHERE id=? AND status='running' AND reserved>0 AND expires>? AND day=?""", (plan_id, self.clock(), self._day())).rowcount
            if changed != 1:
                raise SourceImportError('plan_expired', '這次網頁整理已停止，請重新開始。', 409)

    def _scrape(self, url):
        payload = {'url': url, 'formats': ['markdown'], 'onlyMainContent': True,
                   'parsers': [], 'proxy': 'basic', 'timeout': 45000,
                   'removeBase64Images': True, 'skipTlsVerification': False}
        try:
            with self.client() as client, client.stream('POST', self.base_url + '/v2/scrape', json=payload) as response:
                if response.status_code != 200:
                    raise SourceImportError('upstream', 'Firecrawl 未能完成擷取；不會自動重試。', 502)
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > self.MAX_RESPONSE_BYTES:
                        raise SourceImportError('too_large', '網頁回傳的資料太大，已停止匯入。', 502)
            result = json.loads(content)
            data = result.get('data')
            if result.get('success') is not True or not isinstance(data, dict):
                raise ValueError()
            return data
        except httpx.TimeoutException:
            raise SourceImportError('timeout', '網頁擷取逾時；不會自動重試。', 504) from None
        except (httpx.HTTPError, ValueError, AttributeError):
            raise SourceImportError('upstream', 'Firecrawl 未能完成擷取；不會自動重試。', 502) from None

    @staticmethod
    def _published_at(metadata):
        # Keep only a precise, explicitly zoned publication timestamp. A date or
        # a modification timestamp cannot be silently promoted to this field.
        for key in ('publishedTime', 'publishedAt', 'published_at', 'datePublished', 'article:published_time'):
            value = metadata.get(key)
            if not isinstance(value, str) or len(value) > 40:
                continue
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:[Zz]|[+-]\d{2}:\d{2})', value):
                continue
            try:
                parsed = datetime.fromisoformat(value.upper().replace('Z', '+00:00'))
                return parsed.astimezone(timezone.utc).isoformat()
            except (ValueError, OverflowError):
                continue
        return None

    def _document(self, url, data):
        metadata = data.get('metadata') or {}
        if not isinstance(metadata, dict):
            raise SourceImportError('empty', '未取得可匯入的網頁文字。', 502)
        status = metadata.get('statusCode', 200)
        if not isinstance(status, int) or not (200 <= status < 300 or status == 304):
            raise SourceImportError('page_error', '來源網頁回傳錯誤，已排除這份資料。', 502)
        content_type = str(metadata.get('contentType', 'text/html')).split(';')[0].lower()
        if content_type not in {'text/html', 'application/xhtml+xml', 'text/plain', 'text/markdown'}:
            raise SourceImportError('documents', '此入口只擷取網頁；文件請使用原有上傳功能。', 502)
        source_url = self.normalize_url(metadata.get('sourceURL') or url)
        body = data.get('markdown')
        if not isinstance(body, str) or not body.strip():
            raise SourceImportError('empty', '未取得可匯入的網頁文字。', 502)
        body = body.strip()
        title = re.sub(r'[\r\n\x00-\x1f]+', ' ', str(metadata.get('title') or urlsplit(url).hostname))[:200]
        fetched_at = datetime.fromtimestamp(self.clock(), self.timezone).isoformat()
        truncated = len(body) > self.MAX_CHARS
        text = (f'# {title}\n\n來源網址：{url}\n最終來源：{source_url}\n擷取時間：{fetched_at}'
                '\n\n---\n\n' + body[:self.MAX_CHARS])
        if truncated:
            text += f'\n\n[此頁超過 {self.MAX_CHARS:,} 字，匯入內容已截短。]\n'
        filename = f"web-{urlsplit(url).hostname[:60]}-{hashlib.sha256(url.encode()).hexdigest()[:8]}.md"
        return {'id': hashlib.sha256(url.encode()).hexdigest()[:16], 'url': url, 'source_url': source_url,
                'title': title, 'fetched_at': fetched_at, 'filename': filename, 'markdown': text,
                'published_at': self._published_at(metadata), 'parse_status': 'truncated' if truncated else 'parsed',
                'chars': min(len(body), self.MAX_CHARS), 'truncated': truncated, 'cached': False}

    def fetch(self, plan_id):
        self.require_configured()
        if not isinstance(plan_id, str) or not re.fullmatch(r'[a-f0-9]{32}', plan_id):
            raise SourceImportError('plan_expired', '無法確認這次網頁整理，請重新開始。', 409)
        replay, work = self._claim(plan_id)
        if replay is not None:
            return {**replay, 'documents': [self._clean_document_prelude(doc) for doc in replay['documents']],
                    'budget': self.status()['budget'], 'replayed': True}
        documents, errors, skipped_urls = [], [], []
        stopped = False
        try:
            for entry, cached in work:
                if cached:
                    documents.append(cached)
                    continue
                if stopped:
                    skipped_urls.append(entry['url'])
                    continue
                try:
                    self.assert_public_dns(entry['url'])
                    self._mark_attempt(plan_id)
                    document = self._document(entry['url'], self._scrape(entry['url']))
                    with self.db() as conn:
                        conn.execute('INSERT OR REPLACE INTO cache (url,fetched,document) VALUES (?,?,?)',
                                     (entry['url'], self.clock(), json.dumps(document, ensure_ascii=False)))
                    documents.append(document)
                except SourceImportError as exc:
                    errors.append({'url': entry['url'], 'code': exc.code, 'error': str(exc)})
                    # Stop spending after the first failure, while retaining
                    # later cache hits regardless of the submitted URL order.
                    stopped = True
                except Exception:
                    errors.append({'url': entry['url'], 'code': 'storage',
                                   'error': '資料收集已停止，請稍後再試。'})
                    stopped = True
        except Exception:
            errors.append({'code': 'storage', 'error': '資料收集已停止，請稍後再試。'})
        finally:
            with self.db() as conn:
                attempted = conn.execute('SELECT attempted FROM plans WHERE id=?', (plan_id,)).fetchone()['attempted']
                result = {'documents': documents, 'errors': errors, 'skipped_urls': skipped_urls,
                          'attempted': attempted,
                          'cloud_credits': 0, 'replayed': False,
                          'status': 'failed' if errors else 'completed'}
                conn.execute("UPDATE plans SET status=?, reserved=0, result=? WHERE id=?",
                             (result['status'], json.dumps(result, ensure_ascii=False), plan_id))
        return {**result, 'budget': self.status()['budget']}
