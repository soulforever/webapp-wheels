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
import functools

from abc import abstractmethod
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
# a compiled regular expression for the start of interceptor
_RE_INTERCEPTOR_STARTS_WITH = re.compile(r'^([^\*\?]+)\*?$')
# a compiled regular expression for the end of interceptor
_RE_INTERCEPTOR_ENDS_WITH = re.compile(r'^\*([^\*\?]+)$')
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


def view(path):
    """
    A view decorator that render a view by dict.

    >>> @view('test/view.html')
    ... def hello():
    ...     return dict(name='Bob')
    >>> t = hello()
    >>> isinstance(t, Template)
    True
    >>> t.template_name
    'test/view.html'
    >>> @view('test/view.html')
    ... def hello2():
    ...     return ['a list']
    >>> t = hello2()
    Traceback (most recent call last):
      ...
    ValueError: Expect return a dict when using @view() decorator.
    """
    def _decorator(func):
        @functools.wraps(func)
        def _wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            if isinstance(result, dict):
                logging.info('Return template.')
                return Template(path, **result)
            raise ValueError('Expect return a dict when using @view() decorator.')
        return _wrapper
    return _decorator




def _build_pattern_fn(pattern):
    m = _RE_INTERCEPTOR_STARTS_WITH.match(pattern)
    if m:
        return lambda p: p.startswith(m.group(1))
    m = _RE_INTERCEPTOR_ENDS_WITH.match(pattern)
    if m:
        return lambda p: p.endswith(m.group(1))
    raise ValueError('Invalid pattern definition in interceptor.')


def interceptor(pattern='/'):
    """
    An @interceptor decorator.

    @interceptor('/admin/')
    def check_admin(req, resp):
        pass
    """
    def _decorator(func):
        func.__interceptor__ = _build_pattern_fn(pattern)
        return func
    return _decorator


def _build_interceptor_fn(func, next_fn):
    def _wrapper():
        if func.__interceptor__(context.request.path_info):
            return func(next_fn)
        else:
            return next_fn()
    return _wrapper


def _build_interceptor_chain(last_fn, *interceptors):
    """
    Build interceptor chain.

    >>> def target():
    ...     print 'target'
    ...     return 123
    >>> @interceptor('/')
    ... def f1(next):
    ...     print 'before f1()'
    ...     return next()
    >>> @interceptor('/test/')
    ... def f2(next):
    ...     print 'before f2()'
    ...     try:
    ...         return next()
    ...     finally:
    ...         print 'after f2()'
    >>> @interceptor('/')
    ... def f3(next):
    ...     print 'before f3()'
    ...     try:
    ...         return next()
    ...     finally:
    ...         print 'after f3()'
    >>> chain = _build_interceptor_chain(target, f1, f2, f3)
    >>> context.request = Dict(path_info='/test/abc')
    >>> chain()
    before f1()
    before f2()
    before f3()
    target
    after f3()
    after f2()
    123
    >>> context.request = Dict(path_info='/api/')
    >>> chain()
    before f1()
    before f3()
    target
    after f3()
    123
    """
    ic_list = list(interceptors)
    ic_list.reverse()
    fn = last_fn
    for f in ic_list:
        fn = _build_interceptor_fn(f, fn)
    return fn


def _load_module(module_name):
    """
    Load module from name as str.

    >>> m = _load_module('xml')
    >>> m.__name__
    'xml'
    >>> m = _load_module('xml.sax')
    >>> m.__name__
    'xml.sax'
    >>> m = _load_module('xml.sax.handler')
    >>> m.__name__
    'xml.sax.handler'
    """
    last_dot = module_name.rfind('.')
    if last_dot == -1:
        return __import__(module_name, globals(), locals())
    from_module = module_name[:last_dot]
    import_module = module_name[last_dot+1:]
    m = __import__(from_module, globals(), locals(), [import_module])
    return getattr(m, import_module)


def _default_error_handler(e, start_response, is_debug):
    if isinstance(e, HttpError):
        logging.info('HttpError: %s' % e.status)
        headers = e.headers[:]
        headers.append(('Content-Type', 'text/html'))
        start_response(e.status, headers)
        return '<html><body><h1>%s</h1></body></html>' % e.status
    logging.exception('Exception:')
    start_response('500 Internal Server Error', [('Content-Type', 'text/html'), _HEADER_X_POWERED_BY])
    if is_debug:
        # return _debug()
        logging.info('Debug...')
    return '<html><body><h1>500 Internal Server Error</h1><h3>%s</h3></body></html>' % str(e)


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
        self._environ = env

    def _parse_input(self):
        def _convert(item):
            if isinstance(item, list):
                return [_to_encode(o.value) for o in item]
            if item.filename:
                return MultiPartFile(item)
            return _to_encode(item.value)
        fs = cgi.FieldStorage(fp=self._environ['wsgi.input'], environ=self._environ, keep_blank_values=True)
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
        fp = self._environ['wsgi.input']
        return fp.read()

    @property
    def remote_addr(self):
        """
        Get remote addr. Return '0.0.0.0' if cannot get remote_addr.

        >>> r = Request({'REMOTE_ADDR': '192.168.0.100'})
        >>> r.remote_addr
        '192.168.0.100'
        """
        return self._environ.get('REMOTE_ADDR', '0.0.0.0')

    @property
    def document_root(self):
        """
        Get raw document_root as str. Return '' if no document_root.
        >>> r = Request({'DOCUMENT_ROOT': '/srv/path/to/doc'})
        >>> r.document_root
        '/srv/path/to/doc'
        """
        return self._environ.get('DOCUMENT_ROOT', '')

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
        return self._environ.get('QUERY_STRING', '')

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
        return self._environ

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
        return self._environ['REQUEST_METHOD']

    # TODO: check _unquote function
    @property
    def path_info(self):
        """
        Get request path as str.

        >>> r = Request({'PATH_INFO': '/test/a%20b.html'})
        >>> r.path_info
        '/test/a b.html'
        """
        return urllib.unquote(self._environ.get('PATH_INFO', ''))

    @property
    def host(self):
        """
        Get request host as str. Default to '' if cannot get host.

        >>> r = Request({'HTTP_HOST': 'localhost:8080'})
        >>> r.host
        'localhost:8080'
        """
        return self._environ.get('HTTP_HOST', '')

    def _get_headers(self):
        if not hasattr(self, '_headers'):
            headers = dict()
            for k, v in self._environ.iteritems():
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
            cookie_str = self._environ.get('HTTP_COOKIE')
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

    @property
    def headers(self):
        """
        Return response headers as [(key1, value1), (key2, value2)...] including cookies.

        >>> r = Response()
        >>> r.headers
        [('Content-Type', 'text/html; charset=utf-8'), ('X-Powered-By', 'transwarp/1.0')]
        >>> r.set_cookie('s1', 'ok', 3600)
        >>> r.headers
        [('Content-Type', 'text/html; charset=utf-8'), ('Set-Cookie', 's1=ok; Max-Age=3600; Path=/; HttpOnly'),\
 ('X-Powered-By', 'transwarp/1.0')]
        """
        header_list = [(_RESPONSE_HEADER_DICT.get(k, k), v) for k, v in self._headers.iteritems()]
        if hasattr(self, '_cookies'):
            for v in self._cookies.itervalues():
                header_list.append(('Set-Cookie', v))
        header_list.append(_HEADER_X_POWERED_BY)
        return header_list

    def header(self, name):
        """
        Get header by name, case-insensitive.

        >>> r = Response()
        >>> r.header('content-type')
        'text/html; charset=utf-8'
        >>> r.header('CONTENT-type')
        'text/html; charset=utf-8'
        >>> r.header('X-Powered-By')
        """
        key = name.upper()
        if key not in _RESPONSE_HEADER_DICT:
            key = name
        return self._headers.get(key)

    def del_header(self, name):
        """
        Delete header by name and value.

        >>> r = Response()
        >>> r.header('content-type')
        'text/html; charset=utf-8'
        >>> r.del_header('CONTENT-type')
        >>> r.header('content-type')
        """
        key = name.upper()
        if key not in _RESPONSE_HEADER_DICT:
            key = name
        if key in self._headers:
            del self._headers[key]

    def set_header(self, name, value):
        """
        Set header by name and value.

        >>> r = Response()
        >>> r.header('content-type')
        'text/html; charset=utf-8'
        >>> r.set_header('CONTENT-type', 'image/png')
        >>> r.header('content-TYPE')
        'image/png'
        """
        key = name.upper()
        if key not in _RESPONSE_HEADER_DICT:
            key = name
        self._headers[key] = _to_str(value)

    @property
    def content_type(self):
        """
        Get content type from response. This is a shortcut for header('Content-Type').

        >>> r = Response()
        >>> r.content_type
        'text/html; charset=utf-8'
        >>> r.content_type = 'application/json'
        >>> r.content_type
        'application/json'
        """
        return self._headers['CONTENT-TYPE']

    @content_type.setter
    def content_type(self, value):
        """
        Set content type for response. This is a shortcut for set_header('Content-Type', value).
        If value is None, del the content type in headers
        """
        if value:
            self._headers['CONTENT-TYPE'] = value
        else:
            self.del_header('CONTENT-TYPE')

    @property
    def content_len(self):
        """
        Get content length. Return None if not set.

        >>> r = Response()
        >>> r.content_len
        >>> r.content_len = 100
        >>> r.content_len
        '100'
        """
        return self.header('CONTENT-LENGTH')

    @content_len.setter
    def content_len(self, value):
        """
        Set content length, the value can be int or str.

        >>> r = Response()
        >>> r.content_len = '1024'
        >>> r.content_len
        '1024'
        >>> r.content_len = 1024 * 8
        >>> r.content_len
        '8192'
        """
        self.set_header('CONTENT-LENGTH', value)

    def del_cookie(self, name):
        """
        Delete a cookie immediately.
        """
        self.set_cookie(name, '__deleted__', expires=0)

    def set_cookie(self, name, value, max_age=None, expires=None, path='/', domain=None, secure=False,
                   http_only=True):
        """
        Set a cookie.

        :param name: the cookie name.
        :param value: the cookie value.
        :param max_age: optional, seconds of cookie's max age.
        :param expires: optional, unix timestamp, datetime or date object that indicate an absolute time of the
                        expiration time of cookie. Note that if expires specified, the max_age will be ignored.
        :param path: the cookie path, default to '/'.
        :param domain: the cookie domain, default to None.
        :param secure: if the cookie secure, default to False.
        :param http_only: if the cookie is for http only, default to True for better safety.
                          (client-side script cannot access cookies with HttpOnly flag).

        >>> r = Response()
        >>> r.set_cookie('company', 'Abc, Inc.', max_age=3600)
        >>> r._cookies
        {'company': 'company=Abc%2C%20Inc.; Max-Age=3600; Path=/; HttpOnly'}
        >>> r.set_cookie('company', r'Example="Limited"', expires=1342274794.123, path='/sub/')
        >>> r._cookies
        {'company': 'company=Example%3D%22Limited%22; Expires=Sat, 14-Jul-2012 14:06:34 GMT; Path=/sub/; HttpOnly'}
        >>> dt = datetime.datetime(2012, 7, 14, 22, 6, 34, tzinfo=UTC('+8:00'))
        >>> r.set_cookie('company', 'Expires', expires=dt)
        >>> r._cookies
        {'company': 'company=Expires; Expires=Sat, 14-Jul-2012 14:06:34 GMT; Path=/; HttpOnly'}
        """
        if not hasattr(self, '_cookies'):
            self._cookies = dict()
        cookie_list = ['%s=%s' % (_quote(name), _quote(value))]
        if isinstance(max_age, (int, long)):
            cookie_list.append('Max-Age=%d' % max_age)
        if expires is not None:
            time_str = ''
            if isinstance(expires, (int, float, long)):
                time_str = datetime.datetime.fromtimestamp(expires, _UTC_0).strftime('%a, %d-%b-%Y %H:%M:%S GMT')
            if isinstance(expires, (datetime.date, datetime.datetime)):
                time_str = expires.astimezone(_UTC_0).strftime('%a, %d-%b-%Y %H:%M:%S GMT')
            cookie_list.append('Expires=%s' % time_str)
        cookie_list.append('Path=%s' % path)
        if domain:
            cookie_list.append('Domain=%s' % domain)
        if secure:
            cookie_list.append('Secure')
        if http_only:
            cookie_list.append('HttpOnly')
        self._cookies[name] = '; '.join(cookie_list)

    def del_cookie(self, name):
        """
        Delete a cookie.
        >>> r = Response()
        >>> r.set_cookie('company', 'Abc, Inc.', max_age=3600)
        >>> r._cookies
        {'company': 'company=Abc%2C%20Inc.; Max-Age=3600; Path=/; HttpOnly'}
        >>> r.del_cookie('company')
        >>> r._cookies
        {}
        """
        if hasattr(self, '_cookies'):
            if name in self._cookies:
                del self._cookies[name]

    @property
    def status_code(self):
        """
        Get response status code as int.

        >>> r = Response()
        >>> r.status_code
        200
        >>> r.status = 404
        >>> r.status_code
        404
        >>> r.status = '500 Internal Error'
        >>> r.status_code
        500
        """
        return int(self._status[:3])

    @property
    def status(self):
        """
        Get response status. Default to '200 OK'.
        >>> r = Response()
        >>> r.status
        '200 OK'
        >>> r.status = 404
        >>> r.status
        '404 Not Found'
        >>> r.status = '500 Oh My God'
        >>> r.status
        '500 Oh My God'
        """
        return self._status

    @ status.setter
    def status(self, value):
        """
        Set response status as int or str.

        >>> r = Response()
        >>> r.status = 404
        >>> r.status
        '404 Not Found'
        >>> r.status = '500 ERR'
        >>> r.status
        '500 ERR'
        >>> r.status = u'403 Denied'
        >>> r.status
        '403 Denied'
        >>> r.status = 99
        Traceback (most recent call last):
          ...
        ValueError: Bad response code: 99
        >>> r.status = 'ok'
        Traceback (most recent call last):
          ...
        ValueError: Bad response code: ok
        >>> r.status = [1, 2, 3]
        Traceback (most recent call last):
          ...
        TypeError: Bad type of response code.
        """
        if isinstance(value, (long, int)):
            if 100 <= value <= 900:
                status = _RESPONSE_STATUSES.get(value, '')
                if status:
                    self._status = '%d %s' % (value, status)
                else:
                    self._status = str(value)
            else:
                raise ValueError('Bad response code: %d' % value)
        elif isinstance(value, basestring):
            if isinstance(value, unicode):
                value = value.encode('utf-8')
            if _RE_RESPONSE_STATUS.match(value):
                self._status = value
            else:
                raise ValueError('Bad response code: %d' % value)
        else:
            raise TypeError('Bad type of response code.')


class Template(object):
    def __init__(self, template_name, **kwargs):
        """
        Init a template object with template name, model as dict, and additional kw that will append to model.

        >>> t = Template('hello.html', title='Hello', copyright='@2012')
        >>> t.model['title']
        'Hello'
        >>> t.model['copyright']
        '@2012'
        >>> t = Template('test.html', abc=u'ABC', xyz=u'XYZ')
        >>> t.model['abc']
        u'ABC'
        """
        self.template_name = template_name
        self.model = dict(**kwargs)


class TemplateEngine(object):
    """
    Base Template Engine
    """
    @abstractmethod
    def __call__(self, path, model):
        return '<!-- override this method to render template -->'


class Jinja2TemplateEngine(TemplateEngine):
    def __init__(self, tmp_dir, **kwargs):
        from jinja2 import Environment, FileSystemLoader
        if 'auto_escape' not in kwargs:
            kwargs['auto_escape'] = True
        self._environ = Environment(loader=FileSystemLoader(tmp_dir), **kwargs)

    def add_filter(self, name, fn_filter):
        self._environ.filters[name] = fn_filter

    def __call__(self, path, model):
        return self._environ.get_template(path).render(**model).encode('utf-8')


class WSGIApplication(object):
    def __init__(self, document_root=None, **kwargs):
        self._running = False

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