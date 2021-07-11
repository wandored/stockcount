''' User utilities '''
import os
import secrets
from PIL import Image
from flask import url_for, current_app
from flask_mail import Message
from dailystockcount import mail


def save_picture(form_picture):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(
        current_app.root_path, 'static/profile_pics', picture_fn)
    output_size = (125, 125)
    i = Image.open(form_picture)
    i.thumbnail(output_size)
    i.save(picture_path)

    return picture_fn


def send_reset_email(user):
    token = user.get_reset_token(expires_sec=1800)
    msg = Message('Password Reset Request',
                  recipients=[user.email])
    msg.body = f'''To reset your password, visit the following link:

{url_for('users.reset_token', token=token, _external=True)}

If you did not make this request then simply ignore this email and no changes will be made. The link will expire in 30 minutes.
'''
    mail.send(msg)


def send_welcome_email(user):
    token = user.get_reset_token(expires_sec=86400)
    msg = Message('Welcome to DailyStockCount.com',
                  recipients=[user.email])
    msg.body = f'''You have been registered with DailyStockCount.com, you must reset your password before you can login. To do so visit the following link:

{url_for('users.reset_token', token=token, _external=True)}

DailyStockCount.com is an app used for daily inventory of critical items.  If you feel you have received this email by mistake you may delete it.  The link will expire in 24 hours.
'''
    mail.send(msg)
