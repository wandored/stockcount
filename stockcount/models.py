""" sqlalchemy database models """
from datetime import datetime

from flask import current_app
from flask_security import (
    Security,
    SQLAlchemySessionUserDatastore,
    RoleMixin,
    UserMixin,
)

from stockcount import db, login_manager


# Create a table to support a many-to-many relationship between Users and Roles
roles_users = db.Table(
    "roles_users",
    db.Column("users_id", db.Integer, db.ForeignKey("users.id")),
    db.Column("roles_id", db.Integer, db.ForeignKey("roles.id")),
)

# Create a table to support a many-to-many relationship between Users and Stores
stores_users = db.Table(
    "stores_users",
    db.Column("users_id", db.Integer, db.ForeignKey("users.id")),
    db.Column("restaurants_id", db.Integer, db.ForeignKey("restaurants.id")),
)


# Role class
class Roles(db.Model, RoleMixin):
    __tablename__ = "roles"

    # Our Role has three fields, ID, name and description
    id = db.Column(db.Integer(), primary_key=True, autoincrement=True)
    name = db.Column(db.String(80), unique=True)
    description = db.Column(db.String(255))

    # __str__ is required by Flask-Admin, so we can have human-readable values for the Role when editing a User.
    # If we were using Python 2.7, this would be __unicode__ instead.
    def __str__(self):
        return self.name

    # __hash__ is required to avoid the exception TypeError: unhashable type: 'Role' when saving a User
    def __hash__(self):
        return hash(self.name)


class Restaurants(db.Model):
    __tablename__ = "restaurants"

    id = db.Column(db.Integer, primary_key=True)
    locationid = db.Column(db.String(64), unique=True)
    name = db.Column(db.String(64), unique=True)
    toast_id = db.Column(db.Integer)
    active = db.Column(db.Boolean())

    # __str__ is required by Flask-Admin, so we can have human-readable values for the Role when editing a User.
    # If we were using Python 2.7, this would be __unicode__ instead.
    def __str__(self):
        return self.name

    # __hash__ is required to avoid the exception TypeError: unhashable type: 'Role' when saving a User
    def __hash__(self):
        return hash(self.name)


class Users(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    first_name = db.Column(db.String(255))
    last_name = db.Column(db.String(255))
    email = db.Column(db.String(255), unique=True)
    password = db.Column(db.String(255))
    active = db.Column(db.Boolean())
    fs_uniquifier = db.Column(db.String(64), unique=True)
    confirmed_at = db.Column(db.DateTime())
    last_login_at = db.Column(db.DateTime())
    current_login_at = db.Column(db.DateTime())
    last_login_ip = db.Column(db.String(100))
    current_login_ip = db.Column(db.String(100))
    login_count = db.Column(db.Integer)
    roles = db.relationship("Roles", secondary=roles_users, backref="users", lazy=True)
    stores = db.relationship(
        "Restaurants", secondary=stores_users, backref="users", lazy=True
    )


user_datastore = SQLAlchemySessionUserDatastore(db.session, Users, Roles)
security = Security()


class UnitsOfMeasure(db.Model):
    __tablename__ = "unitsofmeasure"

    uofm_id = db.Column(db.String(64), primary_key=True, unique=True)
    name = db.Column(db.String(64))
    equivalent_qty = db.Column(db.Float)
    equivalent_uofm = db.Column(db.String(64))
    measure_type = db.Column(db.String(64))
    base_qty = db.Column(db.Float)
    base_uofm = db.Column(db.String(64))


class Calendar(db.Model):
    __tablename__ = "calendar"

    date = db.Column(db.String(64), primary_key=True, unique=True)
    week = db.Column(db.Integer)
    week_start = db.Column(db.String(64))
    week_end = db.Column(db.String(64))
    period = db.Column(db.Integer)
    period_start = db.Column(db.String(64))
    period_end = db.Column(db.String(64))
    quarter = db.Column(db.Integer)
    quarter_start = db.Column(db.String(64))
    quarter_end = db.Column(db.String(64))
    year = db.Column(db.Integer)
    year_start = db.Column(db.String(64))
    year_end = db.Column(db.String(64))
    dow = db.Column(db.Integer)
    day = db.Column(db.String(64))

    def as_dict(self):
        return {
            "date": self.date,
            "week": self.week,
            "period": self.period,
            "quarter": self.quarter,
            "year": self.year,
            "dow": self.dow,
            "day": self.day,
        }


class Company(db.Model):
    __tablename__ = "company"

    companyid = db.Column(db.String, primary_key=True)
    name = db.Column(db.String)


class Items(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    itemname = db.Column(db.String(), nullable=False)
    casepack = db.Column(db.Integer)
    count = db.relationship("Invcount", backref="count_id", lazy=True)
    buy = db.relationship("Invcount", backref="buy_id", lazy=True)
    sell = db.relationship("Invcount", backref="sell_id", lazy=True)

    def __repr__(self):
        return f"Items('{self.id}', '{self.itemname}', '{self.casepack}')"


class Invcount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trans_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    count_time = db.Column(db.String(), nullable=False)
    itemname = db.Column(db.String(), nullable=False)
    casecount = db.Column(db.Integer, nullable=False)
    eachcount = db.Column(db.Integer, nullable=False)
    count_total = db.Column(db.Integer, nullable=False)
    previous_total = db.Column(db.Integer, nullable=False)
    theory = db.Column(db.Integer, nullable=False)
    daily_variance = db.Column(db.Integer, nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("items.id"), nullable=False)

    def __repr__(self):
        return f"Invcount('{self.trans_date}', '{self.count_time}', '{self.itemname}', '{self.casecount}', '{self.eachcount}', '{self.count_total}')"


class Purchases(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trans_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    count_time = db.Column(db.String(), nullable=False)
    itemname = db.Column(db.String(), nullable=False)
    casecount = db.Column(db.Integer, nullable=False)
    eachcount = db.Column(db.Integer, nullable=False)
    purchase_total = db.Column(db.Integer, nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("items.id"), nullable=False)

    def __repr__(self):
        return f"Purchases('{self.trans_date}', '{self.itemname}', '{self.count_time}', '{self.casecount}', '{self.purchase_total}')"


class Sales(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trans_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    count_time = db.Column(db.String(), nullable=False)
    itemname = db.Column(db.String(), nullable=False)
    eachcount = db.Column(db.Integer, nullable=False)
    waste = db.Column(db.Integer, nullable=False)
    sales_total = db.Column(db.Integer, nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("items.id"), nullable=False)

    def __repr__(self):
        return f"Sales('{self.trans_date}', '{self.itemname}', '{self.eachcount}', '{self.waste}', '{self.sales_total}')"
