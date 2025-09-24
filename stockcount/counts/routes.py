"""
count/routes.py is flask routes for counts, purchases, sales and items
"""

import logging
from datetime import datetime, timedelta

from flask import flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from zoneinfo import ZoneInfo

from stockcount import db
from stockcount.counts import blueprint
from stockcount.counts.forms import (
    CountForm,
    NewItemForm,
    NewMenuItemForm,
    StoreForm,
    UpdateCountForm,
    UpdateItemForm,
)
from stockcount.counts.utils import calculate_totals
from stockcount.main.utils import get_current_day_menu_item_sales
from stockcount.models import (
    Calendar,
    InvCount,
    InvItems,
    InvPurchases,
    InvSales,
    MenuItems,
    Restaurants,
    StockcountSales,
)

eastern = ZoneInfo("America/New_York")


@blueprint.route("/count/", methods=["GET", "POST"])
@login_required
def count():
    """Enter count for an item"""
    current_location = Restaurants.query.filter_by(id=session["store"]).first()
    page = request.args.get("page", 1, type=int)
    inv_items = InvCount.query.filter(InvCount.store_id == session["store"]).all()

    ordered_items = (
        db.session.query(
            InvCount.trans_date,
            InvCount.count_time,
        )
        .filter(InvCount.store_id == session["store"])
        .group_by(InvCount.trans_date, InvCount.count_time)
        .order_by(InvCount.trans_date.desc(), InvCount.count_time.desc())
        .limit(7)
        .all()
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
        return redirect(url_for("counts_blueprint.count"))

    item_list = (
        db.session.query(InvItems.id, InvItems.item_name)
        .filter(InvItems.store_id == session["store"])
        .all()
    )
    if item_list == []:
        flash(
            "You must add items to your inventory before you can count them!", "warning"
        )
        logging.error(
            f"User {current_user.email} attempted to count items without adding any items to inventory"
        )
        return redirect(url_for("counts_blueprint.new_item"))

    multi_form = CountForm(counts=item_list)
    index = 0

    for form in multi_form.counts:
        form.itemname.data = item_list[index].item_name
        form.item_id.data = item_list[index].id
        index += 1

    del index

    # on form submission
    if multi_form.submit.data:
        # Check if count exists for same day and time
        # for each count entry, check if it already exists
        for count_entry in multi_form.counts.data:
            double_count = InvCount.query.filter_by(
                item_id=count_entry["item_id"],
                trans_date=multi_form.transdate.data,
                count_time=multi_form.am_pm.data,
            ).first()
            ic(double_count)
            if double_count is not None:
                flash(
                    f"{count_entry['itemname']} already has a count on {multi_form.transdate.data}, please enter a different date or time",
                    "warning",
                )
                logging.error(
                    f"User {current_user.email} attempted to count item {count_entry['itemname']} that already has a count for {multi_form.transdate.data}"
                )
                return redirect(url_for("counts_blueprint.count"))

        # get previous count
        for count_entry in multi_form.counts.data:
            items_object = InvItems.query.filter_by(id=count_entry["item_id"]).first()
            filter_item = InvCount.query.filter(
                InvCount.store_id == session["store"],
                InvCount.item_id == count_entry["item_id"],
            )
            previous_count = filter_item.order_by(InvCount.trans_date.desc()).first()
            if previous_count is None:
                total_previous = 0
            else:
                total_previous = previous_count.count_total

            # Calculate total purchases
            purchase_item = InvPurchases.query.filter_by(
                store_id=session["store"],
                item_id=count_entry["item_id"],
                trans_date=multi_form.transdate.data,
            ).first()
            if purchase_item is None:
                total_purchase = 0
            else:
                total_purchase = purchase_item.purchase_total

            # Calculate total sales
            sales_item = InvSales.query.filter_by(
                store_id=session["store"],
                item_id=count_entry["item_id"],
                trans_date=multi_form.transdate.data,
            ).first()
            if sales_item is None:
                total_sales = 0
            else:
                total_sales = sales_item.sales_total

            for count_entry in multi_form.counts.data:
                items_object = InvItems.query.filter_by(
                    id=count_entry["item_id"]
                ).first()

                inventory = InvCount(
                    trans_date=multi_form.transdate.data,
                    count_time=multi_form.am_pm.data,
                    item_name=count_entry["itemname"],
                    case_count=count_entry["casecount"],
                    each_count=count_entry["eachcount"],
                    count_total=(
                        (items_object.case_pack * count_entry["casecount"])
                        + count_entry["eachcount"]
                    ),
                    previous_total=total_previous,
                    theory=(total_previous + total_purchase - total_sales),
                    daily_variance=(
                        (
                            (items_object.case_pack * count_entry["casecount"])
                            + count_entry["eachcount"]
                        )
                        - (total_previous + total_purchase - total_sales)
                    ),
                    item_id=count_entry["item_id"],
                    store_id=session["store"],
                )
                db.session.add(inventory)
            db.session.commit()
            # flash(
            #     f"Count submitted for {count_entry['itemname ']} on {multi_form.transdate.data}!",
            #     "success",
            # )
            return redirect(url_for("counts_blueprint.count"))

    return render_template(
        "counts/count.html",
        title="Enter Count",
        **locals(),
    )


@blueprint.route("/count/<int:count_id>/update", methods=["GET", "POST"])
@login_required
def update_count(count_id):
    """route for count/id/update"""
    current_location = Restaurants.query.filter_by(id=session["store"]).first()
    item = InvCount.query.get_or_404(count_id)
    if not item.item_id:
        flash(f"{item.item_name} is not an active product!", "warning")
        logging.error(
            f"User {current_user.email} attempted to update count for inactive item {item.item_name}"
        )
        return redirect(url_for("counts_blueprint.count"))
    inv_items = InvCount.query.all()
    form = UpdateCountForm()
    store_form = StoreForm()

    if store_form.storeform_submit.data and store_form.validate():
        # session["date_selected"] = fiscal_dates["start_day"]
        data = store_form.stores.data
        for x in data:
            session["store"] = x.id
        return redirect(url_for("counts_blueprint.count"))

    if form.validate_on_submit():
        items_object = InvItems.query.filter_by(id=form.item_id.data).first()
        filter_item = InvCount.query.filter(
            InvCount.item_id == form.item_id.data,
            InvCount.trans_date <= form.transdate.data,
        )
        ordered_count = (
            filter_item.order_by(InvCount.trans_date.desc(), InvCount.count_time.desc())
            .offset(1)
            .first()
        )
        if ordered_count is None:
            total_previous = 0
        else:
            total_previous = ordered_count.count_total

        purchase_item = InvPurchases.query.filter_by(
            item_id=form.item_id.data, trans_date=form.transdate.data
        ).first()
        if purchase_item is None:
            total_purchase = 0
        else:
            total_purchase = purchase_item.purchase_total

        sales_item = InvSales.query.filter_by(
            item_id=form.item_id.data, trans_date=form.transdate.data
        ).first()
        if sales_item is None:
            total_sales = 0
        else:
            total_sales = sales_item.sales_total

        item.trans_date = form.transdate.data
        item.count_time = form.am_pm.data
        item.item_name = form.itemname.data
        item.case_count = form.casecount.data
        item.each_count = form.eachcount.data
        item.count_total = (
            items_object.case_pack * form.casecount.data + form.eachcount.data
        )
        item.previous_total = total_previous
        item.theory = total_previous + total_purchase - total_sales
        item.daily_variance = (
            items_object.case_pack * form.casecount.data + form.eachcount.data
        ) - (total_previous + total_purchase - total_sales)
        db.session.commit()
        flash("Item counts have been updated!", "success")
        return redirect(url_for("counts_blueprint.count"))
    if request.method == "GET":
        form.item_id.data = item.item_id
        form.transdate.data = item.trans_date
        form.am_pm.data = item.count_time
        form.itemname.data = item.item_name
        form.casecount.data = item.case_count
        form.eachcount.data = item.each_count
    return render_template(
        "counts/update_count.html",
        title="Update Item Count",
        legend="Update Count",
        **locals(),
    )


@blueprint.route("/count/<string:count_date>/update", methods=["GET", "POST"])
@login_required
def update_count_all(count_date):
    """Update count items"""
    current_location = Restaurants.query.filter_by(id=session["store"]).first()
    # Check if date exists in count
    # make sure count-date is in the format of dd-mm-yyyy
    count_date = datetime.strptime(count_date, "%Y-%m-%d")

    # get the count_time from the most recent count on given date
    count_time = (
        InvCount.query.filter(
            InvCount.store_id == session["store"],
            InvCount.trans_date == count_date,
        )
        .order_by(InvCount.count_time.desc())
        .first()
    )

    # ic(count_time.count_time)

    store_form = StoreForm()
    if store_form.storeform_submit.data and store_form.validate():
        # session["date_selected"] = fiscal_dates["start_day"]
        data = store_form.stores.data
        for x in data:
            session["store"] = x.id
        return redirect(url_for("counts_blueprint.count"))

    if count_date is None:
        flash("No count for that date!", "warning")
        logging.error(
            f"User {current_user.email} attempted to update count for non-existent date {count_date}"
        )
        return redirect(url_for("counts_blueprint.count"))

    # Get a list of all the items for the restaurant
    item_list = (
        db.session.query(InvItems.id, InvItems.item_name)
        .filter(InvItems.store_id == session["store"])
        .all()
    )
    if item_list == []:
        flash(
            "You must add items to your inventory before you can count them!", "warning"
        )
        logging.error(
            f"User {current_user.email} attempted to update count without adding any items to inventory"
        )
        return redirect(url_for("counts_blueprint.new_item"))

    # ic(item_list)

    # Get the count for the selected date
    counts = InvCount.query.filter(
        InvCount.store_id == session["store"],
        InvCount.trans_date == count_date,
    ).all()

    # ic(counts)

    # Create a form for the count based off the item_list
    multi_form = CountForm(counts=item_list)

    # ic(multi_form.counts.data)

    if multi_form.validate_on_submit():
        # Submit count update for each item
        for count_entry in multi_form.counts.data:
            # First Update exisiting count
            count = InvCount.query.filter(
                InvCount.store_id == session["store"],
                InvCount.trans_date == multi_form.transdate.data,
            ).all()

            # Check if count exists for same day and time
            exisiting_item = InvCount.query.filter_by(
                item_id=count_entry["item_id"],
                trans_date=count_date,
            ).first()

            if exisiting_item is not None:
                # if not new data, skip
                if (
                    exisiting_item.each_count == count_entry["eachcount"]
                    and exisiting_item.case_count == count_entry["casecount"]
                ):
                    # print("No changes for: ", count_entry["itemname"])
                    continue
                # print("Updating count for existing item: ", count_entry["itemname"])
                exisiting_item.each_count = count_entry["eachcount"]
                exisiting_item.casecount = count_entry["casecount"]
                exisiting_item.count_total = (
                    count_entry["eachcount"] + count_entry["casecount"]
                )
                exisiting_item.previous_total = 0
                exisiting_item.theory = 0
                exisiting_item.daily_variance = 0
                db.session.commit()
                continue

            # Secondly add new count
            # For items in item_list that are not in count
            if count_entry["item_id"] not in [count.item_id for count in count]:
                # print("Updating count for new item: ", count_entry["itemname"])
                count_item = InvCount(
                    trans_date=count_date,
                    count_time=count_time.count_time,
                    item_name=count_entry["itemname"],
                    each_count=count_entry["eachcount"],
                    case_count=count_entry["casecount"],
                    count_total=(count_entry["eachcount"] + count_entry["casecount"]),
                    previous_total=0,
                    theory=0,
                    daily_variance=0,
                    item_id=count_entry["item_id"],
                    store_id=session["store"],
                )
                db.session.add(count_item)
                db.session.commit()
                # ic(count_item)
        flash("Counts have been updated!", "success")
        return redirect(url_for("counts_blueprint.count"))
    elif request.method == "GET":
        multi_form.transdate.data = count_date
        multi_form.am_pm.data = count_time.count_time
        index = 0
        for item in item_list:
            multi_form.counts[index].itemname.data = item.item_name
            multi_form.counts[index].item_id.data = item.id
            for count in counts:
                if item.id == count.item_id:
                    multi_form.counts[index].eachcount.data = count.each_count
                    multi_form.counts[index].casecount.data = count.case_count
            index += 1
        del index, item, count

    return render_template(
        "counts/update_count_all.html",
        title="Update count",
        legend="Update count",
        **locals(),
    )


@blueprint.route("/count/<int:count_id>/delete", methods=["POST"])
@login_required
def delete_count(count_id):
    """Delete an item count"""
    current_location = Restaurants.query.filter_by(id=session["store"]).first()
    item = InvCount.query.get_or_404(count_id)
    db.session.delete(item)
    db.session.commit()
    flash("Item counts have been deleted!", "success")
    return redirect(url_for("counts_blueprint.count"))


@blueprint.route("/sales/", methods=["GET", "POST"])
@login_required
def sales():
    # determine real today and reporting today (yesterday)
    now = datetime.now(eastern)
    real_today = now.date()
    reporting_today = (now - timedelta(days=1)).date()

    if 8 <= now.hour <= 23:  # 8 AM to midnight
        business_date = real_today
    elif 0 <= now.hour <= 7:  # midnight to 8 AM
        business_date = reporting_today
    else:
        business_date = None  # outside your Toast window, use R365 or other logic

    cal_row = (
        db.session.query(
            Calendar.week_start, Calendar.year_start, Calendar.period, Calendar.week
        )
        .filter(Calendar.date == str(reporting_today))
        .first()
    )
    week_start = cal_row.week_start
    year_start = cal_row.year_start
    weeks_elapsed = (cal_row.period - 1) * 4 + cal_row.week

    store_id = session["store"]
    current_location = Restaurants.query.get(store_id)
    store_form = StoreForm()

    if store_form.storeform_submit.data and store_form.validate():
        data = store_form.stores.data
        for x in data:
            session["store"] = x.id
        return redirect(url_for("counts_blueprint.sales"))

    page = request.args.get("page", 1, type=int)

    # paginate over just the dates
    ordered_sales = (
        db.session.query(StockcountSales.date)
        .filter_by(store_id=store_id)
        .group_by(StockcountSales.date)
        .order_by(StockcountSales.date.desc())
        .limit(7)
        .all()
    )
    # ordered_sales = sales_dates.paginate(page=page, per_page=7)

    # pull all menuitem + counts for the dates in this page
    sales_items = (
        db.session.query(
            StockcountSales.date.label("date"),
            StockcountSales.menuitem.label("menuitem"),
            func.sum(StockcountSales.sales_count).label("sales_count"),
        )
        .filter(
            StockcountSales.store_id == store_id,
            StockcountSales.date.in_([d.date for d in ordered_sales]),
        )
        .group_by(StockcountSales.date, StockcountSales.menuitem)
        .all()
    )

    # get current day sales
    unique_items = (
        row.menuitem
        for row in db.session.query(StockcountSales.menuitem)
        .filter(StockcountSales.store_id == store_id)
        .distinct()
    )

    current_day_sales = get_current_day_menu_item_sales(
        store_id, unique_items, business_date
    )

    # calculate week to date sales
    wtd_sales = (
        db.session.query(
            StockcountSales.menuitem.label("menuitem"),
            func.sum(StockcountSales.sales_count).label("wtd_sales"),
        )
        .filter(
            StockcountSales.store_id == store_id,
            StockcountSales.date >= week_start,
            StockcountSales.date <= reporting_today,
        )
        .group_by(StockcountSales.menuitem)
        .order_by(StockcountSales.menuitem)
        .all()
    )

    # # calculate year to date sales
    # ytd_sales = (
    #     db.session.query(
    #         StockcountSales.menuitem.label("menuitem"),
    #         func.sum(StockcountSales.sales_count).label("ytd_sales"),
    #     )
    #     .filter(
    #         StockcountSales.store_id == store_id,
    #         StockcountSales.date >= year_start,
    #         StockcountSales.date <= reporting_today,
    #     )
    #     .group_by(StockcountSales.menuitem)
    #     .order_by(StockcountSales.menuitem)
    #     .all()
    # )

    # weekly_avg_sales = [
    #     {
    #         "menuitem": row.menuitem,
    #         "weekly_avg_sales": round(row.ytd_sales / weeks_elapsed, 0),
    #     }
    #     for row in ytd_sales
    # ]

    return render_template(
        "counts/sales.html",
        current_location=current_location,
        title="Sales",
        date=business_date,
        store_form=store_form,
        sales_items=sales_items,
        ordered_sales=ordered_sales,
        current_day_sales=current_day_sales,
        wtd_sales=wtd_sales,
        # weekly_avg_sales=weekly_avg_sales,
    )


@blueprint.route("/item/new", methods=["GET", "POST"])
@login_required
def new_item():
    """Create new inventory items"""
    current_location = Restaurants.query.filter_by(id=session["store"]).first()
    inv_items = InvItems.query.filter(InvItems.store_id == session["store"]).all()
    menu_items = MenuItems.query.filter(MenuItems.store_id == session["store"]).all()
    form = NewItemForm()
    menuItemForm = NewMenuItemForm()
    store_form = StoreForm()

    if store_form.storeform_submit.data and store_form.validate():
        data = store_form.stores.data
        for x in data:
            session["store"] = x.id
        return redirect(url_for("counts_blueprint.new_item"))

    if form.validate_on_submit():
        item = InvItems(
            item_name=form.itemname.data.name,
            case_pack=form.casepack.data,
            store_id=session["store"],
        )
        db.session.add(item)
        db.session.commit()
        flash(
            f"{form.itemname.data.name} has been added to your stockcount items list!",
            "success",
        )
        return redirect(url_for("counts_blueprint.new_item"))

    return render_template(
        "counts/new_item.html",
        title="New Inventory Item",
        legend="Enter New Item",
        **locals(),
    )


@blueprint.route("/item/<int:item_id>/update", methods=["GET", "POST"])
@login_required
def update_item(item_id):
    """Update current inventory items"""
    current_location = Restaurants.query.filter_by(id=session["store"]).first()
    inv_items = InvItems.query.filter(InvItems.store_id == session["store"]).all()
    item = InvItems.query.get_or_404(item_id)
    form = UpdateItemForm()
    store_form = StoreForm()

    if store_form.storeform_submit.data and store_form.validate():
        # session["date_selected"] = fiscal_dates["start_day"]
        data = store_form.stores.data
        for x in data:
            session["store"] = x.id
        return redirect(url_for("counts_blueprint.new_item"))

    if form.validate_on_submit():
        item.item_name = form.itemname.data
        item.case_pack = form.casepack.data
        db.session.commit()
        flash(f"{item.item_name} has been updated!", "success")
        return redirect(url_for("counts_blueprint.new_item"))
    elif request.method == "GET":
        form.itemname.data = item.item_name
        form.casepack.data = item.case_pack

    return render_template(
        "counts/update_item.html",
        title="Update Inventory Item",
        legend="Update Case Pack for ",
        **locals(),
    )


@blueprint.route("/item/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_item(item_id):
    """Delete current items"""
    # TODO: method to delete all counts for an item
    current_location = Restaurants.query.filter_by(id=session["store"]).first()
    inv_items = InvItems.query.filter(InvItems.store_id == session["store"]).all()
    item = InvItems.query.get_or_404(item_id)
    counts = InvCount.query.filter_by(item_id=item.id).all()
    # purchases = InvPurchases.query.filter_by(item_id=item.id).all()
    # sales = InvSales.query.filter_by(item_id=item.id).all()
    menu_items = MenuItems.query.filter_by(
        purchases_id=item.id, store_id=session["store"]
    ).all()
    store_form = StoreForm()

    ic(item.id, session["store"], counts, menu_items)

    if store_form.storeform_submit.data and store_form.validate():
        data = store_form.stores.data
        for x in data:
            session["store"] = x.id
        return redirect(url_for("counts_blueprint.new_item"))

    InvCount.query.filter_by(item_id=item.id).delete()
    InvSales.query.filter_by(item_id=item.id).delete()
    MenuItems.query.filter_by(purchases_id=item.id, store_id=session["store"]).delete()

    db.session.delete(item)
    db.session.commit()
    flash("Product has been 86'd!", "success")
    return redirect(url_for("counts_blueprint.new_item"))
