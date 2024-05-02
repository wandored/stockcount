from datetime import datetime

from flask import session
from flask_wtf import FlaskForm, Form
from wtforms import (
    widgets,
    FieldList,
    FormField,
    HiddenField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
)
from wtforms.fields import DateField
from wtforms.validators import DataRequired
from wtforms_sqlalchemy.fields import QuerySelectField, QuerySelectMultipleField
from collections import namedtuple

from stockcount.models import InvItems, Restaurants, Item


def store_query():
    return (
        Restaurants.query.filter(Restaurants.id.in_(session["access"]))
        .order_by(Restaurants.name)
        .all()
    )


def stockcount_query():
    # return InvCount items that begin with "BEEF"
    return Item.query.filter(Item.name.like("BEEF%")).order_by(Item.name).all()


def item_query():
    return InvItems.query.filter(InvItems.store_id == session["store"])


def item_number():
    return InvItems.query.count()


class MultiCheckboxField(QuerySelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


class StoreForm(FlaskForm):
    stores = MultiCheckboxField(
        "Select Store",
        query_factory=store_query,
        get_label="name",
    )
    storeform_submit = SubmitField("Submit")


class NewItemForm(FlaskForm):
    itemname = QuerySelectField(
        "Select Item: ",
        query_factory=stockcount_query,
        allow_blank=False,
        get_label="name",
        get_pk=lambda x: x.name,
    )
    casepack = IntegerField("# per Case: ", validators=[DataRequired()])
    submit = SubmitField("Submit")


class UpdateItemForm(FlaskForm):
    itemname = StringField("Item Name: ", validators=[DataRequired()])
    casepack = IntegerField("# per Case: ", validators=[DataRequired()])
    submit = SubmitField("Submit")


class EnterCountForm(FlaskForm):
    transdate = DateField("Count Date: ", format="%Y-%m-%d", default=datetime.today)
    am_pm = SelectField("Count Type: ", choices=["PM", "AM"])
    itemname = QuerySelectField(
        "Item Name: ", query_factory=item_query, allow_blank=True, get_label="item_name"
    )
    casecount = IntegerField("Case Count: ", default=0)
    eachcount = IntegerField("Each Count: ", default=0)
    submit = SubmitField("Submit!")


class UpdateCountForm(FlaskForm):
    transdate = DateField("Count Date: ", format="%Y-%m-%d")
    am_pm = SelectField("Count Type: ", choices=["PM", "AM"])
    itemname = StringField("Item Name: ", validators=[DataRequired()])
    item_id = HiddenField(validators=[DataRequired()])
    casecount = IntegerField("Case Count: ")
    eachcount = IntegerField("Each Count: ")
    submit = SubmitField("Submit!")


class EnterPurchasesForm(FlaskForm):
    transdate = DateField("Purchase Date: ", format="%Y-%m-%d", default=datetime.today)
    itemname = QuerySelectField(
        "Item Name: ", query_factory=item_query, allow_blank=True, get_label="item_name"
    )
    casecount = IntegerField("Cases Purchased: ", default=0)
    eachcount = IntegerField("Each Purchased: ", default=0)
    submit = SubmitField("Submit!")


class UpdatePurchasesForm(FlaskForm):
    transdate = DateField("Purchase Date: ", format="%Y-%m-%d")
    itemname = StringField("Item Name", validators=[DataRequired()])
    item_id = HiddenField(validators=[DataRequired()])
    casecount = IntegerField("Cases Purchased")
    eachcount = IntegerField("Each Purchased")
    submit = SubmitField("Submit!")


class EnterSalesForm(FlaskForm):
    itemname = SelectField("Item Name: ", choices=[], validators=[DataRequired()])
    item_id = HiddenField(validators=[DataRequired()])
    eachcount = IntegerField("Each Sales: ", default=0)
    waste = IntegerField("Waste", default=0)


class SalesForm(FlaskForm):
    transdate = DateField("Sales Date: ", format="%Y-%m-%d", default=datetime.today)
    sales = FieldList(FormField(EnterSalesForm), min_entries=1)
    submit = SubmitField("Submit!")


class UpdateSalesForm(FlaskForm):
    transdate = DateField("Sales Date: ", format="%Y-%m-%d")
    itemname = StringField("Item Name: ", validators=[DataRequired()])
    eachcount = IntegerField("Each Sales: ")
    waste = IntegerField("Waste: ")
    submit = SubmitField("Submit!")
    item_id = HiddenField(validators=[DataRequired()])
