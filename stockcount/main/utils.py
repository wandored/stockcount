from flask_security import current_user
import base64
import json
import os
import time
import logging

from stockcount.models import (
    InvCount,
    ItemConversion,
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
from sqlalchemy import or_, and_, func
from sqlalchemy.orm import joinedload

import datetime
from stockcount import db
import requests
from collections import namedtuple, defaultdict
from stockcount.config import Config

# Define a namedtuple called 'MenuItem'

MenuItem = namedtuple("MenuItem", ["menu_item", "recipe", "ingredient", "id"])


def decode_jwt(token):
    """Decode a JWT without verification just to extract the payload"""
    payload = token.split(".")[1]
    padded = payload + "=" * (-len(payload) % 4)  # JWT base64 padding
    decoded_bytes = base64.urlsafe_b64decode(padded)
    return json.loads(decoded_bytes)


def get_access_token(api_access_url):
    """
    Fetches the OAuth2 access token required to authenticate API requests.
    Always returns a dict with structure matching Toast's spec:
    {
        "token": {
            "tokenType": "Bearer",
            "scope": "...",
            "expiresIn": int,
            "accessToken": "...",
            "idToken": "...",
            "refreshToken": "..."
        },
        "status": "SUCCESS"
    }
    """
    if os.path.exists(Config.TOKEN_CACHE_FILE):
        with open(Config.TOKEN_CACHE_FILE) as f:
            cache = json.load(f)
            token_data = cache.get("token")
            if isinstance(token_data, dict) and "token" in token_data:
                access_token = token_data["token"].get("accessToken")
                if access_token:
                    payload = decode_jwt(access_token)
                    exp = payload.get("exp", 0)
                    if time.time() < exp - 60:
                        return token_data

    url = f"{api_access_url}/authentication/v1/authentication/login"
    headers = {"Content-Type": "application/json"}
    data = {
        "userAccessType": Config.USER_ACCESS_TYPE,
        "clientId": Config.CLIENT_ID,
        "clientSecret": Config.CLIENT_SECRET,
    }

    response = requests.post(
        url,
        headers=headers,
        json=data,
    )
    if response.ok:
        token_data = response.json()
        with open(Config.TOKEN_CACHE_FILE, "w") as f:
            json.dump({"token": token_data}, f)
        return token_data
    else:
        raise RuntimeError(
            f"Failed to get access token: {response.status_code} {response.text}"
        )


def get_bulk_orders(url, headers, params, max_page_size=100, rate_limit_wait=5):
    """Fetch all orders from /ordersBulk using page & pageSize pagination."""
    all_orders = []
    page = 1

    while True:
        query = params.copy()
        query["pageSize"] = max_page_size
        query["page"] = page

        response = requests.get(url, headers=headers, params=query)
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, list):
            raise ValueError("Expected a list of orders from /ordersBulk")

        all_orders.extend(data)

        if len(data) < max_page_size:
            break  # last page reached

        page += 1
        time.sleep(rate_limit_wait)  # avoid hitting Toast’s rate limits

    return all_orders


def get_current_day_menu_item_sales(store_id, unique_items, businessDate=None):
    """
    Fetch sales for a given Toast business date.

    Args:
        store_id (int): Store ID.
        unique_items (list[str]): Menu items to filter.
        business_date (date, optional): Business date for Toast query.
                                        Defaults to today's calendar date.

    Returns:
        dict: {menuitem_name: {"count": int, "item_name": str}, ...}
    """
    if businessDate is None:
        businessDate = datetime.date.today()

    business_date_str = businessDate.strftime("%Y%m%d")

    restaurant = Restaurants.query.filter_by(id=store_id).first()
    if not restaurant or not getattr(restaurant, "toast_guid", None):
        raise ValueError(f"Invalid store ID or missing Toast GUID: {store_id}")
    guid = str(restaurant.toast_guid)

    api_access_url = Config.TOAST_API_ACCESS_URL
    token_data = get_access_token(api_access_url)
    if not isinstance(token_data, dict):
        raise TypeError("Expected token to be a dictionary")
    access_token = token_data["token"]["accessToken"]

    url = f"{api_access_url}/orders/v2/ordersBulk"
    query = {
        "businessDate": business_date_str,
    }
    headers = {
        "Toast-Restaurant-External-ID": guid,
        "Authorization": f"Bearer {access_token}",
    }

    try:
        payload = get_bulk_orders(url, headers, params=query)
    except Exception as e:
        print(f"Error fetching sales data: {e}")
        return 0

    item_counts = defaultdict(lambda: {"count": 0, "item_name": ""})

    def process_selection(sel):
        """Recursively process a selection and any nested children."""
        if sel.get("voided", False):
            return

        item_name = sel.get("displayName", "Unknown Item")
        quantity = sel.get("quantity", 0) or 0

        item_counts[item_name]["count"] += quantity
        if not item_counts[item_name]["item_name"]:
            item_counts[item_name]["item_name"] = item_name

        # Recurse into nested selections (casual combos often nest here)
        for child in sel.get("selections", []):
            process_selection(child)

    for order in payload:
        for check in order.get("checks", []):
            for sel in check.get("selections", []):
                process_selection(sel)

    item_counts = {
        name: item_counts[name] for name in unique_items if name in item_counts
    }
    # for item in item_counts.values():
    #     print(f"Item: {item['item_name']}, Count: {item['count']}")

    return dict(item_counts)


def get_current_day_ingredient_usage(
    store_id, target_ingredients, business_date, use_toast=False
):
    """
    Get ingredient usage for a given store and business date.

    Args:
        store_id (int): Store ID.
        target_ingredients (list[str]): Ingredients to include in the result.
        business_date (date): Date for which to calculate usage.
        use_toast (bool): If True, pull menuitem sales from Toast; otherwise use StockcountSales (R365).

    Returns:
        dict: {ingredient_name: usage_count}
    """
    usage_map = defaultdict(float)
    # print(f"Fetching menu item sales for {store_id} on {business_date}")

    if use_toast:
        # Step 1: get menuitem sales from Toast
        unique_items = (
            row.menuitem
            for row in db.session.query(StockcountSales.menuitem)
            .filter(StockcountSales.store_id == store_id)
            .distinct()
        )
        sales_dict = get_current_day_menu_item_sales(
            store_id, list(unique_items), business_date
        )
        menuitem_sales = {name: data["count"] for name, data in sales_dict.items()}

        if not menuitem_sales:
            return {}

        # Step 2: get count_usage per menuitem → ingredient from StockcountSales
        rows = (
            db.session.query(
                StockcountSales.menuitem,
                StockcountSales.ingredient,
                StockcountSales.count_usage,
            )
            .filter(
                StockcountSales.store_id == store_id,
                StockcountSales.menuitem.in_(menuitem_sales.keys()),
                StockcountSales.date == business_date,
            )
            .all()
        )

        # Step 3: sum count_usage per ingredient (no multiplication needed)
        for menu_item, ingredient, count_usage in rows:
            usage_map[ingredient] += count_usage

    else:
        # Business hours: just sum count_usage from StockcountSales
        rows = (
            db.session.query(
                StockcountSales.ingredient, func.sum(StockcountSales.count_usage)
            )
            .filter(
                StockcountSales.store_id == store_id,
                StockcountSales.date == business_date,
                StockcountSales.ingredient.in_(target_ingredients),
            )
            .group_by(StockcountSales.ingredient)
            .all()
        )
        for ingredient, count_usage in rows:
            usage_map[ingredient] += count_usage

    # Filter to only target ingredients if provided
    if target_ingredients:
        usage_map = {
            ing: usage for ing, usage in usage_map.items() if ing in target_ingredients
        }

    return dict(usage_map)


# def get_today_ingredient_usage(
#     store_id: int, ingredient_name: str, business_date: datetime.date, eastern_tz
# ) -> int:
#     """
#     Returns the total sales count for a given ingredient today, applying weight/each conversions.
#
#     :param store_id: ID of the store
#     :param ingredient_name: Name of the ingredient to calculate usage for
#     :param business_date: Date for which to pull Toast sales
#     :param eastern_tz: pytz timezone object (for now handling)
#     :return: int, total ingredient usage
#     """
#
#     # Helper function for conversion calculation
#     def get_each_conversion(row):
#         if row.uofm == getattr(row, "weight_uofm", None) and getattr(
#             row, "weight_qty", None
#         ):
#             return row.qty / row.weight_qty * (row.each_qty or 1)
#         elif row.uofm == row.each_uofm and row.each_qty:
#             return row.qty / row.each_qty
#         else:
#             return 0
#
#     # Get list of menu items that use this ingredient
#     menu_items_query = (
#         RecipeIngredients.query.join(
#             ItemConversion, ItemConversion.name == RecipeIngredients.ingredient
#         )
#         .filter(RecipeIngredients.ingredient == ingredient_name)
#         .with_entities(
#             RecipeIngredients.menu_item,
#             RecipeIngredients.qty,
#             RecipeIngredients.uofm,
#             ItemConversion.weight_qty,
#             ItemConversion.weight_uofm,
#             ItemConversion.each_qty,
#             ItemConversion.each_uofm,
#         )
#         .distinct()
#     )
#
#     each_conversions = {}
#     menu_items = []
#     for row in menu_items_query:
#         menu_items.append(row.menu_item)
#         each_conversions[row.menu_item] = get_each_conversion(row)
#
#     if not menu_items:
#         return 0
#
#     # Get Toast sales for the menu items
#     toast_sales = get_current_day_menu_item_sales(
#         store_id=store_id,
#         unique_items=menu_items,
#         businessDate=business_date,
#     )
#
#     # Compute total ingredient usage applying conversions
#     total_count_usage = sum(
#         toast_sales.get(menu_item, {}).get("count", 0) * conversion
#         for menu_item, conversion in each_conversions.items()
#     )
#
#     return round(total_count_usage)


def set_user_access():
    store_list = Users.query.filter_by(id=current_user.id).first()
    # get number of stores user has access to and store id in a list
    access = []
    for store in store_list.stores:
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
