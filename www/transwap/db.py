#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'guti'

'''
Database base module.
'''

import threading
import logging
import functools
import time
import traceback


class _Engine(object):
    """
    Class database engine

    Used to connect the database.
    """
    def __init__(self, connect):
        self._connect = connect

    def connect(self):
        return self._connect()


class _DbContext(threading.local):
    """
    Thread local object of database context

    Used to record the context of database connection in different thread.
    """
    def __init__(self):
        super(_DbContext, self).__init__()
        # save the connection object in the context
        self.connection = None
        # record the numbers of transactions
        self.transactions = 0

    def is_init(self):
        return self.connection is not None

    def init(self):
        self.connection = _ConnectionInThread()
        self.transactions = 0

    def clean(self):
        self.connection.clean()
        self.connection = None
        self.transactions = 0

    def cursor(self):
        return self.connection.cursor()


class _ConnectionInThread(object):
    """
    Connection package

    Provide the access of operating database for _DbContext object for operating database in different thread.
    After connection from global variable engine got, recording the connection in the _ConnectionInThread object.
    Then getting a thread local connection to avoid influence of different thread's operation.
    """
    def __init__(self):
        self.connection = None

    def clean(self):
        if self.connection:
            conn = self.connection
            self.connection = None
            logging.info('Close connection id(%s)' % hex(id(conn)))
            conn.close()

    def cursor(self):
        # get the connection only when want get the cursor
        if self.connection is None:
            conn = engine.connect()
            logging.info('Open connection id(%s)' % hex(id(conn)))
            self.connection = conn
        return self.connection.cursor()

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()


class _ConnectionContext(object):
    """
    Database connection context

    _ConnectionContext object can be used to open and close connection.
    Nesting _ConnectionContext object to the functions needing database connection, then opening and closing\
    of database connection can be ignored.

    usage:
    with _ConnectionContext():
        # operation needing database connection
        pass
    """
    def __enter__(self):
        global _db_ctx
        self.is_cleanable = False
        if not _db_ctx.is_init():
            _db_ctx.init()
            self.is_cleanable = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        global _db_ctx
        if self.is_cleanable:
            if exc_type is not None:
                logging.warning(''.join(traceback.format_exception(exc_type, exc_val, exc_tb)))
            _db_ctx.clean()


class _TransactionContext(object):
    """
    Database transaction context
    _ConnectionContext object can be used to handle database transactions.
    Nesting _TransactionContext object to the functions handling database transactions, then recording transactions\
    of database can be ignored

    usage:
    with _TransactionContext():
        # transactions operation
        pass
    """
    def __enter__(self):
        global _db_ctx
        self.is_closable = False
        if not _db_ctx.is_init():
            _db_ctx.init()
            self.is_closable = True
        _db_ctx.transactions += 1
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        global _db_ctx
        _db_ctx.transactions -= 1
        try:
            if _db_ctx.transactions == 0:
                if exc_type is None:
                    # exit without exception
                    self.commit()
                else:
                    self.rollback()
        finally:
            if self.is_closable:
                if exc_type is not None:
                    logging.warning(''.join(traceback.format_exception(exc_type, exc_val, exc_tb)))
                _db_ctx.clean()

    @staticmethod
    def commit():
        global _db_ctx
        logging.info('Commit transaction.')
        try:
            _db_ctx.connection.commit()
            logging.info('Commit finished.')
        except Exception, e:
            logging.warning('Commit failed, try to rollback...')
            _db_ctx.connection.rollback()
            logging.warning('Rollback finished.')
            raise e
        finally:
            logging.info('Commit finished')

    @staticmethod
    def rollback():
        global _db_ctx
        logging.info('Rollback transaction')
        _db_ctx.connection.rollback()
        logging.info('Rollback finished')


class DBError(Exception):
    """
    Database error exception

    Exception for database operation.
    """
    pass


class MultiColumnsError(DBError):
    """
    Multiply column exception

    DBError child class for describing too much column got.
    """
    pass


class Dict(dict):
    """
    Dict support dict_object.key operation.

    Simplify getting item from dict.

    >>> d1 = Dict()
    >>> d1['x'] = 100
    >>> d1.x
    100
    >>> d1.y = 200
    >>> d1['y']
    200
    >>> d2 = Dict(a=1, b=2, c='a')
    >>> d2.c
    'a'
    >>> d2['key_not_exist']
    Traceback (most recent call last):
    ...
    KeyError: 'key_not_exist'
    >>> d2.key_not_exist
    Traceback (most recent call last):
    ...
    AttributeError: 'Dict' object has no attribute 'key_not_exist'
    >>> d3 = Dict(('a', 'b', 'c'), (1, 2))
    >>> d3.a
    1
    >>> d3.b
    2
    >>> d3.c
    Traceback (most recent call last):
    ...
    AttributeError: 'Dict' object has no attribute 'c'
    """
    def __init__(self, names=(), values=(), **kwargs):
        super(Dict, self).__init__(**kwargs)
        for k, v in zip(names, values):
            self[k] = v

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            raise AttributeError(r"'Dict' object has no attribute '%s'" % item)

    def __setattr__(self, key, value):
        self[key] = value


def connection():
    """
    Get database connection context object
    :return: _ConnectionContext object

    usage:
    with connection():
        # operation needing database connection
        pass
    """
    return _ConnectionContext()


def with_connection(func):
    """
    Decorate connection functions
    :param func: function object
    :return: decoration function

    usage:
    @ with_connection()
    def func(*args, **kwargs):
        # operation needing database connection
        pass
    """
    @functools.wraps(func)
    def _wrapper(*args, **kwargs):
        with _ConnectionContext():
            return func(*args, **kwargs)
    return _wrapper


def transaction():
    """
    Get database transaction object
    :return: _TransactionContext object

    usage:
    with transaction():
        # transactions operation
        pass

    >>> def update_profile(t_id, name, rollback):
    ...     u = dict(id=t_id, name=name, email='%s@test.org' % name, password=name, last_modified=time.time())
    ...     insert('testuser', **u)
    ...     update('update testuser set password=%s where id=%s', name.upper(), t_id)
    ...     if rollback:
    ...         raise StandardError('will cause rollback...')
    >>> with transaction():
    ...     update_profile(900301, 'Python', False)
    >>> select_one('select * from testuser where id=%s', 900301).name
    u'Python'
    >>> with transaction():
    ...     update_profile(900302, 'Ruby', True)
    Traceback (most recent call last):
      ...
    StandardError: will cause rollback...
    >>> select('select * from testuser where id=%s', 900302)
    []
    """
    return _TransactionContext()


def with_transaction(func):
    """
    Decorate transactions function
    :param func: function object
    :return: decoration function

    usage:
    @with_transaction
    def func(*args, **kwargs):
        # transactions operation
        pass
    """
    @functools.wraps(func)
    def _wrapper(*args, **kwargs):
        with _TransactionContext():
            return func(*args, **kwargs)
    return _wrapper


def _select(sql, first, *args):
    """
    Execute select sql
    :param sql: select sql string, using '%s' represent parameter need to replaced.
    :param first: boolean to check if getting one line or not.
    :param args: parameters to replace the '%s' in sql string.
    :return: list formed by Dict object.
    """
    global _db_ctx
    cursor = None
    logging.info('SQL: %s, ARGS: %s' % (sql, args))
    try:
        cursor = _db_ctx.connection.cursor()
        cursor.execute(sql, args)
        if cursor.description:
            names = [x[0] for x in cursor.description]
            if first:
                values = cursor.fetchone()
                if not values:
                    return None
                return Dict(names, values)
            return [Dict(names, x) for x in cursor.fetchall()]
    finally:
        if cursor:
            cursor.close()


def _update(sql, *args):
    """
    Execute update or insert sql
    :param sql: select sql string.
    :param args: parameters to replace the '%s' in sql string.
    :return: row numbers of transactions.
    """
    global _db_ctx
    cursor = None
    logging.info('SQL: %s, ARGS: %s' % (sql, args))
    try:
        cursor = _db_ctx.connection.cursor()
        cursor.execute(sql, args)
        row = cursor.rowcount
        if _db_ctx.transactions == 0:
            _db_ctx.connection.commit()
        return row
    finally:
        if cursor:
            cursor.close()

# global engine object
engine = None

# global database context object
_db_ctx = _DbContext()


def create_engine(user, password, database, host='127.0.0.1', port=5432, **kwargs):
    """
    Create the engine connect the database.
    Use postgreSQL database.
    """
    import psycopg2
    global engine
    # set psycopg2 module select unicode result
    psycopg2.extensions.register_type(psycopg2.extensions.UNICODE, None)
    if engine is not None:
        raise DBError('Engine is already initialized.')
    params = dict(user=user, password=password, database=database, host=host, port=port)
    defaults = dict(client_encoding='UTF8', connection_factory=None, cursor_factory=None, async=False)
    for k, v in defaults.items():
        params[k] = kwargs.pop(k, v)
    params.update(kwargs)
    engine = _Engine(lambda: psycopg2.connect(**params))
    logging.info('Initialize postgreSQL engine <%s>' % hex(id(engine)))


@with_connection
def select_one(sql, *args):
    """
    Execute select SQL and expected one result.

    >>> u1 = dict(id=100, name='Alice', email='alice@test.org', password='ABC-12345', last_modified=time.time())
    >>> u2 = dict(id=101, name='Sarah', email='sarah@test.org', password='ABC-12345', last_modified=time.time())
    >>> insert('testuser', **u1)
    1
    >>> insert('testuser', **u2)
    1
    >>> u = select_one('select * from testuser where id=%s and name=%s', 100, 'Alice')
    >>> u.name
    u'Alice'
    >>> select_one('select * from testuser where email=%s', 'abc@email.com')
    >>> u2 = select_one('select * from testuser where password=%s order by email', 'ABC-12345')
    >>> u2.name
    u'Alice'
    """
    return _select(sql, True, *args)


@with_connection
def select_int(sql, *args):
    """
    Execute select SQL and expected one int and only one int result.

    >>> n = update('delete from testuser')
    >>> u1 = dict(id=96900, name='Ada', email='ada@test.org', password='A-12345', last_modified=time.time())
    >>> u2 = dict(id=96901, name='Adam', email='adam@test.org', password='A-12345', last_modified=time.time())
    >>> insert('testuser', **u1)
    1
    >>> insert('testuser', **u2)
    1
    >>> select_int('select count(*) from testuser')
    2L
    >>> select_int('select count(*) from testuser where email=%s', 'ada@test.org')
    1L
    >>> select_int('select count(*) from testuser where email=%s', 'notexist@test.org')
    0L
    >>> select_int('select id from testuser where email=%s', 'ada@test.org')
    96900
    >>> select_int('select id, name from testuser where email=%s', 'ada@test.org')
    Traceback (most recent call last):
        ...
    MultiColumnsError: Expect only one column.
    """
    d = _select(sql, True, *args)
    if len(d) != 1:
        raise MultiColumnsError('Expect only one column.')
    return d.values()[0]


@with_connection
def select(sql, *args):
    """
    Execute select SQL and return list or empty list if no result.

    >>> u1 = dict(id=200, name='Wall.E', email='wall.e@test.org', password='back-to-earth', last_modified=time.time())
    >>> u2 = dict(id=201, name='Eva', email='eva@test.org', password='back-to-earth', last_modified=time.time())
    >>> insert('testuser', **u1)
    1
    >>> insert('testuser', **u2)
    1
    >>> L = select('select * from testuser where id=%s', 900900900)
    >>> L
    []
    >>> L = select('select * from testuser where id=%s', 200)
    >>> L[0].email
    u'wall.e@test.org'
    >>> L = select('select * from testuser where password=%s order by id desc', 'back-to-earth')
    >>> L[0].name
    u'Eva'
    >>> L[1].name
    u'Wall.E'
    """
    return _select(sql, False, *args)


@with_connection
def update(sql, *args):
    r"""
    Execute update SQL.

    >>> u1 = dict(id=1000, name='Michael', email='michael@test.org', password='123456', last_modified=time.time())
    >>> insert('testuser', **u1)
    1
    >>> u2 = select_one('select * from testuser where id=%s', 1000)
    >>> u2.email
    u'michael@test.org'
    >>> u2.password
    u'123456'
    >>> update('update testuser set email=%s, password=%s where id=%s', 'michael@example.org', '654321', 1000)
    1
    >>> u3 = select_one('select * from testuser where id=%s', 1000)
    >>> u3.email
    u'michael@example.org'
    >>> u3.password
    u'654321'
    >>> update('update testuser set password=%s where id=%s or id=%s', '***', 123, 456)
    0
    """
    return _update(sql, *args)


@with_connection
def insert(table, **kwargs):
    """
    Execute insert SQL.
    :param table: the table name.
    :param kwargs: dict of data to be inserted.
    :return: int number of raw number.

    >>> u1 = dict(id=2000, name='Bob', email='bob@test.org', password='cool_word', last_modified=time.time())
    >>> insert('testuser', **u1)
    1
    >>> u2 = select_one('select * from testuser where id=%s', 2000)
    >>> u2.name
    u'Bob'
    >>> insert('testuser', **u1)
    Traceback (most recent call last):
      ...
    IntegrityError: duplicate key value violates unique constraint "testuser_pkey"
    DETAIL:  Key (id)=(2000) already exists.
    <BLANKLINE>
    """
    cols, args = zip(*kwargs.iteritems())
    sql = 'insert into %s (%s) values (%s)' % (table, ','.join(['"%s"' % col for col in cols]),
                                               (','.join(['%s' for _ in range(len(cols))])))
    r = _update(sql, *args)
    return r

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    # TODO: should be modified to your own test database
    create_engine('test_user', 'test_pw', 'test_db')
    update('drop table if exists testuser')
    update('create table testuser (id int primary key, name text, email text, password text, last_modified real)')
    # delete the test data if needed
    # update('drop table if exists "testuser"')
    import doctest
    doctest.testmod()
