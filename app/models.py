from unicodedata import category
from . import db
from datetime import datetime
from werkzeug.security import generate_password_hash,check_password_hash
from flask_login import UserMixin, current_user
from . import login_manager
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(UserMixin,db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer,primary_key = True)
    username = db.Column(db.String(255),index = True)
    email = db.Column(db.String(255),unique = True,index = True)
    bio = db.Column(db.String(255))
    profile_pic_path = db.Column(db.String())
    secure_password = db.Column(db.String(255),nullable = False)

    @property
    def set_password(self):
        raise AttributeError('You cannot read the password attribute')
    @set_password.setter
    def password(self, password):
        self.secure_password = generate_password_hash(password)
    def verify_password(self, password):
        return check_password_hash(self.secure_password,password) 
    def save_u(self):
        db.session.add(self)
        db.session.commit()
    def delete(self):
        db.session.delete(self)
        db.session.commit()
    def __repr__(self):
        return f'User {self.username}'

class Bikes(db.Model):
    __tablename__='bikes'
    id = db.Column(db.Integer,primary_key = True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    category = db.Column(db.String(255))
    bike_pic_path = db.Column(db.String())
    bike_reviews = db.relationship("Reviews",backref="username")

    def save_bike(self):
        db.session.add(self)
        db.session.commit()

    @classmethod
    def get_bike(cls,id):
        bike = Bikes .query.filter_by(category=category).all()
        return bike

    def __repr__(self):
        return f"Bikes ('{self.bike}', '{self.date_posted}')"



class Reviews(db.Model):
    __tablename__='reviews'
    id = db.Column(db.Integer,primary_key =True)
    review = db.Column(db.Text())
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    bikes_id =db.Column(db.Integer, db.ForeignKey("bikes.id"))
    
    def save_review(self):
        db.session.add(self)
        db.session.commit()

    @classmethod
    def get_review(cls,id):
        reviews = Reviews .query.filter_by(bikes_id=id).all()
        return reviews

    def __repr__(self):
        return f"Reviews ('{self.review}', '{self.date_posted}')"
