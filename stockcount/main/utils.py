from flask_security import current_user
from stockcount.models import Users




def set_user_access():
    store = Users.query.filter_by(id=current_user.id).first().stores
    # get number of stores user has access to and store id in a list
    access = []
    if 99 or 98 in access:
        access = [3,4,5,6,9,10,11,12,13,14,15,16,17,18,19]
        return access
    for i in store:
        access.append(i.id)

    return access
