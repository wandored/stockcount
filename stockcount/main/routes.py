""" main/routes.py is the main flask routes page """
from datetime import timedelta

from flask import flash, redirect, render_template, session, url_for
from flask_security import current_user, login_required
from icecream import ic
from sqlalchemy import and_, func

from stockcount import db
from stockcount.main import blueprint
from stockcount.main.utils import set_user_access
from stockcount.models import InvCount, InvItems, InvPurchases, InvSales, Restaurants


@blueprint.route("/home/")
def home():
    return render_template("main_blueprint/home.html", title="Home")


@blueprint.route("/")
@blueprint.route("/report/", methods=["GET", "POST"])
@login_required
def report():
    """route for reports.html"""
    session["access"] = set_user_access()
    if session.get("store") is None or session.get("store") not in session["access"]:
        session["store"] = session["access"][0]
    current_location = Restaurants.query.filter_by(id=session["store"]).first()

    ordered_counts = (
        InvCount.query.filter_by(store_id=session["store"])
        .order_by(
            InvCount.trans_date.desc(),
            InvCount.count_time.desc(),
            InvCount.daily_variance,
        )
        .all()
    )
    date_time = (
        InvCount.query.filter_by(store_id=session["store"])
        .order_by(InvCount.trans_date.desc(), InvCount.count_time.desc())
        .first()
    )

    if not ordered_counts:
        flash("You must first enter Counts to see Reports!", "warning")
        return redirect(url_for("counts_blueprint.count"))

    return render_template(
        "main/report.html",
        title="Variance-Daily",
        **locals(),
    )


@blueprint.route("/report/<product>/details", methods=["GET", "POST"])
@login_required
def report_details(product):
    """display item details"""
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
        func.sum(InvPurchases.purchase_total).label("total")
    ).filter(
        InvPurchases.store_id == session["store"],
        InvPurchases.item_id == product,
        InvPurchases.trans_date >= weekly,
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
            InvCount.previous_total,
            func.sum(InvPurchases.purchase_total).label("purchase_count"),
            func.sum(InvSales.each_count).label("sales_count"),
            func.sum(InvSales.waste).label("sales_waste"),
            InvCount.theory,
            InvCount.count_total,
            InvCount.daily_variance,
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
            InvPurchases,
            and_(
                InvPurchases.trans_date == InvCount.trans_date,
                InvPurchases.item_id == product,
                InvPurchases.store_id == session["store"],
            ),
        )
        .group_by(
            InvCount.trans_date,
            InvCount.previous_total,
            InvCount.count_total,
            InvCount.theory,
            InvCount.daily_variance,
        )
        .order_by(InvCount.trans_date.desc())
        .filter(
            InvCount.store_id == session["store"],
            InvCount.item_id == product,
            InvCount.count_time == "PM",
            InvCount.trans_date >= weekly,
        )
    )

    item_name = db.session.query(InvItems).filter(InvItems.id == product).first()

    return render_template(
        "main/details.html",
        title="Item Variance Details",
        **locals(),
    )
