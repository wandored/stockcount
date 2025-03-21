from flask_security import current_user

from stockcount.models import (
    InvCount,
    StockcountPurchases,
    StockcountSales,
    StockcountWaste,
    Users,
    Restaurants,
    InvItems,
    Item,
    RecipeIngredients,
    MenuItems,
)
from flask import session
from sqlalchemy import or_, and_, not_
from sqlalchemy.orm import joinedload

from datetime import timedelta
from stockcount import db

from icecream import ic

from collections import namedtuple

# Define a namedtuple called 'MenuItem'
MenuItem = namedtuple("MenuItem", ["menu_item", "recipe", "ingredient", "id"])


def set_user_access():
    store_list = Users.query.filter_by(id=current_user.id).first()
    # get number of stores user has access to and store id in a list
    access = []
    for store in store_list.stores:
        # print(store.id)
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
    return (
        Item.query.filter(
            or_(
                Item.name.like("BEEF%"),
                and_(
                    Item.name.like("PORK%"),
                    Item.name.like("%Chop %"),  # Added wildcard for "Chop" match
                ),
                Item.name.like("%Chicken Wing Jumbo%"),
                Item.name.like("%SEAFOOD Crab Cake%"),
                Item.name.like("%PREP Marination Sirloin%"),
            )
        )
        .order_by(Item.name)
        .all()
    )


def menu_item_query():
    result = []
    missing = []

    # Initial query to get all items
    initial_results = (
        db.session.query(
            RecipeIngredients.menu_item,
            RecipeIngredients.recipe,
            RecipeIngredients.ingredient,
            InvItems.id,
        )
        .join(InvItems, RecipeIngredients.ingredient == InvItems.item_name)
        .filter(InvItems.store_id == session["store"])
        .distinct()
        .order_by(RecipeIngredients.menu_item)
        .all()
    )

    # Separate items with menu_item as None and not None
    missing = [item for item in initial_results if item.menu_item is None]
    result = [item for item in initial_results if item.menu_item is not None]

    # ic(missing)
    for item in missing:
        # Fetch the menu_item from RecipeIngredients and extract the value
        menu_item_result = (
            db.session.query(RecipeIngredients.menu_item)
            .filter(RecipeIngredients.ingredient == item.recipe)
            .all()
        )
        # drop any duplicates or menu_item is None
        menu_item_result = list(set(menu_item_result))
        # drop any row with menu_item = None
        menu_item_result = [
            menu_item for menu_item in menu_item_result if menu_item[0] is not None
        ]
        # if menu_item_result is empty, skip it
        if not menu_item_result:
            continue

        # Fetch the id from InvItems and extract the value
        id_result = (
            db.session.query(InvItems.id)
            .filter(
                InvItems.item_name == item.ingredient,
                InvItems.store_id == session["store"],
            )
            .scalar()
        )

        # ic(menu_item_result, item.recipe, item.ingredient, id_result, session["store"])

        # Add a new row to result for each menu_item_result using the same recipe, ingredient, and id
        for menu_item in menu_item_result:
            result.append(
                MenuItem(menu_item[0], item.recipe, item.ingredient, id_result)
            )
        # remove the item from missing
        missing.remove(item)

    # Query inv_menu_items and remove any that are already in result
    menu_items = (
        db.session.query(MenuItems.menu_item)
        .filter(MenuItems.store_id == session["store"])
        .all()
    )
    menu_items = [menu_item[0] for menu_item in menu_items]
    result = [item for item in result if item.menu_item not in menu_items]

    # ic(result)
    return result


def item_query():
    return InvItems.query.filter(InvItems.store_id == session["store"])


def item_number():
    return InvItems.query.count()


def execute_query(query, param):
    stmt = db.text(query)
    results = db.session.execute(stmt, param).fetchall()
    return results


def getSirloinPurchases(store_id, start_date, end_date):
    query = """
    SELECT
        date,
        item,
        unit_count
    FROM stockcount_purchases
    WHERE date >= :start_date AND date <= :end_date AND store_id = :store_id AND item = 'BEEF Steak 10oz Sirloin Choice';
    """

    params = {"store_id": store_id, "start_date": start_date, "end_date": end_date}

    results = execute_query(query, params)
    return results


def getTheory(item_name, date):
    begin_count = (
        db.session.query(InvCount.previous_total)
        .filter(
            InvCount.store_id == session["store"],
            InvCount.item_name == item_name,
            InvCount.trans_date == date,
        )
        .first()
    )
    if begin_count is None:
        begin_count = 0
    else:
        begin_count = begin_count[0]

    purchases = (
        db.session.query(StockcountPurchases.unit_count)
        .filter(
            StockcountPurchases.store_id == session["store"],
            StockcountPurchases.item == item_name,
            StockcountPurchases.date == date,
        )
        .first()
    )
    if purchases is None:
        purchases = 0
    else:
        purchases = purchases[0]

    sales = (
        db.session.query(StockcountSales.count_usage)
        .filter(
            StockcountSales.store_id == session["store"],
            StockcountSales.ingredient == item_name,
            StockcountSales.date == date,
        )
        .first()
    )
    if sales is None:
        sales = 0
    else:
        sales = sales[0]

    waste = (
        db.session.query(StockcountWaste.quantity)
        .filter(
            StockcountWaste.store_id == session["store"],
            StockcountWaste.item == item_name,
            StockcountWaste.date == date,
        )
        .first()
    )
    if waste is None:
        waste = 0
    else:
        waste = waste[0]

    print(
        f"{begin_count + purchases - sales - waste} = {begin_count} + {purchases} - {sales} - {waste}"
    )
    theory = begin_count + purchases - sales - waste

    return theory


def getCount(item_name, date):
    count = (
        db.session.query(InvCount.count_total)
        .filter(
            InvCount.store_id == session["store"],
            InvCount.item_name == item_name,
            InvCount.trans_date == date,
        )
        .first()
    )
    if count is None:
        count = 0
    else:
        count = count[0]

    return count


def getVariance(store_id, date, prev_date):
    query = """
    WITH current_day AS (
        SELECT item_id, item_name, count_total
        FROM inv_count
        WHERE store_id = :store_id AND trans_date = :trans_date
    ),
    previous_day AS (
        SELECT item_name, COALESCE(count_total, 0) AS previous_total
        FROM inv_count
        WHERE store_id = :store_id AND trans_date = :previous_date
    ),
    sales_counts AS (
        SELECT item_name, COALESCE(each_count, 0) AS sales_count, COALESCE(waste, 0) AS waste_count
        FROM inv_sales
        WHERE trans_date = :sales_date AND store_id = :store_id
        GROUP BY item_name, each_count, waste
    ),
    purchase_counts AS (
        SELECT item, CAST(COALESCE(unit_count, 0) AS int) AS purchase_count
        FROM stockcount_purchases
        WHERE date = :purchase_date AND store_id = :store_id
    ),
    locations AS (
        SELECT name AS store
        FROM restaurants
        WHERE id = :store_id
    ),
    theory_calculation AS (
        SELECT
            current_day.item_name,
            COALESCE(previous_day.previous_total, 0) + COALESCE(purchase_counts.purchase_count, 0)
            - COALESCE(sales_counts.sales_count, 0)
            - COALESCE(sales_counts.waste_count, 0) AS theory
            FROM current_day
            LEFT JOIN previous_day ON current_day.item_name = previous_day.item_name
            LEFT JOIN purchase_counts ON current_day.item_name = purchase_counts.item
            LEFT JOIN sales_counts ON current_day.item_name = sales_counts.item_name
    )
    SELECT
        item_id,
        item_name,
        CAST(COALESCE(count_total, 0) - theory AS INT) AS daily_variance
    FROM current_day
    JOIN theory_calculation USING (item_name);
    """

    params = {
        "store_id": store_id,
        "trans_date": date,
        "previous_date": prev_date,  # Provide the correct date for previous_day query
        "sales_date": date,
        "purchase_date": date,
        "waste_date": date,
    }
    results = execute_query(query, params)
    return results
