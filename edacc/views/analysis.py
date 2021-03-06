# -*- coding: utf-8 -*-
"""
    edacc.views.analysis
    --------------------

    Defines request handler functions for the analysis pages.

    :copyright: (c) 2010 by Daniel Diepold.
    :license: MIT, see LICENSE for details.
"""

import math
import numpy
import StringIO
import csv

from sqlalchemy.orm import joinedload
from sqlalchemy import or_, func, and_, not_
from sqlalchemy.sql import expression, select

from flask import Blueprint
from flask import render_template as render, g, session
from flask import abort, request, jsonify, Response
from werkzeug import Headers, secure_filename

from edacc import models, forms, ranking, statistics, algorithms
from edacc.web import cache
from edacc.views.helpers import require_phase, require_login, is_admin
from edacc.constants import RANKING, ANALYSIS1, ANALYSIS2, OWN_RESULTS
from edacc.views import plot
from edacc.forms import EmptyQuery

analysis = Blueprint('analysis', __name__, template_folder='static')

#def render(*args, **kwargs):
#    from tidylib import tidy_document
#    res = render_template(*args, **kwargs)
#    doc, errs = tidy_document(res)
#    return doc

@analysis.route('/<database>/experiment/<int:experiment_id>/careful-ranking/')
@require_phase(phases=RANKING)
@require_login
def careful_solver_ranking(database, experiment_id):
    """
        Display the raw-scores matrix that is calculated for the careful ranking
    """
    db = models.get_database(database) or abort(404)
    experiment = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    form = forms.RankingForm(request.args)
    form.i.query = experiment.get_instances(db) or EmptyQuery()

    if form.i.data:
        if form.cost.data == 'None': form.cost.data = experiment.defaultCost

        solver_configs = experiment.solver_configurations
        if not is_admin() and db.is_competition() and db.competition_phase() in OWN_RESULTS:
            solver_configs = filter(lambda sc: sc.solver_binary.solver.user == g.User, solver_configs)

        results_matrix, _, _ = experiment.get_result_matrix(db, solver_configs, form.i.data, form.cost.data,
                                                            form.fixed_limit.data)

        carefully_ranked_solvers, raw_scores, dom_matrix = ranking.careful_ranking(db, experiment, form.i.data,
                                                                                   solver_configs, results_matrix,
                                                                                   form.cost.data,
                                                                                   noise=form.careful_ranking_noise.data,
                                                                                   break_ties=form.break_careful_ties.data)

        return render("/analysis/careful_ranking.html", db=db, experiment=experiment, database=database,
                      raw_scores=raw_scores, solver_configs=solver_configs, dom_matrix=dom_matrix)

    return render("/analysis/careful_ranking.html", db=db, experiment=experiment, database=database)


@analysis.route('/<database>/experiment/<int:experiment_id>/survival-ranking/')
@require_phase(phases=RANKING)
@require_login
def survival_solver_ranking(database, experiment_id):
    """
        Display the domination matrix that is calculated for the survival ranking
    """
    db = models.get_database(database) or abort(404)
    experiment = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    form = forms.RankingForm(request.args)
    form.i.query = experiment.get_instances(db) or EmptyQuery()

    if form.i.data:
        if form.cost.data == 'None': form.cost.data = experiment.defaultCost

        solver_configs = experiment.solver_configurations
        if not is_admin() and db.is_competition() and db.competition_phase() in OWN_RESULTS:
            solver_configs = filter(lambda sc: sc.solver_binary.solver.user == g.User, solver_configs)

        results_matrix, _, _ = experiment.get_result_matrix(db, solver_configs, form.i.data, form.cost.data,
                                                            form.fixed_limit.data)

        survival_ranked_solvers, survival_winner, M_surv, p_values, tests_performed, dot_code, count_values_tied = ranking.survival_ranking(
            db, experiment, form.i.data,
            solver_configs, results_matrix, form.cost.data, form.survnoise.data, form.survival_ranking_alpha.data)

        return render("/analysis/survival_ranking.html", db=db, experiment=experiment, database=database,
                      survival_winner=survival_winner, solver_configs=solver_configs, p_values=p_values,
                      tests_performed=tests_performed, dot_code=dot_code, count_values_tied=count_values_tied)

    return render("/analysis/survival_ranking.html", db=db, experiment=experiment, database=database)


@analysis.route('/<database>/experiment/<int:experiment_id>/ranking/')
@require_phase(phases=RANKING)
@require_login
def solver_ranking(database, experiment_id):
    """ Display a page with the ranking of the solvers of
        the experiment.
    """
    db = models.get_database(database) or abort(404)
    experiment = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    form = forms.RankingForm(request.args)
    if form.cost.data == 'None': form.cost.data = experiment.defaultCost
    form.i.query = sorted(experiment.get_instances(db), key=lambda i: i.get_name()) or EmptyQuery()
    form.sc.query = experiment.solver_configurations or EmptyQuery()
    if not is_admin() and db.is_competition() and db.competition_phase() in OWN_RESULTS:
        form.sc.query = filter(lambda sc: sc.solver_binary.solver.user == g.User, form.sc.query) or EmptyQuery()
    if len(experiment.solver_configurations) > 100 and not form.i.data: form.careful_ranking.data = False

    result_properties = db.get_plotable_result_properties()
    result_properties = zip([p.idProperty for p in result_properties], [p.name for p in result_properties])
    form.cost.choices = [('resultTime', 'CPU Time'), ('wallTime', 'Wall Clock Time'),
                         ('cost', 'Cost')] + result_properties

    if form.i.data:
        solver_configs = form.sc.data
        if not is_admin() and db.is_competition() and db.competition_phase() in OWN_RESULTS:
            solver_configs = filter(lambda sc: sc.solver_binary.solver.user == g.User, solver_configs)
        show_top = form.show_top.data

        solver_config_ids = [sc.idSolverConfig for sc in solver_configs]

        CACHE_TIME = 7 * 24 * 60 * 60
        #CACHE_TIME = 1
        @cache.memoize(timeout=CACHE_TIME)
        def cached_ranking(database, experiment_id, solver_config_ids, sc_names, last_modified_job, show_top,
                           job_count, form_i_data, form_par, form_avg_dev, form_careful_ranking,
                           careful_ranking_noise, form_survival_ranking, form_survnoise, form_survival_ranking_alpha,
                           form_break_ties, cost, form_par_factor, form_fixed_limit, form_median_runtime, csv_response,
                           latex_response, user_id):

            if cost not in ('resultTime', 'wallTime', 'cost'): cost = int(cost)

            ranked_solvers = ranking.number_of_solved_instances_ranking(db, experiment, form.i.data, solver_configs,
                                                                        cost, form_fixed_limit)
            ranking_data, _ = ranking.get_ranking_data(db, experiment, ranked_solvers, form.i.data,
                                                       form.penalized_average_runtime.data,
                                                       form.calculate_average_dev.data, cost, form_par_factor,
                                                       form_fixed_limit)

            if len(ranking_data) > show_top:
                ranking_data = ranking_data[:show_top]

            faulty_solvers_ids = db.session.query(db.ExperimentResult.SolverConfig_idSolverConfig) \
                .filter(db.ExperimentResult.SolverConfig_idSolverConfig.in_(solver_config_ids)) \
                .filter(db.ExperimentResult.resultCode == -1).distinct().all()

            if form_careful_ranking or form_survival_ranking:
                results_matrix, _, _ = experiment.get_result_matrix(db, solver_configs, form.i.data, cost,
                                                                    form_fixed_limit)

            careful_rank = dict()
            if form_careful_ranking:
                carefully_ranked_solvers, _, _ = ranking.careful_ranking(db, experiment, form.i.data,
                                                                         solver_configs, results_matrix, cost,
                                                                         noise=careful_ranking_noise,
                                                                         break_ties=form_break_ties)
                careful_rank_counter = 1 # 1 is VBS
                for tied_solvers in carefully_ranked_solvers:
                    careful_rank_counter += 1
                    careful_rank_comp_counter = 1
                    for solver in tied_solvers:
                        careful_rank[solver] = careful_rank_counter
                        if form_break_ties and len(tied_solvers) > 1:
                            careful_rank[solver] = str(careful_rank[solver]) + "_" + str(careful_rank_comp_counter)
                            careful_rank_comp_counter += 1

            survival_rank = dict()
            if form_survival_ranking:
                survival_ranked_solvers, _, _, _, _, _, _ = ranking.survival_ranking(db, experiment, form.i.data,
                                                                                     solver_configs, results_matrix,
                                                                                     cost, form_survnoise,
                                                                                     form_survival_ranking_alpha)

                survival_rank_counter = 1
                for tied_solvers in survival_ranked_solvers:
                    survival_rank_counter += 1
                    survival_rank_comp_counter = 1
                    for solver in tied_solvers:
                        survival_rank[solver] = survival_rank_counter
                        if len(tied_solvers) > 1: # TODO and break ties checked
                            survival_rank[solver] = str(survival_rank[solver]) + "_" + str(survival_rank_comp_counter)
                            survival_rank_comp_counter += 1

            if csv_response:
                head = ['#', 'Solver', '# of successful runs', '% of all runs', '% of VBS runs',
                        'penalized cumulated cost', 'penalized median cost']

                if form.calculate_average_dev.data:
                    head.append('avg. deviation of successful runs')
                    head.append('avg. coefficient of variation')
                    head.append('avg. quartile coefficient of dispersion')
                if form.penalized_average_runtime.data: head.append('penalized avg. runtime')
                csv_response = StringIO.StringIO()
                csv_writer = csv.writer(csv_response)
                csv_writer.writerow(head)

                for rnk, row in enumerate(ranking_data):
                    write_row = [rnk, row[0], row[1], round(row[2] * 100, 2), round(row[3] * 100, 2)] + map(
                        lambda x: round(x, 4), row[4:6])
                    if form.calculate_average_dev.data:
                        write_row.append(round(row[6], 4))
                        write_row.append(round(row[7], 4))
                        write_row.append(round(row[8], 4))
                    if form.penalized_average_runtime.data: write_row.append(round(row[9], 4))
                    csv_writer.writerow(write_row)

                csv_response.seek(0)
                headers = Headers()
                headers.add('Content-Type', 'text/csv')
                headers.add('Content-Disposition', 'attachment',
                            filename=secure_filename(experiment.name + "_ranking.csv"))
                return Response(response=csv_response.read(), headers=headers)
            elif latex_response:
                head = ['\\#', 'Solver', '\\# of successful runs', '\\% of all runs', '\\% of VBS runs',
                        'cumulated cost', 'median cost']

                if form.calculate_average_dev.data:
                    head.append('avg. deviation of successful runs')
                    head.append('avg. coefficient of variation')
                    head.append('avg. quartile coefficient of dispersion')
                if form.penalized_average_runtime.data: head.append('penalized avg. cost')
                table = "\\begin{tabular}{" + ('|'.join(['c'] * len(head))) + "}\n"
                table += ' & '.join(head) + "\\\\ \\hline\n"
                for rnk, row in enumerate(ranking_data):
                    table += ' & '.join(map(str,
                                            [rnk, row[0], row[1], round(row[2] * 100, 2), round(row[3] * 100, 2)] + map(
                                                lambda x: round(x, 4), row[4:6])))
                    if form.calculate_average_dev.data:
                        table += " & " + str(round(row[6], 4))
                        table += " & " + str(round(row[7], 4))
                        table += " & " + str(round(row[8], 4))
                    if form.penalized_average_runtime.data: table += " & " + str(round(row[9], 4))
                    table += "\\\\ \\hline\n"
                table += "\\end{tabular}"

                headers = Headers()
                headers.add('Content-Type', 'text/plain')
                return Response(response=table, headers=headers)

            GET_data = "&".join(['='.join(list(t)) for t in request.args.items(multi=True)])
            return render('/analysis/ranking.html', database=database, db=db,
                          experiment=experiment, ranked_solvers=ranked_solvers,
                          careful_rank=careful_rank, survival_rank=survival_rank,
                          data=ranking_data, form=form, instance_properties=db.get_instance_properties(),
                          GET_data=GET_data,
                          faulty_solvers_ids=faulty_solvers_ids)

        last_modified_job = db.session.query(func.max(db.ExperimentResult.date_modified)) \
            .filter_by(experiment=experiment).first()
        job_count = db.session.query(db.ExperimentResult).filter_by(experiment=experiment).count()

        return cached_ranking(database, experiment_id, solver_config_ids,
                              ''.join(sc.get_name() for sc in solver_configs),
                              last_modified_job, show_top, job_count, [i.idInstance for i in form.i.data],
                              form.penalized_average_runtime.data, form.calculate_average_dev.data,
                              form.careful_ranking.data, form.careful_ranking_noise.data or 1.0,
                              form.survival_ranking.data,
                              form.survnoise.data, form.survival_ranking_alpha.data,
                              form.break_careful_ties.data, form.cost.data, form.par_factor.data, form.fixed_limit.data,
                              form.median_runtime.data, 'csv' in request.args, 'latex' in request.args,
                              session.get('idUser', None))

    return render('/analysis/ranking.html', database=database, db=db,
                  experiment=experiment, form=form, instance_properties=db.get_instance_properties())


@analysis.route('/<database>/experiment/<int:experiment_id>/sota/')
@require_phase(phases=ANALYSIS1)
@require_login
def sota_solvers(database, experiment_id):
    db = models.get_database(database) or abort(404)
    experiment = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    form = forms.SOTAForm(request.args)
    if form.cost.data == 'None': form.cost.data = experiment.defaultCost
    form.i.query = experiment.get_instances(db) or EmptyQuery()
    form.sc.query = experiment.solver_configurations or EmptyQuery()

    if form.i.data:
        solver_config_ids = [sc.idSolverConfig for sc in form.sc.data]
        instance_ids = [i.idInstance for i in form.i.data]

        @cache.memoize(1) # 7*24*60*60
        def cached_sota_solvers(database, experiment_id, solver_config_ids, sc_names, instance_ids, job_count,
                                last_modified_job, user_id):
            sota_solvers = experiment.get_sota_solvers(db, form.i.data, form.sc.data)
            unique_solver_contribs = experiment.unique_solver_contributions(db, form.i.data, form.sc.data)
            ranked_solvers = ranking.number_of_solved_instances_ranking(db, experiment, form.i.data, form.sc.data,
                                                                        form.cost.data)
            ranking_data, vbs_uses_solver_count = ranking.get_ranking_data(db, experiment, ranked_solvers, form.i.data,
                                                                           False, False, form.cost.data)
            result_matrix, _, _ = experiment.get_result_matrix(db, form.sc.data, form.i.data, form.cost.data)
            sc_correlation = dict((sc, dict()) for sc in form.sc.data)
            for sc1 in form.sc.data:
                for sc2 in form.sc.data:
                    if sc1 == sc2: sc_correlation[sc1][sc2] = sc_correlation[sc2][sc1] = 1.0; continue
                    if sc1 in sc_correlation and sc2 in sc_correlation[sc1]: continue
                    v1 = []
                    v2 = []
                    for instance in form.i.data:
                        for sc1run, sc2run in zip(result_matrix[instance.idInstance][sc1.idSolverConfig],
                                                  result_matrix[instance.idInstance][sc2.idSolverConfig]):
                            v1.append(sc1run.penalized_time1)
                            v2.append(sc2run.penalized_time1)
                    sc_correlation[sc1][sc2] = statistics.spearman_correlation(v1, v2)[0]
                    sc_correlation[sc2][sc1] = sc_correlation[sc1][sc2]

            solved_instances = experiment.get_solved_instance_ids_by_solver_id(db, form.i.data, form.sc.data)
            solved_instance_ids = set()
            for sc in solved_instances:
                for solved_instance in solved_instances[sc]:
                    solved_instance_ids.add(solved_instance)

            minimum_covering_set_solver_combinations = algorithms.ak_min_set_cover(set(solved_instance_ids),
                                                                                   [set(solved_instances[sc_id]) for
                                                                                    sc_id in solver_config_ids],
                                                                                   solver_config_ids)

            sc_by_id = dict((sc.idSolverConfig, sc) for sc in form.sc.data)

            results_params = '&'.join("solver_configs=%d" % (sc.idSolverConfig,) for sc in sota_solvers)
            results_params += '&' + '&'.join("i=%d" % (i.idInstance,) for i in form.i.data)

            unique_params = '&'.join("solver_configs=%d" % (sc.idSolverConfig,) for sc in sota_solvers)
            unique_params_by_sc = dict()
            for sc in unique_solver_contribs:
                unique_params_by_sc[sc] = unique_params + '&' + '&'.join(
                    "i=%d" % (i,) for i in unique_solver_contribs[sc])

            GET_data = "&".join(['='.join(list(t)) for t in request.args.items(multi=True)])

            return render("/analysis/sota_solvers.html", database=database, db=db, form=form,
                          instance_properties=db.get_instance_properties(), experiment=experiment,
                          sota_solvers=sota_solvers, results_params=results_params,
                          unique_solver_contribs=unique_solver_contribs,
                          unique_params_by_sc=unique_params_by_sc, ranking_data=ranking_data,
                          vbs_uses_solver_count=vbs_uses_solver_count, GET_data=GET_data,
                          sc_correlation=sc_correlation, sc_by_id=sc_by_id,
                          minimum_covering_set_solver_combinations=minimum_covering_set_solver_combinations)

        last_modified_job = db.session.query(func.max(db.ExperimentResult.date_modified)) \
            .filter_by(experiment=experiment).first()
        job_count = db.session.query(db.ExperimentResult).filter_by(experiment=experiment).count()

        return cached_sota_solvers(database, experiment_id, solver_config_ids,
                                   ''.join(sc.get_name() for sc in form.sc.data),
                                   instance_ids, job_count, last_modified_job, session.get('idUser', None))

    return render("/analysis/sota_solvers.html", database=database, db=db, form=form,
                  instance_properties=db.get_instance_properties(), experiment=experiment,
                  sota_solvers=None)


@analysis.route('/<database>/experiment/<int:experiment_id>/cactus/')
@require_phase(phases=ANALYSIS1)
@require_login
def cactus_plot(database, experiment_id):
    """ Displays a page where the user can select a set of instances and a
        result property and obtains a cactus plot of the number of instances
        solved within a given amount of the result property.

        For example: Number of instances the program can solve when given 100 seconds
        of CPU time.
    """
    db = models.get_database(database) or abort(404)
    experiment = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    form = forms.CactusPlotForm(request.args)
    form.i.query = sorted(experiment.get_instances(db), key=lambda i: i.get_name()) or EmptyQuery()
    result_properties = db.get_plotable_result_properties()
    result_properties = zip([p.idProperty for p in result_properties], [p.name for p in result_properties])
    form.result_property.choices = [('resultTime', 'CPU Time'), ('wallTime', 'Wall Clock Time'),
                                    ('cost', 'Cost')] + result_properties
    form.sc.query = experiment.solver_configurations or EmptyQuery()
    numRuns = experiment.get_max_num_runs(db)
    form.run.choices = [('all', 'All runs'),
                        ('average', 'All runs - average'),
                        ('penalized_average', 'All runs - penalized average runtime'),
                        ('median', 'All runs - median'),
                        ('random', 'Random run')] + zip(range(numRuns), ["#" + str(i) for i in range(numRuns)])

    GET_data = "&".join(['='.join(list(t)) for t in request.args.items(multi=True)])

    return render('/analysis/solved_instances.html', database=database,
                  experiment=experiment, db=db, form=form, GET_data=GET_data,
                  instance_properties=db.get_instance_properties())


@analysis.route('/<database>/experiment/<int:experiment_id>/rtd-comparison/')
@require_phase(phases=ANALYSIS2)
@require_login
def result_property_comparison(database, experiment_id):
    """
        Displays a page allowing the user to compare the result property distributions
        of two solvers on an instance. The solvers and instance can be selected
        in a form.
        The page then displays a plot with the two distributions
        aswell as statistical tests of hypothesis such as "The distribution of solver A
        is significantly different to the one of solver B".

        Statistical tests implemented:
        - Kolmogorow-Smirnow two-sample test (Distribution1 = Distribution2)
        - Mann-Whitney-U-test (Distribution1 = Distribution2 or Median1 = Median2)
    """
    db = models.get_database(database) or abort(404)
    experiment = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    form = forms.RTDComparisonForm(request.args)
    form.i.query = experiment.get_instances(db) or EmptyQuery()
    form.solver_config1.query = experiment.solver_configurations or EmptyQuery()
    form.solver_config2.query = experiment.solver_configurations or EmptyQuery()
    result_properties = db.get_plotable_result_properties()
    result_properties = zip([p.idProperty for p in result_properties], [p.name for p in result_properties])
    form.result_property.choices = [('resultTime', 'CPU Time'), ('wallTime', 'Wall Clock Time'),
                                    ('cost', 'Cost')] + result_properties
    GET_data = "&".join(['='.join(list(t)) for t in request.args.items(multi=True)])

    if form.solver_config1.data and form.solver_config2.data and form.i.data:
        instance_ids = [i.idInstance for i in form.i.data]
        #instance = db.session.query(db.Instance).filter_by(idInstance=int(request.args['instance'])).first() or abort(404)
        s1 = db.session.query(db.SolverConfiguration).get(int(request.args['solver_config1'])) or abort(404)
        s2 = db.session.query(db.SolverConfiguration).get(int(request.args['solver_config2'])) or abort(404)

        result_property = request.args.get('result_property')
        if result_property not in ('resultTime', 'wallTime', 'cost'):
            result_property = db.session.query(db.Property).get(int(result_property)).idProperty

        results1 = [r.get_property_value(result_property, db) for r in db.session.query(db.ExperimentResult)
        .filter_by(experiment=experiment,
                   solver_configuration=s1)
        .filter(db.ExperimentResult.Instances_idInstance.in_(instance_ids))
        .order_by(db.ExperimentResult.Instances_idInstance, db.ExperimentResult.run).all()]

        results2 = [r.get_property_value(result_property, db) for r in db.session.query(db.ExperimentResult)
        .filter_by(experiment=experiment,
                   solver_configuration=s2)
        .filter(db.ExperimentResult.Instances_idInstance.in_(instance_ids))
        .order_by(db.ExperimentResult.Instances_idInstance, db.ExperimentResult.run).all()]

        results1 = filter(lambda r: r is not None, results1)
        results2 = filter(lambda r: r is not None, results2)

        median1 = numpy.median(results1)
        median2 = numpy.median(results2)
        #sample_size1 = len(results1)
        #sample_size2 = len(results2)

        try:
            ks_statistic, ks_p_value = statistics.kolmogorow_smirnow_2sample_test(results1, results2)
            ks_error = None
        except Exception as e:
            ks_statistic, ks_p_value = None, None
            ks_error = str(e)

        try:
            wx_statistic, wx_p_value = statistics.wilcox_test(results1, results2)
            wx_error = None
        except Exception as e:
            wx_statistic, wx_p_value = None, None
            wx_error = str(e)

        return render('/analysis/result_property_comparison.html', database=database,
                      experiment=experiment, db=db, form=form, GET_data=GET_data,
                      ks_statistic=ks_statistic, ks_p_value=ks_p_value,
                      wx_statistic=wx_statistic, wx_p_value=wx_p_value,
                      wx_error=wx_error, ks_error=ks_error, median1=median1, median2=median2,
                      instance_properties=db.get_instance_properties())

    return render('/analysis/result_property_comparison.html', database=database,
                  experiment=experiment, db=db, form=form, GET_data=GET_data,
                  instance_properties=db.get_instance_properties())


@analysis.route('/<database>/experiment/<int:experiment_id>/property-distributions/')
@require_phase(phases=ANALYSIS2)
@require_login
def property_distributions(database, experiment_id):
    """
        Displays a page allowing the user to choose several solver configurations
        and an instance and displays a plot with the runtime distributions (as
        cumulative empirical distribution functions) of the solvers on the
        chosen instance.
    """
    db = models.get_database(database) or abort(404)
    experiment = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    form = forms.RTDPlotsForm(request.args)
    form.instance.query = experiment.get_instances(db) or EmptyQuery()
    form.sc.query = experiment.solver_configurations or EmptyQuery()
    result_properties = db.get_plotable_result_properties()
    result_properties = zip([p.idProperty for p in result_properties], [p.name for p in result_properties])
    form.result_property.choices = [('resultTime', 'CPU Time'), ('wallTime', 'Wall Clock Time'),
                                    ('cost', 'Cost')] + result_properties

    GET_data = "&".join(['='.join(list(t)) for t in request.args.items(multi=True)])

    return render('/analysis/property_distributions.html', database=database,
                  experiment=experiment, db=db, form=form, GET_data=GET_data,
                  instance_properties=db.get_instance_properties())


@analysis.route('/<database>/experiment/<int:experiment_id>/scatter-two-solvers/')
@require_phase(phases=ANALYSIS2)
@require_login
def scatter_2solver_1property(database, experiment_id):
    """
        Displays a page allowing the user to plot the results of two solvers
        on the instances against each other in a scatter plot.
    """
    db = models.get_database(database) or abort(404)
    experiment = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    result_properties = db.get_plotable_result_properties()
    result_properties = zip([p.idProperty for p in result_properties], [p.name for p in result_properties])
    numRuns = experiment.get_max_num_runs(db)
    runs = zip(range(numRuns), ["#" + str(i) for i in range(numRuns)])

    form = forms.TwoSolversOnePropertyScatterPlotForm(request.args)
    form.solver_config1.query = experiment.solver_configurations or EmptyQuery()
    form.solver_config2.query = experiment.solver_configurations or EmptyQuery()
    form.i.query = sorted(experiment.get_instances(db), key=lambda i: i.get_name()) or EmptyQuery()
    form.run.choices = [('average', 'All runs - average'),
                        ('median', 'All runs - median'),
                        ('all', 'All runs')
                       ] + runs
    form.result_property.choices = [('resultTime', 'CPU Time'), ('wallTime', 'Wall Clock Time'),
                                    ('cost', 'Cost')] + result_properties

    GET_data = "&".join(['='.join(list(t)) for t in request.args.items(multi=True)])

    spearman_r, spearman_p_value = None, None
    pearson_r, pearson_p_value = None, None
    if form.solver_config1.data and form.solver_config2.data:
        points = plot.scatter_2solver_1property_points(db, experiment,
                                                       form.solver_config1.data, form.solver_config2.data,
                                                       form.i.data, form.result_property.data, form.run.data)

        # log transform data if axis scaling is enabled, only affects pearson's coeff.
        if form.xscale.data == 'log':
            points = map(lambda p: (math.log(p[0]) if p[0] != 0 else 0, p[1]), points)
        if form.yscale.data == 'log':
            points = map(lambda p: (p[0], math.log(p[1]) if p[1] != 0 else 0), points)

        spearman_r, spearman_p_value = statistics.spearman_correlation([p[0] for p in points], [p[1] for p in points])
        pearson_r, pearson_p_value = statistics.pearson_correlation([p[0] for p in points], [p[1] for p in points])

        if request.args.has_key('ajax_correlation'):
            # this request was an ajax call from the form, return correlation data in JSON
            return jsonify({'spearman_r': spearman_r, 'spearman_p_value': spearman_p_value,
                            'pearson_r': pearson_r, 'pearson_p_value': pearson_p_value})

    return render('/analysis/scatter_2solver_1property.html', database=database,
                  experiment=experiment, db=db, form=form, GET_data=GET_data,
                  spearman_r=spearman_r, spearman_p_value=spearman_p_value,
                  pearson_r=pearson_r, pearson_p_value=pearson_p_value,
                  instance_properties=db.get_instance_properties())


@analysis.route('/<database>/experiment/<int:experiment_id>/scatter-instance-vs-result/')
@require_phase(phases=ANALYSIS2)
@require_login
def scatter_1solver_instance_vs_result_property(database, experiment_id):
    """
        Displays a page allowing the user to plot a result property against
        an instance property of one solver's results on instances in a scatter
        plot.
        For example: Number of Atoms in the instance against CPU time needed
    """
    db = models.get_database(database) or abort(404)
    experiment = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    result_properties = db.get_plotable_result_properties()
    result_properties = zip([p.idProperty for p in result_properties], [p.name for p in result_properties])
    instance_properties = db.get_plotable_instance_properties()
    instance_properties = zip([p.idProperty for p in instance_properties], [p.name for p in instance_properties])
    numRuns = experiment.get_max_num_runs(db)
    runs = zip(range(numRuns), ["#" + str(i) for i in range(numRuns)])

    form = forms.OneSolverInstanceAgainstResultPropertyPlotForm(request.args)
    form.solver_config.query = experiment.solver_configurations or EmptyQuery()
    form.result_property.choices = [('resultTime', 'CPU Time'), ('wallTime', 'Wall Clock Time'),
                                    ('cost', 'Cost')] + result_properties
    form.instance_property.choices = instance_properties
    form.i.query = sorted(experiment.get_instances(db), key=lambda i: i.get_name()) or EmptyQuery()
    form.run.choices = [('average', 'All runs - average'),
                        ('median', 'All runs - median'),
                        ('all', 'All runs')
                       ] + runs

    GET_data = "&".join(['='.join(list(t)) for t in request.args.items(multi=True)])
    spearman_r, spearman_p_value = None, None
    pearson_r, pearson_p_value = None, None
    if form.solver_config.data and form.instance_property.data:
        points = plot.scatter_1solver_instance_vs_result_property_points(db, experiment,
                                                                         form.solver_config.data, form.i.data,
                                                                         form.instance_property.data,
                                                                         form.result_property.data,
                                                                         form.run.data)

        # log transform data if axis scaling is enabled, only affects pearson's coeff.
        if form.xscale.data == 'log':
            points = map(lambda p: (math.log(p[0]) if p[0] != 0 else 0, p[1]), points)
        if form.yscale.data == 'log':
            points = map(lambda p: (p[0], math.log(p[1]) if p[1] != 0 else 0), points)

        spearman_r, spearman_p_value = statistics.spearman_correlation([p[0] for p in points], [p[1] for p in points])
        pearson_r, pearson_p_value = statistics.pearson_correlation([p[0] for p in points], [p[1] for p in points])

        if request.args.has_key('ajax_correlation'):
            # this request was an ajax call from the form, return correlation data in JSON
            return jsonify({'spearman_r': spearman_r, 'spearman_p_value': spearman_p_value,
                            'pearson_r': pearson_r, 'pearson_p_value': pearson_p_value})

    return render('/analysis/scatter_solver_instance_vs_result.html', database=database,
                  experiment=experiment, db=db, form=form, GET_data=GET_data,
                  spearman_r=spearman_r, spearman_p_value=spearman_p_value,
                  pearson_r=pearson_r, pearson_p_value=pearson_p_value,
                  instance_properties=db.get_instance_properties())


@analysis.route('/<database>/experiment/<int:experiment_id>/scatter-result-vs-result/')
@require_phase(phases=ANALYSIS2)
@require_login
def scatter_1solver_result_vs_result_property(database, experiment_id):
    """
        Displays a page allowing the user to plot two result properties of one
        solver's results on instances in a scatter plot.
        For example: CPU time vs. Memory used
    """
    db = models.get_database(database) or abort(404)
    experiment = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    result_properties = db.get_plotable_result_properties()
    result_properties = zip([p.idProperty for p in result_properties], [p.name for p in result_properties])
    numRuns = experiment.get_max_num_runs(db)
    runs = zip(range(numRuns), ["#" + str(i) for i in range(numRuns)])

    form = forms.OneSolverTwoResultPropertiesPlotForm(request.args)
    form.solver_config.query = experiment.solver_configurations or EmptyQuery()
    form.result_property1.choices = [('resultTime', 'CPU Time'), ('wallTime', 'Wall Clock Time'),
                                     ('cost', 'Cost')] + result_properties
    form.result_property2.choices = [('resultTime', 'CPU Time'), ('wallTime', 'Wall Clock Time'),
                                     ('cost', 'Cost')] + result_properties
    form.i.query = sorted(experiment.get_instances(db), key=lambda i: i.get_name()) or EmptyQuery()
    form.run.choices = [('average', 'All runs - average'),
                        ('median', 'All runs - median'),
                        ('all', 'All runs')
                       ] + runs

    GET_data = "&".join(['='.join(list(t)) for t in request.args.items(multi=True)])
    spearman_r, spearman_p_value = None, None
    pearson_r, pearson_p_value = None, None
    if form.solver_config.data:
        points = plot.scatter_1solver_result_vs_result_property_plot(db, experiment,
                                                                     form.solver_config.data, form.i.data,
                                                                     form.result_property1.data,
                                                                     form.result_property2.data, form.run.data)

        # log transform data if axis scaling is enabled, only affects pearson's coeff.
        if form.xscale.data == 'log':
            points = map(lambda p: (math.log(p[0]) if p[0] != 0 else 0, p[1]), points)
        if form.yscale.data == 'log':
            points = map(lambda p: (p[0], math.log(p[1]) if p[1] != 0 else 0), points)

        spearman_r, spearman_p_value = statistics.spearman_correlation([p[0] for p in points], [p[1] for p in points])
        pearson_r, pearson_p_value = statistics.pearson_correlation([p[0] for p in points], [p[1] for p in points])

        if request.args.has_key('ajax_correlation'):
            # this request was an ajax call from the form, return correlation data in JSON
            return jsonify({'spearman_r': spearman_r, 'spearman_p_value': spearman_p_value,
                            'pearson_r': pearson_r, 'pearson_p_value': pearson_p_value})

    return render('/analysis/scatter_solver_result_vs_result.html', database=database,
                  experiment=experiment, db=db, form=form, GET_data=GET_data,
                  spearman_r=spearman_r, spearman_p_value=spearman_p_value,
                  pearson_r=pearson_r, pearson_p_value=pearson_p_value,
                  instance_properties=db.get_instance_properties())


@analysis.route('/<database>/experiment/<int:experiment_id>/property-distribution/')
@require_phase(phases=ANALYSIS2)
@require_login
def property_distribution(database, experiment_id):
    """
        Displays a page with plots of the runtime distribution (as CDF) and
        the kernel density estimation of a chosen solver on a chosen instance.
    """
    db = models.get_database(database) or abort(404)
    experiment = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    form = forms.RTDPlotForm(request.args)
    form.i.query = sorted(experiment.get_instances(db), key=lambda i: i.get_name()) or EmptyQuery()
    form.sc.query = experiment.solver_configurations or EmptyQuery()
    result_properties = db.get_plotable_result_properties()
    result_properties = zip([p.idProperty for p in result_properties], [p.name for p in result_properties])
    form.result_property.choices = [('resultTime', 'CPU Time'), ('wallTime', 'Wall Clock Time'),
                                    ('cost', 'Cost')] + result_properties
    GET_data = "&".join(['='.join(list(t)) for t in request.args.items(multi=True)])

    return render('/analysis/property_distribution.html', database=database, experiment=experiment,
                  db=db, form=form, GET_data=GET_data,
                  instance_properties=db.get_instance_properties())


@analysis.route('/<database>/experiment/<int:experiment_id>/probabilistic-domination/')
@require_phase(phases=ANALYSIS2)
@require_login
def probabilistic_domination(database, experiment_id):
    """
        Displays a page allowing the user to choose two solver configurations and
        categorizing the instances of the experiment into three groups:
        - Instances where solver A prob. dominates solver B.
        - Instances where solver B prob. dominates solver A.
        - Instances with crossovers in the RTD's CDF
        See edacc.statistics for a definition of probabilistic domination
    """
    db = models.get_database(database) or abort(404)
    experiment = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    form = forms.ProbabilisticDominationForm(request.args)
    form.solver_config1.query = experiment.solver_configurations or EmptyQuery()
    form.solver_config2.query = experiment.solver_configurations or EmptyQuery()
    form.i.query = sorted(experiment.get_instances(db), key=lambda i: i.get_name()) or EmptyQuery()
    result_properties = db.get_plotable_result_properties() # plotable = numeric
    result_properties = zip([p.idProperty for p in result_properties], [p.name for p in result_properties])
    form.result_property.choices = [('resultTime', 'CPU Time'), ('wallTime', 'Wall Clock Time'),
                                    ('cost', 'Cost')] + result_properties

    if form.solver_config1.data and form.solver_config2.data:
        instances = db.session.query(db.Instance).filter(
            db.Instance.idInstance.in_(map(int, request.args.getlist('i')))).all()
        instance_ids = [i.idInstance for i in instances]
        sc1 = form.solver_config1.data
        sc2 = form.solver_config2.data

        query = db.session.query(db.ExperimentResult)
        query = query.enable_eagerloads(True).options(joinedload(db.ExperimentResult.properties))

        sc1_results_by_instance_id = {}
        sc2_results_by_instance_id = {}
        for r in query.filter_by(experiment=experiment, solver_configuration=sc1).filter(
                db.ExperimentResult.Instances_idInstance.in_(instance_ids)).all():
            if r.Instances_idInstance in sc1_results_by_instance_id:
                sc1_results_by_instance_id[r.Instances_idInstance].append(r)
            else:
                sc1_results_by_instance_id[r.Instances_idInstance] = [r]

        for r in query.filter_by(experiment=experiment, solver_configuration=sc2).filter(
                db.ExperimentResult.Instances_idInstance.in_(instance_ids)).all():
            if r.Instances_idInstance in sc2_results_by_instance_id:
                sc2_results_by_instance_id[r.Instances_idInstance].append(r)
            else:
                sc2_results_by_instance_id[r.Instances_idInstance] = [r]

        sc1_dom_sc2 = []
        sc2_dom_sc1 = []
        no_dom = []

        for instance in instances:
            if instance.idInstance not in sc1_results_by_instance_id: continue
            if instance.idInstance not in sc2_results_by_instance_id: continue
            res1 = [r.get_property_value(form.result_property.data, db) for r in
                    sc1_results_by_instance_id[instance.idInstance]]
            res2 = [r.get_property_value(form.result_property.data, db) for r in
                    sc2_results_by_instance_id[instance.idInstance]]
            res1 = filter(lambda r: r is not None, res1)
            res2 = filter(lambda r: r is not None, res2)
            if len(res1) > 0 and len(res2) > 0:
                d = statistics.prob_domination(res1, res2)
                if d == 1:
                    sc1_dom_sc2.append(instance)
                elif d == -1:
                    sc2_dom_sc1.append(instance)
                else:
                    no_dom.append(instance)

        num_total = max(max(len(sc1_dom_sc2), len(sc2_dom_sc1)), len(no_dom))

        return render('/analysis/probabilistic_domination.html',
                      database=database, db=db, experiment=experiment,
                      form=form, sc1_dom_sc2=sc1_dom_sc2, sc2_dom_sc1=sc2_dom_sc1,
                      no_dom=no_dom, instance_properties=db.get_instance_properties(),
                      num_total=num_total)

    return render('/analysis/probabilistic_domination.html', database=database, db=db,
                  experiment=experiment, form=form, instance_properties=db.get_instance_properties())


@analysis.route('/<database>/experiment/<int:experiment_id>/box-plots/')
@require_phase(phases=ANALYSIS2)
@require_login
def box_plots(database, experiment_id):
    """ Displays a page allowing the user to plot box plots with the results of all runs
        of some solvers on some instances
    """
    db = models.get_database(database) or abort(404)
    experiment = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    form = forms.BoxPlotForm(request.args)
    form.solver_configs.query = experiment.solver_configurations or EmptyQuery()
    form.i.query = sorted(experiment.get_instances(db), key=lambda i: i.get_name()) or EmptyQuery()
    result_properties = db.get_plotable_result_properties()
    result_properties = zip([p.idProperty for p in result_properties], [p.name for p in result_properties])
    form.result_property.choices = [('resultTime', 'CPU Time'), ('wallTime', 'Wall Clock Time'),
                                    ('cost', 'Cost')] + result_properties
    GET_data = "&".join(['='.join(list(t)) for t in request.args.items(multi=True)])

    return render('/analysis/box_plots.html', database=database, db=db,
                  experiment=experiment, form=form, GET_data=GET_data,
                  instance_properties=db.get_instance_properties())


@analysis.route('/<database>/experiment/<int:experiment_id>/runtime-matrix-plot/')
@require_phase(phases=ANALYSIS2)
@require_login
def runtime_matrix_plot(database, experiment_id):
    db = models.get_database(database) or abort(404)
    experiment = db.session.query(db.Experiment).get(experiment_id) or abort(404)

    form = forms.RuntimeMatrixPlotForm(request.args)
    result_properties = db.get_plotable_result_properties()
    result_properties = zip([p.idProperty for p in result_properties], [p.name for p in result_properties])
    form.result_property.choices = [('resultTime', 'CPU Time'), ('wallTime', 'Wall Clock Time'),
                                    ('cost', 'Cost')] + result_properties
    GET_data = "&".join(['='.join(list(t)) for t in request.args.items(multi=True)])
    if request.args.get('measure') is None: GET_data += "&measure=par10"

    return render('/analysis/runtime_matrix_plot.html', database=database, db=db,
                  experiment=experiment, form=form, GET_data=GET_data)


@analysis.route('/<database>/experiment/<int:experiment_id>/parameter-plot-1d/')
@require_phase(phases=ANALYSIS2)
@require_login
def parameter_plot_1d(database, experiment_id):
    db = models.get_database(database) or abort(404)
    experiment = db.session.query(db.Experiment).get(experiment_id) or abort(404)
    if not experiment.configurationExp: abort(404)

    cs_params = [param for param in experiment.configuration_scenario.parameters if param.configurable and \
                                                                                    experiment.configuration_scenario.get_parameter_domain(
                                                                                        param.parameter.name) in (
                                                                                    'realDomain', 'integerDomain',
                                                                                    'ordinalDomain',
                                                                                    'categoricalDomain')]

    form = forms.ParameterPlot1DForm(request.args)
    form.parameter.choices = [(p.parameter.idParameter, p.parameter.name) for p in cs_params]
    form.i.query = sorted(experiment.get_instances(db), key=lambda i: i.get_name()) or EmptyQuery()
    GET_data = "&".join(['='.join(list(t)) for t in request.args.items(multi=True)])

    max_runtime = None
    if form.i.data:
        instance_ids = [i.idInstance for i in form.i.data]
        table = db.metadata.tables['ExperimentResults']
        table_sc = db.metadata.tables['SolverConfig']
        if form.measure.data == 'par10':
            to_expr = (experiment.costPenalty if experiment.defaultCost == 'cost' else table.c['CPUTimeLimit'] if experiment.defaultCost == 'resultTime' else table.c['wallClockTimeLimit'])
            time_case = expression.case([
                                            (table.c['resultCode'].like(u'1%'), table.c[experiment.defaultCost])],
                                        else_=to_expr * 10.0)
        else:
            time_case = table.c[experiment.defaultCost]

        s = select([func.max(time_case)],
                   and_(table.c['Experiment_idExperiment'] == experiment_id,
                        table_sc.c[
                            'SolverBinaries_idSolverBinary'] == experiment.configuration_scenario.SolverBinaries_idSolverBinary,
                        not_(table.c['status'].in_((-1, 0,))),
                        table.c['Instances_idInstance'].in_(instance_ids)
                   ), from_obj=table.join(table_sc))
        max_runtime = db.session.connection().execute(s).fetchone()[0] or 0.0

    return render('/analysis/parameter_plot_1d.html', database=database, db=db, max_runtime=max_runtime,
                  experiment=experiment, form=form, GET_data=GET_data)


@analysis.route('/<database>/experiment/<int:experiment_id>/parameter-plot-2d/')
@require_phase(phases=ANALYSIS2)
@require_login
def parameter_plot_2d(database, experiment_id):
    db = models.get_database(database) or abort(404)
    experiment = db.session.query(db.Experiment).get(experiment_id) or abort(404)
    if not experiment.configurationExp: abort(404)

    cs_params = [param for param in experiment.configuration_scenario.parameters if param.configurable and \
                                                                                    experiment.configuration_scenario.get_parameter_domain(
                                                                                        param.parameter.name) in (
                                                                                    'realDomain', 'integerDomain',
                                                                                    'ordinalDomain',
                                                                                    'categoricalDomain')]

    form = forms.ParameterPlot2DForm(request.args)
    form.parameter1.choices = [(p.parameter.idParameter, p.parameter.name) for p in cs_params]
    form.parameter2.choices = reversed([(p.parameter.idParameter, p.parameter.name) for p in cs_params])
    form.i.query = sorted(experiment.get_instances(db), key=lambda i: i.get_name()) or EmptyQuery()

    table = db.metadata.tables['ExperimentResults']
    to_expr = (experiment.costPenalty if experiment.defaultCost == 'cost' else table.c['CPUTimeLimit'] if experiment.defaultCost == 'resultTime' else table.c['wallClockTimeLimit'])
    time_case = expression.case([
                                    (table.c['resultCode'].like(u'1%'), table.c[experiment.defaultCost])],
                                else_=to_expr * 10.0)

    s = select([table.c['Instances_idInstance'], func.AVG(time_case)],
               and_(
                   table.c['Experiment_idExperiment'] == experiment_id,
               ),
               from_obj=table).group_by(table.c['Instances_idInstance'])
    instance_avg = db.session.connection().execute(s)

    avg_by_instance = dict((instance.idInstance, 0) for instance in experiment.get_instances(db))
    for avg in instance_avg:
        avg_by_instance[avg[0]] = avg[1]

    form.i.query.sort(key=lambda i: avg_by_instance[i.idInstance])

    GET_data = "&".join(['='.join(list(t)) for t in request.args.items(multi=True)])

    max_runtime = None
    if form.i.data:
        instance_ids = [i.idInstance for i in form.i.data]
        table = db.metadata.tables['ExperimentResults']
        table_sc = db.metadata.tables['SolverConfig']
        if form.measure.data == 'par10':
            time_case = expression.case([
                                            (table.c['resultCode'].like(u'1%'), table.c[experiment.defaultCost])],
                                        else_=to_expr * 10.0)
        else:
            time_case = table.c[experiment.defaultCost]

        s = select([func.max(time_case)],
                   and_(table.c['Experiment_idExperiment'] == experiment_id,
                        table_sc.c[
                            'SolverBinaries_idSolverBinary'] == experiment.configuration_scenario.SolverBinaries_idSolverBinary,
                        not_(table.c['status'].in_((-1, 0,))),
                        table.c['Instances_idInstance'].in_(instance_ids)
                   ), from_obj=table.join(table_sc))
        max_runtime = db.session.connection().execute(s).fetchone()[0] or 0.0

    return render('/analysis/parameter_plot_2d.html', database=database, db=db, max_runtime=max_runtime,
                  experiment=experiment, form=form, GET_data=GET_data)
