from flask_security import current_user

from stockcount.models import Users, Restaurants, InvItems, Item
from flask import session
from sqlalchemy import or_, and_


def set_user_access():
    store_list = Users.query.filter_by(id=current_user.id).first()
    # get number of stores user has access to and store id in a list
    access = []
    for store in store_list.stores:
        print(store.id)
        if store.id in [99, 98]:
            access = [3, 4, 5, 6, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
            return access
        access.append(store.id)
    return access

def store_query():
    return (
        Restaurants.query.filter(Restaurants.id.in_(session["access"]))
        .order_by(Restaurants.name)
        .all()
    )


def stockcount_query():
    # Return InvCount items that begin with "BEEF" or contain "PORK Chop"
    return Item.query.filter(
        or_(
            Item.name.like("BEEF%"),
            and_(
                Item.name.like("PORK%"),
                Item.name.like("%Chop %")  # Added wildcard for "Chop" match
            )
        )
    ).order_by(Item.name).all()


def item_query():
    return InvItems.query.filter(InvItems.store_id == session["store"])


def item_number():
    return InvItems.query.count()

