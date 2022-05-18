from flask_wtf import FlaskForm
from wtforms import StringField,TextAreaField,SubmitField,SelectField
from wtforms.validators import DataRequired
from flask_wtf.file import FileField, FileRequired

class ReviewForm(FlaskForm):
    
    review = TextAreaField('Review')
    submit = SubmitField('Post Review')

class UpdateProfile(FlaskForm):
    bio = TextAreaField('Help us know you better.',validators = [DataRequired()])
    submit = SubmitField('Submit')

class BikeForm(FlaskForm):
    
    category = TextAreaField('Category')
    image = FileField(validators=[FileRequired()]) # IMAGE
    submit = SubmitField('Submit')