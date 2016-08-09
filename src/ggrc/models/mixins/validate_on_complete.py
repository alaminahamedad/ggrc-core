# Copyright (C) 2016 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Contains ValidateOnComplete mixin.

This defines a procedure of an object's validation when its status moves from
one of NOT_DONE_STATES to DONE_STATES.
"""

from collections import defaultdict
from collections import namedtuple

from sqlalchemy import case
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy import orm
from sqlalchemy.orm import validates

from ggrc import db
from ggrc.models.comment import Comment
from ggrc.models.computed_property import computed_property
from ggrc.models.custom_attribute_definition import CustomAttributeDefinition
from ggrc.models.exceptions import ValidationError


class RequirementError(namedtuple("RequirementError", ["cad", "cav",
                                                       "requirement"])):
  def __str__(self):
    if self.requirement == "comment":
      return ("Comment required by '{cad.title}' on value "
              "'{cav.attribute_value}'".format(cad=self.cad, cav=self.cav))
    elif self.requirement == "evidence":
      return ("Evidence required by '{cad.title}' on value "
              "'{cav.attribute_value}'".format(cad=self.cad, cav=self.cav))
    elif self.requirement == "value":
      return ("Value for definition '{cad.title}' is missing"
              .format(cad=self.cad))
    else:
      raise ValueError("Invalid 'requirement': {}".format(self.requirement))


class ValidateOnComplete(object):
  """Defines the validation routine before marking an object as complete.

  Requires Stateful and Statusable to be mixed in as well."""

  # pylint: disable=too-few-public-methods

  @computed_property
  def preconditions_failed(self):
    """Find failed preconditions that block self from moving to "Complete".

    Returns:
      {
         cad.id: [str], - mapping from id of a CA which blocks completion
                          to reasons why this CA blocks completion
      }
      Possible errors are "value" (missing mandatory CA value), "comment"
        (missing mandatory comment), "evidence" (missing mandatory evidence).
    """
    def get_failed_preconditions(errors):
      """Transform error list to cad.id -> relevant error dict."""
      preconditions_failed = defaultdict(list)
      for error in errors:
        preconditions_failed[error.cad.id].append(error.requirement)
      return preconditions_failed

    errors = self._get_unsatisfied_requirements()
    return get_failed_preconditions(errors)

  @declared_attr
  def _related_comments(self):
    """Comments related to self via Relationship table."""
    from ggrc.models.relationship import Relationship
    comment_id = case(
        [(Relationship.destination_type == "Comment",
          Relationship.destination_id)],
        else_=Relationship.source_id,
    )
    commentable_id = case(
        [(Relationship.destination_type == "Comment",
          Relationship.source_id)],
        else_=Relationship.destination_id,
    )

    return db.relationship(
        Comment,
        primaryjoin=lambda: self.id == commentable_id,
        secondary=Relationship.__table__,
        secondaryjoin=lambda: Comment.id == comment_id,
        viewonly=True,
    )

  @classmethod
  def eager_query(cls):
    """Special query to fetch all required fields."""
    query = super(ValidateOnComplete, cls).eager_query()
    return query.options(
        orm.subqueryload("_related_comments")
           .joinedload("revision"),
    )

  def _get_custom_attributes_comments(self):
    # pylint: disable=not-an-iterable; self._related_comments is a list-like
    return [comment for comment in self._related_comments
            if comment.revision_id]

  @staticmethod
  def _multi_choice_options_to_flags(cad):
    """Parse mandatory comment and evidence flags from dropdown CA definition.

    Args:
      cad - a CA definition object

    Returns:
      {option_value: Flags} - a dict from dropdown options values to Flags
                              objects where Flags.comment_required and
                              Flags.evidence_required correspond to the values
                              from multi_choice_mandatory bitmasks
    """
    flags = namedtuple("Flags", ["comment_required", "evidence_required"])

    def make_flags(multi_choice_mandatory):
      flags_mask = int(multi_choice_mandatory)
      return flags(comment_required=flags_mask & (CustomAttributeDefinition
                                                  .MultiChoiceMandatoryFlags
                                                  .COMMENT_REQUIRED),
                   evidence_required=flags_mask & (CustomAttributeDefinition
                                                   .MultiChoiceMandatoryFlags
                                                   .EVIDENCE_REQUIRED))

    if not cad.multi_choice_options or not cad.multi_choice_mandatory:
      return {}
    else:
      return dict(zip(
          cad.multi_choice_options.split(","),
          (make_flags(mask)
           for mask in cad.multi_choice_mandatory.split(",")),
      ))

  @validates("status")
  def validate_status(self, key, value):
    """Check that mandatory fields and CAs are filled in.

    Also checks that comments and evidences required by dropdown CAs present.
    """
    # support for multiple validators for status
    if hasattr(super(ValidateOnComplete, self), "validate_status"):
      value = super(ValidateOnComplete, self).validate_status(key, value)

    if self.status in self.NOT_DONE_STATES and value in self.DONE_STATES:
      errors = self._get_unsatisfied_requirements()

      if errors:
        raise ValidationError(". ".join(str(error) for error in errors))

    return value

  def _get_unsatisfied_requirements(self):
    """Get any missing mandatory CAs, comments and evidences."""
    # pylint: disable=attribute-defined-outside-init ; it's a mixin

    errors = []
    comments = self._get_custom_attributes_comments()
    self._definition_value_map = {int(cav.custom_attribute_id): cav
                                  for cav in self.custom_attribute_values}
    self._ca_comment_map = {
        int(comment.revision
            .content["custom_attribute_id"]): comment
        for comment in comments
    }
    for cad in self.custom_attribute_definitions:
      # find the value for this definition
      cav = self._definition_value_map.get(cad.id)

      # check mandatory values
      errors += self._check_mandatory_value(cad, cav)

      # check relevant comments and attachments
      if cad.attribute_type == CustomAttributeDefinition.ValidTypes.DROPDOWN:
        errors += self._check_dropdown_requirements(cad, cav)

    return errors

  @staticmethod
  def _check_mandatory_value(cad, cav):
    if cad.mandatory and (not cav or not cav.attribute_value):
      return [RequirementError(cad=cad, cav=cav, requirement="value")]
    else:
      return []

  def _check_dropdown_requirements(self, cad, cav):
    """Check mandatory comment and evidence for the CA value."""
    errors = []
    options_to_flags = self._multi_choice_options_to_flags(cad)
    if cav:
      flags = options_to_flags.get(cav.attribute_value)
      if flags:
        if flags.comment_required:
          # check the presence of a comment mapped to the CA
          errors += self._check_mandatory_comment(cad, cav)
        if flags.evidence_required:
          # check the presence of an evidence
          errors += self._check_mandatory_evidence(cad, cav)
    return errors

  def _check_mandatory_comment(self, cad, cav):
    """Check mandatory comment for the CA value."""
    if not self._ca_comment_map.get(cad.id):
      return [RequirementError(cad=cad, cav=cav, requirement="comment")]
    else:
      return []

  def _check_mandatory_evidence(self, cad, cav):
    # pylint: disable=no-self-use
    # pylint: disable=unused-argument
    # not implemented yet
    return []
