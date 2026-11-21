from datetime import datetime, timezone
from urllib.parse import urlparse

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired, MultipleFileField
from wtforms import (
    BooleanField, DateField, FieldList, FloatField, Form, FormField,
    IntegerField, SelectField, SelectMultipleField, StringField, SubmitField, TextAreaField,
)
from wtforms.validators import Length, NumberRange, Optional
from wtforms.widgets import CheckboxInput, ListWidget

from app.profiles.geocode import LAT_RANGE, LNG_RANGE, in_india
from app.profiles.options import CLASS_LEVELS, FACILITIES, MEDIUMS, SPECIALITIES

CLASS_CHOICES_FROM = [("", "From")] + [(c, c) for c in CLASS_LEVELS]
CLASS_CHOICES_TO = [("", "To")] + [(c, c) for c in CLASS_LEVELS]


class ResultRowForm(Form):
    """One row of the results table. Plain wtforms Form, so no CSRF token per row."""

    year = IntegerField("Year", validators=[Optional()])
    class10 = FloatField("Class 10 pass %", validators=[Optional(), NumberRange(0, 100)])
    class12 = FloatField("Class 12 pass %", validators=[Optional(), NumberRange(0, 100)])


class SchoolProfileForm(FlaskForm):
    tagline = StringField("Tagline", validators=[Optional(), Length(max=150)])
    about = TextAreaField("About the school", validators=[Optional(), Length(max=2000)])

    medium = SelectField("Medium of teaching", choices=MEDIUMS, validators=[Optional()])
    classes_from = SelectField("Classes from", choices=CLASS_CHOICES_FROM, validators=[Optional()])
    classes_to = SelectField("Classes up to", choices=CLASS_CHOICES_TO, validators=[Optional()])
    total_students = IntegerField("Total students", validators=[Optional(), NumberRange(1, 50000)])

    fee_min = IntegerField("Yearly fees from (Rs.)", validators=[Optional(), NumberRange(0, 5000000)])
    fee_max = IntegerField("Yearly fees up to (Rs.)", validators=[Optional(), NumberRange(0, 5000000)])

    facilities = SelectMultipleField(
        "Facilities", choices=FACILITIES,
        widget=ListWidget(prefix_label=False), option_widget=CheckboxInput(),
    )
    specialities = SelectMultipleField(
        "Specialities", choices=SPECIALITIES,
        widget=ListWidget(prefix_label=False), option_widget=CheckboxInput(),
    )

    results = FieldList(FormField(ResultRowForm), min_entries=3, max_entries=3)

    admission_open = BooleanField("Admissions are open")
    admission_deadline = DateField("Last date to apply", validators=[Optional()])
    admission_url = StringField("Admission form link", validators=[Optional(), Length(max=300)])

    latitude = FloatField("Latitude", validators=[Optional()])
    longitude = FloatField("Longitude", validators=[Optional()])
    redetect = BooleanField("Detect the location again from my address")

    submit = SubmitField("Save profile")

    def validate(self, extra_validators=None):
        ok = super().validate(extra_validators=extra_validators)

        if self.fee_min.data is not None and self.fee_max.data is not None \
                and self.fee_min.data > self.fee_max.data:
            self.fee_max.errors.append("Maximum fees cannot be less than minimum fees.")
            ok = False

        start, end = self.classes_from.data, self.classes_to.data
        if bool(start) != bool(end):
            self.classes_to.errors.append("Choose both the first and the last class.")
            ok = False
        elif start and CLASS_LEVELS.index(start) > CLASS_LEVELS.index(end):
            self.classes_to.errors.append("The last class cannot come before the first class.")
            ok = False

        url = (self.admission_url.data or "").strip()
        if url:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                self.admission_url.errors.append("Enter a full link starting with http:// or https://")
                ok = False

        this_year = datetime.now(timezone.utc).year
        seen = set()
        for row in self.results:
            year, c10, c12 = row.year.data, row.class10.data, row.class12.data
            if c10 is None and c12 is None:
                if year is not None:
                    row.class10.errors.append("Enter at least one pass percentage.")
                    ok = False
                continue
            if year is None or not (this_year - 20 <= year <= this_year):
                row.year.errors.append(f"Enter a year between {this_year - 20} and {this_year}.")
                ok = False
            elif year in seen:
                row.year.errors.append("This year is entered twice.")
                ok = False
            else:
                seen.add(year)

        lat, lng = self.latitude.data, self.longitude.data
        if (lat is None) != (lng is None):
            self.longitude.errors.append("Enter both latitude and longitude, or leave both empty.")
            ok = False
        elif lat is not None and not in_india(lat, lng):
            self.latitude.errors.append(
                f"The location must be inside India (latitude {LAT_RANGE[0]} to {LAT_RANGE[1]}, "
                f"longitude {LNG_RANGE[0]} to {LNG_RANGE[1]})."
            )
            ok = False
        return ok


class LogoForm(FlaskForm):
    logo = FileField("School logo", validators=[FileRequired(), FileAllowed(["jpg", "jpeg", "png"], "Only JPG or PNG files.")])
    submit = SubmitField("Upload logo")


class GalleryForm(FlaskForm):
    photos = MultipleFileField("Gallery photos")
    submit = SubmitField("Upload photos")