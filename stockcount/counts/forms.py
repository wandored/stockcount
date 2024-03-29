from datetime import datetime

from flask_wtf import FlaskForm, Form
from wtforms import (
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
from wtforms_sqlalchemy.fields import QuerySelectField

from stockcount.models import InvItems


def item_query():
    return InvItems.query


def item_number():
    return InvItems.query.count()


class NewItemForm(FlaskForm):
    itemname = StringField("Item Name: ", validators=[DataRequired()])
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
    itemid = HiddenField(validators=[DataRequired()])
    casecount = IntegerField("Case Count: ")
    eachcount = IntegerField("Each Count: ")
    submit = SubmitField("Submit!")


# class PurchaseForm(Form):      for entering all items at same time.  not working
#    itemname = QuerySelectField('Item Name: ',
#                                query_factory=item_query,
#                                allow_blank=True,
#                                get_label='itemname')
#    casecount = IntegerField('Cases Purchased: ',
#                             default=0)


class EnterPurchasesForm(FlaskForm):
    transdate = DateField("Purchase Date: ", format="%Y-%m-%d", default=datetime.today)
    am_pm = HiddenField("PM")
    #    itemname = FieldList(FormField(PurchaseForm), min_entries=5)
    itemname = QuerySelectField(
        "Item Name: ", query_factory=item_query, allow_blank=True, get_label="item_name"
    )
    casecount = IntegerField("Cases Purchased: ", default=0)
    eachcount = IntegerField("Each Purchased: ", default=0)
    submit = SubmitField("Submit!")


class UpdatePurchasesForm(FlaskForm):
    transdate = DateField("Purchase Date: ", format="%Y-%m-%d")
    am_pm = HiddenField("PM")
    itemname = StringField("Item Name", validators=[DataRequired()])
    item_id = HiddenField(validators=[DataRequired()])
    casecount = IntegerField("Cases Purchased")
    eachcount = IntegerField("Each Purchased")
    submit = SubmitField("Submit!")


class EnterSalesForm(FlaskForm):
    transdate = DateField("Sales Date: ", format="%Y-%m-%d", default=datetime.today)
    am_pm = HiddenField("PM")
    itemname = QuerySelectField(
        "Item Name: ", query_factory=item_query, allow_blank=True, get_label="item_name"
    )
    eachcount = IntegerField("Each Sales: ", default=0)
    waste = IntegerField("Waste", default=0)
    submit = SubmitField("Submit!")


class UpdateSalesForm(FlaskForm):
    transdate = DateField("Sales Date: ", format="%Y-%m-%d")
    am_pm = HiddenField("PM")
    itemname = StringField("Item Name: ", validators=[DataRequired()])
    eachcount = IntegerField("Each Sales: ")
    waste = IntegerField("Waste: ")
    submit = SubmitField("Submit!")
    item_id = HiddenField(validators=[DataRequired()])
