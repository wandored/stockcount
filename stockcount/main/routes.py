""" main/routes.py is the main flask routes page """
from datetime import timedelta

from flask import flash, redirect, render_template, url_for
from flask_login import login_required
from sqlalchemy import and_, func

from stockcount.main import blueprint
from stockcount.models import InvCount, InvItems, InvPurchases, InvSales


@blueprint.route("/home/")
def home():
    return render_template("main_blueprint/home.html", title="Home")


@blueprint.route("/")
@blueprint.route("/report/", methods=["GET", "POST"])
@login_required
def report():
    """route for reports.html"""
    is_items = InvItems.query.first()
    if not is_items:
        flash("The first step is to add the items you want to count!", "warning")
        return redirect(url_for("counts_blueprint.new_item"))
    ordered_counts = InvCount.query.order_by(
        InvCount.trans_date.desc(), InvCount.count_time.desc(), InvCount.daily_variance
    ).all()
    date_time = InvCount.query.order_by(
        InvCount.trans_date.desc(), InvCount.count_time.desc()
    ).first()

    if not ordered_counts:
        flash("You must first enter Counts to see Reports!", "warning")
        return redirect(url_for("counts_blueprint.count"))

    return render_template(
        "main/report.html",
        title="Variance-Daily",
        ordered_counts=ordered_counts,
        date_time=date_time,
    )


@blueprint.route("/report/<product>/details", methods=["GET", "POST"])
@login_required
def report_details(product):
    """display item details"""
    # restrict results to the last 7 & 28 days
    last_count = InvCount.query.order_by(InvCount.trans_date.desc()).first()
    end_date = last_count.trans_date
    weekly = end_date - timedelta(days=6)
    monthly = end_date - timedelta(days=27)

    # Boxes Calculations
    count_daily = (
        db.session.query(InvCount)
        .filter(
            InvCount.item_id == product,
            InvCount.count_time == "PM",
            InvCount.trans_date == end_date,
        )
        .first()
    )
    sales_weekly = (
        db.session.query(
            InvSales,
            func.sum(InvSales.eachcount).label("total"),
            func.avg(InvSales.eachcount).label("sales_avg"),
        )
        .filter(
            InvSales.item_id == product,
            InvSales.count_time == "PM",
            InvSales.trans_date >= weekly,
        )
        .all()
    )
    purchase_weekly = (
        db.session.query(
            InvPurchases, func.sum(InvPurchases.purchase_total).label("total")
        )
        .filter(
            InvPurchases.item_id == product,
            InvPurchases.count_time == "PM",
            InvPurchases.trans_date >= weekly,
        )
        .all()
    )
    on_hand_weekly = (
        db.session.query(InvCount, func.avg(InvCount.count_total).label("average"))
        .filter(InvCount.item_id == product, InvCount.trans_date >= weekly)
        .all()
    )

    # Chart 1
    items_list = (
        db.session.query(InvCount)
        .filter(
            InvCount.item_id == product,
            InvCount.count_time == "PM",
            InvCount.trans_date >= weekly,
        )
        .order_by(InvCount.trans_date)
        .all()
    )
    labels = []
    values = []
    day_sales = []
    for i in items_list:
        labels.append(i.trans_date.strftime("%A"))
        values.append(i.count_total)
        sales_list = (
            db.session.query(InvSales)
            .filter(InvSales.item_id == product, InvSales.trans_date == i.trans_date)
            .first()
        )
        if sales_list:
            day_sales.append(sales_list.sales_total)
        else:
            day_sales.append(0)

    # Chart #2
    daily_sales = (
        db.session.query(
            func.extract("dow", InvSales.trans_date).label("dow"),
            func.avg(InvSales.eachcount).label("average"),
        )
        .filter(InvSales.item_id == product, InvSales.trans_date >= monthly)
        .group_by(func.extract("dow", InvSales.trans_date))
        .all()
    )

    weekly_avg = db.session.query(
        InvSales,
        func.avg(InvSales.eachcount).label("sales_avg"),
        func.avg(InvSales.waste).label("waste_avg"),
    ).filter(InvSales.item_id == product, InvSales.trans_date >= monthly)

    values2 = []
    values3 = []
    values4 = []
    for d in daily_sales:
        values2.append(d.average)
        for w in weekly_avg:
            values3.append(w.sales_avg)
            values4.append(w.waste_avg)

    # Details Table
    result = (
        db.session.query(
            InvCount,
            func.sum(InvSales.eachcount).label("sales_count"),
            func.sum(InvSales.waste).label("sales_waste"),
            func.sum(InvPurchases.purchase_total).label("purchase_count"),
        )
        .select_from(InvCount)
        .outerjoin(
            InvSales,
            and_(
                InvSales.trans_date == InvCount.trans_date, InvSales.item_id == product
            ),
        )
        .outerjoin(
            InvPurchases,
            and_(
                InvPurchases.trans_date == InvCount.trans_date,
                InvPurchases.item_id == product,
            ),
        )
        .group_by(InvCount.item_id, InvCount.trans_date)
        .order_by(InvCount.trans_date.desc())
        .filter(
            InvCount.item_id == product,
            InvCount.count_time == "PM",
            InvCount.trans_date >= weekly,
        )
    )

    item_name = db.session.query(InvItems).filter(InvItems.id == product).first()

    return render_template(
        "main/details.html",
        title="Item Variance Details",
        count_daily=count_daily,
        sales_weekly=sales_weekly,
        purchase_weekly=purchase_weekly,
        on_hand_weekly=on_hand_weekly,
        item_name=item_name,
        labels=labels,
        labels2=labels,
        values=values,
        values2=values2,
        values3=values3,
        values4=values4,
        day_sales=day_sales,
        daily_sales=daily_sales,
        result=result,
    )
