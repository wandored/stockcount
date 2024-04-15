from flask_security import current_user
from stockcount.models import Users




def set_user_access():
    store_list = Users.query.filter_by(id=current_user.id).first()
    # get number of stores user has access to and store id in a list
    access = []
    for store in store_list.stores:
        print(store.id)
        if store.id in [99, 98]:
            access = [3,4,5,6,9,10,11,12,13,14,15,16,17,18,19]
            return access
        access.append(store.id)
    return access
