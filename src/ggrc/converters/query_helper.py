# Copyright (C) 2016 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""This module contains a class for handling request queries."""

# flake8: noqa

import datetime
import collections
from sqlalchemy import and_
from sqlalchemy import not_
from sqlalchemy import or_

from ggrc import db
from ggrc.rbac import permissions
from ggrc.models.custom_attribute_value import CustomAttributeValue
from ggrc.models.custom_attribute_definition import \
    CustomAttributeDefinition as CAD
from ggrc.models.reflection import AttributeInfo
from ggrc.models.relationship_helper import RelationshipHelper
from ggrc.converters import get_exportables


class BadQueryException(Exception):
  pass


# pylint: disable=too-few-public-methods

class QueryHelper(object):

  """Helper class for handling request queries

  Primary use for this class is to get list of object ids for each object type
  defined in the query. All objects must pass the query filters if they are
  defined.

  query object = [
    {
      object_name: search class name,
      permissions: either read or update, if none are given it defaults to read
      order_by: [
        Note: only the first order_by list item is processed
        {
          "name": the name of the field by which to do the sorting
          "desc": optional; if True, invert the sorting order
        }
      ]
      limit: [from, to] - limit the result list to a slice result[from, to]
      filters: {
        relevant_filters:
          these filters will return all ids of the "search class name" object
          that are mapped to objects defined in the dictionary inside the list.
          [ list of filters joined by OR expression
            [ list of filters joined by AND expression
              {
                "object_name": class of relevant object,
                "slugs": list of relevant object slugs,
                        optional and if exists will be converted into ids
                "ids": list of relevant object ids
              }
            ]
          ],
        object_filters: {
          TODO: allow filtering by title, description and other object fields
        }
      }
    }
  ]

  After the query is done (by `get_ids` method), the results are appended to
  each query object:

  query object with results = [
    {
      object_name: search class name,
      (all other object query fields)
      ids: [ list of filtered objects ids ]
    }
  ]

  The result fields may or may not be present in the resulting query depending
  on the attributes of `get` method.

  """

  def __init__(self, query, ca_disabled=False):
    importable = get_exportables()
    self.object_map = {o.__name__: o for o in importable.values()}
    self.query = self._clean_query(query)
    self.ca_disabled = ca_disabled
    self._set_attr_name_map()

  def _set_attr_name_map(self):
    """ build a map for attributes names and display names

    Dict containing all display_name to attr_name mappings
    for all objects used in the current query
    Example:
        { Program: {"Program URL": "url", "Code": "slug", ...} ...}
    """
    self.attr_name_map = {}
    for object_query in self.query:
      object_name = object_query["object_name"]
      object_class = self.object_map[object_name]
      aliases = AttributeInfo.gather_aliases(object_class)
      self.attr_name_map[object_class] = {}
      for key, value in aliases.items():
        filter_by = None
        if isinstance(value, dict):
          filter_name = value.get("filter_by", None)
          if filter_name is not None:
            filter_by = getattr(object_class, filter_name, None)
          value = value["display_name"]
        if value:
          self.attr_name_map[object_class][value.lower()] = (key.lower(),
                                                             filter_by)
      if not self.ca_disabled:
        custom_attrs = AttributeInfo.get_custom_attr_definitions(
            object_class)
      else:
        custom_attrs = {}

      for key, definition in custom_attrs.items():
        if not key.startswith("__custom__:") or \
           "display_name" not in definition:
          continue
        try:
          # Global custom attribute definition can only have a single id on
          # their name, so it is safe for that. Currently the filters do not
          # work with object level custom attributes.
          attr_id = definition["definition_ids"][0]
        except KeyError:
          continue
        filter_by = CustomAttributeValue.mk_filter_by_custom(object_class,
                                                             attr_id)
        name = definition["display_name"].lower()
        self.attr_name_map[object_class][name] = (name, filter_by)

  def _clean_query(self, query):
    """ sanitize the query object """
    for object_query in query:
      filters = object_query.get("filters", {}).get("expression")
      self._clean_filters(filters)
      self._macro_expand_object_query(object_query)
    return query

  def _clean_filters(self, expression):
    """Prepare the filter expression for building the query."""
    if not expression or not isinstance(expression, dict):
      return
    slugs = expression.get("slugs")
    if slugs:
      ids = expression.get("ids", [])
      ids.extend(self._slugs_to_ids(expression["object_name"], slugs))
      expression["ids"] = ids
    try:
      expression["ids"] = [int(id_) for id_ in expression.get("ids", [])]
    except ValueError as error:
      # catch missing relevant filter (undefined id)
      if expression.get("op", {}).get("name", "") == "relevant":
        raise BadQueryException("Invalid relevant filter for {}".format(
                                expression.get("object_name", "")))
      raise error
    self._clean_filters(expression.get("left"))
    self._clean_filters(expression.get("right"))

  def _expression_keys(self, exp):
    operator = exp.get("op", {}).get("name", None)
    if operator in ["AND", "OR"]:
      return self._expression_keys(exp["left"]).union(
          self._expression_keys(exp["right"]))
    left = exp.get("left", None)
    if left is not None and isinstance(left, collections.Hashable):
      return set([left])
    else:
      return set()

  def _macro_expand_object_query(self, object_query):
    def expand_task_dates(exp):
      if not isinstance(exp, dict) or "op" not in exp:
        return
      operator = exp["op"]["name"]
      if operator in ["AND", "OR"]:
        expand_task_dates(exp["left"])
        expand_task_dates(exp["right"])
      elif isinstance(exp["left"], (str, unicode)):
        key = exp["left"]
        if key in ["start", "end"]:
          parts = exp["right"].split("/")
          if len(parts) == 3:
            try:
              month, day, year = [int(part) for part in parts]
            except Exception:
              raise BadQueryException(
                  "Date must consist of numbers")
            exp["left"] = key + "_date"
            exp["right"] = datetime.date(year, month, day)
          elif len(parts) == 2:
            month, day = parts
            exp["op"] = {"name": u"AND"}
            exp["left"] = {
                "op": {"name": operator},
                "left": "relative_" + key + "_month",
                "right": month,
            }
            exp["right"] = {
                "op": {"name": operator},
                "left": "relative_" + key + "_day",
                "right": day,
            }
          elif len(parts) == 1:
            exp["left"] = "relative_" + key + "_day"
          else:
            raise BadQueryException("Field {} should be a date of one of the"
                                    " following forms: DD, MM/DD, MM/DD/YYYY"
                                    .format(key))

    if object_query["object_name"] == "TaskGroupTask":
      filters = object_query.get("filters")
      if filters is not None:
        exp = filters["expression"]
        keys = self._expression_keys(exp)
        if "start" in keys or "end" in keys:
          expand_task_dates(exp)

  def get_ids(self):
    """Get a list of filtered object IDs.

    self.query should contain a list of queries for different objects which
    will get evaluated and turned into a list of object IDs.

    Returns:
      list of dicts: same query as the input with all ids that match the filter
    """
    for object_query in self.query:
      objects = self._get_objects(object_query)
      objects = self._apply_order_by_and_limit(
          objects,
          order_by=object_query.get("order_by"),
          limit=object_query.get("limit"),
      )
      object_query["ids"] = [o.id for o in objects]
    return self.query

  def _get_objects(self, object_query):
    """Get a set of objects described in the filters."""
    object_name = object_query["object_name"]
    expression = object_query.get("filters", {}).get("expression")

    if expression is None:
      return set()
    object_class = self.object_map[object_name]

    query = object_class.eager_query()
    filter_expression = self._build_expression(
        expression,
        object_class,
        object_query.get('fields', []),
    )
    if filter_expression is not None:
      query = query.filter(filter_expression)
    requested_permissions = object_query.get("permissions", "read")
    if requested_permissions == "update":
      objs = [o for o in query if permissions.is_allowed_update_for(o)]
    else:
      objs = [o for o in query if permissions.is_allowed_read_for(o)]

    return objs

  @staticmethod
  def _apply_order_by_and_limit(objects, order_by=None, limit=None):
    """Order objects and apply limits for pagination.

    Args:
      objects: a list of objects to sort and limit;
      order_by: a list of dicts with keys "name" (the name of the field by which
                to sort) and "desc" (optional; do reverse sort if True);
      limit: a tuple of indexes in format (from, to); objects is sliced to
             objects[from, to]

    Returns:
      a sorted and sliced list of objects
    """
    if order_by:
      try:
        # Note: currently we sort only by the first column from the list
        order_by = order_by[0]
        order_field = order_by["name"]
        order_desc = order_by.get("desc", False)
        objects = sorted(
            objects,
            key=lambda obj: getattr(obj, order_field),
            reverse=order_desc,
        )
      except:
        raise BadQueryException("Bad query: Invalid 'order_by' parameter")

    if limit:
      try:
        from_, to_ = limit
        objects = objects[from_: to_]
      except:
        raise BadQueryException("Bad query: Invalid 'limit' parameter.")

    return objects

  def _build_expression(self, exp, object_class, fields):
    """Make an SQLAlchemy filtering expression from exp expression tree."""
    if "op" not in exp:
      return None

    def autocast(o_key, value):
      """Try to guess the type of `value` and parse it from the string."""
      if not isinstance(o_key, (str, unicode)):
        return value
      key, _ = self.attr_name_map[object_class].get(o_key, (o_key, None))
      # handle dates
      if ("date" in key and "relative" not in key) or \
         key in ["end_date", "start_date"]:
        if isinstance(value, datetime.date):
          return value
        try:
          month, day, year = [int(part) for part in value.split("/")]
          return datetime.date(year, month, day)
        except Exception:
          raise BadQueryException("Field \"{}\" expects a MM/DD/YYYY date"
                                  .format(o_key))
      # fallback
      return value

    def relevant():
      """Filter by relevant object."""
      query = (self.query[exp["ids"][0]]
               if exp["object_name"] == "__previous__" else exp)
      return object_class.id.in_(
          RelationshipHelper.get_ids_related_to(
              object_class.__name__,
              query["object_name"],
              query["ids"],
          )
      )

    def similar():
      """Filter by relationships similarity."""
      similar_class = self.object_map[exp["object_name"]]
      if not hasattr(similar_class, "get_similar_objects"):
        return BadQueryException("{} does not define weights to count "
                                 "relationships similarity"
                                 .format(similar_class.__name__))
      return object_class.id.in_(
          [r[0] for r in similar_class
           .get_similar_objects(id_=exp["id"], types=[object_class.__name__])]
      )

    def unknown():
      raise BadQueryException("Unknown operator \"{}\""
                              .format(exp["op"]["name"]))

    def with_key(key, p):
      key = key.lower()
      key, filter_by = self.attr_name_map[
          object_class].get(key, (key, None))
      if hasattr(filter_by, "__call__"):
        return filter_by(p)
      else:
        attr = getattr(object_class, key, None)
        if attr is None:
          raise BadQueryException("Bad query: object '{}' does "
                                  "not have attribute '{}'."
                                  .format(object_class.__name__, key))
        return p(attr)

    with_left = lambda p: with_key(exp["left"], p)

    lift_bin = lambda f: f(self._build_expression(exp["left"], object_class,
                                                  fields),
                           self._build_expression(exp["right"], object_class,
                                                  fields))

    def text_search():
      """Filter by text search.

      The search is done only in fields listed in external `fields` var.
      """
      existing_fields = self.attr_name_map[object_class]
      text = "%{}%".format(exp["text"])
      p = lambda f: f.ilike(text)
      return or_(*(
          with_key(field, p)
          for field in fields
          if field in existing_fields
      ))

    rhs = lambda: autocast(exp["left"], exp["right"])

    ops = {
        "AND": lambda: lift_bin(and_),
        "OR": lambda: lift_bin(or_),
        "=": lambda: with_left(lambda l: l == rhs()),
        "!=": lambda: not_(with_left(
                           lambda l: l == rhs())),
        "~": lambda: with_left(lambda l:
                               l.ilike("%{}%".format(rhs()))),
        "!~": lambda: not_(with_left(
                           lambda l: l.ilike("%{}%".format(rhs())))),
        "<": lambda: with_left(lambda l: l < rhs()),
        ">": lambda: with_left(lambda l: l > rhs()),
        "relevant": relevant,
        "text_search": text_search,
        "similar": similar,
    }

    return ops.get(exp["op"]["name"], unknown)()

  def _slugs_to_ids(self, object_name, slugs):
    object_class = self.object_map.get(object_name)
    if not object_class:
      return []
    ids = [c.id for c in object_class.query.filter(
        object_class.slug.in_(slugs)).all()]
    return ids
