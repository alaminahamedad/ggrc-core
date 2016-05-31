# Copyright (C) 2013 Google Inc., authors, and contributors <see AUTHORS file>
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
# Created By: dan@reciprocitylabs.com
# Maintained By: dan@reciprocitylabs.com

from contextlib import contextmanager

from ggrc.models.all_models import register_model
from ggrc.models.all_models import unregister_model


@contextmanager
def model_registered(model):
  register_model(model)
  yield
  unregister_model(model)
