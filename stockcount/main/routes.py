"""main/routes.py is the main flask routes page"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import flash, redirect, render_template, session, url_for
from flask_security import current_user, login_required
from sqlalchemy import Integer, cast, func

from stockcount import db
from stockcount.counts.forms import StoreForm
from stockcount.main import blueprint
from stockcount.main.utils import (
    get_cached_sales,
    set_user_access,
    get_current_day_menu_item_sales,
    get_current_day_ingredient_usage,
)
from stockcount.models import (
    InvCount,
    InvItems,
    InvSales,
    ItemConversion,
    UnitsOfMeasure,
    Restaurants,
    RecipeIngredients,
    StockcountMonthly,
    StockcountPurchases,
    StockcountSales,
    StockcountWaste,
)

logger = logging.getLogger(__name__)
eastern = ZoneInfo("America/New_York")


@blueprint.route("/", methods=["GET", "POST"])
@blueprint.route("/report/", methods=["GET", "POST"])
@login_required
def report():
    # skip the first error message in the session
    if session.get("_flashes") is not None:
        session["_flashes"] = session["_flashes"][1:]

    session["access"] = set_user_access()
    if session.get("store") is None or session.get("store") not in session["access"]:
        session["store"] = session["access"][0]
    current_location = Restaurants.query.filter_by(id=session["store"]).first()

    store_form = StoreForm()
    if store_form.storeform_submit.data and store_form.validate():
        data = store_form.stores.data
        for x in data:
            if x.id in session["access"]:
                session["store"] = x.id
                flash(f"Store changed to {x.name}", "success")
            else:
                flash("You do not have access to that store!", "danger")
                logging.error(
                    f"User {current_user.email} attempted to access store {x.id} without permission"
                )
        return redirect(url_for("main_blueprint.report"))

    # Get the most recent day that was counted
    last_count_obj = (
        InvCount.query.filter_by(store_id=session["store"])
        .order_by(InvCount.trans_date.desc(), InvCount.count_time.desc())
        .first()
    )
    if last_count_obj is None:
        flash("You must first enter Counts to see Reports!", "warning")
        logging.error(
            f"User {current_user.email} attempted to access reports without counts"
        )
        return redirect(url_for("counts_blueprint.count"))

    now = datetime.now(eastern)
    today = (now - timedelta(days=1)).date() if now.hour < 8 else now.date()

    last_count = last_count_obj.trans_date
    penultimate_count = last_count - timedelta(days=1)
    count_warning_date = today - timedelta(days=2)
    missing_count_days = today - last_count
    if last_count < count_warning_date:
        flash(f"Your last count was {missing_count_days.days} days ago", "danger")

    items = (
        db.session.query(
            InvItems.id, InvItems.item_name, InvItems.store_id, InvItems.id
        )
        .filter(InvItems.store_id == session["store"])
        .all()
    )

    # --- Bulk fetch purchases ---
    purchases_results = (
        db.session.query(
            StockcountPurchases.item, func.sum(StockcountPurchases.unit_count)
        )
        .filter(
            StockcountPurchases.store_id == session["store"],
            StockcountPurchases.date == last_count,
        )
        .group_by(StockcountPurchases.item)
        .all()
    )
    purchases_map = {item: count for item, count in purchases_results}

    # --- Bulk fetch waste ---
    waste_results = (
        db.session.query(StockcountWaste.item, func.sum(StockcountWaste.quantity))
        .filter(
            StockcountWaste.store_id == session["store"],
            StockcountWaste.date == last_count,
        )
        .group_by(StockcountWaste.item)
        .all()
    )
    waste_map = {item: count for item, count in waste_results}

    # --- Bulk fetch sales ---
    sales_map = {}
    unique_items = [item.item_name for item in items]

    if now.hour < 8 or now.hour >= 21:
        for ingredient in unique_items:
            # Helper function for conversion calculation
            def get_each_conversion(row):
                if row.uofm == getattr(row, "weight_uofm", None) and getattr(
                    row, "weight_qty", None
                ):
                    return row.qty / row.weight_qty * (row.each_qty or 1)
                elif row.uofm == getattr(row, "volume_uofm", None) and getattr(
                    row, "volume_qty", None
                ):
                    return row.qty / row.volume_qty * (row.each_qty or 1)
                elif row.uofm == row.each_uofm and row.each_qty:
                    return row.qty / row.each_qty
                else:
                    return 1

            # Get menu items that use this ingredient
            menu_items_query = (
                db.session.query(
                    RecipeIngredients.menu_item,
                    RecipeIngredients.qty,
                    RecipeIngredients.uofm,
                    ItemConversion.weight_qty,
                    ItemConversion.weight_uofm,
                    ItemConversion.each_qty,
                    ItemConversion.each_uofm,
                )
                .join(
                    ItemConversion, ItemConversion.name == RecipeIngredients.ingredient
                )
                .filter(RecipeIngredients.ingredient == ingredient)
                .distinct()
            )

            menu_items = []
            each_conversions = {}
            for row in menu_items_query:
                menu_items.append(row.menu_item)
                each_conversions[row.menu_item] = get_each_conversion(row)

            if menu_items:
                toast_sales = get_cached_sales(
                    store_id=session["store"],
                    unique_items=menu_items,
                    business_date=today,
                )
                # toast_sales = get_current_day_menu_item_sales(
                #     store_id=session["store"],
                #     unique_items=menu_items,
                #     businessDate=today,
                # )

                total_count_usage = sum(
                    toast_sales.get(menu_item, {}).get("count", 0) * conversion
                    for menu_item, conversion in each_conversions.items()
                )
            else:
                total_count_usage = 0

            sales_map[ingredient] = round(total_count_usage)

    else:
        sales_map = get_current_day_ingredient_usage(
            session["store"], unique_items, last_count, use_toast=False
        )

    # --- Build data rows ---
    data_rows = []
    for item in items:
        current_count = (
            db.session.query(StockcountMonthly.count_total)
            .filter_by(
                store_id=session["store"],
                item_id=item.id,
                date=last_count,
            )
            .scalar()
            or 0
        )
        previous_count = (
            db.session.query(StockcountMonthly.count_total)
            .filter_by(
                store_id=session["store"],
                item_id=item.id,
                date=penultimate_count,
            )
            .scalar()
            or 0
        )

        purchases = purchases_map.get(item.item_name, 0) or 0
        sales = sales_map.get(item.item_name, 0)
        waste = waste_map.get(item.item_name, 0) or 0

        theory = previous_count + purchases - sales - waste
        variance = current_count - theory

        data_rows.append(
            {
                "date": last_count,
                "item_name": item.item_name,
                "item_id": item.id,
                "begin": previous_count,
                "purchases": purchases,
                "sales": sales,
                "waste": waste,
                "theory": theory,
                "count": current_count,
                "variance": variance,
            }
        )

    # sort results by variance
    data_rows = sorted(data_rows, key=lambda x: x["variance"])
    for row in data_rows:
        print(row)

    return render_template(
        "main/report.html",
        title="Variance-Daily",
        store_form=store_form,
        current_location=current_location,
        data_rows=data_rows,
        last_count=last_count,
    )


@blueprint.route("/report/<product>/details", methods=["GET", "POST"])
@login_required
def report_details(product):
    """display item details"""

    store_form = StoreForm()
    if store_form.storeform_submit.data and store_form.validate():
        data = store_form.stores.data
        for x in data:
            if x.id in session["access"]:
                session["store"] = x.id
                flash(f"Store changed to {x.name}", "success")
            else:
                flash("You do not have access to that store!", "danger")
                logging.error(
                    f"User {current_user.email} attempted to access store {x.id} without permission"
                )
        return redirect(url_for("main_blueprint.report"))

    current_location = Restaurants.query.filter_by(id=session["store"]).first()
    current_product = InvItems.query.filter_by(id=product).first()

    now = datetime.now(eastern)
    if now.hour < 8:
        today = (now - timedelta(days=1)).date()
    else:
        today = now.date()

    # set end_date to today() - 1
    end_date = datetime.now().date() - timedelta(days=1)
    weekly = end_date - timedelta(days=6)
    monthly = end_date - timedelta(days=27)
    eight_weeks = end_date - timedelta(days=55)

    count_list = (
        db.session.query(StockcountMonthly)
        .filter(
            StockcountMonthly.store_id == session["store"],
            StockcountMonthly.item_id == product,
            StockcountMonthly.date <= today,
        )
        .order_by(StockcountMonthly.date.desc())
        .limit(9)
    )

    purchase_list = (
        db.session.query(
            StockcountPurchases.date,
            func.sum(cast(StockcountPurchases.unit_count, Integer)).label("unit_count"),
        )
        .filter(
            StockcountPurchases.store == current_location.name,
            StockcountPurchases.item == current_product.item_name,
            StockcountPurchases.date >= monthly,
            StockcountPurchases.date <= today,
        )
        .group_by(StockcountPurchases.date)
        .order_by(StockcountPurchases.date.desc())
    )

    sales_list = (
        db.session.query(
            StockcountSales.date,
            func.sum(cast(StockcountSales.count_usage, Integer)).label("sales_count"),
        )
        .filter(
            StockcountSales.store == current_location.name,
            StockcountSales.ingredient == current_product.item_name,
            StockcountSales.date >= monthly,
            StockcountSales.date <= today,
        )
        .group_by(StockcountSales.date)
        .order_by(StockcountSales.date.desc())
    )

    waste_list = (
        db.session.query(
            StockcountWaste.date,
            func.sum(cast(StockcountWaste.base_qty, Integer)).label("base_qty"),
        )
        .filter(
            StockcountWaste.store == current_location.name,
            StockcountWaste.item == current_product.item_name,
            StockcountWaste.date >= monthly,
            StockcountWaste.date <= today,
        )
        .group_by(StockcountWaste.date)
        .order_by(StockcountWaste.date.desc())
    )

    # Fetch all purchase, sales, and waste data upfront
    purchase_data = {
        purchase.date: int(purchase.unit_count) for purchase in purchase_list
    }
    sales_data = {sale.date: int(sale.sales_count) for sale in sales_list}
    waste_data = {waste.date: abs(int(waste.base_qty)) for waste in waste_list}

    count_list = list(count_list)
    count_map = {count.date: count.count_total for count in count_list}

    # Initialize variables to keep track of previous_total
    details = []

    start_date = today

    # Iterate over the last 7 days starting from the start_date
    for day in range(8):
        current_date = start_date - timedelta(days=day)
        count_total = count_map.get(current_date, 0)  # Default to 0 to

        # Create a dictionary with trans_date and count_total
        detail = {
            "trans_date": current_date,
            "count_total": count_total,
            "purchase_count": purchase_data.get(current_date, 0),
            "sales_count": sales_data.get(current_date, 0),
            "sales_waste": waste_data.get(current_date, 0),
            "theory": 0,
            "daily_variance": 0,
            "previous_total": 0,
        }

        if current_date == today:
            # Helper function for conversion calculation
            def get_each_conversion(row):
                if row.uofm == getattr(row, "weight_uofm", None) and getattr(
                    row, "weight_qty", None
                ):
                    return row.qty / row.weight_qty * (row.each_qty or 1)
                elif row.uofm == getattr(row, "volume_uofm", None) and getattr(
                    row, "volume_qty", None
                ):
                    return row.qty / row.volume_qty * (row.each_qty or 1)
                elif row.uofm == row.each_uofm and row.each_qty:
                    return row.qty / row.each_qty
                else:
                    # Optionally log missing conversion
                    return 0

            # get list of menu items that use this ingredient, with recipe + conversion info
            menu_items_query = (
                db.session.query(
                    RecipeIngredients.menu_item,
                    RecipeIngredients.qty,
                    RecipeIngredients.uofm,
                    ItemConversion.weight_qty,
                    ItemConversion.weight_uofm,
                    ItemConversion.each_qty,
                    ItemConversion.each_uofm,
                )
                .join(
                    ItemConversion, ItemConversion.name == RecipeIngredients.ingredient
                )
                .filter(RecipeIngredients.ingredient == current_product.item_name)
                .distinct()
            )

            # build dict of conversions per menu item
            each_conversions = {}
            menu_items = []
            for row in menu_items_query:
                menu_items.append(row.menu_item)
                each_conversions[row.menu_item] = get_each_conversion(row)

            toast_sales = get_current_day_menu_item_sales(
                store_id=session["store"],
                unique_items=menu_items,
                businessDate=today,
            )

            total_count_usage = sum(
                toast_sales.get(menu_item, {}).get("count", 0) * conversion
                for menu_item, conversion in each_conversions.items()
            )

            detail["sales_count"] = round(total_count_usage)
            detail["sales_waste"] = 0  # No waste data for current day

        details.append(detail)

    for i in range(0, len(details) - 1):
        details[i]["previous_total"] = details[i + 1]["count_total"]

    # Recalculate theory and daily_variance after updating previous_total
    for detail in details:
        detail["theory"] = (
            detail["previous_total"]
            + detail["purchase_count"]
            - detail["sales_count"]
            - detail["sales_waste"]
        )
        detail["daily_variance"] = detail["count_total"] - detail["theory"]

    # drop last item in details list so we only have 7 days
    details.pop()

    first_entry = details[0]
    current_on_hand = (
        first_entry["count_total"]
        if first_entry["count_total"] != 0
        else first_entry["theory"]
    )
    purchase_total = sum(d["purchase_count"] for d in details)
    sales_total = sum(d["sales_count"] for d in details)
    avg_sales_total = sales_total / 7
    count_total_list = [d["count_total"] for d in details]
    avg_count_total = sum(count_total_list) / len(count_total_list)
    # watch for division by 0
    try:
        avg_on_hand = current_on_hand / avg_sales_total
    except ZeroDivisionError:
        avg_on_hand = 0

    # Chart 1
    unit_query = (
        db.session.query(StockcountMonthly)
        .filter(
            StockcountMonthly.store_id == session["store"],
            StockcountMonthly.item_id == product,
            StockcountMonthly.date >= weekly,
        )
        .order_by(StockcountMonthly.date)
        .all()
    )
    labels = []
    unit_onhand = []
    unit_sales = []
    for i in unit_query:
        labels.append(i.date.strftime("%A"))
        unit_onhand.append(i.count_total)
        sales_list = db.session.query(
            func.sum(StockcountSales.count_usage).label("total")
        ).filter(
            StockcountSales.date == i.date,
            StockcountSales.store == current_location.name,
            StockcountSales.ingredient == current_product.item_name,
        )
        for row in sales_list:
            unit_sales.append(int(row.total or 0))

    # Ensure all three lists have exactly 8 items before trimming
    if len(unit_sales) == 8 and len(unit_onhand) == 8 and len(labels) == 8:
        if unit_sales[7] == 0 and unit_onhand[7] == 0:
            # Drop the last item
            unit_sales.pop()
            unit_onhand.pop()
            labels.pop()
        else:
            # Drop the first item
            unit_sales.pop(0)
            unit_onhand.pop(0)
            labels.pop(0)

    # Chart #2
    sales_query = (
        db.session.query(
            StockcountSales.dow,
            func.avg(StockcountSales.count_usage).label("average"),
        )
        .filter(
            StockcountSales.store_id == session["store"],
            StockcountSales.ingredient == current_product.item_name,
            StockcountSales.date >= monthly,
        )
        .group_by(StockcountSales.dow)
        .order_by(StockcountSales.dow)
    )

    weekly_hi_low_sales = (
        db.session.query(
            func.max(StockcountSales.count_usage).label("sales_high"),
            func.min(StockcountSales.count_usage).label("sales_low"),
            func.avg(StockcountSales.count_usage).label("sales_avg"),
        )
        .filter(
            StockcountSales.store_id == session["store"],
            StockcountSales.ingredient == current_product.item_name,
            StockcountSales.date >= eight_weeks,
        )
        .group_by(StockcountSales.dow)
        .order_by(StockcountSales.dow)
    )

    daily_sales = []
    for row in sales_query:
        daily_sales.append(float(row.average))
    day_avg_sales = []
    for d in daily_sales:
        day_avg_sales.append(d)
    avg_sales_dow = []
    max_sales_dow = []
    min_sales_dow = []
    for w in weekly_hi_low_sales:
        avg_sales_dow.append(w.sales_avg)
        max_sales_dow.append(w.sales_high)
        min_sales_dow.append(w.sales_low)

    item_name = db.session.query(InvItems).filter(InvItems.id == product).first()

    return render_template(
        "main/details.html",
        store_form=store_form,
        title="Item Variance Details",
        current_location=current_location,
        item_name=item_name,
        details=details,
        purchase_total=purchase_total,
        sales_total=sales_total,
        avg_count_total=avg_count_total,
        avg_on_hand=avg_on_hand,
        labels=labels,
        unit_sales=unit_sales,
        unit_onhand=unit_onhand,
        day_avg_sales=day_avg_sales,
        avg_sales_dow=avg_sales_dow,
        max_sales_dow=max_sales_dow,
        min_sales_dow=min_sales_dow,
    )
