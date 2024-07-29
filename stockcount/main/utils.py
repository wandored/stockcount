from flask_security import current_user

from stockcount.models import Users, Restaurants, InvItems, Item, RecipeIngredients, MenuItems
from flask import session
from sqlalchemy import or_, and_, not_
from sqlalchemy.orm import joinedload

from datetime import timedelta
from stockcount import db

from icecream import ic

from collections import namedtuple

# Define a named tuple to hold the query results
MenuItemResult = namedtuple('MenuItemResult', ['menu_item', 'recipe', 'ingredient', 'id'])

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
    return Item.query.filter(
        or_(
            Item.name.like("BEEF%"),
            and_(
                Item.name.like("PORK%"),
                Item.name.like("%Chop %")  # Added wildcard for "Chop" match
            ),
            Item.name.like("%Chicken Wing Jumbo%"),
            Item.name.like("%SEAFOOD Crab Cake%"),
            Item.name.like("%PREP Marination Sirloin%")
        )
    ).order_by(Item.name).all()

def menu_item_query():
    # Subquery to get the menu_item values from the menu_items table
    menu_items_query = db.session.query(MenuItems.menu_item).filter(MenuItems.store_id == session["store"])
    excluded_menu_items = [item[0] for item in menu_items_query.all()]

    # Main query with improved exclusion to include None values
    result = db.session.query(
        RecipeIngredients.menu_item,
        RecipeIngredients.recipe,
        RecipeIngredients.ingredient,
        InvItems.id
    ).join(
        InvItems,
        RecipeIngredients.ingredient == InvItems.item_name
    ).filter(
        InvItems.store_id == session["store"],
        or_(
            RecipeIngredients.menu_item.notin_(excluded_menu_items),
            RecipeIngredients.menu_item == None
        )
    ).distinct().order_by(
        RecipeIngredients.menu_item
    ).all()
    
    # ic(result)
    
    # look for any null menu_items in result, store their recipe value
    missing = []
    for row in result:
        if row[0] is None:
            missing.append((row[1], row[2]))  # Use tuple instead of set
            result.remove(row)  # Be cautious about modifying a list while iterating

    # Output the missing items for debugging
    # ic(missing)

    # Query for each value in missing
    for item in missing:
        query_result = db.session.query(
            RecipeIngredients.menu_item,
            RecipeIngredients.recipe,
            RecipeIngredients.ingredient,
            InvItems.id
        ).join(
            InvItems, InvItems.item_name == item[1]  # Use item[1] for joining
        ).filter(
            RecipeIngredients.ingredient == item[0]  # Use item[0] for filtering
        ).first()

        if query_result:
            # result.append(MenuItemResult(*query_result))
            query_result = list(query_result)
            query_result[2] = item[1]
            result.append(MenuItemResult(*query_result))
            # ic(query_result.menu_item, query_result.recipe, query_result.ingredient, query_result.id)
                
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
    WHERE date >= :start_date AND date <= :end_date AND id = :store_id AND item = 'BEEF Steak 10oz Sirloin Choice';
    """

    params = {
        'store_id': store_id,
        'start_date': start_date,
        'end_date': end_date
    }

    results = execute_query(query, params)
    return results


def getVariance(store_id, date):
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
        WHERE date = :purchase_date AND id = :store_id
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
        'store_id': store_id,
        'trans_date': date,
        'previous_date': date - timedelta(days=1),  # Provide the correct date for previous_day query
        'sales_date': date,
        'purchase_date': date,
        'waste_date': date
    }
    results = execute_query(query, params)
    return results