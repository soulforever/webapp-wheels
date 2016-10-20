# -*- coding: utf-8 -*-
__author__ = 'guti'


from models import User

from transwarp import db

# TODO: change the database info by config
db.create_engine(user='test_user', password='test_pw', database='wheels')

u = User(name='Test', email='test@example.com', password='1234567890', image='about:blank')

u.insert()
print 'u.u_id = %s' % u.u_id

u1 = User.find_first('email=%s', 'test@example.com')
print 'find user, named: %s' % u1.name

u1.delete()

u2 = User.find_first('email=%s', 'test@example.com')
print 'find user: named: %s' % u2