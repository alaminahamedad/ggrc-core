# Copyright (C) 2016 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""This module contains logic to handle '/query' endpoint."""

from datetime import datetime
import time
from wsgiref.handlers import format_date_time

from flask import request
from flask import current_app
from werkzeug.exceptions import BadRequest

from ggrc.services.query_helper import QueryAPIQueryHelper
from ggrc.login import login_required
from ggrc.models.inflector import get_model
from ggrc.services.common import etag
from ggrc.utils import as_json


def build_collection_representation(model, **kwargs):
  """Enclose `kwargs` collection description into a type-describing block."""
  # pylint: disable=protected-access
  collection = {
      model.__name__: kwargs,
      "selfLink": None,  # not implemented yet
  }
  return collection


def get_last_modified(model, objects):
  """Get last object update time for Last-Modified header."""
  if hasattr(model, 'updated_at') and objects:
    last_modified = max(obj.updated_at for obj in objects)
  else:
    last_modified = None
  return last_modified


def json_success_response(response_object, last_modified=None, status=200):
  """Build a 200-response with metadata headers."""
  if last_modified is None:
    last_modified = datetime.now()
  headers = [
      ('Last-Modified', http_timestamp(last_modified)),
      ('Etag', etag(response_object)),
      ('Content-Type', 'application/json'),
  ]
  return current_app.make_response(
      (as_json(response_object), status, headers),
  )


def http_timestamp(timestamp):
  return format_date_time(time.mktime(timestamp.utctimetuple()))


def get_objects_by_query():
  """Return objects corresponding to a POST'ed query list."""
  query = request.json

  query_helper = QueryAPIQueryHelper(query)
  results = query_helper.get_results()

  last_modified = None
  collections = []
  collection_fields = ["ids", "values", "count", "total"]

  for result in results:
    if last_modified is None:
      last_modified = result["last_modified"]
    elif result["last_modified"] is not None:
      last_modified = max(last_modified, result["last_modified"])

    model = get_model(result["object_name"])

    collection = build_collection_representation(
        model,
        **{
            field: result[field] for field in collection_fields
            if field in result
        }
    )
    collections.append(collection)

  if last_modified is None:
    last_modified = datetime.now()

  return json_success_response(collections, last_modified)


def init_query_view(app):
  # pylint: disable=unused-variable
  @app.route('/query', methods=['POST'])
  @login_required
  def query_objects():
    """Advanced object collection queries view."""
    try:
      return get_objects_by_query()
    except NotImplementedError as exc:
      raise BadRequest(exc.message)
