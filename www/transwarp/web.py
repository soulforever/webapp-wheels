# -*- coding: utf-8 -*-
__author__ = 'guti'


import os
import threading
import datetime
import re
import urllib
import string
import mimetypes
import cgi
import logging

from copy import deepcopy
from db import Dict


# letters and digits
_LETTERS_DIGITS = string.letters + string.digits
# block size when read the file.
_BLOCK_SIZE = 1024 * 8
# thread local context object.
context = threading.local()
# define constant for 0 timedelta.
_TIMEDELTA_ZERO = datetime.timedelta(0)
# a compiled regular expression for utc time.
_RE_TZ = re.compile(r'^([\+\-])([0-9]{1,2}):([0-9]{1,2})$')
# a compiled regular expression for response status.
_RE_RESPONSE_STATUS = re.compile(r'^\d\d\d( [\w ]+)?$')
# a compiled regular expression for route.
_RE_ROUTE = re.compile(r'(:[a-zA-Z_]\w*)')
# all known response status.
_RESPONSE_STATUSES = {
    # Informational
    100: 'Continue',
    101: 'Switching Protocols',
    102: 'Processing',

    # Successful
    200: 'OK',
    201: 'Created',
    202: 'Accepted',
    203: 'Non-Authoritative Information',
    204: 'No Content',
    205: 'Reset Content',
    206: 'Partial Content',
    207: 'Multi Status',
    226: 'IM Used',

    # Redirection
    300: 'Multiple Choices',
    301: 'Moved Permanently',
    302: 'Found',
    303: 'See Other',
    304: 'Not Modified',
    305: 'Use Proxy',
    307: 'Temporary Redirect',

    # Client Error
    400: 'Bad Request',
    401: 'Unauthorized',
    402: 'Payment Required',
    403: 'Forbidden',
    404: 'Not Found',
    405: 'Method Not Allowed',
    406: 'Not Acceptable',
    407: 'Proxy Authentication Required',
    408: 'Request Timeout',
    409: 'Conflict',
    410: 'Gone',
    411: 'Length Required',
    412: 'Precondition Failed',
    413: 'Request Entity Too Large',
    414: 'Request URI Too Long',
    415: 'Unsupported Media Type',
    416: 'Requested Range Not Satisfiable',
    417: 'Expectation Failed',
    418: "I'm a teapot",
    422: 'Unprocessable Entity',
    423: 'Locked',
    424: 'Failed Dependency',
    426: 'Upgrade Required',

    # Server Error
    500: 'Internal Server Error',
    501: 'Not Implemented',
    502: 'Bad Gateway',
    503: 'Service Unavailable',
    504: 'Gateway Timeout',
    505: 'HTTP Version Not Supported',
    507: 'Insufficient Storage',
    510: 'Not Extended',
}
# keys in response headers.
_RESPONSE_HEADERS = (
    'Accept-Ranges',
    'Age',
    'Allow',
    'Cache-Control',
    'Connection',
    'Content-Encoding',
    'Content-Language',
    'Content-Length',
    'Content-Location',
    'Content-MD5',
    'Content-Disposition',
    'Content-Range',
    'Content-Type',
    'Date',
    'ETag',
    'Expires',
    'Last-Modified',
    'Link',
    'Location',
    'P3P',
    'Pragma',
    'Proxy-Authenticate',
    'Refresh',
    'Retry-After',
    'Server',
    'Set-Cookie',
    'Strict-Transport-Security',
    'Trailer',
    'Transfer-Encoding',
    'Vary',
    'Via',
    'Warning',
    'WWW-Authenticate',
    'X-Frame-Options',
    'X-XSS-Protection',
    'X-Content-Type-Options',
    'X-Forwarded-Proto',
    'X-Powered-By',
    'X-UA-Compatible',
)
# user upper string as key for keys in response headers.
_RESPONSE_HEADER_DICT = dict(zip(map(lambda x: x.upper(), _RESPONSE_HEADERS), _RESPONSE_HEADERS))
# TODO: what's this??
_HEADER_X_POWERED_BY = ('X-Powered-By', 'transwarp/1.0')


class UTC(datetime.tzinfo):
    """
    A UTC time zone information object.

    >>> tz0 = UTC('+00:00')
    >>> tz0.tzname(None)
    'UTC+00:00'
    >>> tz8 = UTC('+8:00')
    >>> tz8.tzname(None)
    'UTC+8:00'
    >>> tz7 = UTC('+7:30')
    >>> tz7.tzname(None)
    'UTC+7:30'
    >>> tz5 = UTC('-05:30')
    >>> tz5.tzname(None)
    'UTC-05:30'
    >>> u = datetime.datetime.utcnow().replace(tzinfo=tz0)
    >>> l1 = u.astimezone(tz8)
    >>> l2 = u.replace(tzinfo=tz8)
    >>> d1 = u - l1
    >>> d2 = u - l2
    >>> d1.seconds
    0
    >>> d2.seconds
    28800
    """

    def __init__(self, utc, *args, **kwargs):
        super(UTC, self).__init__(*args, **kwargs)
        utc = str(utc.strip().upper())
        mt = _RE_TZ.match(utc)
        if mt:
            minus = mt.group(1)
            hours = int(mt.group(2))
            minutes = int(mt.group(3))
            if minus == '-':
                hours, minutes = (-hours), (-minutes)
            self._utc_offset = datetime.timedelta(hours=hours, minutes=minutes)
            self._tz_name = 'UTC%s' % utc
        else:
            raise ValueError('Bad utc time zone.')

    def utcoffset(self, date_time):
        return self._utc_offset

    def dst(self, date_time):
        return _TIMEDELTA_ZERO

    def tzname(self, date_time):
        return self._tz_name

    def __str__(self):
        return 'UTC time zone information object (%s)' % self._tz_name

    __repr__ = __str__

# zero UTC time.
_UTC_0 = UTC('+00:00')


class HttpError(Exception):
    """
     HttpError that defines http error code.

    >>> e = HttpError(404)
    >>> e.status
    '404 Not Found'
    >>> e.headers
    [('X-Powered-By', 'transwarp/1.0')]
    >>> e.header('Content-Encoding', 'utf-8')
    >>> e.headers
    [('X-Powered-By', 'transwarp/1.0'), ('Content-Encoding', 'utf-8')]
    >>> e
    404 Not Found
    >>> print e
    404 Not Found
    """
    def __init__(self, code):
        """
        :param code: http response code, like keys in _RESPONSE_STATUSES
        """
        super(HttpError, self).__init__()
        self.status = '%d %s' % (code, _RESPONSE_STATUSES[code])
        if not hasattr(self, '_headers'):
            self._headers = [_HEADER_X_POWERED_BY]

    def header(self, name, value):
        self._headers.append((name, value))

    @property
    def headers(self):
        return self._headers

    def __str__(self):
        return self.status

    __repr__ = __str__


class RedirectError(HttpError):
    """
    RedirectError that defines http redirect code.

    >>> e = RedirectError(302, 'http://www.apple.com/')
    >>> e.status
    '302 Found'
    >>> e.location
    'http://www.apple.com/'
    """
    def __init__(self, code, location):
        """
        :param code: response code.
        :param location: response location url
        """
        super(RedirectError, self).__init__(code)
        self.location = location

    def __str__(self):
        return '%s, %s' % (self.status, self.location)

    __repr__ = __str__


def bad_request():
    """
    Bad request response.

    >>> raise bad_request()
    Traceback (most recent call last):
        ...
    HttpError: 400 Bad Request
    """
    return HttpError(400)


def unauthorized():
    """
    unauthorized response.

    >>> raise unauthorized()
    Traceback (most recent call last):
        ...
    HttpError: 401 Unauthorized
    """
    return HttpError(401)


def forbidden():
    """
    Http request forbidden response

    >>> raise forbidden()
    Traceback (most recent call last):
      ...
    HttpError: 403 Forbidden
    """
    return HttpError(403)


def not_found():
    """
    Send a not found response.

    >>> raise not_found()
    Traceback (most recent call last):
      ...
    HttpError: 404 Not Found
    """
    return HttpError(404)


def conflict():
    """
    Send a conflict response.

    >>> raise conflict()
    Traceback (most recent call last):
      ...
    HttpError: 409 Conflict
    """
    return HttpError(409)


def internal_error():
    """
    Send an internal error response.

    >>> raise internal_error()
    Traceback (most recent call last):
      ...
    HttpError: 500 Internal Server Error
    """
    return HttpError(500)


def redirect(location):
    """
    Do permanent redirect.

    >>> raise redirect('http://www.itranswarp.com/')
    Traceback (most recent call last):
      ...
    RedirectError: 301 Moved Permanently, http://www.itranswarp.com/
    """
    return RedirectError(301, location)


def found(location):
    """
    Do temporary redirect.

    >>> raise found('http://www.itranswarp.com/')
    Traceback (most recent call last):
      ...
    RedirectError: 302 Found, http://www.itranswarp.com/
    """
    return RedirectError(302, location)


def see_other(location):
    """
    Do temporary redirect.

    >>> raise see_other('http://www.itranswarp.com/')
    Traceback (most recent call last):
      ...
    RedirectError: 303 See Other, http://www.itranswarp.com/
    >>> e = see_other('http://www.itranswarp.com/seeother?r=123')
    >>> e.location
    'http://www.itranswarp.com/seeother?r=123'
    """
    return RedirectError(303, location)


def _to_str(s):
    """
    Convert object to string

    >>> _to_str('123') == '123'
    True
    >>> _to_str(u'\u4e2d\u6587') == '中文'
    True
    >>> _to_str(-123) == '-123'
    True
    """
    if isinstance(s, unicode):
        return s.encode('utf-8')
    else:
        return str(s)


def _to_encode(s, encoding='utf-8'):
    """
    Convert string to unicode as default.
    >>> _to_encode('中文') == u'\u4e2d\u6587'
    True
    """
    return s.decode(encoding)


def _quote(s, encoding='utf-8'):
    """
    Url quote as str.

    >>> _quote('http://example/test?a=1+')
    'http%3A//example/test%3Fa%3D1%2B'
    >>> _quote(u"hello world!")
    'hello%20world%21'
    >>> _quote('http://example/s=中文')
    'http%3A//example/s%3D%E4%B8%AD%E6%96%87'
    """
    if isinstance(s, unicode):
        s = s.encode(encoding)
    return urllib.quote(s)


def _unquote(s, encoding='utf-8'):
    """
    Url unquote as unicode.

    >>> _unquote('http%3A//example/test%3Fa%3D1+')
    u'http://example/test?a=1+'
    """
    return urllib.unquote(s).decode(encoding)


def get(path):
    """
    A @get decorator.

    @get('/:id')
    def index(id):
        pass
    >>> @get('/test/:id')
    ... def test():
    ...     return 'ok'
    ...
    >>> test.__web_route__
    '/test/:id'
    >>> test.__web_method__
    'GET'
    >>> test()
    'ok'
    """
    def _decorator(func):
        func.__web_route__ = path
        func.__web_method__ = 'GET'
        return func
    return _decorator


def post(path):
    """
    A @get decorator.

    @get('/:id')
    def index(id):
        pass
    >>> @post('/test/:id')
    ... def test():
    ...     return 'ok'
    ...
    >>> test.__web_route__
    '/test/:id'
    >>> test.__web_method__
    'POST'
    >>> test()
    'ok'
    """
    def _decorator(func):
        func.__web_route__ = path
        func.__web_method__ = 'POST'
        return func
    return _decorator


class Route(object):
    """
    Route object for record route information

    >>> @post('/test/:id')
    ... def test():
    ...     return 'ok'
    ...
    >>> r = Route(test)
    >>> r.path
    '/test/:id'
    >>> r.method
    'POST'
    >>> r.is_static
    False
    """
    def __init__(self, func):
        self.path = func.__web_route__
        self.method = func.__web_method__
        self.is_static = _RE_ROUTE.search(self.path) is None
        if not self.is_static:
            self.route = re.compile(self._build_regex(self.path))
        self.func = func

    @staticmethod
    def _build_regex(path):
        r"""
        Convert route path to regular expression.

        >>> @post('/test/:id')
        ... def test():
        ...     return 'ok'
        ...
        >>> r = Route(test)
        >>> Route._build_regex('/path/to/:file')
        '^\\/path\\/to\\/(?P<file>[^\\/]+)$'
        >>> Route._build_regex('/:user/:comments/list')
        '^\\/(?P<user>[^\\/]+)\\/(?P<comments>[^\\/]+)\\/list$'
        >>> Route._build_regex(':id-:pid/:w')
        '^(?P<id>[^\\/]+)\\-(?P<pid>[^\\/]+)\\/(?P<w>[^\\/]+)$'
        """
        re_list = ['^']
        var_list = list()
        is_var = False
        for v in _RE_ROUTE.split(path):
            if is_var:
                var_name = v[1:]
                var_list.append(var_name)
                re_list.append(r'(?P<%s>[^\/]+)' % var_name)
            else:
                s = ''
                for ch in v:
                    if ch in _LETTERS_DIGITS:
                        s += ch
                    else:
                        s += '\\' + ch
                re_list.append(s)
            is_var = not is_var
        re_list.append('$')
        return ''.join(re_list)

    def match(self, url):
        m = self.route.match(url)
        return m.groups() if m else None

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def __str__(self):
        status = 'static' if self.is_static else 'dynamic'
        return 'Route %s: %s, path=%s' % (status, self.method, self.path)

    __repr__ = __str__


class StaticFileRoute(object):
    def __init__(self):
        self.method = 'GET'
        self.is_static = False
        self.route = re.compile('^/static/(.+)$')

    def match(self, url):
        if url.startwith('/static/'):
            return url[1:]
        return None

    def __call__(self, *args):
        file_path = os.path.join(context.application.document_root, args[0])
        if not os.path.isdir(file_path):
            raise not_found()
        file_ext = os.path.splitext(file_path)[1]
        context.response.content_type = mimetypes.types_map.get(file_ext, 'application/octet-stream')
        return self._static_file_generator(file_path)

    @staticmethod
    def _static_file_generator(file_path):
        with open(file_path, 'rb') as f:
            block = f.read(_BLOCK_SIZE)
            while block:
                yield block
                block = f.read(_BLOCK_SIZE)


class MultiPartFile(object):
    """
    Multi Part file storage get from request input.

    f = ctx.request['file']
    f.filename # 'test.png'
    f.file # file-like object
    """
    def __init__(self, storage):
        self.filename = _to_encode(storage.filename)
        self.file = storage.file


class Request(object):
    """
    Request object for obtaining all http request information.
    """
    def __init__(self, env):
        # record the environment of the request object.
        self._env = env

    def _parse_input(self):
        def _convert(item):
            if isinstance(item, list):
                return [_to_encode(o.value) for o in item]
            if item.filename:
                return MultiPartFile(item)
            return _to_encode(item.value)
        fs = cgi.FieldStorage(fp=self._env['wsgi.input'], environ=self._env, keep_blank_values=True)
        inputs = dict()
        for key in fs:
            inputs[key] = _convert(fs[key])
        return inputs

    def _get_raw_input(self):
        """
        Get raw input as dict containing values as unicode, list or MultiPartFile.
        """
        if not hasattr(self, '_raw_input'):
            self._raw_input = self._parse_input()
        return self._raw_input

    def __getitem__(self, item):
        r"""
        Get input parameter value. If the specified key has multiple value, the first one is returned.
        If the specified key is not exist, then raise KeyError.

        >>> from StringIO import StringIO
        >>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('a=1&b=M%20M&c=ABC&c=XYZ&e=')})
        >>> r['a']
        u'1'
        >>> r['c']
        u'ABC'
        >>> r['empty']
        Traceback (most recent call last):
            ...
        KeyError: 'empty'
        >>> b = '----WebKitFormBoundaryQQ3J8kPsjFpTmqNz'
        >>> pl = ['--%s' % b, 'Content-Disposition: form-data; name="name"\n',
        ... 'Scofield', '--%s' % b, 'Content-Disposition: form-data; name="name"\n',
        ... 'Lincoln', '--%s' % b, 'Content-Disposition: form-data; name="file"; filename="test.txt"',
        ... 'Content-Type: text/plain\n', 'just a test', '--%s' % b,
        ... 'Content-Disposition: form-data; name="id"\n', '4008009001', '--%s--' % b, '']
        >>> payload = '\n'.join(pl)
        >>> r = Request({'REQUEST_METHOD':'POST', 'CONTENT_LENGTH':str(len(payload)),
        ... 'CONTENT_TYPE':'multipart/form-data; boundary=%s' % b, 'wsgi.input':StringIO(payload)})
        >>> r.get('name')
        u'Scofield'
        >>> r.gets('name')
        [u'Scofield', u'Lincoln']
        >>> f = r.get('file')
        >>> f.filename
        u'test.txt'
        >>> f.file.read()
        'just a test'
        """
        result = self._get_raw_input()[item]
        return result[0] if isinstance(result, list) else result

    def get(self, key, default=None):
        """
        Get value from request by key.It's the same as request[key], but return default value if key isn't in request.

        >>> from StringIO import StringIO
        >>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('a=1&b=M%20M&c=ABC&c=XYZ&e=')})
        >>> r.get('a')
        u'1'
        >>> r.get('empty')
        >>> r.get('empty', 'DEFAULT')
        'DEFAULT'
        """
        result = self._get_raw_input().get(key, default)
        return result[0] if isinstance(result, list) else result

    def gets(self, key):
        """
        Get multiple values for specified key. If the specified key is not exist, then raise KeyError.

        >>> from StringIO import StringIO
        >>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('a=1&b=M%20M&c=ABC&c=XYZ&e=')})
        >>> r.gets('a')
        [u'1']
        >>> r.gets('c')
        [u'ABC', u'XYZ']
        >>> r.gets('empty')
        Traceback (most recent call last):
            ...
        KeyError: 'empty'
        """
        result = self._get_raw_input()[key]
        if isinstance(result, list):
            return deepcopy(result)
        return [result]

    def input(self, **kwargs):
        """
        Get input as dict from request, fill dict using provided default value if key not exist.

        i = ctx.request.input(role='guest')
        i.role ==> 'guest'
        >>> from StringIO import StringIO
        >>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('a=1&b=M%20M&c=ABC&c=XYZ&e=')})
        >>> i = r.input(x=2008)
        >>> i.a
        u'1'
        >>> i.b
        u'M M'
        >>> i.c
        u'ABC'
        >>> i.x
        2008
        >>> i.get('d', u'100')
        u'100'
        >>> i.x
        2008
        """
        copy = Dict(**kwargs)
        raw = self._get_raw_input()
        for k, v in raw.iteritems():
            copy[k] = v[0] if isinstance(v, list) else v
        return copy

    def get_body(self):
        """
        Get raw data from HTTP POST and return as string.

        >>> from StringIO import StringIO
        >>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('<xml><raw/>')})
        >>> r.get_body()
        '<xml><raw/>'
        """
        fp = self._env['wsgi.input']
        return fp.read()

    @property
    def remote_addr(self):
        """
        Get remote addr. Return '0.0.0.0' if cannot get remote_addr.

        >>> r = Request({'REMOTE_ADDR': '192.168.0.100'})
        >>> r.remote_addr
        '192.168.0.100'
        """
        return self._env.get('REMOTE_ADDR', '0.0.0.0')

    @property
    def document_root(self):
        """
        Get raw document_root as str. Return '' if no document_root.
        >>> r = Request({'DOCUMENT_ROOT': '/srv/path/to/doc'})
        >>> r.document_root
        '/srv/path/to/doc'
        """
        return self._env.get('DOCUMENT_ROOT', '')

    @property
    def query_string(self):
        """
        Get raw query string as str. Return '' if no query string.
        >>> r = Request({'QUERY_STRING': 'a=1&c=2'})
        >>> r.query_string
        'a=1&c=2'
        >>> r = Request({})
        >>> r.query_string
        ''
        """
        return self._env.get('QUERY_STRING', '')

    @property
    def environment(self):
        """
        Get raw environ as dict, both key, value are str.

        >>> r = Request({'REQUEST_METHOD': 'GET', 'wsgi.url_scheme':'http'})
        >>> r.environment.get('REQUEST_METHOD')
        'GET'
        >>> r.environment.get('wsgi.url_scheme')
        'http'
        >>> r.environment.get('SERVER_NAME')
        >>> r.environment.get('SERVER_NAME', 'name')
        'name'
        """
        return self._env

    @property
    def request_method(self):
        """
        Get request method. The valid returned values are 'GET', 'POST', 'HEAD'.

        >>> r = Request({'REQUEST_METHOD': 'GET'})
        >>> r.request_method
        'GET'
        >>> r = Request({'REQUEST_METHOD': 'POST'})
        >>> r.request_method
        'POST'
        """
        return self._env['REQUEST_METHOD']

    # TODO: check _unquote function
    @property
    def path_info(self):
        """
        Get request path as str.

        >>> r = Request({'PATH_INFO': '/test/a%20b.html'})
        >>> r.path_info
        '/test/a b.html'
        """
        return urllib.unquote(self._env.get('PATH_INFO', ''))

    @property
    def host(self):
        """
        Get request host as str. Default to '' if cannot get host.

        >>> r = Request({'HTTP_HOST': 'localhost:8080'})
        >>> r.host
        'localhost:8080'
        """
        return self._env.get('HTTP_HOST', '')

    def _get_headers(self):
        if not hasattr(self, '_headers'):
            headers = dict()
            for k, v in self._env.iteritems():
                if k.startswith('HTTP_'):
                    # convert 'HTTP_ACCEPT_ENCODING' to 'ACCEPT-ENCODING'
                    headers[k[5:].replace('_', '-').upper()] = _to_encode(v)
            self._headers = headers
        return self._headers

    @property
    def headers(self):
        """
        Get all HTTP headers with key as str and value as unicode. The header names are 'XXX-XXX' uppercase.

        >>> r = Request({'HTTP_USER_AGENT': 'Mozilla/5.0', 'HTTP_ACCEPT': 'text/html'})
        >>> H = r.headers
        >>> H['ACCEPT']
        u'text/html'
        >>> H['USER-AGENT']
        u'Mozilla/5.0'
        >>> L = H.items()
        >>> L.sort()
        >>> L
        [('ACCEPT', u'text/html'), ('USER-AGENT', u'Mozilla/5.0')]
        """
        return Dict(**self._get_headers())

    def header(self, key, default=None):
        """
        Get header from request as unicode, return None if not exist, or default if specified.
        The header name is case-insensitive such as "USER-AGENT" or u"Content-Type".

        >>> r = Request({'HTTP_USER_AGENT': 'Mozilla/5.0', 'HTTP_ACCEPT': 'text/html'})
        >>> r.header('User-Agent')
        u'Mozilla/5.0'
        >>> r.header('USER-AGENT')
        u'Mozilla/5.0'
        >>> r.header('Accept')
        u'text/html'
        >>> r.header('Test')
        >>> r.header('Test', u'DEFAULT')
        u'DEFAULT'
        """
        return self._get_headers().get(key.upper(), default)

    def _get_cookies(self):
        if not hasattr(self, '_cookies'):
            cookies = dict()
            cookie_str = self._env.get('HTTP_COOKIE')
            if cookie_str:
                for c in cookie_str.split(';'):
                    position = c.find('=')
                    if position > 0:
                        cookies[c[:position].strip()] = _unquote(c[position+1:])
            self._cookies = cookies
        return self._cookies

    @property
    def cookies(self):
        """
        Return all cookies as dict. The cookie name is str and values is unicode.
        >>> r = Request({'HTTP_COOKIE':'A=123; url=http%3A%2F%2Fwww.example.com%2F'})
        >>> r.cookies['A']
        u'123'
        >>> r.cookies.url
        u'http://www.example.com/'
        >>>
        """
        return Dict(**self._get_cookies())

    # get value by key in cookie
    def cookie(self, key, default=None):
        """
        Return specified cookie value as unicode. Default to None if cookie not exists.

        >>> r = Request({'HTTP_COOKIE':'A=123; url=http%3A%2F%2Fwww.example.com%2F'})
        >>> r.cookie('A')
        u'123'
        >>> r.cookie('url')
        u'http://www.example.com/'
        >>> r.cookie('test')
        >>> r.cookie('test', u'DEFAULT')
        u'DEFAULT'
        """
        return self._get_cookies().get(key, default)


class Response(object):

    def __init__(self):
        self._status = '200 OK'
        self._headers = {'CONTENT-TYPE': 'text/html; charset=utf-8'}

    def set_header(self, key, value):
        pass

    def set_cookie(self, key, value, max_age=None, expires=None, path='/'):
        pass

    @property
    def status(self):
        pass

    @ status.setter
    def status(self, value):
        pass

    # http get
    def get(self, path):
        pass

    # http post
    def post(self, path):
        pass

    # http model
    def view(self, path):
        pass

    def interceptor(self):
        pass


class TemplateEngine(object):
    def __call__(self, *args, **kwargs):
        pass


class Jinja2TemplateEngine(TemplateEngine):
    def __init__(self, tmp_dir, **kwargs):
        from jinja2 import Environment, FileSystemLoader
        self._env = Environment(loader=FileSystemLoader(tmp_dir), **kwargs)

    def __call__(self, path, model):
        return self._env.get_template(path).render(**model).encode('utf-8')


class WSGIApplication(object):
    def __init__(self, document_root=None, **kwargs):
        pass

    # add an url define
    def add_url(self, func):
        pass

    def add_interceptor(self, func):
        pass

    @property
    def template_engine(self):
        pass

    @template_engine.setter
    def template_engine(self, engine):
        pass

    def get_wsgi_application(self):
        def wsgi(env, start_respone):
            pass
        return wsgi

    # when in the develop mode, it will restart the server.
    def run(self, host='127.0.0.1', port=9000):
        from wsgiref.simple_server import make_server
        server = make_server(host, port, self.get_wsgi_application())
        server.serve_forever()


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    import doctest
    doctest.testmod()