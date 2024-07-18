""" main/routes.py is the main flask routes page """
from datetime import datetime, timedelta

from flask import flash, redirect, render_template, session, url_for
from flask_security import current_user, login_required
from icecream import ic
from sqlalchemy import and_, func, cast, Integer

from stockcount import db
from stockcount.main import blueprint
from stockcount.main.utils import set_user_access
from stockcount.models import InvCount, InvItems, InvPurchases, InvSales, Restaurants, StockcountPurchases, StockcountSales, StockcountWaste
from stockcount.counts.forms import StoreForm

import logging
import time

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
        
    # Get list of restaurant's items
    inv_items = InvItems.query.filter(InvItems.store_id == session["store"]).all()
    
    # Get the most recent day that was counted
    date_time = (
        InvCount.query.filter_by(store_id=session["store"])
        .order_by(InvCount.trans_date.desc(), InvCount.count_time.desc())
        .first()
    )
    
    # ic(date_time)

    store_form = StoreForm()
    if store_form.storeform_submit.data and store_form.validate():
        data = store_form.stores.data
        for x in data:
            if x.id in session["access"]:
                session["store"] = x.id
                flash(f"Store changed to {x.name}", "success")
            else:
                flash("You do not have access to that store!", "danger")
                logging.error(f"User {current_user.email} attempted to access store {x.id} without permission")
        return redirect(url_for("main_blueprint.report"))

    current_location = Restaurants.query.filter_by(id=session["store"]).first()
    
    if date_time is None:
        flash("You must first enter Counts to see Reports!", "warning")
        logging.error(f"User {current_user.email} attempted to access reports without counts")
        return redirect(url_for("counts_blueprint.count"))
    
    # convert the date_time to a date
    today = date_time.trans_date.strftime("%Y-%m-%d")
    today = datetime.strptime(today, "%Y-%m-%d")
    yesterday = today - timedelta(days=1)    

    ordered_counts = []
    for item in inv_items:
        # Query for today's count, purchases, sales, and waste
        count_list = (
            db.session.query(InvCount)
            .filter(
                InvCount.store_id == session["store"],
                InvCount.item_id == item.id,
                InvCount.count_time == "PM",
                InvCount.trans_date >= yesterday,
            )
            .order_by(InvCount.trans_date.desc())
        )
        
        # ic(count_list.all())
        
        purchase_list = (
            db.session.query(
                StockcountPurchases.date,
                func.sum(cast(StockcountPurchases.unit_count, Integer)).label("unit_count")
            )
            .filter(
                StockcountPurchases.store == current_location.name,
                StockcountPurchases.item == item.item_name,
                StockcountPurchases.date == today,
            )
            .group_by(StockcountPurchases.date)
            .order_by(StockcountPurchases.date.desc())
        )
        
        sales_list = (
            db.session.query(
                StockcountSales.date,
                func.sum(cast(StockcountSales.sales_count, Integer)).label("sales_count")
            )
            .filter(
                StockcountSales.store == current_location.name,
                StockcountSales.ingredient == item.item_name,
                StockcountSales.date == today,
            )
            .group_by(StockcountSales.date)
            .order_by(StockcountSales.date.desc())
        )
        ic(sales_list.all())
        
        waste_list = (
            db.session.query(
                StockcountWaste.date,
                func.sum(cast(StockcountWaste.base_qty, Integer)).label("base_qty")
            )
            .filter(
                StockcountWaste.store == current_location.name,
                StockcountWaste.item == item.item_name,
                StockcountWaste.date == today,
            )
            .group_by(StockcountWaste.date)
            .order_by(StockcountWaste.date.desc())
        )
        
        # previous_total = yesterday's count_total
        try:
            previous_total = count_list[1].count_total
        except:
            previous_total = 0
            
        sales = sales_list.first()
        waste = waste_list.first()
        purchase = purchase_list.first()
        # create a dictionary
        detail = {
            "item_id": item.id,
            "item_name": item.item_name,
            "trans_date": today,
            "count_total": count_list[0].count_total,
            "purchase_count": purchase.unit_count if purchase is not None else 0,
            "sales_count": sales.sales_count if sales is not None else 0,
            "sales_waste": waste.base_qty if waste is not None else 0,
            "theory": 0,
            "daily_variance": 0,
            "previous_total": previous_total if previous_total is not None else 0,
        }

        # Calculate the theory and daily_variance
        detail["theory"] = detail["previous_total"] + detail["purchase_count"] - detail["sales_count"] - detail["sales_waste"]
        detail["daily_variance"] = detail["count_total"] - detail["theory"]
        
        # print the dictionary
        ic(detail)

        # Append the current detail to the details list
        ordered_counts.append(detail) 
           

    # sort by name
    ordered_counts = sorted(ordered_counts, key=lambda x: x["item_name"])
                            
    return render_template(
        "main/report.html",
        title="Variance-Daily",
        **locals(),
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
                logging.error(f"User {current_user.email} attempted to access store {x.id} without permission")
        return redirect(url_for("main_blueprint.report"))

    current_location = Restaurants.query.filter_by(id=session["store"]).first()
    current_product = InvItems.query.filter_by(id=product).first()
    # restrict results to the last 7 & 28 days
    last_count = (
        InvCount.query.filter_by(store_id=session["store"])
        .order_by(InvCount.trans_date.desc())
        .first()
    )
    end_date = last_count.trans_date
    weekly = end_date - timedelta(days=6)
    monthly = end_date - timedelta(days=27)
    ic(weekly)

    # Boxes Calculations
    count_daily = (
        db.session.query(InvCount)
        .filter(
            InvCount.store_id == session["store"],
            InvCount.item_id == product,
            InvCount.count_time == "PM",
            InvCount.trans_date == end_date,
        )
        .first()
    )
    sales_weekly = db.session.query(
        func.sum(cast(StockcountSales.sales_count, Integer)).label("total"),
        func.avg(cast(StockcountSales.sales_count, Integer)).label("sales_avg"),
    ).filter(
        StockcountSales.store == current_location.name,
        StockcountSales.ingredient == current_product.item_name,
        StockcountSales.date >= weekly,
        StockcountSales.date <= end_date
    )
    purchase_weekly = db.session.query(
        func.sum(cast(StockcountPurchases.unit_count, Integer)).label("total")
    ).filter(
        StockcountPurchases.store == current_location.name,
        StockcountPurchases.item == current_product.item_name,
        StockcountPurchases.date >= weekly,
        StockcountPurchases.date <= end_date
    )
        
    on_hand_weekly = db.session.query(
        func.avg(InvCount.count_total).label("average")
    ).filter(
        InvCount.store_id == session["store"],
        InvCount.item_id == product,
        InvCount.trans_date >= weekly,
    )
    
    # get the number from purchase_weekly
    purchase_total = 0
    for row in purchase_weekly:
        purchase_total = row.total
    
    purchase_total = int(purchase_total or 0)
    # ic(purchase_total)

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
        sales_list = (
            db.session.query(
            func.sum(StockcountSales.sales_count).label("total")
            ).filter(
                StockcountSales.date == i.trans_date,
                StockcountSales.store == current_location.name,
                StockcountSales.ingredient == current_product.item_name,
            )
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

    # Details Table
    # get the last 7 days of counts starting from the end_date
    
    count_list = (
        db.session.query(InvCount)
        .filter(
            InvCount.store_id == session["store"],
            InvCount.item_id == product,
            InvCount.count_time == "PM",
            InvCount.trans_date >= monthly,
            InvCount.trans_date <= end_date,
        )
        .order_by(InvCount.trans_date.desc())
        .limit(6)
    )
    
    purchase_list = (
        db.session.query(
            StockcountPurchases.date,
            func.sum(cast(StockcountPurchases.unit_count, Integer)).label("unit_count")
        )
        .filter(
            StockcountPurchases.store == current_location.name,
            StockcountPurchases.item == current_product.item_name,
            StockcountPurchases.date >= monthly,
            StockcountPurchases.date <= end_date,
        )
        .group_by(StockcountPurchases.date)
        .order_by(StockcountPurchases.date.desc())
    )
    
    sales_list = (
        db.session.query(
            StockcountSales.date,
            func.sum(cast(StockcountSales.sales_count, Integer)).label("sales_count")
        )
        .filter(
            StockcountSales.store == current_location.name,
            StockcountSales.ingredient == current_product.item_name,
            StockcountSales.date >= monthly,
            StockcountSales.date <= end_date,
        )
        .group_by(StockcountSales.date)
        .order_by(StockcountSales.date.desc())
    )
    
    waste_list = (
        db.session.query(
            StockcountWaste.date,
            func.sum(cast(StockcountWaste.base_qty, Integer)).label("base_qty")
        )
        .filter(
            StockcountWaste.store == current_location.name,
            StockcountWaste.item == current_product.item_name,
            StockcountWaste.date >= monthly,
            StockcountWaste.date <= end_date,
        )
        .group_by(StockcountWaste.date)
        .order_by(StockcountWaste.date.desc())
    )
        
    # Fetch all purchase, sales, and waste data upfront
    purchase_data = {purchase.date: int(purchase.unit_count) for purchase in purchase_list}
    sales_data = {sale.date: int(sale.sales_count) for sale in sales_list}
    waste_data = {waste.date: abs(int(waste.base_qty)) for waste in waste_list}   

    # Initialize variables to keep track of previous_total
    details = []
    previous_total = None
    # Iterate over count_list
    for i, count in enumerate(count_list):
        # Fetch previous_total from the previous iteration
        try:
            previous_total = count_list[i + 1].count_total
        except:
            previous_total = 0
            
        # Create a dictionary with trans_date and count_total
        detail = {
            "trans_date": count.trans_date,
            "count_total": count.count_total,
            "purchase_count": purchase_data.get(count.trans_date, 0),
            "sales_count": sales_data.get(count.trans_date, 0),
            "sales_waste": waste_data.get(count.trans_date, 0),
            "theory": 0,
            "daily_variance": 0,
            "previous_total": previous_total if previous_total is not None else 0,
        }

        # Calculate the theory and daily_variance
        detail["theory"] = detail["previous_total"] + detail["purchase_count"] - detail["sales_count"] - detail["sales_waste"]
        detail["daily_variance"] = detail["count_total"] - detail["theory"]

        # Append the current detail to the details list
        details.append(detail)
        
    item_name = db.session.query(InvItems).filter(InvItems.id == product).first()

    return render_template(
        "main/details.html",
        title="Item Variance Details",
        **locals(),
    )
