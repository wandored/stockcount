# -*- encoding: utf-8 -*-
"""
authentication/forms.py

This module provides forms for user authentication and data input.

Classes:
    - LoginForm: Form for user login.
    - DateForm: Form for selecting a date.
    - UpdateForm: Form for updating data.
    - MultiCheckboxField: Field for selecting multiple checkboxes.
    - StoreForm: Form for selecting stores.
"""

from flask_wtf import FlaskForm
from datetime import datetime
from wtforms import widgets, SubmitField, StringField, PasswordField
from wtforms.fields import DateField
from wtforms_sqlalchemy.fields import QuerySelectMultipleField, QuerySelectField
from wtforms.validators import Email, DataRequired
from stockcount.models import Restaurants

# login and registration


def store_query():
    return (
        Restaurants.query.filter(Restaurants.active == "true")
        .order_by(Restaurants.name)
        .all()
    )


class LoginForm(FlaskForm):
    email = StringField(
        "Email Address", id="email_login", validators=[DataRequired(), Email()]
    )
    password = PasswordField("Password", id="pwd_login", validators=[DataRequired()])


class DateForm(FlaskForm):
    selectdate = DateField("", format="%Y-%m-%d")
    submit1 = SubmitField("Submit")


class UpdateForm(FlaskForm):
    selectdate = DateField("Data Update", format="%Y-%m-%d", default=datetime.today())
    submit2 = SubmitField("Submit")


class MultiCheckboxField(QuerySelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


class StoreForm(FlaskForm):
    stores = MultiCheckboxField(
        "Select Stores",
        query_factory=store_query,
        get_label="name",
    )
    submit3 = SubmitField("Submit")

