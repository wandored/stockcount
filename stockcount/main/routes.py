""" main/routes.py is the main flask routes page """
from datetime import datetime, timedelta

from flask import flash, redirect, render_template, session, url_for
from flask_security import current_user, login_required
from icecream import ic
from sqlalchemy import and_, func

from stockcount import db
from stockcount.main import blueprint
from stockcount.main.utils import set_user_access
from stockcount.models import InvCount, InvItems, InvPurchases, InvSales, Restaurants, StockcountPurchases
from stockcount.counts.forms import StoreForm

import logging

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
    
    ic(date_time)

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
        query = db.session.query(
            InvCount.count_total.label("today_count"),
            StockcountPurchases.each_count.label("today_purchase"),
            InvSales.each_count.label("today_sales_total"),
            InvSales.waste.label("today_sales_waste"),
        ).outerjoin(
            StockcountPurchases,
            and_(
                StockcountPurchases.id == InvCount.store_id,
                StockcountPurchases.item == InvCount.item_name,
                StockcountPurchases.date == InvCount.trans_date
            )
        ).outerjoin(
            InvSales,
            and_(
                InvSales.store_id == InvCount.store_id,
                InvSales.item_id == InvCount.item_id,
                InvSales.trans_date == InvCount.trans_date
            )
        ).filter(
            InvCount.store_id == session["store"],
            InvCount.item_id == item.id,
            InvCount.trans_date == today,
        ).first()
                
        # Query for yesterday's count
        yesterday_query = db.session.query(
            InvCount.count_total.label("yesterday_count"),
        ).filter(
            InvCount.store_id == session["store"],
            InvCount.item_id == item.id,
            InvCount.trans_date == yesterday,
        ).first()
        
        ic(item.item_name, query, yesterday_query)
        
        # Get values needed for variance calculation & display 
        if query.today_count is not None:
            item.count_total = query.today_count
        else:
            item.count_total = 0
        if query.today_purchase is not None:
            item.purchase_count = int(query.today_purchase)
        else:
            item.purchase_count = 0
        if query.today_sales_total is not None:
            item.sales_count = query.today_sales_total
        else:
            item.sales_count = 0
        if query.today_sales_waste is not None:
            item.sales_waste = query.today_sales_waste
        else:
            item.sales_waste = 0
        if yesterday_query is not None:
            item.previous_count = yesterday_query.yesterday_count
        else:
            item.previous_count = 0

        # calculate the theory and variance
        item.theory = item.previous_count + item.purchase_count - item.sales_count - item.sales_waste        
        item.daily_variance = item.count_total - item.theory

        # list of needed data
        list_item = {"item_id": item.id, "item_name": item.item_name, "daily_variance": item.daily_variance}
        ordered_counts.append(list_item)
        
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
    # restrict results to the last 7 & 28 days
    last_count = (
        InvCount.query.filter_by(store_id=session["store"])
        .order_by(InvCount.trans_date.desc())
        .first()
    )
    end_date = last_count.trans_date
    weekly = end_date - timedelta(days=6)
    monthly = end_date - timedelta(days=27)

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
        func.sum(InvSales.each_count).label("total"),
        func.avg(InvSales.each_count).label("sales_avg"),
    ).filter(
        InvSales.store_id == session["store"],
        InvSales.item_id == product,
        InvSales.trans_date >= weekly,
    )
    purchase_weekly = db.session.query(
        func.sum(StockcountPurchases.each_count).label("total")
    ).filter(
        StockcountPurchases.id == session["store"],
        StockcountPurchases.item == product,
        StockcountPurchases.date >= weekly,
    )
    on_hand_weekly = db.session.query(
        func.avg(InvCount.count_total).label("average")
    ).filter(
        InvCount.store_id == session["store"],
        InvCount.item_id == product,
        InvCount.trans_date >= weekly,
    )

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
            db.session.query(InvSales)
            .filter(
                InvSales.store_id == session["store"],
                InvSales.item_id == product,
                InvSales.trans_date == i.trans_date,
            )
            .first()
        )
        if sales_list:
            unit_sales.append(sales_list.sales_total)
        else:
            unit_sales.append(0)

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
    result = (
        db.session.query(
            InvCount.trans_date,
            func.sum(StockcountPurchases.each_count).label("purchase_count"),
            func.sum(InvSales.each_count).label("sales_count"),
            func.sum(InvSales.waste).label("sales_waste"),
            InvCount.count_total,
        )
        .select_from(InvCount)
        .outerjoin(
            InvSales,
            and_(
                InvSales.trans_date == InvCount.trans_date,
                InvSales.item_id == product,
                InvSales.store_id == session["store"],
            ),
        )
        .outerjoin(
            StockcountPurchases,
            and_(
                StockcountPurchases.date == InvCount.trans_date,
                StockcountPurchases.item == InvCount.item_name,
                StockcountPurchases.id == session["store"],
            ),
        )
        .group_by(
            InvCount.trans_date,
            InvCount.count_total,
        )
        .order_by(InvCount.trans_date.desc())
        .filter(
            InvCount.store_id == session["store"],
            InvCount.item_id == product,
            InvCount.count_time == "PM",
            InvCount.trans_date >= weekly,
        )
    )
    
    # convert result to dict
    details = []
    for row in result:
        row_dict = row._asdict()
        row_dict['previous_total'] = 0
        row_dict['purchase_count'] = int(row_dict['purchase_count'] or 0)
        row_dict['theory'] = 0
        row_dict['daily_variance'] = 0
        details.append(row_dict)
    
    # Get previous total and add to details
    yesterday = end_date - timedelta(days=1)
    for i in range(len(details)):
        seven_days_ago_total = (
            db.session.query(InvCount.count_total)
            .filter(
                InvCount.trans_date == yesterday,
                InvCount.store_id == session["store"],
                InvCount.item_id == product
            ).first())
        if seven_days_ago_total is not None:        
            details[i]['previous_total'] = seven_days_ago_total[0]
            
        # calculate theory and variance
        details[i]['theory'] = (details[i]['previous_total'] or 0) + int(details[i]['purchase_count'] or 0) - (details[i]['sales_count'] or 0) - (details[i]['sales_waste'] or 0)
        details[i]['daily_variance'] = (details[i]['count_total'] or 0) - (details[i]['theory'] or 0)
        
        yesterday -= timedelta(days=1)
        
    item_name = db.session.query(InvItems).filter(InvItems.id == product).first()

    return render_template(
        "main/details.html",
        title="Item Variance Details",
        **locals(),
    )
