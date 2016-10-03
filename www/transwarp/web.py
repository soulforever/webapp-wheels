# -*- coding: utf-8 -*-
__author__ = 'guti'


import threading
import datetime
import re
import urllib

from db import Dict

# thread local context object.
context = threading.local()
# define constant for 0 timedelta.
_TIMEDELTA_ZERO = datetime.timedelta(0)
# a compiled regular expression for utc time.
_RE_TZ = re.compile(r'^([\+\-])([0-9]{1,2}):([0-9]{1,2})$')
# a compiled regular expression for response status.
_RE_RESPONSE_STATUS = re.compile(r'^\d\d\d( [\w ]+)?$')
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
    def __init__(self, utc):
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
        func.__web_method__ = 'POST'
        return func
    return _decorator


class Request(object):
    # get value from request by key
    def get(self, key, default=None):
        pass

    # get key-value dict from input
    def input(self):
        pass

    # return url information
    @property
    def path_info(self):
        pass

    # return http headers dict
    @property
    def headers(self):
        pass

    # get value by key in cookie
    def cookie(self, value, default=None):
        pass


class Response(object):
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
    import doctest
    doctest.testmod()