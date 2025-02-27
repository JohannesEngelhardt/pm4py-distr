from threading import Thread
from pm4pydistr import configuration
from flask import Flask, request, jsonify
from flask_cors import CORS
from pm4pydistr.slave.variable_container import SlaveVariableContainer
from pm4pydistr.configuration import PARAMETER_USE_TRANSITION, DEFAULT_USE_TRANSITION
from pm4pydistr.configuration import PARAMETER_NO_SAMPLES, DEFAULT_MAX_NO_SAMPLES
from pm4py.util import constants as pm4py_constants
from pm4py.objects.log.util import xes
from pm4py.objects.log.importer.parquet import factory as parquet_importer
from pm4py.objects.log.exporter.parquet import factory as parquet_exporter
from pm4py.objects.log.importer.xes import factory as xes_importer
from pm4pydistr.configuration import PARAMETER_NUM_RET_ITEMS, DEFAULT_MAX_NO_RET_ITEMS

from pm4py.objects.log.log import EventLog, Trace, Event
from pm4pypred.algo.prediction import factory as prediction_factory
from pm4py.objects.log.util import dataframe_utils
from pm4py.objects.conversion.log import factory as conversion_factory
import pickle

from pm4pydistr.log_handlers import parquet as parquet_handler

import os
import json
import sys
import statistics


import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

class SlaveSocketListener(Thread):
    app = Flask(__name__)
    CORS(app)

    def __init__(self, slave, host, port, master_host, master_port, conf):
        SlaveVariableContainer.slave = slave
        SlaveVariableContainer.host = host
        SlaveVariableContainer.port = port
        SlaveVariableContainer.master_host = master_host
        SlaveVariableContainer.master_port = master_port
        SlaveVariableContainer.conf = conf

        Thread.__init__(self)

    def run(self):
        self.app.run(host="0.0.0.0", port=SlaveVariableContainer.port, threaded=True)


@SlaveSocketListener.app.route("/synchronizeFiles", methods=["POST"])
def synchronize_files():
    keyphrase = request.args.get('keyphrase', type=str)
    if keyphrase == configuration.KEYPHRASE:
        try:
            json_content = json.loads(request.data)
        except:
            json_content = json.loads(request.data.decode('utf-8'))
        for log_folder in json_content["logs"]:
            SlaveVariableContainer.managed_logs[log_folder] = None
            SlaveVariableContainer.managed_logs[log_folder] = []

            if log_folder not in os.listdir(SlaveVariableContainer.conf):
                SlaveVariableContainer.slave.create_folder(log_folder)
            for log_name in json_content["logs"][log_folder]:
                SlaveVariableContainer.slave.load_log(log_folder, log_name)
                SlaveVariableContainer.managed_logs[log_folder].append(log_name)
    return jsonify({})


@SlaveSocketListener.app.route("/setFilters", methods=["POST"])
def set_filters():
    process = request.args.get('process', type=str)
    keyphrase = request.args.get('keyphrase', type=str)
    session = request.args.get('session', type=str)

    if keyphrase == configuration.KEYPHRASE:
        if not session in SlaveVariableContainer.slave.filters:
            SlaveVariableContainer.slave.filters[session] = {}
        try:
            SlaveVariableContainer.slave.filters[session][process] = eval(json.loads(request.data)["filters"])
        except:
            SlaveVariableContainer.slave.filters[session][process] = eval(json.loads(request.data.decode('utf-8'))["filters"])
    return jsonify({})

def get_filters_per_session(process, session):
    if session in SlaveVariableContainer.slave.filters:
        if process in SlaveVariableContainer.slave.filters[session]:
            return SlaveVariableContainer.slave.filters[session][process]
    return []

@SlaveSocketListener.app.route("/calculateDfg", methods=["GET"])
def calculate_dfg():
    process = request.args.get('process', type=str)
    keyphrase = request.args.get('keyphrase', type=str)
    session = request.args.get('session', type=str)
    attribute_key = request.args.get('attribute_key', type=str, default=xes.DEFAULT_NAME_KEY)

    use_transition = request.args.get(PARAMETER_USE_TRANSITION, type=str, default=str(DEFAULT_USE_TRANSITION))
    no_samples = request.args.get(PARAMETER_NO_SAMPLES, type=int, default=DEFAULT_MAX_NO_SAMPLES)

    if use_transition == "True":
        use_transition = True
    else:
        use_transition = False

    if keyphrase == configuration.KEYPHRASE:
        filters = get_filters_per_session(process, session)
        parameters = {}
        parameters["filters"] = filters
        parameters[PARAMETER_USE_TRANSITION] = use_transition
        parameters[PARAMETER_NO_SAMPLES] = no_samples
        parameters[pm4py_constants.PARAMETER_CONSTANT_ATTRIBUTE_KEY] = attribute_key

        returned_dict = parquet_handler.calculate_dfg(SlaveVariableContainer.conf, process, SlaveVariableContainer.managed_logs[process], parameters=parameters)

        return jsonify({"dfg": returned_dict})
    return jsonify({"dfg": {}})


@SlaveSocketListener.app.route("/calculatePerformanceDfg", methods=["GET"])
def calculate_performance_dfg():
    process = request.args.get('process', type=str)
    keyphrase = request.args.get('keyphrase', type=str)
    session = request.args.get('session', type=str)
    attribute_key = request.args.get('attribute_key', type=str, default=xes.DEFAULT_NAME_KEY)

    use_transition = request.args.get(PARAMETER_USE_TRANSITION, type=str, default=str(DEFAULT_USE_TRANSITION))
    no_samples = request.args.get(PARAMETER_NO_SAMPLES, type=int, default=DEFAULT_MAX_NO_SAMPLES)

    if use_transition == "True":
        use_transition = True
    else:
        use_transition = False

    if keyphrase == configuration.KEYPHRASE:
        filters = get_filters_per_session(process, session)
        parameters = {}
        parameters["filters"] = filters
        parameters[PARAMETER_USE_TRANSITION] = use_transition
        parameters[PARAMETER_NO_SAMPLES] = no_samples
        parameters[pm4py_constants.PARAMETER_CONSTANT_ATTRIBUTE_KEY] = attribute_key

        returned_dict = parquet_handler.calculate_performance_dfg(SlaveVariableContainer.conf, process, SlaveVariableContainer.managed_logs[process], parameters=parameters)

        return jsonify({"dfg": returned_dict})
    return jsonify({"dfg": {}})


@SlaveSocketListener.app.route("/calculateCompositeObj", methods=["GET"])
def calculate_composite_obj():
    process = request.args.get('process', type=str)
    keyphrase = request.args.get('keyphrase', type=str)
    session = request.args.get('session', type=str)
    attribute_key = request.args.get('attribute_key', type=str, default=xes.DEFAULT_NAME_KEY)
    performance_required = request.args.get('performance_required', type=str, default="False")
    if performance_required == "True":
        performance_required = True
    else:
        performance_required = False

    use_transition = request.args.get(PARAMETER_USE_TRANSITION, type=str, default=str(DEFAULT_USE_TRANSITION))
    no_samples = request.args.get(PARAMETER_NO_SAMPLES, type=int, default=DEFAULT_MAX_NO_SAMPLES)

    if use_transition == "True":
        use_transition = True
    else:
        use_transition = False

    if keyphrase == configuration.KEYPHRASE:
        filters = get_filters_per_session(process, session)
        parameters = {}
        parameters["filters"] = filters
        parameters[PARAMETER_USE_TRANSITION] = use_transition
        parameters[PARAMETER_NO_SAMPLES] = no_samples
        parameters[pm4py_constants.PARAMETER_CONSTANT_ATTRIBUTE_KEY] = attribute_key
        parameters["performance_required"] = performance_required

        returned_dict = parquet_handler.calculate_process_schema_composite_object(SlaveVariableContainer.conf, process, SlaveVariableContainer.managed_logs[process], parameters=parameters)

        return jsonify({"obj": returned_dict})
    return jsonify({"obj": {}})


@SlaveSocketListener.app.route("/getEndActivities", methods=["GET"])
def calculate_end_activities():
    process = request.args.get('process', type=str)
    keyphrase = request.args.get('keyphrase', type=str)
    session = request.args.get('session', type=str)
    use_transition = request.args.get(PARAMETER_USE_TRANSITION, type=str, default=str(DEFAULT_USE_TRANSITION))
    no_samples = request.args.get(PARAMETER_NO_SAMPLES, type=int, default=DEFAULT_MAX_NO_SAMPLES)

    if use_transition == "True":
        use_transition = True
    else:
        use_transition = False

    if keyphrase == configuration.KEYPHRASE:
        filters = get_filters_per_session(process, session)
        parameters = {}
        parameters["filters"] = filters
        parameters[PARAMETER_USE_TRANSITION] = use_transition
        parameters[PARAMETER_NO_SAMPLES] = no_samples

        returned_dict = parquet_handler.get_end_activities(SlaveVariableContainer.conf, process, SlaveVariableContainer.managed_logs[process], parameters=parameters)

        return jsonify({"end_activities": returned_dict})
    return jsonify({"end_activities": {}})


@SlaveSocketListener.app.route("/getStartActivities", methods=["GET"])
def calculate_start_activities():
    process = request.args.get('process', type=str)
    keyphrase = request.args.get('keyphrase', type=str)
    session = request.args.get('session', type=str)
    use_transition = request.args.get(PARAMETER_USE_TRANSITION, type=str, default=str(DEFAULT_USE_TRANSITION))
    no_samples = request.args.get(PARAMETER_NO_SAMPLES, type=int, default=DEFAULT_MAX_NO_SAMPLES)

    if use_transition == "True":
        use_transition = True
    else:
        use_transition = False

    if keyphrase == configuration.KEYPHRASE:
        filters = get_filters_per_session(process, session)
        parameters = {}
        parameters["filters"] = filters
        parameters[PARAMETER_USE_TRANSITION] = use_transition
        parameters[PARAMETER_NO_SAMPLES] = no_samples

        returned_dict = parquet_handler.get_start_activities(SlaveVariableContainer.conf, process, SlaveVariableContainer.managed_logs[process], parameters=parameters)

        return jsonify({"start_activities": returned_dict})
    return jsonify({"start_activities": {}})


@SlaveSocketListener.app.route("/getAttributeValues", methods=["GET"])
def calculate_attribute_values():
    process = request.args.get('process', type=str)
    keyphrase = request.args.get('keyphrase', type=str)
    session = request.args.get('session', type=str)
    attribute_key = request.args.get('attribute_key', type=str, default=xes.DEFAULT_NAME_KEY)

    use_transition = request.args.get(PARAMETER_USE_TRANSITION, type=str, default=str(DEFAULT_USE_TRANSITION))
    no_samples = request.args.get(PARAMETER_NO_SAMPLES, type=int, default=DEFAULT_MAX_NO_SAMPLES)

    if use_transition == "True":
        use_transition = True
    else:
        use_transition = False

    if keyphrase == configuration.KEYPHRASE:
        filters = get_filters_per_session(process, session)
        parameters = {}
        parameters["filters"] = filters
        parameters[PARAMETER_USE_TRANSITION] = use_transition
        parameters[PARAMETER_NO_SAMPLES] = no_samples
        parameters[pm4py_constants.PARAMETER_CONSTANT_ATTRIBUTE_KEY] = attribute_key

        returned_dict = parquet_handler.get_attribute_values(SlaveVariableContainer.conf, process, SlaveVariableContainer.managed_logs[process], parameters=parameters)

        return jsonify({"values": returned_dict})
    return jsonify({"values": {}})


@SlaveSocketListener.app.route("/getAttributesNames", methods=["GET"])
def calculate_attribute_names():
    process = request.args.get('process', type=str)
    keyphrase = request.args.get('keyphrase', type=str)
    session = request.args.get('session', type=str)

    use_transition = request.args.get(PARAMETER_USE_TRANSITION, type=str, default=str(DEFAULT_USE_TRANSITION))
    no_samples = request.args.get(PARAMETER_NO_SAMPLES, type=int, default=DEFAULT_MAX_NO_SAMPLES)

    if use_transition == "True":
        use_transition = True
    else:
        use_transition = False

    if keyphrase == configuration.KEYPHRASE:
        filters = get_filters_per_session(process, session)
        parameters = {}
        parameters["filters"] = filters
        parameters[PARAMETER_USE_TRANSITION] = use_transition
        parameters[PARAMETER_NO_SAMPLES] = no_samples

        returned_list = parquet_handler.get_attribute_names(SlaveVariableContainer.conf, process, SlaveVariableContainer.managed_logs[process], parameters=parameters)

        return jsonify({"names": returned_list})
    return jsonify({"names": {}})


@SlaveSocketListener.app.route("/getLogSummary", methods=["GET"])
def calculate_log_summary():
    process = request.args.get('process', type=str)
    keyphrase = request.args.get('keyphrase', type=str)
    session = request.args.get('session', type=str)

    use_transition = request.args.get(PARAMETER_USE_TRANSITION, type=str, default=str(DEFAULT_USE_TRANSITION))
    no_samples = request.args.get(PARAMETER_NO_SAMPLES, type=int, default=DEFAULT_MAX_NO_SAMPLES)

    if use_transition == "True":
        use_transition = True
    else:
        use_transition = False

    if keyphrase == configuration.KEYPHRASE:
        filters = get_filters_per_session(process, session)
        parameters = {}
        parameters["filters"] = filters
        parameters[PARAMETER_USE_TRANSITION] = use_transition
        parameters[PARAMETER_NO_SAMPLES] = no_samples

        summary = parquet_handler.get_log_summary(SlaveVariableContainer.conf, process, SlaveVariableContainer.managed_logs[process], parameters=parameters)

        return jsonify({"summary": summary})
    return jsonify({"summary": {}})


@SlaveSocketListener.app.route("/getVariants", methods=["GET"])
def get_variants():
    process = request.args.get('process', type=str)
    keyphrase = request.args.get('keyphrase', type=str)
    session = request.args.get('session', type=str)

    use_transition = request.args.get(PARAMETER_USE_TRANSITION, type=str, default=str(DEFAULT_USE_TRANSITION))
    no_samples = request.args.get(PARAMETER_NO_SAMPLES, type=int, default=DEFAULT_MAX_NO_SAMPLES)
    max_no_ret_items = request.args.get(PARAMETER_NUM_RET_ITEMS, type=int, default=DEFAULT_MAX_NO_RET_ITEMS)

    if use_transition == "True":
        use_transition = True
    else:
        use_transition = False

    if keyphrase == configuration.KEYPHRASE:
        filters = get_filters_per_session(process, session)
        parameters = {}
        parameters["filters"] = filters
        parameters[PARAMETER_USE_TRANSITION] = use_transition
        parameters[PARAMETER_NO_SAMPLES] = no_samples
        parameters[PARAMETER_NUM_RET_ITEMS] = max_no_ret_items

        returned_dict = parquet_handler.get_variants(SlaveVariableContainer.conf, process, SlaveVariableContainer.managed_logs[process], parameters=parameters)

        return jsonify(returned_dict)
    return jsonify({"variants": [], "events": 0, "cases": 0})


@SlaveSocketListener.app.route("/getCases", methods=["GET"])
def get_cases():
    process = request.args.get('process', type=str)
    keyphrase = request.args.get('keyphrase', type=str)
    session = request.args.get('session', type=str)

    use_transition = request.args.get(PARAMETER_USE_TRANSITION, type=str, default=str(DEFAULT_USE_TRANSITION))
    no_samples = request.args.get(PARAMETER_NO_SAMPLES, type=int, default=DEFAULT_MAX_NO_SAMPLES)
    max_no_ret_items = request.args.get(PARAMETER_NUM_RET_ITEMS, type=int, default=DEFAULT_MAX_NO_RET_ITEMS)

    if use_transition == "True":
        use_transition = True
    else:
        use_transition = False

    if keyphrase == configuration.KEYPHRASE:
        filters = get_filters_per_session(process, session)
        parameters = {}
        parameters["filters"] = filters
        parameters[PARAMETER_USE_TRANSITION] = use_transition
        parameters[PARAMETER_NO_SAMPLES] = no_samples
        parameters[PARAMETER_NUM_RET_ITEMS] = max_no_ret_items

        returned_dict = parquet_handler.get_cases(SlaveVariableContainer.conf, process, SlaveVariableContainer.managed_logs[process], parameters=parameters)

        return jsonify(returned_dict)
    return jsonify({"cases_list": [], "events": 0, "cases": 0})


@SlaveSocketListener.app.route("/doCaching", methods=["GET"])
def do_caching():
    keyphrase = request.args.get('keyphrase', type=str)
    process = request.args.get('process', type=str)

    no_samples = request.args.get(PARAMETER_NO_SAMPLES, type=int, default=DEFAULT_MAX_NO_SAMPLES)

    if keyphrase == configuration.KEYPHRASE:
        parameters = {}
        parameters[PARAMETER_NO_SAMPLES] = no_samples

        parquet_handler.do_caching(SlaveVariableContainer.conf, process, SlaveVariableContainer.managed_logs[process], parameters=parameters)

    return jsonify({})


@SlaveSocketListener.app.route("/getEvents", methods=["GET"])
def get_events():
    process = request.args.get('process', type=str)
    keyphrase = request.args.get('keyphrase', type=str)
    session = request.args.get('session', type=str)
    case_id = request.args.get('case_id', type=str)
    use_transition = request.args.get(PARAMETER_USE_TRANSITION, type=str, default=str(DEFAULT_USE_TRANSITION))
    no_samples = request.args.get(PARAMETER_NO_SAMPLES, type=int, default=DEFAULT_MAX_NO_SAMPLES)

    if use_transition == "True":
        use_transition = True
    else:
        use_transition = False

    if keyphrase == configuration.KEYPHRASE:
        filters = get_filters_per_session(process, session)
        parameters = {}
        parameters["filters"] = filters
        parameters[PARAMETER_USE_TRANSITION] = use_transition
        parameters[PARAMETER_NO_SAMPLES] = no_samples
        parameters["case_id"] = case_id

        events = parquet_handler.get_events(SlaveVariableContainer.conf, process, SlaveVariableContainer.managed_logs[process], parameters=parameters)

        return jsonify({"events": events})
    return jsonify({"events": {}})


@SlaveSocketListener.app.route("/getEventsPerDotted", methods=["GET"])
def get_events_per_dotted():
    process = request.args.get('process', type=str)
    keyphrase = request.args.get('keyphrase', type=str)
    session = request.args.get('session', type=str)

    use_transition = request.args.get(PARAMETER_USE_TRANSITION, type=str, default=str(DEFAULT_USE_TRANSITION))
    no_samples = request.args.get(PARAMETER_NO_SAMPLES, type=int, default=DEFAULT_MAX_NO_SAMPLES)
    attribute1 = request.args.get("attribute1", type=str)
    attribute2 = request.args.get("attribute2", type=str)
    attribute3 = request.args.get("attribute3", type=str, default=None)
    max_no_ret_items = request.args.get(PARAMETER_NUM_RET_ITEMS, type=int, default=10000)

    if use_transition == "True":
        use_transition = True
    else:
        use_transition = False

    if keyphrase == configuration.KEYPHRASE:
        filters = get_filters_per_session(process, session)
        parameters = {}
        parameters["filters"] = filters
        parameters[PARAMETER_USE_TRANSITION] = use_transition
        parameters[PARAMETER_NO_SAMPLES] = no_samples
        parameters["attribute1"] = attribute1
        parameters["attribute2"] = attribute2
        parameters["attribute3"] = attribute3
        parameters["max_no_events"] = max_no_ret_items

        returned_dict = parquet_handler.get_events_per_dotted(SlaveVariableContainer.conf, process, SlaveVariableContainer.managed_logs[process], parameters=parameters)

        return jsonify(returned_dict)
    return jsonify({})


@SlaveSocketListener.app.route("/getEventsPerTime", methods=["GET"])
def get_events_per_time():
    process = request.args.get('process', type=str)
    keyphrase = request.args.get('keyphrase', type=str)
    session = request.args.get('session', type=str)

    use_transition = request.args.get(PARAMETER_USE_TRANSITION, type=str, default=str(DEFAULT_USE_TRANSITION))
    no_samples = request.args.get(PARAMETER_NO_SAMPLES, type=int, default=DEFAULT_MAX_NO_SAMPLES)
    max_no_ret_items = request.args.get(PARAMETER_NUM_RET_ITEMS, type=int, default=100000)

    if use_transition == "True":
        use_transition = True
    else:
        use_transition = False

    if keyphrase == configuration.KEYPHRASE:
        filters = get_filters_per_session(process, session)
        parameters = {}
        parameters["filters"] = filters
        parameters[PARAMETER_USE_TRANSITION] = use_transition
        parameters[PARAMETER_NO_SAMPLES] = no_samples
        parameters[PARAMETER_NUM_RET_ITEMS] = max_no_ret_items
        parameters["max_no_of_points_to_sample"] = max_no_ret_items

        returned_list = parquet_handler.get_events_per_time(SlaveVariableContainer.conf, process, SlaveVariableContainer.managed_logs[process], parameters=parameters)

        return jsonify({"points": returned_list})

    return jsonify({})


@SlaveSocketListener.app.route("/getCaseDuration", methods=["GET"])
def get_case_duration():
    process = request.args.get('process', type=str)
    keyphrase = request.args.get('keyphrase', type=str)
    session = request.args.get('session', type=str)

    use_transition = request.args.get(PARAMETER_USE_TRANSITION, type=str, default=str(DEFAULT_USE_TRANSITION))
    no_samples = request.args.get(PARAMETER_NO_SAMPLES, type=int, default=DEFAULT_MAX_NO_SAMPLES)
    max_no_ret_items = request.args.get(PARAMETER_NUM_RET_ITEMS, type=int, default=100000)

    if use_transition == "True":
        use_transition = True
    else:
        use_transition = False

    if keyphrase == configuration.KEYPHRASE:
        filters = get_filters_per_session(process, session)
        parameters = {}
        parameters["filters"] = filters
        parameters[PARAMETER_USE_TRANSITION] = use_transition
        parameters[PARAMETER_NO_SAMPLES] = no_samples
        parameters[PARAMETER_NUM_RET_ITEMS] = max_no_ret_items
        parameters["max_no_of_points_to_sample"] = max_no_ret_items

        returned_list = parquet_handler.get_case_duration(SlaveVariableContainer.conf, process, SlaveVariableContainer.managed_logs[process], parameters=parameters)

        return jsonify({"points": returned_list})

    return jsonify({})


@SlaveSocketListener.app.route("/getNumericAttributeValues", methods=["GET"])
def get_numeric_attribute_values():
    process = request.args.get('process', type=str)
    keyphrase = request.args.get('keyphrase', type=str)
    session = request.args.get('session', type=str)

    use_transition = request.args.get(PARAMETER_USE_TRANSITION, type=str, default=str(DEFAULT_USE_TRANSITION))
    no_samples = request.args.get(PARAMETER_NO_SAMPLES, type=int, default=DEFAULT_MAX_NO_SAMPLES)
    max_no_ret_items = request.args.get(PARAMETER_NUM_RET_ITEMS, type=int, default=100000)
    attribute_key = request.args.get("attribute_key", type=str)

    if use_transition == "True":
        use_transition = True
    else:
        use_transition = False

    if keyphrase == configuration.KEYPHRASE:
        filters = get_filters_per_session(process, session)
        parameters = {}
        parameters["filters"] = filters
        parameters[PARAMETER_USE_TRANSITION] = use_transition
        parameters[PARAMETER_NO_SAMPLES] = no_samples
        parameters[PARAMETER_NUM_RET_ITEMS] = max_no_ret_items
        parameters["max_no_of_points_to_sample"] = max_no_ret_items
        parameters["attribute_key"] = attribute_key

        returned_list = parquet_handler.get_numeric_attribute_values(SlaveVariableContainer.conf, process, SlaveVariableContainer.managed_logs[process], parameters=parameters)

        return jsonify({"points": returned_list})

    return jsonify({})


@SlaveSocketListener.app.route("/performAlignments", methods=["POST"])
def perform_alignments():
    from pm4pydistr.slave import slave

    process = request.args.get('process', type=str)
    keyphrase = request.args.get('keyphrase', type=str)
    session = request.args.get('session', type=str)
    use_transition = request.args.get(PARAMETER_USE_TRANSITION, type=str, default=str(DEFAULT_USE_TRANSITION))
    no_samples = request.args.get(PARAMETER_NO_SAMPLES, type=int, default=DEFAULT_MAX_NO_SAMPLES)

    try:
        content = json.loads(request.data)
    except:
        content = json.loads(request.data.decode('utf-8'))

    petri_string = content["petri_string"]
    var_list = content["var_list"]
    max_align_time = content["max_align_time"]
    max_align_time_trace = content["max_align_time_trace"]
    align_variant = content["align_variant"]

    if keyphrase == configuration.KEYPHRASE:
        parameters = {}
        parameters["max_align_time"] = max_align_time
        parameters["max_align_time_trace"] = max_align_time_trace
        parameters["align_variant"] = align_variant

        return jsonify({"alignments": slave.perform_alignments(petri_string, var_list, parameters=parameters)})

    return jsonify({})


@SlaveSocketListener.app.route("/performTbr", methods=["POST"])
def perform_tbr():
    from pm4pydistr.slave import slave

    process = request.args.get('process', type=str)
    keyphrase = request.args.get('keyphrase', type=str)
    session = request.args.get('session', type=str)
    use_transition = request.args.get(PARAMETER_USE_TRANSITION, type=str, default=str(DEFAULT_USE_TRANSITION))
    no_samples = request.args.get(PARAMETER_NO_SAMPLES, type=int, default=DEFAULT_MAX_NO_SAMPLES)

    try:
        content = json.loads(request.data)
    except:
        content = json.loads(request.data.decode('utf-8'))

    petri_string = content["petri_string"]
    var_list = content["var_list"]
    enable_parameters_precision = content["enable_parameters_precision"]
    consider_remaining_in_fitness = content["consider_remaining_in_fitness"]

    if keyphrase == configuration.KEYPHRASE:
        parameters = {"enable_parameters_precision": enable_parameters_precision, "consider_remaining_in_fitness": consider_remaining_in_fitness}

        return jsonify({"tbr": slave.perform_token_replay(petri_string, var_list, parameters=parameters)})

    return jsonify({})


@SlaveSocketListener.app.route("/doShutdown", methods=["GET"])
def do_shutdown():
    keyphrase = request.args.get('keyphrase', type=str)
    process = request.args.get('process', type=str)

    no_samples = request.args.get(PARAMETER_NO_SAMPLES, type=int, default=DEFAULT_MAX_NO_SAMPLES)

    if keyphrase == configuration.KEYPHRASE:
        # do shutdown
        os._exit(0)

    return jsonify({})


#Additional functionality
def clean_log_from_na(log):
    for trace in log:
        for event in trace:
            attr_keys = list(event.keys())
            for k in attr_keys:
                if str(event[k]).lower() == "nan" or str(event[k]).lower() == "nat":
                    del event[k]
    return log

@SlaveSocketListener.app.route("/doTraining", methods=["GET"])
def do_training():
    keyphrase = request.args.get('keyphrase', type=str)
    process = request.args.get('process', type=str)

    if keyphrase == configuration.KEYPHRASE:
        # Import the part of the training log assigned to the slave
        training_df = parquet_handler.load_parquet_from_path(SlaveVariableContainer.conf, None, None)
        training_log = clean_log_from_na(conversion_factory.apply(training_df))

        # Import the test log
        test_df = parquet_handler.load_parquet_from_path(configuration.TEST_LOG_PATH, None, None)
        test_log = clean_log_from_na(conversion_factory.apply(test_df))

        # Declare lists that store the total time of each case in the training and test logs
        training_time_vector = []
        test_time_vector = []

        # Create event log with only the first event of each case of the training log
        training_log_first_event = EventLog()
        for index, case in enumerate(training_log):

            new_case = Trace()
            new_case.attributes["concept:name"] = str(index)
            new_case.append(case[0])

            training_log_first_event.append(new_case)

            # Store total time of case
            training_time_vector.append([(case[-1]["time:timestamp"] - case[0]["time:timestamp"]).total_seconds()])

        # Create event log with only the first event of each case of the training log
        test_log_first_event = EventLog()
        for index, case in enumerate(test_log):
            new_case = Trace()
            new_case.attributes["concept:name"] = str(index)

            new_case.append(case[0])

            test_log_first_event.append(new_case)

            # Store total time of case
            test_time_vector.append((case[-1]["time:timestamp"] - case[0]["time:timestamp"]).total_seconds())

        # Train and persist the ensemble
        parameters = configuration.TRAINING_ATTRIBUTES[process]
        parameters["y_orig"] = training_time_vector

        model = prediction_factory.train(training_log_first_event, variant="elasticnet", parameters=parameters)
        with open(os.path.join(configuration.MODEL_PATH, SlaveVariableContainer.conf + '@@' + str(process)), "wb") as output:
            pickle.dump(model, output, pickle.HIGHEST_PROTOCOL)

        # Perform tests on prediction quality
        prediction_error = []
        for i in range(len(test_log_first_event)):
            prediction = prediction_factory.test(model, test_log_first_event[i])
            real_value = test_time_vector[i]
            error = prediction - real_value
            prediction_error.append(abs(error))
            print("Predicted time for case " + str(i) + ": " + str(prediction) + "; Real value: " + str(
                real_value) + "; Relative error: " + str(error))
        print("Mean error: " + str(statistics.mean(prediction_error)))

        print("Training of ensemble complete.")

    return jsonify({})


@SlaveSocketListener.app.route("/doPrediction", methods=["POST"])
def do_prediction():
    keyphrase = request.args.get('keyphrase', type=str)
    process = request.args.get('process', type=str)

    if keyphrase == configuration.KEYPHRASE:
        # Load the given event
        try:
            content = json.loads(request.data)
        except:
            content = json.loads(request.data.decode('utf-8'))

        # Create a trace with only the first event
        first_event = Event(content)
        trace = Trace()
        trace.append(first_event)

        with open(os.path.join(configuration.MODEL_PATH, SlaveVariableContainer.conf + '@@' + str(process)), "rb") as input:
            # Load the model that was trained on the given process
            model = pickle.load(input)

            # Perform prediction
            prediction = prediction_factory.test(model, trace)

    return jsonify({'prediction': prediction})

