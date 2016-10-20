#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'guti'

'''
Database object relation mapping module.
'''

import time
import logging
import db


_triggers = frozenset(['pre_insert', 'pre_update', 'pre_delete'])


def _gen_sql(table_name, mapping):
    """
    Generate the sql string of database operations.

    :param table_name: name of table in database.
    :param mapping: dict, key is the name of Field object, value is the Filed object.
    :return: sql string
    """
    pk = None
    sql = ['-- generating SQL for %s:' % table_name, 'create table %s (' % table_name]
    for f in sorted(mapping.values(), lambda x, y: cmp(x.order, y.order)):
        if not hasattr(f, 'ddl'):
            raise StandardError('No ddl in field %s.' % f)
        if f.primary_key:
            pk = f.name
        sql.append(('%s %s,' if f.nullable else ' %s %s not null,') % (f.name, f.ddl))
    sql.append(' primary key(%s)' % pk)
    sql.append(');')
    return '\n'.join(sql)


class ModelMetaClass(type):
    """
    MetaClass for Model.

    When the Base is Model, just create Model object.
    When creating the subclasses of Model, building the mapping relation of name and Field object.
    Set some attributes to the Model class dynamically.
    """
    def __new__(mcs, name, bases, attrs):
        # skip base Model class:
        if name == 'Model':
            return type.__new__(mcs, name, bases, attrs)

        # store subclasses information.
        if not hasattr(mcs, 'subclasses'):
            mcs.subclasses = dict()
        if name not in mcs.subclasses:
            mcs.subclasses[name] = name
        else:
            logging.warning('Redefine class: %s' % name)
        # move the Filed object attributes to mapping.
        # record, check and modify the primary key.
        logging.info('Scan ORM %s...' % name)
        mapping = dict()
        primary_key = None
        for k, v in attrs.items():
            if isinstance(v, Field):
                if not v.name:
                    v.name = k
                logging.info('Found Mapping %s --> %s...' % (k, v))
                # check if there are more than 1 primary keys.
                # set the primary key non-updatable and non-nullable.
                if v.primary_key:
                    if primary_key:
                        raise TypeError('Cannot define more than 1 primary key in class: %s' % name)
                    if v.updatable:
                        logging.warning('Change primary key to not non-updatable.')
                        v.updatable = False
                    if v.nullable:
                        logging.warning('Change primary key to non-nullable.')
                        v.nullable = False
                    primary_key = v
                mapping[k] = v
        # check exist of primary key.
        if not primary_key:
            raise TypeError('Primary key not defined in class: %s' % name)
        # the Field object attributes has been recorded in dict mapping.
        for k in mapping:
            attrs.pop(k)
        # set new attributes for the class.
        if '__table__' not in attrs:
            attrs['__table__'] = name.lower()
        attrs['__mappings__'] = mapping
        attrs['__primary_key__'] = primary_key
        attrs['__sql__'] = lambda self: _gen_sql(attrs['__table__'], mapping)
        # set pre-operation function attributes if they are exist.
        for trigger in _triggers:
            if trigger not in attrs:
                attrs[trigger] = None
        return type.__new__(mcs, name, bases, attrs)


class Model(dict):
    """
    Base model class

    >>> class TestUser(Model):
    ...     id = IntegerField(primary_key=True)
    ...     name = StringField()
    ...     email = StringField(updatable=False)
    ...     password = StringField(default=lambda: '******')
    ...     last_modified = FloatField()
    ...     def pre_insert(self):
    ...         self.last_modified = time.time()
    >>> u = TestUser(id=10190, name='Michael', email='orm@db.org')
    >>> r = u.insert()
    >>> u.find_first('id=10190').password
    u'******'
    >>> TestUser.find_by("where name='Michael'")[0]['email']
    u'orm@db.org'
    >>> print TestUser.__mappings__['id']
    <IntegerField: id, bigint, default(0), I>
    >>> u.email
    'orm@db.org'
    >>> u.password
    '******'
    >>> u.last_modified > (time.time() - 2)
    True
    >>> f = TestUser.get(10190)
    >>> f.count_by("where name=%s and password=%s", 'Michael', '******')
    1L
    >>> f.name
    u'Michael'
    >>> f.email
    u'orm@db.org'
    >>> f.email = 'changed@db.org'
    >>> r = f.update() # change email but email is non-updatable!
    >>> len(TestUser.find_all())
    1
    >>> g = TestUser.get(10190)
    >>> g.email
    u'orm@db.org'
    >>> r = g.delete()
    >>> len(db.select('select * from testuser where id=10190'))
    0
    >>> print TestUser().__sql__()
    -- generating SQL for testuser:
    create table testuser (
     id bigint not null,
     name varchar(255) not null,
     email varchar(255) not null,
     password varchar(255) not null,
     last_modified real not null,
     primary key(id)
    );
    """
    __metaclass__ = ModelMetaClass

    def __init__(self, **kwargs):
        super(Model, self).__init__(**kwargs)

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            raise AttributeError(r"'Dict' object has no attribute '%s'" % item)

    def __setattr__(self, key, value):
        self[key] = value

    @classmethod
    def get(cls, pk):
        """
        Get by primary key
        :param pk: primary key.
        :return: Model object or None
        """
        result = db.select_one('select * from %s where %s=%%s' % (cls.__table__, cls.__primary_key__.name), pk)
        return cls(**result) if result else None

    @classmethod
    def find_first(cls, where, *args):
        """
        Find by where clause and return one result. If multiple results found,
        only the first one returned. If no result found, return None.
        :param where: string like "name='Michael'" or "name=%s"
        :param args: parameters of "%s" in where
         """
        result = db.select_one('select * from %s where %s' % (cls.__table__, where), *args)
        return cls(**result) if result else None

    @classmethod
    def find_all(cls):
        """
        Find all and return list.
        """
        result = db.select('select * from %s' % cls.__table__)
        return [cls(**r) for r in result]

    @classmethod
    def find_by(cls, where, *args):
        """
        Find by where clause and return list.
        """
        result = db.select('select * from %s %s' % (cls.__table__, where), *args)
        return [cls(**r) for r in result]

    @classmethod
    def count_all(cls):
        """
        Find by 'select count(pk) from table' and return integer.
        """
        return db.select_int('select count(%s) from %s' % (cls.__primary_key__.name, cls.__table__))

    @classmethod
    def count_by(cls, where, *args):
        """
        Find by 'select count(pk) from table where ... ' and return int.
        """
        return db.select_int('select count(%s) from %s %s' %
                             (cls.__primary_key__.name, cls.__table__, where), *args)

    def update(self):
        """
        Update the object in the database.
        :type self: Model
        """
        self.pre_update and self.pre_update()
        col_list = list()
        args = list()
        for k, v in self.__mappings__.iteritems():
            if v.updatable:
                if hasattr(self, k):
                    arg = getattr(self, k)
                else:
                    arg = v.default
                    setattr(self, k, arg)
                col_list.append('%s=%%s' % k)
                args.append(arg)
        pk = self.__primary_key__.name
        args.append(getattr(self, pk))
        db.update('update %s set %s where %s=%%s' % (self.__table__, ','.join(col_list), pk), *args)

    def delete(self):
        """
        Delete the object in the database.
        :return: Model object itself.
        """
        self.pre_delete and self.pre_delete()
        pk = self.__primary_key__.name
        args = (getattr(self, pk),)
        db.update('delete from %s where %s=%%s' % (self.__table__, pk), *args)
        return self

    def insert(self):
        """
        Insert the object into the database.
        :return: Model object itself.
        """
        self.pre_insert and self.pre_insert()
        params = dict()
        for k, v in self.__mappings__.iteritems():
            if v.insertable:
                if not hasattr(self, k):
                    setattr(self, k, v.default)
                params[v.name] = getattr(self, k)
        db.insert('%s' % self.__table__, **params)
        return self


class Field(object):
    """
    Information of column in the database table.
    """
    # class variable to represent the oder of different Field object.
    _count = 0

    def __init__(self, **kwargs):
        self.name = kwargs.get('name', None)
        # could be a function when the value is created dynamically
        self._default = kwargs.get('default', None)
        self.primary_key = kwargs.get('primary_key', False)
        self.nullable = kwargs.get('nullable', False)
        self.updatable = kwargs.get('updatable', True)
        self.insertable = kwargs.get('insertable', True)
        self.ddl = kwargs.get('ddl', '')
        self._order = Field._count
        Field._count += 1

    @property
    def default(self):
        d = self._default
        return d() if callable(d) else d

    @property
    def order(self):
        return self._order

    def __str__(self):
        s = ['<%s: %s, %s, default(%s), ' % (self.__class__.__name__, self.name, self.ddl, self._default)]
        self.nullable and s.append('N')
        self.updatable and s.append('U')
        self.insertable and s.append('I')
        s.append('>')
        return ''.join(s)


class StringField(Field):
    def __init__(self, **kwargs):
        if 'default' not in kwargs:
            kwargs['default'] = ''
        if 'ddl' not in kwargs:
            kwargs['ddl'] = 'varchar(255)'
        super(StringField, self).__init__(**kwargs)


class IntegerField(Field):
    def __init__(self, **kwargs):
        if 'default' not in kwargs:
            kwargs['default'] = 0
        if 'ddl' not in kwargs:
            kwargs['ddl'] = 'bigint'
        super(IntegerField, self).__init__(**kwargs)


class FloatField(Field):
    def __init__(self, **kwargs):
        if 'default' not in kwargs:
            kwargs['default'] = 0.0
        if 'ddl' not in kwargs:
            kwargs['ddl'] = 'real'
        super(FloatField, self).__init__(**kwargs)


class BooleanField(Field):
    def __init__(self, **kwargs):
        if 'default' not in kwargs:
            kwargs['default'] = False
        if 'ddl' not in kwargs:
            kwargs['ddl'] = 'boolean'
        super(BooleanField, self).__init__(**kwargs)


class TextField(Field):
    def __init__(self, **kwargs):
        if 'default' not in kwargs:
            kwargs['default'] = False
        if 'ddl' not in kwargs:
            kwargs['ddl'] = 'text'
        super(TextField, self).__init__(**kwargs)


class VersionField(Field):
    def __init__(self, name=None):
        super(VersionField, self).__init__(name=name, default=0, ddl='bigint')


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    # TODO: should be modified to your own test database
    db.create_engine('test_user', 'test_pw', 'test_db')
    db.update('drop table if exists testuser')
    db.update('create table testuser (id int primary key, name text, email text, password text, last_modified real)')
    import doctest
    doctest.testmod()
