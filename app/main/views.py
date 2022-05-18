from pickle import GET
from flask import abort, render_template
from flask import render_template,request,redirect,url_for
from flask_login import login_required,current_user
from ..models import Bikes, User, Reviews
from . import main
from .. import db,photos
from .forms import ReviewForm, UpdateProfile, BikeForm
from werkzeug.utils import secure_filename

@main.route('/')
def index():

    '''
    View root page function that returns the index page and its data
    '''
   
    title = 'Bike Hire'
    return render_template('index.html',  title = title)

@main.route('/user')
@login_required
def user():
    username = current_user.username
    user = User.query.filter_by(username=username).first()
    if user is None:
        return ('not found')
    return render_template('profile.html', user=user)


@main.route('/user/<username>')
def profile(username):
    user = User.query.filter_by(username = username).first()

    if user is None:
        abort(404)

    return render_template("profile/profile.html", user = user)


@main.route('/user/<username>/update',methods = ['GET','POST'])
@login_required
def update_profile(username):
    user = User.query.filter_by(username = username).first()
    if user is None:
        abort(404)

    form = UpdateProfile()

    if form.validate_on_submit():
        user.bio = form.bio.data

        db.session.add(user)
        db.session.commit()

        return redirect(url_for('.profile',username=user.username))

    return render_template('profile/updates.html',update_form =form)

@main.route('/user/<username>/update/pic',methods= ['POST'])
@login_required
def update_pic(username):
    user = User.query.filter_by(username = username).first()
    if 'photo' in request.files:
        filename = photos.save(request.files['photo'])
        path = f'photos/{filename}'
        user.profile_pic_path = path
        db.session.commit()
    return redirect(url_for('main.profile',username=username))

@main.route('/reviews/<bikes_id>')
@login_required
def review(bikes_id):
    '''
    function to return the comments
    '''
    form = ReviewForm()
    bike = Bikes.query.get(bikes_id)
    user = User.query.all()
    reviews = Reviews.query.filter_by(bikes_id=bikes_id).all()
    if form.validate_on_submit():
        review = form.review.data
        bikes_id = bikes_id
        user_id = current_user._get_current_object().id
        new_review = Reviews(
            review=review,
            bikes_id=bikes_id,
            user_id=user_id,
            )

        new_review.save()
        new_reviews = [new_review]
        print(new_reviews)
        return redirect(url_for('.review', bikes_id=bikes_id))
    return render_template('reviews.html', form=form, bike=bike, reviews=reviews, user=user)

@main.route('/bikes')
@login_required
def bike():
    bikes = Bikes.query.all()
    return render_template('bikes_display.html', bikes=bikes, user=user)

@main.route('/new_bike', methods=['GET', 'POST'])
@login_required
def new_bike():

    '''
    View bike page function that returns the bike details page and its data
    '''
    title = 'Bike Hire'
    

    form = BikeForm()
    if form.validate_on_submit():
        category= form.category.data
        bike_pic_path=form.image.data 
        user_id = current_user._get_current_object().id
        bikes_obj = Bikes(user_id=user_id,category=category,bike_pic_path=bike_pic_path)
        bikes_obj.save_bike
        return redirect(url_for('main.bike'))
    return render_template('new_bike.html', bike_form=form)

# @main.route('/new_bike/', methods = ['GET','POST'])
# @login_required
# def new_bike():

#     form = BikeForm()

#     if form.validate_on_submit():
#         category = form.category.data
#         bike_pic= form.image
        
#         bike_obj = Bikes(category=category,bike_pic_path=bike_pic)
#         bike_obj.save()

#         # Updated bike instance
#         new_bike = Bikes(title=title,category= category,user_id=current_user.id,bike_pic=bike_pic)

#         title='New Bike'

#         new_bike.save_bike()

#         # return redirect(url_for('main.catalog')) #or main.bike ??

#     return render_template('new_bike.html',bike_form= form)

@main.route('/categories/<category>')
def category(category):
    '''
    function to return the pitches by category
    '''
    category = Bikes.get_bikes(category) #get_bikes defined in the bikes route
    # print(category)
    title = f'{category}'
    return render_template('catalogue.html',title = title, category = category)
