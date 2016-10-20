# -*- coding: utf-8 -*-
__author__ = 'guti'

'''
Initialize the database, web framework and start web service.
'''

import logging
import os

import urls
from transwarp import db
from transwarp.web import WSGIApplication, Jinja2TemplateEngine
from config import configs


def datetime_filter(t):
    delta = int(time.time() - t)
    if delta < 60:
        return u'A minute ago'
    if delta < 3600:
        return u'%s minutes ago' % (delta // 60)
    if delta < 86400:
        return u'%s hours ago' % (delta // 3600)
    if delta < 604800:
        return u'%s days ago' % (delta // 86400)
    dt = datetime.fromtimestamp(t)
    return u'%sY%sM%sD' % (dt.year, dt.month, dt.day)

# logging status
logging.basicConfig(level=logging.DEBUG)

# initialize the database
db.create_engine(**configs.db)

current_path = os.path.dirname(os.path.abspath(__file__))
# create a wsgi application
wsgi_app = WSGIApplication(current_path)

# initialize the Jinja2 engine
template_engine = Jinja2TemplateEngine(os.path.join(current_path, 'templates'))
template_engine.add_filter('datetime', datetime_filter)
wsgi_app.template_engine = template_engine

# add the urls module
wsgi_app.add_module(urls)

if __name__ == '__main__':
    wsgi_app.run(9000, host='0.0.0.0')
else:
    application = wsgi_app.get_wsgi_application()
