"""
count/routes.py is flask routes for counts, purchases, sales and items
"""

from flask import flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from stockcount import db
from stockcount.counts import blueprint
from stockcount.counts.forms import (
    CountForm,
    PurchasesForm,
    SalesForm,
    NewItemForm,
    NewMenuItemForm,
    StoreForm,
    UpdateCountForm,
    UpdateItemForm,
    UpdatePurchasesForm,
    UpdateSalesForm,
)
from stockcount.counts.utils import calculate_totals
from stockcount.models import InvCount, InvItems, InvPurchases, InvSales, Restaurants, RecipeIngredients

from sqlalchemy import func

from icecream import ic
from datetime import datetime

import logging

@blueprint.route("/count/", methods=["GET", "POST"])
@login_required
def count():
    """Enter count for an item"""
    current_location = Restaurants.query.filter_by(id=session["store"]).first()
    page = request.args.get("page", 1, type=int)
    inv_items = InvCount.query.filter(InvCount.store_id == session["store"]).all()
    count_dates = (
        db.session.query(
            InvCount.trans_date,
            InvCount.count_time,
        )
        .filter(InvCount.store_id == session["store"])
        .group_by(InvCount.trans_date, InvCount.count_time)
    )
    ordered_items = count_dates.order_by(InvCount.trans_date.desc(), InvCount.count_time.desc()).paginate(
        page=page, per_page=10
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
                logging.error(f"User {current_user.email} attempted to access store {x.id} without permission")
        return redirect(url_for("counts_blueprint.count"))

    item_list = db.session.query(InvItems.id, InvItems.item_name).filter(InvItems.store_id == session["store"]).all()
    if(item_list == []):
        flash("You must add items to your inventory before you can count them!", "warning")
        logging.error(f"User {current_user.email} attempted to count items without adding any items to inventory")
        return redirect(url_for("counts_blueprint.new_item")
        )
        
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
        #for each count entry, check if it already exists
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
                logging.error(f"User {current_user.email} attempted to count item {count_entry['itemname']} that already has a count for {multi_form.transdate.data}")
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
                items_object = InvItems.query.filter_by(id=count_entry["item_id"]).first()
                
                inventory = InvCount(
                    trans_date=multi_form.transdate.data,
                    count_time=multi_form.am_pm.data,
                    item_name=count_entry["itemname"],
                    case_count=count_entry["casecount"],
                    each_count=count_entry["eachcount"],
                    count_total=(
                        items_object.case_pack * count_entry["casecount"] + count_entry["eachcount"]
                    ),
                    previous_total=total_previous,
                    theory=(total_previous + total_purchase - total_sales),
                    daily_variance=(
                        (items_object.case_pack * count_entry["casecount"] + count_entry["eachcount"])
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
        logging.error(f"User {current_user.email} attempted to update count for inactive item {item.item_name}")
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
    count_time = InvCount.query.filter(
        InvCount.store_id == session["store"],
        InvCount.trans_date == count_date,
    ).order_by(InvCount.count_time.desc()).first()

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
        logging.error(f"User {current_user.email} attempted to update count for non-existent date {count_date}")
        return redirect(url_for("counts_blueprint.count"))
    
    # Get a list of all the items for the restaurant
    item_list = db.session.query(InvItems.id, InvItems.item_name).filter(InvItems.store_id == session["store"]).all()
    if(item_list == []):
        flash("You must add items to your inventory before you can count them!", "warning")
        logging.error(f"User {current_user.email} attempted to update count without adding any items to inventory")
        return redirect(url_for("counts_blueprint.new_item")
        )
        
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
                if exisiting_item.each_count == count_entry["eachcount"] and exisiting_item.case_count == count_entry["casecount"]:
                    # print("No changes for: ", count_entry["itemname"])
                    continue
                # print("Updating count for existing item: ", count_entry["itemname"])
                exisiting_item.each_count = count_entry["eachcount"]
                exisiting_item.casecount = count_entry["casecount"]
                exisiting_item.count_total = (count_entry["eachcount"] + count_entry["casecount"])
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
    """Enter Todays Sales"""
    current_location = Restaurants.query.filter_by(id=session["store"]).first()

    # crate list of daily sales
    page = request.args.get("page", 1, type=int)
    sales_list = InvSales.query.filter(InvSales.store_id == session["store"]).all()
    sales_dates = (
        db.session.query(InvSales.trans_date)
        .filter_by(store_id=session["store"])
        .group_by(InvSales.trans_date)
    )
    ordered_sales = sales_dates.order_by(InvSales.trans_date.desc()).paginate(
        page=page, per_page=10
    )

    store_form = StoreForm()
    if store_form.storeform_submit.data and store_form.validate():
        # session["date_selected"] = fiscal_dates["start_day"]
        data = store_form.stores.data
        for x in data:
            session["store"] = x.id
        return redirect(url_for("counts_blueprint.sales"))

    # create sales form for input
    item_list = db.session.query(InvItems.id, InvItems.item_name).filter(InvItems.store_id == session["store"]).all()
    if(item_list == []):
        flash("You must add items to your inventory before you can count them!", "warning")
        logging.error(f"User {current_user.email} attempted to sales items without adding any items to inventory")
        return redirect(url_for("counts_blueprint.new_item")
        )
        
    # From recipe_ingredients, get a list of the actual menu items possible that match ingredients to the item_list above
    menu_items = db.session.query(
    RecipeIngredients.menu_item,
    RecipeIngredients.ingredient,
    InvItems.id
    ).join(
        InvItems,
        RecipeIngredients.ingredient == InvItems.item_name
    ).filter(
        InvItems.store_id == session["store"]
    ).distinct().all()
        
    # Get the date in format of mm-dd-yyyy
    date = datetime.now().strftime("%m-%d-%Y")

    multi_form = SalesForm(sales=menu_items)
    index = 0
    for form in multi_form.sales:
            form.itemname.data = menu_items[index].menu_item     
            form.item_id.data = menu_items[index].id   
            index += 1
            
    del index

    if multi_form.validate_on_submit():
        # Condense the sales_entries by combinding the sales of the same item_id
        sales_entries = {}
        for sales_entry in multi_form.sales.data:
            if sales_entry["item_id"] in sales_entries:
                sales_entries[sales_entry["item_id"]]["eachcount"] += sales_entry["eachcount"]
                sales_entries[sales_entry["item_id"]]["waste"] += sales_entry["waste"]
            else:
                sales_entries[sales_entry["item_id"]] = sales_entry
                sales_entries[sales_entry["item_id"]]["itemname"] = InvItems.query.filter_by(id=sales_entry["item_id"]).first().item_name
                
        # Check if sales exists for same day and time
        # for each sales entry, check if it already exists
        for sales_entry in sales_entries.values():
            double_sales = InvSales.query.filter_by(
                item_id=sales_entry["item_id"],
                trans_date= datetime.now().strftime("%Y-%m-%d"),
            ).first()
            # delete sales if it already exists
            if double_sales is not None:
                db.session.delete(double_sales)
                db.session.commit()
            
        
        for sales_entry in sales_entries.values():
            # ic(sales_entry.items())
            sale_item = InvSales(
                trans_date=multi_form.transdate.data,
                item_name=sales_entry["itemname"],
                each_count=sales_entry["eachcount"],
                waste=sales_entry["waste"],
                sales_total=(sales_entry["eachcount"] + sales_entry["waste"]),
                item_id=sales_entry["item_id"],
                store_id=session["store"],
            )
            # ic(sale_item.item_id, sale_item.item_name, sale_item.sales_total)
            db.session.add(sale_item)
        db.session.commit()
        # flash(
        #         f"Sales of {sales_form.eachcount.data + sales_form.waste.data} {sales_form.itemname.data.item_name} submitted on {multi_form.transdate.data}!",
        #         "success",
        #         )
        unit = InvItems.query.filter_by(id=sales_entry['item_id']).all()
        for item in unit:
            calculate_totals(item.id)
        return redirect(url_for("counts_blueprint.sales"))

    return render_template(
        "counts/sales.html",
        title="Sales",
        **locals(),
    )


@blueprint.route("/sales/<int:sales_id>/update", methods=["GET", "POST"])
@login_required
def update_sales(sales_id):
    """Update sales items"""
    current_location = Restaurants.query.filter_by(id=session["store"]).first()
    item = InvSales.query.get_or_404(sales_id)
    if not item.item_id:
        flash(f"{item.item_name} is not an active product!", "warning")
        logging.error(f"User {current_user.email} attempted to update sales for inactive item {item.item_name}")
        return redirect(url_for("counts_blueprint.sales"))
    inv_items = InvSales.query.all()
    form = UpdateSalesForm()
    store_form = StoreForm()

    if store_form.storeform_submit.data and store_form.validate():
        # session["date_selected"] = fiscal_dates["start_day"]
        data = store_form.stores.data
        for x in data:
            session["store"] = x.id
        return redirect(url_for("counts_blueprint.sales"))

    if form.validate_on_submit():
        unit = InvItems.query.filter_by(id=form.item_id.data).first()
        item.trans_date = form.transdate.data
        item.item_name = form.itemname.data
        item.each_count = form.eachcount.data
        item.waste = form.waste.data
        item.sales_total = form.eachcount.data + form.waste.data
        db.session.commit()
        flash("Item Sales have been updated!", "success")
        calculate_totals(unit.id)
        return redirect(url_for("counts_blueprint.sales"))
    elif request.method == "GET":
        form.transdate.data = item.trans_date
        form.itemname.data = item.item_name
        form.eachcount.data = item.each_count
        form.waste.data = item.waste
        form.item_id.data = item.item_id
    return render_template(
        "counts/update_sales.html",
        title="Update Item Sales",
        legend="Update Sales",
        **locals(),
    )


@blueprint.route("/sales/<int:sales_id>/delete", methods=["POST"])
@login_required
def delete_sales(sales_id):
    """Delete sales items"""
    current_location = Restaurants.query.filter_by(id=session["store"]).first()
    item = InvSales.query.get_or_404(sales_id)
    unit = InvItems.query.filter_by(id=item.item_id).first()
    db.session.delete(item)
    db.session.commit()
    flash("Item Sales have been deleted!", "success")
    calculate_totals(unit.id)
    return redirect(url_for("counts_blueprint.sales"))

@blueprint.route("/sales/<string:sales_date>/update", methods=["GET", "POST"])
@login_required
def update_sales_all(sales_date):
    """Update sales items"""
    current_location = Restaurants.query.filter_by(id=session["store"]).first()
    # Check if date exists in sales
    # make sure sales-date is in the format of dd-mm-yyyy
    sales_date = datetime.strptime(sales_date, "%Y-%m-%d")
    
    store_form = StoreForm()
    if store_form.storeform_submit.data and store_form.validate():
        # session["date_selected"] = fiscal_dates["start_day"]
        data = store_form.stores.data
        for x in data:
            session["store"] = x.id
        return redirect(url_for("counts_blueprint.sales"))
    
    if sales_date is None:
        flash("No sales for that date!", "warning")
        logging.error(f"User {current_user.email} attempted to update sales for non-existent date {sales_date}")
        return redirect(url_for("counts_blueprint.sales"))
    
    # Get a list of all the items for the restaurant
    item_list = db.session.query(InvItems.id, InvItems.item_name).filter(InvItems.store_id == session["store"]).all()
    if(item_list == []):
        flash("You must add items to your inventory before you can count them!", "warning")
        logging.error(f"User {current_user.email} attempted to sales items without adding any items to inventory")
        return redirect(url_for("counts_blueprint.new_item")
        )
        
    # Get the sales for the selected date
    sales = InvSales.query.filter(
        InvSales.store_id == session["store"],
        InvSales.trans_date == sales_date,
    ).all()
        
    # Create a form for the sales based off the item_list
    multi_form = SalesForm(sales=item_list)
    
    # ic(multi_form.sales.data)
        
    if multi_form.validate_on_submit():        
        # Submit sales update for each item
        for sales_entry in multi_form.sales.data:
            # First Update exisiting sales
            sales = InvSales.query.filter(
                InvSales.store_id == session["store"],
                InvSales.trans_date == multi_form.transdate.data,
            ).all()
            
            # Check if sales exists for same day and time 
            exisiting_item = InvSales.query.filter_by(
                item_id=sales_entry["item_id"],
                trans_date=sales_date,
            ).first()
            
            if exisiting_item is not None:
                # if not new data, skip
                if exisiting_item.each_count == sales_entry["eachcount"] and exisiting_item.waste == sales_entry["waste"]:
                    # print("No changes for: ", sales_entry["itemname"])
                    continue
                # print("Updating sales for existing item: ", sales_entry["itemname"])
                exisiting_item.each_count = sales_entry["eachcount"]
                exisiting_item.waste = sales_entry["waste"]
                exisiting_item.sales_total = (sales_entry["eachcount"] + sales_entry["waste"])
                db.session.commit()
                continue
                
            # Secondly add new sales
            # For items in item_list that are not in sales
            if sales_entry["item_id"] not in [sale.item_id for sale in sales]:
                # print("Updating sales for new item: ", sales_entry["itemname"])
                sales_item = InvSales(
                    trans_date=sales_date,
                    item_name=sales_entry["itemname"],
                    each_count=sales_entry["eachcount"],
                    waste=sales_entry["waste"],
                    sales_total=(sales_entry["eachcount"] + sales_entry["waste"]),
                    item_id=sales_entry["item_id"],
                    store_id=session["store"],
                )
                db.session.add(sales_item)
                db.session.commit()
                # ic(sales_item)
        flash("Sales have been updated!", "success")
        return redirect(url_for("counts_blueprint.sales"))
    elif request.method == "GET":
        multi_form.transdate.data = sales_date
        index = 0
        for item in item_list:
            multi_form.sales[index].itemname.data = item.item_name
            multi_form.sales[index].item_id.data = item.id
            for sale in sales:
                if item.id == sale.item_id:
                    multi_form.sales[index].eachcount.data = sale.each_count
                    multi_form.sales[index].waste.data = sale.waste
            index += 1
        del index, item, sale
        
    return render_template(
        "counts/update_sales_all.html",
        title="Update Sales",
        legend="Update Sales",
        **locals(),
    )
    

@blueprint.route("/item/new", methods=["GET", "POST"])
@login_required
def new_item():
    """Create new inventory items"""
    print(session["store"])
    current_location = Restaurants.query.filter_by(id=session["store"]).first()
    inv_items = InvItems.query.filter(InvItems.store_id == session["store"]).all()
    menu_items = [
    {'id': 1, 'item_name': 'Test 1'},
    {'id': 2, 'item_name': 'Test 2'},
    {'id': 3, 'item_name': 'Test 3'},
    {'id': 4, 'item_name': 'Test 4'}
    ]#MenuItems.query.filter(MenuItems.store_id == session["store"]).all()
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
    purchases = InvPurchases.query.filter_by(item_id=item.id).all()
    sales = InvSales.query.filter_by(item_id=item.id).all()
    store_form = StoreForm()
    
    ic(item.id, session["store"], counts)

    if store_form.storeform_submit.data and store_form.validate():
        data = store_form.stores.data
        for x in data:
            session["store"] = x.id
        return redirect(url_for("counts_blueprint.new_item"))

    if counts is not None:
        for count in counts:
            db.session.delete(count)
    
    if purchases is not None:
        for purchase in purchases:
            db.session.delete(purchase)
            
    if sales is not None:
        for sale in sales:
            db.session.delete(sale)
            
        db.session.commit()

    db.session.delete(item)
    db.session.commit()
    flash("Product has been 86'd!", "success")
    return redirect(url_for("counts_blueprint.new_item"))
