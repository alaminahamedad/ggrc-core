# Copyright (C) 2016 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Contains CanFindSimilar mixin.

This defines a procedure of getting "similar" objects which have similar
relationships.
"""

from sqlalchemy import and_
from sqlalchemy import case
from sqlalchemy import or_
from sqlalchemy.orm import aliased
from sqlalchemy.sql import func

from ggrc import db
from ggrc.models.relationship import Relationship


class CanFindSimilar(object):
  """Defines a routine to get similar object with mappings to same objects."""

  # pylint: disable=too-few-public-methods

  # example of relatable_options:
  # relatable_options = {
  #     "relevant_types": {"Audit": {"weight": 5}, type: {"weight": w}},
  #     "threshold": 10,
  # }

  @classmethod
  def get_similar_objects(cls, id_, types="all", relevant_types=None,
                          threshold=None):
    """Get objects of types similar to cls instance by their mappings.

    Args:
      id_: the id of the object to which the search will be applied;
      types: a list of types of relevant objects (or "all" if you need to find
             objects of any type);
      relevant_types: use this parameter to override parameters from
                      cls.relatable_options["relevant_types"];
      threshold: use this parameter to override
                 cls.relatable_options["threshold"].

    Returns:
      [(similar_object_id, similar_object_type, weight)] - a list of similar
          objects with respective weights.
    """
    if not types or (not isinstance(types, list) and types != "all"):
      raise ValueError("Expected types = 'all' or a non-empty list of "
                       "requested types, got {!r} instead.".format(types))
    if not hasattr(cls, "relatable_options"):
      raise AttributeError("Expected 'relatable_options' defined for "
                           "'{c.__name__}' model.".format(c=cls))
    if relevant_types is None:
      relevant_types = cls.relatable_options["relevant_types"]
    if threshold is None:
      threshold = cls.relatable_options["threshold"]

    relevant_relationships = db.session.query(Relationship).filter(
        or_(and_(Relationship.source_type == cls.__name__,
                 Relationship.source_id == id_),
            and_(Relationship.destination_type == cls.__name__,
                 Relationship.destination_id == id_))).subquery()

    mid_id_case = (case([(and_(relevant_relationships.c.source_id == id_,
                               relevant_relationships.c.source_type ==
                               cls.__name__),
                          relevant_relationships.c.destination_id)],
                        else_=relevant_relationships.c.source_id)
                   .label("mid_id"))
    mid_type_case = (case([(and_(relevant_relationships.c.source_id == id_,
                                 relevant_relationships.c.source_type ==
                                 cls.__name__),
                            relevant_relationships.c.destination_type)],
                          else_=relevant_relationships.c.source_type)
                     .label("mid_type"))

    rel_end = aliased(Relationship, name="rel_end")

    joined = db.session.query(
        mid_type_case,
        rel_end.destination_id.label("end_id"),
        rel_end.destination_type.label("end_type"),
    ).join(
        rel_end,
        and_(mid_id_case == rel_end.source_id,
             mid_type_case == rel_end.source_type),
    ).union(db.session.query(
        mid_type_case,
        rel_end.source_id.label("end_id"),
        rel_end.source_type.label("end_type"),
    ).join(
        rel_end,
        and_(mid_id_case == rel_end.destination_id,
             mid_type_case == rel_end.destination_type),
    )).subquery()

    weight_case = case(
        [(joined.c.mid_type == type_, parameters["weight"])
         for type_, parameters in relevant_types.items()],
        else_=0).label("weight")

    result = db.session.query(
        joined.c.end_id,
        joined.c.end_type,
    ).filter(or_(
        joined.c.end_id != id_,
        joined.c.end_type != cls.__name__,
    ))

    if types is not None:
      if not types:
        return []
      else:
        result = result.filter(joined.c.end_type.in_(types))

    result = result.group_by(
        joined.c.end_type,
        joined.c.end_id,
    ).having(
        func.sum(weight_case) >= threshold,
    )

    return result.all()
