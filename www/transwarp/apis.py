# -*- coding: utf-8 -*-
__author__ = 'guti'

'''
JSON API definition.
'''

import re
import json
import logging
import functools

from web import context


def json_dump(obj):
    return json.dumps(obj)


class APIError(StandardError):
    """
    Base api error which contains error(required), data(optional) and message(optional).
    """
    def __init__(self, error, data='', message=''):
        super(APIError, self).__init__(message)
        self.error = error
        self.data = data
        self.message = message


class APIValueError(APIError):
    """
    Indicate the input value has error or invalid.
    The data specifies the error field of input form.
    """
    def __init__(self, field, message=''):
        super(APIValueError, self).__init__('value:invalid', field, message)


class APIResourceNotFoundError(APIError):
    """
    Indicate the resource was not found.
    The data specifies the resource name.
    """
    def __init__(self, field, message):
        super(APIResourceNotFoundError, self).__init__('value:not found', field, message)


class APIPermissionError(APIError):
    """
    Indicate the api has no permission.
    """
    def __init__(self, message):
        super(APIPermissionError, self).__init__('permission: forbidden', 'permission', message)


def api(func):
    """
    A decorator that makes a function to json api, makes the return value as json.

    :param func:
    :return:

    Usage:
        @get('/api/test')
        @api
        def api_test():
            return dict(result='123', items=[])
    """
    @functools.wraps(func)
    def _wrapper(*args, **kwargs):
        try:
            result = json_dump(func(*args, **kwargs))
        except APIError, e:
            result = json_dump(dict(error=e.error, data=e.data, message=e.message))
        except Excption, e:
            logging.exception(e)
            result = json.dumps(dict(error='internal error', data=e.__class__.__name__, message=e.message))
        context.response.content_type = 'application/json'
        return result
    return _wrapper

if __name__ == '__main__':
    import doctest
    doctest.testmod()
