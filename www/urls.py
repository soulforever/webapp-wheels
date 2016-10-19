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

from transwarp.web import get, view
from models import User, Blog, Comment


@view('blogs.html')
@get('/')
def index():
    blogs = Blog.find_all()
    user = User.find_first('email=%s', 'admin@example.com')
    return dict(blogs=blogs, user=user)
