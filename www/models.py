# -*- coding: utf-8 -*-
__author__ = 'guti'

'''
Database orm models.
'''

import time

from transwarp.db import next_id
from transwarp.orm import Model, StringField, BooleanField, FloatField, TextField


class User(Model):
    __table__ = 'users'

    u_id = StringField(primary_key=True, default=next_id, ddl='varchar(50)')
    email = StringField(updatable=True, ddl='varchar(50)')
    password = StringField(ddl='varchar(50)')
    admin = BooleanField()
    name = StringField(ddl='varchar(50)')
    image = StringField(ddl='varchar(500)')
    created_at = FloatField(updatable=False, default=time.time)


class Blog(Model):
    __table__ = 'blogs'

    b_id = StringField(primary_key=True, default=next_id, ddl='varchar(50)')
    u_id = StringField(updatable=False, ddl='varchar(50)')
    user_name = StringField(ddl='varchar(50)')
    user_image = StringField(ddl='varchar(500)')
    name = StringField(ddl='varchar(50)')
    summary = StringField(ddl='varchar(200)')
    content = TextField()
    created_at = FloatField(updatable=False, default=time.time)


class Comment(Model):
    __table__ = 'comments'

    c_id = StringField(primary_key=True, default=next_id, ddl='varchar(50)')
    b_id = StringField(updatable=False, ddl='varchar(50)')
    u_id = StringField(updatable=False, ddl='varchar(50)')
    user_name = StringField(ddl='varchar(50)')
    user_image = StringField(ddl='varchar(500)')
    content = TextField()
    created_at = FloatField(updatable=False, default=time.time)


if __name__ == '__main__':
    '''
    Generate base sql str for creating table.
    '''
    import os
    base_sql = [User().__sql__(), Blog().__sql__(), Comment().__sql__()]
    with open('../schema_simple.sql', 'w') as f:
        for sql in base_sql:
            sql.replace('\n', os.linesep)
        f.write((os.linesep * 3).join(base_sql))
