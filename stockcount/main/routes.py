"""main/routes.py is the main flask routes page"""

import logging
from datetime import datetime, timedelta

from flask import flash, redirect, render_template, session, url_for
from flask_security import current_user, login_required
from icecream import ic
from sqlalchemy import Integer, cast, func

from stockcount import db
from stockcount.counts.forms import StoreForm
from stockcount.main import blueprint
from stockcount.main.utils import set_user_access
from stockcount.models import (
    InvCount,
    InvItems,
    InvSales,
    Restaurants,
    StockcountMonthly,
    StockcountPurchases,
    StockcountSales,
    StockcountWaste,
)


@blueprint.route("/", methods=["GET", "POST"])
@blueprint.route("/report/", methods=["GET", "POST"])
@login_required
def report():
    # skip the first error message in the session
    if session.get("_flashes") is not None:
        session["_flashes"] = session["_flashes"][1:]

    """route for reports.html"""
    session["access"] = set_user_access()
    if session.get("store") is None or session.get("store") not in session["access"]:
        session["store"] = session["access"][0]
    current_location = Restaurants.query.filter_by(id=session["store"]).first()
    # Get the most recent day that was counted
    last_count = (
        InvCount.query.filter_by(store_id=session["store"])
        .order_by(InvCount.trans_date.desc(), InvCount.count_time.desc())
        .first()
    )

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

    if last_count is None:
        flash("You must first enter Counts to see Reports!", "warning")
        logging.error(
            f"User {current_user.email} attempted to access reports without counts"
        )
        return redirect(url_for("counts_blueprint.count"))

    # convert the last_count to a date
    last_count = last_count.trans_date.strftime("%Y-%m-%d")
    last_count = datetime.strptime(last_count, "%Y-%m-%d")
    penaltimate_count = last_count - timedelta(days=1)

    # Get the date of the 2nd most recent count.
    prev_date = (
        db.session.query(InvCount.trans_date)
        .filter(
            InvCount.store_id == session["store"],
            InvCount.trans_date < last_count,
        )
        .order_by(InvCount.trans_date.desc())
        .first()
    )
    # check if pre_date is None and set it to penaltimate_count if needed
    if prev_date is None:
        prev_date = penaltimate_count
    else:
        prev_date = prev_date[0]
        prev_date = prev_date.strftime("%Y-%m-%d")

    items = (
        db.session.query(
            InvItems.id, InvItems.item_name, InvItems.store_id, InvItems.id
        )
        .filter(InvItems.store_id == session["store"])
        .all()
    )
    data_rows = []
    for item in items:
        # build theory table
        current_count = (
            db.session.query(
                StockcountMonthly.count_total,
            )
            .filter(
                StockcountMonthly.store_id == session["store"],
                StockcountMonthly.item_id == item.id,
                StockcountMonthly.date == last_count,
            )
            .first()
        )
        previous_count = (
            db.session.query(
                StockcountMonthly.count_total,
            )
            .filter(
                StockcountMonthly.store_id == session["store"],
                StockcountMonthly.item_id == item.id,
                StockcountMonthly.date == penaltimate_count,
            )
            .first()
        )
        purchases = (
            db.session.query(func.sum(StockcountPurchases.unit_count))
            .filter(
                StockcountPurchases.store_id == session["store"],
                StockcountPurchases.item == item.item_name,
                StockcountPurchases.date == last_count,
            )
            .scalar()
        )
        sales = (
            db.session.query(func.sum(StockcountSales.count_usage))
            .filter(
                StockcountSales.store_id == session["store"],
                StockcountSales.ingredient == item.item_name,
                StockcountSales.date == last_count,
            )
            .scalar()
        )
        waste = (
            db.session.query(func.sum(StockcountWaste.quantity))
            .filter(
                StockcountWaste.store_id == session["store"],
                StockcountWaste.item == item.item_name,
                StockcountWaste.date == last_count,
            )
            .scalar()
        )

        current_count = current_count[0] if current_count is not None else 0
        previous_count = previous_count[0] if previous_count is not None else 0
        purchases = purchases if purchases is not None else 0
        sales = sales if sales is not None else 0
        waste = waste if waste is not None else 0
        theory = previous_count + purchases - sales - waste
        variance = current_count - theory

        row = {
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
        data_rows.append(row)

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
    # convert the date_time to a date
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)

    # set end_date to today() - 1
    end_date = datetime.now().date() - timedelta(days=1)
    weekly = end_date - timedelta(days=6)
    monthly = end_date - timedelta(days=27)
    entered_count_yesterday = (
        InvCount.query.filter_by(
            store_id=session["store"], trans_date=yesterday
        ).first()
        is not None
    )

    # count_list = (
    #     db.session.query(InvCount)
    #     .filter(
    #         InvCount.store_id == session["store"],
    #         InvCount.item_id == product,
    #         InvCount.count_time == "PM",
    #         InvCount.trans_date >= monthly,
    #         InvCount.trans_date <= today,
    #     )
    #     .order_by(InvCount.trans_date.desc())
    #     .limit(7)
    # )
    count_list = (
        db.session.query(StockcountMonthly)
        .filter(
            StockcountMonthly.store_id == session["store"],
            StockcountMonthly.item_id == product,
            StockcountMonthly.date < today,
        )
        .order_by(StockcountMonthly.date.desc())
        .limit(7)
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

    # get todays sales and waste from Inv_sales
    sales_end = db.session.query(
        InvSales.item_name, InvSales.each_count, InvSales.waste
    ).filter(
        InvSales.store_id == session["store"],
        InvSales.item_id == product,
        InvSales.trans_date == today,
    )

    # Fetch all purchase, sales, and waste data upfront
    purchase_data = {
        purchase.date: int(purchase.unit_count) for purchase in purchase_list
    }
    sales_data = {sale.date: int(sale.sales_count) for sale in sales_list}
    waste_data = {waste.date: abs(int(waste.base_qty)) for waste in waste_list}

    count_list = list(count_list)

    # Initialize variables to keep track of previous_total
    details = []
    previous_total = None

    # Determine the start date
    if any(count.date == today for count in count_list):
        start_date = today
    else:
        start_date = today - timedelta(days=1)

    # Iterate over the last 7 days starting from the start_date
    carryover: int = 0
    for day in range(8):
        current_date = start_date - timedelta(days=day)
        count = next((c for c in count_list if c.date == current_date), None)

        # account for days without a count
        if count:
            count_total = count.count_total
        else:
            count_total = 0

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

        # Append the current detail to the details list
        details.append(detail)

        # if its the last day, get the sales and waste from InvSales
        if current_date == today:
            for sale in sales_end:
                detail["sales_count"] = sale.each_count
                detail["sales_waste"] = sale.waste
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
    waste_total = sum(d["sales_waste"] for d in details)
    count_total_list = [d["count_total"] for d in details]
    avg_count_total = sum(count_total_list) / len(count_total_list)
    # watch for division by 0
    try:
        avg_on_hand = current_on_hand / avg_sales_total
    except ZeroDivisionError:
        avg_on_hand = 0

    # TODO update charts
    # Chart 1
    unit_query = (
        db.session.query(InvCount)
        .filter(
            InvCount.store_id == session["store"],
            InvCount.item_id == product,
            InvCount.count_time == "PM",
            InvCount.trans_date >= weekly,
        )
        .order_by(InvCount.trans_date)
        .all()
    )
    labels = []
    unit_onhand = []
    unit_sales = []
    for i in unit_query:
        labels.append(i.trans_date.strftime("%A"))
        unit_onhand.append(i.count_total)
        sales_list = db.session.query(
            func.sum(StockcountSales.count_usage).label("total")
        ).filter(
            StockcountSales.date == i.trans_date,
            StockcountSales.store == current_location.name,
            StockcountSales.ingredient == current_product.item_name,
        )
        for row in sales_list:
            unit_sales.append(int(row.total or 0))

    # Chart #2
    sales_query = (
        db.session.query(
            func.extract("dow", InvSales.trans_date).label("dow"),
            func.avg(InvSales.each_count).label("average"),
        )
        .filter(
            InvSales.store_id == session["store"],
            InvSales.item_id == product,
            InvSales.trans_date >= monthly,
        )
        .group_by(func.extract("dow", InvSales.trans_date))
    )

    weekly_avg = (
        db.session.query(
            InvSales,
            func.avg(InvSales.each_count).label("sales_avg"),
            func.avg(InvSales.waste).label("waste_avg"),
        )
        .filter(
            InvSales.store_id == session["store"],
            InvSales.item_id == product,
            InvSales.trans_date >= monthly,
        )
        .group_by(InvSales.id)
    )

    daily_sales = []
    for row in sales_query:
        daily_sales.append(float(row.average))
    day_avg_sales = []
    for d in daily_sales:
        day_avg_sales.append(d)
    avg_sales_day = []
    avg_waste_day = []
    for w in weekly_avg:
        avg_sales_day.append(float(w.sales_avg))
        avg_waste_day.append(float(w.waste_avg))

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
        avg_sales_day=avg_sales_day,
        avg_waste_day=avg_waste_day,
    )
