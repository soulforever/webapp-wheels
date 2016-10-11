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

# logging status
logging.basicConfig(level=logging.DEBUG)

# initialize the database
db.create_engine(**configs.db)

current_path = os.path.dirname(os.path.abspath(__file__))
# create a wsgi application
wsgi_app = WSGIApplication(current_path)

# initialize the Jinja2 engine
template_engine = Jinja2TemplateEngine(os.path.join(current_path, 'templates'))
wsgi_app.template_engine = template_engine

# add the urls module
wsgi_app.add_module(urls)

if __name__ == '__main__':
    wsgi_app.run(9000)
