#
#  Copyright 2019 The FATE Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

import copy

from arch.api import session
from arch.api.utils import log_utils
from federatedml.util import consts
from federatedml.model_base import ModelBase
from federatedml.param.column_expand_param import ColumnExpandParam
from federatedml.protobuf.generated import column_expand_meta_pb2, column_expand_param_pb2

DELIMITER = ", "
LOGGER = log_utils.getLogger()


class FeatureGenerator(object):
    def __init__(self, method, append_header, fill_value):
        self.method = method
        self.append_header = append_header
        self.fill_value = fill_value
        self.append_value = self._get_append_value()
        self.generator = self._get_generator()

    def _get_append_value(self):
        if len(self.fill_value) == 0:
            return
        if len(self.fill_value) == 1:
            fill_value = str(self.fill_value[0])
            new_features = [fill_value] * len(self.append_header)
            append_value = DELIMITER.join(new_features)
        else:
            append_value = DELIMITER.join([str(v) for v in self.fill_value])
        return append_value

    def _get_generator(self):
        while True:
            yield self.append_value

    def generate(self):
        return next(self.generator)


class ColumnExpand(ModelBase):
    def __init__(self):
        super(ColumnExpand, self).__init__()
        self.model_param = ColumnExpandParam()
        self.need_run = None
        self.append_header = None
        self.method = None
        self.fill_value = None

        self.summary_obj = None
        self.new_feature_generator = None

        self.model_param_name = 'ColumnExpandParam'
        self.model_meta_name = 'ColumnExpandMeta'


    def _init_model(self, params):
        self.model_param = params
        self.append_header = params.append_header
        self.method = params.method
        self.fill_value = params.fill_value
        self.new_feature_generator = FeatureGenerator(params.method,
                                                      params.append_header,
                                                      params.fill_value)

    @staticmethod
    def _append_feature(entry, append_value):
        new_entry = entry + DELIMITER + append_value
        return new_entry

    def _append_column_deprecated(self, data):
        # used for FATE v1.4.x
        append_value = self.new_feature_generator.generate()
        new_data = data.mapValues(lambda v: ColumnExpand._append_feature(v, append_value))

        new_metas = data.get_metas()
        header = data.get_meta("header")
        new_header = header + DELIMITER + DELIMITER.join(self.append_header)
        new_metas["header"] = new_header
        new_metas["namespace"] = new_data.get_namespace()
        session.save_data_table_meta(new_metas, new_data.get_name(),
                                     new_data.get_namespace())

        return new_data, new_header

    def _append_column(self, data):
        # uses for FATE v.1.5.x
        new_feature_generator = self.new_feature_generator
        new_data = data.mapValues(lambda v: ColumnExpand._append_feature(v, new_feature_generator))

        new_schema = copy.deepcopy(data.schema)
        header = data.get_meta("header")
        new_header = header + DELIMITER + DELIMITER.join(self.append_header)
        new_schema["header"] = new_header
        new_data.schema = new_schema

        return new_data, new_header

    def _get_meta(self):
        meta = column_expand_meta_pb2.ColumnExpandMeta(
            append_header = self.append_header,
            method = self.method,
            fill_value = [str(v) for v in self.fill_value]
        )
        return meta

    def _get_param(self):
        param = column_expand_param_pb2.ColumnExpandParam(
            header = self.header
        )
        return param

    def export_model(self):
        meta_obj = self._get_meta()
        param_obj = self._get_param()
        result = {
            self.model_meta_name: meta_obj,
            self.model_param_name: param_obj
        }
        self.model_output = result
        return result

    def load_model(self, model_dict):
        meta_obj = list(model_dict.get('model').values())[0].get(self.model_meta_name)
        self.new_feature_generator = FeatureGenerator(meta_obj.method,
                                                      meta_obj.append_header,
                                                      meta_obj.fill_value)

        return

    def fit(self, data):
        # return original value if no fill value provided
        if self.method == consts.MANUAL and len(self.fill_value) == 0:
            return data
        new_data, self.header = self._append_column_deprecated(data)
        return new_data

    def predict(self, data):
        if self.method == consts.MANUAL and len(self.fill_value) == 0:
            return data
        new_data, _ = self._append_column_deprecated(data)
        return new_data