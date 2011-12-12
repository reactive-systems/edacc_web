# -*- coding: utf-8 -*-
"""
    edacc.forms
    -----------

    Various WTForms used by the web frontend.

    :copyright: (c) 2010 by Daniel Diepold.
    :license: MIT, see LICENSE for details.
"""

from flaskext.wtf import Form, TextField, PasswordField, TextAreaField, RadioField
from flaskext.wtf import FileField, Required, Length, Email, EqualTo, SelectField
from flaskext.wtf import ValidationError, BooleanField
from wtforms.ext.sqlalchemy.fields import QuerySelectMultipleField,\
                                            QuerySelectField

ERROR_REQUIRED = 'This field is required.'

MAX_SC_LEN = 100 # maximum length of solver config names to display before truncating

def truncate_name(s, l):
    if len(s) > l:
        return s[:l/2] + " [..] " + s[-l/2:]
    return s

class EmptyQuery(list):
    """ Helper class that extends the builtin list class to always evaluate to
        True.
        WTForms tries to iterate over field.query or field.query_factory(). But
        when field.query an empty list and evaluates to False, field.query_factory
        returns None and causes an exception. """
    def __nonzero__(self):
        """ for Python 2.x """
        return True
    def __bool__(self):
        """ for Python 3.x """
        return True


class RegistrationForm(Form):
    lastname = TextField('Last Name',
                         [Required(ERROR_REQUIRED),
                          Length(max=255)])
    firstname = TextField('First Name',
                          [Required(ERROR_REQUIRED),
                           Length(max=255)])
    email = TextField('Email',
                      [Required(ERROR_REQUIRED),
                       Length(max=255),
                       Email(message='Invalid e-mail address.')])
    password = PasswordField('Password',
                             [Required()])
    password_confirm = PasswordField('Confirm Password',
                                     [EqualTo('password',
                                        message='Passwords must match.')])
    address = TextAreaField('Postal Address')
    affiliation = TextAreaField('Affiliation')
    captcha = TextField()

class LoginForm(Form):
    email = TextField('Email', [Required(ERROR_REQUIRED)])
    password = PasswordField('Password',
                             [Required(ERROR_REQUIRED)])

class SolverForm(Form):
    name = TextField('Name', [Required(ERROR_REQUIRED)])
    binary = FileField('Binary')
    code = FileField('Code')
    description = TextAreaField('Description')
    version = TextField('Version', [Required(ERROR_REQUIRED)])
    authors = TextField('Authors', [Required(ERROR_REQUIRED)])
    parameters = TextField('Parameters', [Required(ERROR_REQUIRED)])
    competition_categories = QuerySelectMultipleField(
                                'Competition Categories',
                                query_factory=lambda: [],
                                validators=[Required('Please choose one or more \
                                                     categories for your solver \
                                                     to compete in.')])

    def validate_parameters(self, field):
        if not 'SEED' in field.data or not 'INSTANCE' in field.data:
            raise ValidationError('You have to specify SEED \
                                             and INSTANCE as parameters.')

    def validate_code(self, field):
        if not field.file.filename or not field.file.filename.endswith('.zip'):
            raise ValidationError('The code archive has to be a .zip file.')

class BenchmarkForm(Form):
    instance = FileField('File')
    name = TextField('Name')
    new_benchmark_type = TextField('New Type')
    benchmark_type = QuerySelectField('Existing Type', allow_blank=True,
                                      query_factory=lambda: [],
                                      blank_text='Create a new type')
    new_source_class = TextField('New Source Class')
    new_source_class_description = TextField('New Source Class Description')
    source_class = QuerySelectField('Exisiting Source Class', allow_blank=True,
                                    query_factory=lambda: [],
                                    blank_text='Create a new source class')

    def validate_new_benchmark_type(self, field):
        if self.benchmark_type.data is None and field.data.strip() == '':
            raise ValidationError('Please specify a new benchmark type or choose \
                                  an existing one.')

    def validate_new_source_class(self, field):
        if self.source_class.data is None and field.data.strip() == '':
            raise ValidationError('Please specify a new source class or choose \
                                  an existing one.')

    def validate_instance(self, field):
        if not field.file.filename:
            raise ValidationError(ERROR_REQUIRED)

class ResultBySolverForm(Form):
    solver_config = QuerySelectField('Solver Configuration', get_label=lambda sc: truncate_name(str(sc), MAX_SC_LEN))

class ResultByInstanceForm(Form):
    instance = QuerySelectField('Instance', get_pk=lambda i: i.idInstance)

class TwoSolversOnePropertyScatterPlotForm(Form):
    solver_config1 = QuerySelectField('First Solver Configuration', get_label=lambda sc: truncate_name(str(sc), MAX_SC_LEN))
    solver_config2 = QuerySelectField('Second Solver Configuration', get_label=lambda sc: truncate_name(str(sc), MAX_SC_LEN))
    instance_filter = TextField('Filter Instances')
    result_property = SelectField('Property')
    i = QuerySelectMultipleField('Instances', get_pk=lambda i: i.idInstance, allow_blank=True)
    xscale = RadioField('X-axis scale', choices=[('', 'linear'), ('log', 'log')], default='log')
    yscale = RadioField('Y-axis scale', choices=[('', 'linear'), ('log', 'log')], default='log')
    run = SelectField('Plot for run')

class OneSolverTwoResultPropertiesPlotForm(Form):
    solver_config = QuerySelectField('Solver Configuration', get_label=lambda sc: truncate_name(str(sc), MAX_SC_LEN))
    result_property1 = SelectField('First Result Property')
    result_property2 = SelectField('Second Result Property')
    instance_filter = TextField('Filter Instances')
    i = QuerySelectMultipleField('Instances', get_pk=lambda i: i.idInstance, allow_blank=True)
    xscale = RadioField('X-axis scale', choices=[('', 'linear'), ('log', 'log')], default='log')
    yscale = RadioField('Y-axis scale', choices=[('', 'linear'), ('log', 'log')], default='log')
    run = SelectField('Plot for run')

class OneSolverInstanceAgainstResultPropertyPlotForm(Form):
    solver_config = QuerySelectField('Solver Configuration', get_label=lambda sc: truncate_name(str(sc), MAX_SC_LEN))
    result_property = SelectField('Result Property')
    instance_property = SelectField('Instance Property')
    instance_filter = TextField('Filter Instances')
    i = QuerySelectMultipleField('Instances', get_pk=lambda i: i.idInstance, allow_blank=True)
    xscale = RadioField('X-axis scale', choices=[('', 'linear'), ('log', 'log')], default='')
    yscale = RadioField('Y-axis scale', choices=[('', 'linear'), ('log', 'log')], default='log')
    run = SelectField('Plot for run')

class CactusPlotForm(Form):
    result_property = SelectField('Property')
    sc = QuerySelectMultipleField('Solver Configurations')
    instance_filter = TextField('Filter Instances')
    run = SelectField('Plot for run')
    flip_axes = BooleanField("Swap axes", default=True)
    log_property = BooleanField("Logarithmic property-axis", default=True)
    i = QuerySelectMultipleField('Instances (Group 0)', get_pk=lambda i: i.idInstance, allow_blank=True)

class RTDComparisonForm(Form):
    solver_config1 = QuerySelectField('First Solver Configuration', get_label=lambda sc: truncate_name(str(sc), MAX_SC_LEN))
    solver_config2 = QuerySelectField('Second Solver Configuration', get_label=lambda sc: truncate_name(str(sc), MAX_SC_LEN))
    result_property = SelectField('Property')
    log_property = BooleanField("Logarithmic property-axis", default=True)
    instance = QuerySelectField('Instance', get_pk=lambda i: i.idInstance, allow_blank=True)
    instance_filter = TextField('Filter Instances')

class RTDPlotsForm(Form):
    sc = QuerySelectMultipleField('Solver Configurations', get_label=lambda sc: truncate_name(str(sc), MAX_SC_LEN))
    result_property = SelectField('Property')
    log_property = BooleanField("Logarithmic property-axis", default=True)
    instance = QuerySelectField('Instance', get_pk=lambda i: i.idInstance, allow_blank=True)
    instance_filter = TextField('Filter Instances')

class RTDPlotForm(Form):
    solver_config = QuerySelectField('Solver Configuration', get_label=lambda sc: truncate_name(str(sc), MAX_SC_LEN))
    result_property = SelectField('Property')
    log_property = BooleanField("Logarithmic property-axis", default=True)
    instance = QuerySelectField('Instance', get_pk=lambda i: i.idInstance, allow_blank=True)
    instance_filter = TextField('Filter Instances')

class ProbabilisticDominationForm(Form):
    result_property = SelectField('Property')
    solver_config1 = QuerySelectField('First Solver Configuration', get_label=lambda sc: truncate_name(str(sc), MAX_SC_LEN))
    solver_config2 = QuerySelectField('Second Solver Configuration', get_label=lambda sc: truncate_name(str(sc), MAX_SC_LEN))
    instance_filter = TextField('Filter Instances')
    i = QuerySelectMultipleField('Instances', get_pk=lambda i: i.idInstance, allow_blank=True)

class BoxPlotForm(Form):
    solver_configs = QuerySelectMultipleField('Solver Configurations', get_label=lambda sc: truncate_name(str(sc), MAX_SC_LEN))
    result_property = SelectField('Property')
    instances = QuerySelectMultipleField('Instances')
    instance_filter = TextField('Filter Instances')
    i = QuerySelectMultipleField('Instances', get_pk=lambda i: i.idInstance, allow_blank=True)

class RankingForm(Form):
    i = QuerySelectMultipleField('Instances', get_pk=lambda i: i.idInstance, allow_blank=True)
    calculate_average_dev = BooleanField('Calculate avg. deviation', default=False)
    penalized_average_runtime = BooleanField('Calculate penalized average runtime', default=True)
    instance_filter = TextField('Filter Instances')

class ResultsBySolverAndInstanceForm(Form):
    solver_configs = QuerySelectMultipleField('Solver Configurations', get_label=lambda sc: truncate_name(str(sc), MAX_SC_LEN))
    display_measure = SelectField('Display measure', default='par10',
                                  choices=[('mean', 'mean'), ('median', 'median'),
                                    ('par10', 'par10'), ('min', 'min'), ('max', 'max')])
    i = QuerySelectMultipleField('Instances', get_pk=lambda i: i.idInstance, allow_blank=True)
    instance_filter = TextField('Filter Instances')
    
class RuntimeMatrixPlotForm(Form):
    measure = SelectField('Measure', default='par10',
                                  choices=[('mean', 'mean'),
                                    ('par10', 'par10'), ('min', 'min'), ('max', 'max')])

class MonitorForm(Form):
    experiments = QuerySelectMultipleField('Experiments', get_label = lambda e: e.name)
    status = QuerySelectMultipleField('Status', get_label = lambda e: e.description)

class ClientForm(Form):
    experiments = QuerySelectMultipleField('Experiments', get_label = lambda e: e.name)