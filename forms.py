from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, TextAreaField, FloatField, SelectField, HiddenField
from wtforms.validators import DataRequired, Email, EqualTo, Length, NumberRange, ValidationError
from models import User

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    phone = StringField('Phone Number (optional)', validators=[Length(max=15)])
    submit = SubmitField('Register')
    
    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Username already taken. Please choose a different one.')
    
    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Email already registered. Please use a different email address.')

class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm New Password', validators=[DataRequired(), EqualTo('new_password')])
    submit = SubmitField('Change Password')

class ProfileForm(FlaskForm):
    phone = StringField('Phone Number', validators=[Length(max=15)])
    submit = SubmitField('Update Profile')

class AddFundsForm(FlaskForm):
    amount = FloatField('Amount (₹)', validators=[DataRequired(), NumberRange(min=100)])
    upi_txn_id = StringField('UPI Transaction ID', validators=[DataRequired(), Length(min=6, max=100)])
    submit = SubmitField('Add Funds')

class WithdrawFundsForm(FlaskForm):
    amount = FloatField('Amount (₹)', validators=[DataRequired(), NumberRange(min=100)])
    upi_id = StringField('UPI ID', validators=[DataRequired(), Length(min=5, max=50)])
    submit = SubmitField('Withdraw Funds')

class GameBetForm(FlaskForm):
    amount = FloatField('Bet Amount', validators=[DataRequired(), NumberRange(min=10)])
    color = SelectField('Color', choices=[('red', 'Red'), ('green', 'Green'), ('violet', 'Violet')], validators=[DataRequired()])
    submit = SubmitField('Place Bet')

class PremiumSubscriptionForm(FlaskForm):
    submit = SubmitField('Subscribe to Premium')

class SupportForm(FlaskForm):
    subject = StringField('Subject', validators=[DataRequired(), Length(max=100)])
    message = TextAreaField('Message', validators=[DataRequired()])
    submit = SubmitField('Submit Ticket')

class SupportReplyForm(FlaskForm):
    message = TextAreaField('Reply', validators=[DataRequired()])
    submit = SubmitField('Send Reply')

class ContactForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(max=50)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    subject = StringField('Subject', validators=[DataRequired(), Length(max=100)])
    message = TextAreaField('Message', validators=[DataRequired()])
    submit = SubmitField('Send Message')
