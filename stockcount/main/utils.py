from flask_security import current_user

from stockcount.models import Users, Restaurants, InvItems, Item
from flask import session
from sqlalchemy import or_, and_

from datetime import timedelta
from stockcount import db

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


def item_query():
    return InvItems.query.filter(InvItems.store_id == session["store"])


def item_number():
    return InvItems.query.count()

def execute_query(query, param):
    stmt = db.text(query)
    results = db.session.execute(stmt, param).fetchall()
    return results

def getVariance(store_id, date):
    query = """
        WITH current_day AS (
            SELECT item_id, item_name, count_total
            FROM inv_count
            WHERE store_id = :store_id AND trans_date = :trans_date
        ),
        previous_day AS (
            SELECT item_name, count_total AS previous_total
            FROM inv_count
            WHERE store_id = :store_id AND trans_date = :previous_date
        ),
        sales_counts AS (
            SELECT ingredient, SUM(sales_count) AS sales_count
            FROM stockcount_sales
            WHERE date = :sales_date AND store_id = :store_id
            GROUP BY ingredient
        ),
        purchase_counts AS (
            SELECT item, CAST(unit_count AS int) AS purchase_count
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
                previous_day.previous_total + COALESCE(purchase_counts.purchase_count, 0)
                    - COALESCE(sales_counts.sales_count, 0)
                    - COALESCE(waste_counts.base_qty, 0) AS theory
            FROM current_day
            JOIN previous_day ON current_day.item_name = previous_day.item_name
            LEFT JOIN purchase_counts ON current_day.item_name = purchase_counts.item
            LEFT JOIN sales_counts ON current_day.item_name = sales_counts.ingredient
            LEFT JOIN (
                SELECT base_qty, item
                FROM stockcount_waste
                WHERE date = :waste_date
                  AND store = (SELECT store FROM locations)
            ) AS waste_counts ON current_day.item_name = waste_counts.item
        )
        SELECT
            item_id,
            item_name,
            CAST(count_total - theory AS INT) AS daily_variance
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