-- add init database

drop database if exists wheels;

create database wheels owner "pgAdmin" encoding 'UTF8';

\c wheels



-- generating SQL for bloguser:
create table users (
 u_id varchar(50) not null,
 email varchar(50) not null,
 password varchar(50) not null,
 admin boolean not null,
 name varchar(50) not null,
 image varchar(500) not null,
 created_at real not null,
 unique(email),
 primary key(u_id)
);


-- generating SQL for blogs:
create table blogs (
 b_id varchar(50) not null,
 u_id varchar(50) not null,
 user_name varchar(50) not null,
 user_image varchar(500) not null,
 name varchar(50) not null,
 summary varchar(200) not null,
 content text not null,
 created_at real not null,
 primary key(b_id)
);


-- generating SQL for comments:
create table comments (
 c_id varchar(50) not null,
 b_id varchar(50) not null,
 u_id varchar(50) not null,
 user_name varchar(50) not null,
 user_image varchar(500) not null,
 content text not null,
 created_at real not null,
 primary key(c_id)
);


grant select, insert, update, delete on users, blogs, comments to "pgAdmin";

-- insert admin information

insert into users (u_id, email, password, admin, name, image,created_at)
 values ('0014753981349889e4b6bc4a1b94d7080c70d061053e65f000',
 'admin@example.com', 'test_pw',
 'true', 'Administrator', 'not a image', 1475398130.941814);
