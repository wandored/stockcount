"""sqlalchemy database models"""

from datetime import datetime, timezone

from flask import current_app
from flask_mailman import EmailMessage, Mail
from flask_security.core import (
    RoleMixin,
    Security,
    UserMixin,
)
from flask_security.datastore import SQLAlchemySessionUserDatastore
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import PrimaryKeyConstraint

mail = Mail()
db = SQLAlchemy()
security = Security()
UTC = timezone.utc


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

    # __str__ is required by Flask-Admin, so we can have human-readable values for Restaurants when editing a User.
    def __str__(self):
        return self.name

    # __hash__ is required to avoid the exception TypeError: unhashable type: 'Restaurants' when saving a User
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

    def __str__(self):
        return f"{self.first_name}, {self.last_name}, {self.email}, {self.active}, {self.roles}, {self.stores}"


user_datastore = SQLAlchemySessionUserDatastore(db.session, Users, Roles)


class UnitsOfMeasure(db.Model):
    __tablename__ = "unitsofmeasure"

    uofm_id = db.Column(db.String(64), primary_key=True, unique=True)
    name = db.Column(db.String(64))
    equivalent_qty = db.Column(db.Float)
    equivalent_uofm = db.Column(db.String(64))
    measure_type = db.Column(db.String(64))
    base_qty = db.Column(db.Float)
    base_uofm = db.Column(db.String(64))

    def __repr__(self):
        return f"UnitsOfMeasure('{self.uofm_id}', '{self.name}', '{self.equivalent_qty}', '{self.equivalent_uofm}', '{self.measure_type}', '{self.base_qty}', '{self.base_uofm}')"


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

    def __repr__(self):
        return f"Calendar('{self.date}', '{self.week}', '{self.week_start}', '{self.week_end}', '{self.period}', '{self.period_start}', '{self.period_end}', '{self.quarter}', '{self.quarter_start}', '{self.quarter_end}', '{self.year}', '{self.year_start}', '{self.year_end}', '{self.dow}', '{self.day}')"


class Item(db.Model):
    __tablename__ = "item"

    itemid = db.Column(db.String, primary_key=True)
    name = db.Column(db.String)
    category1 = db.Column(db.String)
    category2 = db.Column(db.String)
    category3 = db.Column(db.String)

    def __repr__(self):
        return f"Item('{self.itemid}', '{self.name}', '{self.category1}', '{self.category2}', '{self.category3}')"


class Company(db.Model):
    __tablename__ = "company"

    companyid = db.Column(db.String, primary_key=True)
    name = db.Column(db.String)

    def __repr__(self):
        return f"Company('{self.companyid}', '{self.name}')"


class InvItems(db.Model):
    __tablename__ = "inv_items"

    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(), nullable=False)
    case_pack = db.Column(db.Integer)
    store_id = db.Column(db.Integer(), nullable=False)
    count = db.relationship("InvCount", backref="item", lazy=True)
    buy = db.relationship("InvPurchases", backref="item", lazy=True)
    sell = db.relationship("InvSales", backref="item", lazy=True)

    def __repr__(self):
        return f"InvItems('{self.id}', '{self.item_name}', '{self.case_pack}' '{self.store_id}')"


class InvCount(db.Model):
    __tablename__ = "inv_count"

    id = db.Column(db.Integer, primary_key=True)
    trans_date = db.Column(
        db.Date, nullable=False, default=lambda: datetime.now(UTC).date()
    )
    count_time = db.Column(db.String(), nullable=False)
    item_name = db.Column(db.String(), nullable=False)
    case_count = db.Column(db.Integer, nullable=False)
    each_count = db.Column(db.Integer, nullable=False)
    count_total = db.Column(db.Integer, nullable=False)
    previous_total = db.Column(db.Integer, nullable=False)
    theory = db.Column(db.Integer, nullable=False)
    daily_variance = db.Column(db.Integer, nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("inv_items.id"), nullable=False)
    store_id = db.Column(db.Integer, db.ForeignKey("restaurants.id"), nullable=False)

    def __repr__(self):
        return f"InvCount('{self.trans_date}', '{self.count_time}', '{self.item_name}', '{self.case_count}', '{self.each_count}', '{self.count_total}', '{self.previous_total}', '{self.theory}', '{self.daily_variance}', '{self.item_id}', '{self.store_id}')"


class InvPurchases(db.Model):
    __tablename__ = "inv_purchases"

    id = db.Column(db.Integer, primary_key=True)
    trans_date = db.Column(
        db.Date, nullable=False, default=lambda: datetime.now(UTC).date()
    )
    item_name = db.Column(db.String(), nullable=False)
    case_count = db.Column(db.Integer, nullable=False)
    each_count = db.Column(db.Integer, nullable=False)
    purchase_total = db.Column(db.Integer, nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("inv_items.id"), nullable=False)
    store_id = db.Column(db.Integer, db.ForeignKey("restaurants.id"), nullable=False)

    def __repr__(self):
        return f"InvPurchases('{self.trans_date}', '{self.item_name}', '{self.case_count}', '{self.each_count}', '{self.purchase_total}', '{self.item_id}', '{self.store_id}')"


class InvSales(db.Model):
    __tablename__ = "inv_sales"

    id = db.Column(db.Integer, primary_key=True)
    trans_date = db.Column(
        db.Date, nullable=False, default=lambda: datetime.now(UTC).date()
    )
    item_name = db.Column(db.String(), nullable=False)
    each_count = db.Column(db.Integer, nullable=False)
    waste = db.Column(db.Integer, nullable=False)
    sales_total = db.Column(db.Integer, nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("inv_items.id"), nullable=False)
    store_id = db.Column(db.Integer, db.ForeignKey("restaurants.id"), nullable=False)

    def __repr__(self):
        return f"InvSales('{self.trans_date}', '{self.item_name}', '{self.each_count}', '{self.waste}', '{self.sales_total}', '{self.item_id}', '{self.store_id}')"


class StockcountPurchases(db.Model):
    __tablename__ = "stockcount_purchases"

    transactionid = db.Column(db.String, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=lambda: datetime.now(UTC).date())
    week = db.Column(db.Integer)
    period = db.Column(db.Integer)
    year = db.Column(db.Integer)
    store_id = db.Column(db.Integer)
    store = db.Column(db.String)
    item = db.Column(db.String)
    quantity = db.Column(db.Integer)
    uofm = db.Column(db.String)
    unit_count = db.Column(db.Float)


class StockcountSales(db.Model):
    __tablename__ = "stockcount_sales"
    date = db.Column(db.Date, nullable=False, default=lambda: datetime.now(UTC).date())
    dow = db.Column(db.Integer)
    week = db.Column(db.Integer)
    period = db.Column(db.Integer)
    year = db.Column(db.Integer)
    store_id = db.Column(db.Integer)
    store = db.Column(db.String)
    menuitem = db.Column(db.String)
    sales_count = db.Column(db.Float)
    ingredient = db.Column(db.String)
    concept = db.Column(db.String)
    base_usage = db.Column(db.Float)
    base_uofm = db.Column(db.String)
    count_usage = db.Column(db.Float)

    __table_args__ = (
        PrimaryKeyConstraint("date", "store", "menuitem", name="unique_sales"),
    )


class StockcountWaste(db.Model):
    __tablename__ = "stockcount_waste"
    date = db.Column(db.Date, nullable=False, default=lambda: datetime.now(UTC).date())
    dow = db.Column(db.Integer)
    week = db.Column(db.Integer)
    period = db.Column(db.Integer)
    year = db.Column(db.Integer)
    store_id = db.Column(db.Integer)
    store = db.Column(db.String)
    item = db.Column(db.String)
    uofm = db.Column(db.String)
    quantity = db.Column(db.Float)
    base_uofm = db.Column(db.String)
    base_qty = db.Column(db.Float)

    __table_args__ = (
        PrimaryKeyConstraint("date", "store", "item", name="unique_waste"),
    )


class StockcountMonthly(db.Model):
    __tablename__ = "stockcount_monthly"

    date = db.Column(db.Date, nullable=False, default=lambda: datetime.now(UTC).date())
    item_id = db.Column(db.Integer)
    item_name = db.Column(db.String)
    store_id = db.Column(db.Integer)
    count_total = db.Column(db.Integer)

    __table_args__ = (
        PrimaryKeyConstraint("date", "store_id", "item_id", name="unique_monthly"),
    )


class RecipeIngredients(db.Model):
    __tablename__ = "recipe_ingredients"

    concept = db.Column(db.String)
    menu_item = db.Column(db.String)
    recipe = db.Column(db.String)
    ingredient = db.Column(db.String)
    qty = db.Column(db.Float)
    uofm = db.Column(db.String)

    __table_args__ = (PrimaryKeyConstraint("menu_item", "recipe", "ingredient"),)


class MenuItems(db.Model):
    __tablename__ = "inv_menu_items"

    id = db.Column(db.Integer, primary_key=True)
    menu_item = db.Column(db.String)
    purchases_name = db.Column(db.String)
    purchases_id = db.Column(db.Integer)
    store_id = db.Column(db.Integer)
