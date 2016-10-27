# -*- coding: utf-8 -*-
__author__ = 'guti'

'''
Urls to deal with templates
'''

import os
import re
import time
import base64
import hashlib
import logging

from transwarp.web import get, post, context, view, see_other, not_found, interceptor
from transwarp.apis import api, APIError, APIValueError, APIPermissionError, APIResourceNotFoundError
from models import User, Blog, Comment
from config import configs


_RE_MD5 = re.compile(r'^[0-9a-f]{32}$')
_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_COOKIE_NAME = 'wheels_session'
_COOKIE_KEY = configs


def make_signed_cookie(u_id, password, max_age):
    expires = str(int(time.time() + (max_age or 86400)))
    return '-'.join([u_id, expires, hashlib.md5('%s-%s-%s-%s' % (u_id, password, expires, _COOKIE_KEY)).hexdigest()])


def parse_signed_cookie(cookie_str):
    try:
        cookie_list = cookie_str.split('-')
        if len(cookie_list) != 3:
            return None
        u_id, expires, md5 = cookie_list
        if int(expires) < time.time():
            return None
        user = User.get(u_id)
        if user is None:
            return None
        if md5 != hashlib.md5('%s-%s-%s-%s' % (u_id, user.password, expires, _COOKIE_KEY)).hexdigest():
            return None
        return user
    except Exception:
        return None


def assert_admin():
    user = context.request.user
    if user and user.admin:
        return
    raise APIPermissionError('No permission')


@interceptor('/')
def user_interceptor(next):
    logging.info('Try to bind user from session cookie...')
    user = None
    cookie = context.request.cookies.get(_COOKIE_NAME)
    if cookie:
        logging.info('Parse session cookie...')
        user = parse_signed_cookie(cookie)
        if user:
            logging.info('Bind user <%s> to session...' % user.email)
    context.request.user = user
    return next()


@interceptor('/manage/')
def manage_interceptor(next):
    user = context.request.user
    if user and user.admin:
        return next()
    raise see_other('/signin')


@view('blogs.html')
@get('/')
def index():
    blogs = Blog.find_all()
    return dict(blogs=blogs, user=context.request.user)


@view('signin.html')
@get('/signin')
def signin():
    return dict()


@get('/signout')
def signout():
    context.response.delete_cookie(_COOKIE_NAME)
    raise see_other('/')


@view('register.html')
@get('/register')
def register():
    return dict()


@api
@post('/api/authenticate')
def authenticate():
    i = context.request.input(remember='')
    email = i.email.strip().lower()
    password = i.password
    remember = i.remember
    user = User.find_first('email=%s', email)
    if user is None:
        raise APIError('auth:failed', 'email', 'Invalid email.')
    elif user.password != password:
        raise APIError('auth:failed', 'password', 'Invalid password.')
    max_age = 604800 if remember == 'true' else None
    cookie = make_signed_cookie(user.u_id, user.password, max_age)
    context.response.set_cookie(_COOKIE_NAME, cookie, max_age=max_age)
    user.password = '******'
    return user


@api
@post('/api/users')
def api_register_user():
    i = context.request.input(name='', email='', password='')
    name = i.name.strip()
    email = i.email.strip().lower()
    password = i.password
    if not name:
        raise APIValueError('name')
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('email')
    if not password or not _RE_MD5.match(password):
        raise APIValueError('password')
    user = User.find_first('email=%s', email)
    if user:
        raise APIError('register:failed', 'email', 'Email is already in use.')
    user = User(name=name, email=email, password=password,
                image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email).hexdigest())
    user.insert()
    print user
    cookie = make_signed_cookie(user.u_id, user.password, None)
    context.response.set_cookie(_COOKIE_NAME, cookie)
    return user


@api
@get('/api/users')
def api_get_users():
    users = User.find_by('order by created_at desc')
    for u in users:
        u.password = '******'
    return dict(users=users)
